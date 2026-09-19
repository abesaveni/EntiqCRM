"""
Verify providers — the EntiqStart pattern: every capability has a live HTTP driver and a
simulation driver. `simulated=True` propagates to the row, the API response and the client
record so a synthetic pass can never be mistaken for a real one. A simulated check does
NOT satisfy AML/CTF obligations, and the UI says so.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings

log = logging.getLogger("entiq.verify.providers")


@dataclass
class IdentityStart:
    provider: str
    reference: str
    url: str | None
    status: str                      # pending | in_progress | verified | failed
    simulated: bool
    result: dict[str, Any] = field(default_factory=dict)


@dataclass
class IdentityResult:
    status: str
    result: dict[str, Any]
    failure_reason: str | None = None


@dataclass
class ScreeningResult:
    provider: str
    simulated: bool
    status: str                      # clear | potential_match | error
    matches: list[dict[str, Any]]
    error: str | None = None


# ------------------------------------------------------------------ identity: Didit
class DiditIdentity:
    """
    Didit v2 sessions. Create a session for a workflow → the person completes it at `url`;
    we read the decision back (poll or webhook). Configured by DIDIT_API_KEY / DIDIT_BASE_URL /
    DIDIT_WORKFLOW_INDIVIDUAL / DIDIT_WORKFLOW_KYB.
    """
    name = "didit"

    def __init__(self):
        self.base = settings.DIDIT_BASE_URL.rstrip("/")
        self.headers = {"x-api-key": settings.DIDIT_API_KEY, "Content-Type": "application/json", "Accept": "application/json"}

    def start(self, *, subject_type: str, subject_name: str, vendor_ref: str, callback_url: str | None) -> IdentityStart:
        workflow = settings.DIDIT_WORKFLOW_KYB if subject_type == "entity" else settings.DIDIT_WORKFLOW_INDIVIDUAL
        payload: dict[str, Any] = {"workflow_id": workflow, "vendor_data": vendor_ref}
        if callback_url:
            payload["callback"] = callback_url
        with httpx.Client(timeout=30) as c:
            r = c.post(f"{self.base}/v2/session/", headers=self.headers, json=payload)
            r.raise_for_status()
            d = r.json()
        return IdentityStart(provider=self.name, reference=str(d.get("session_id") or d.get("id")), url=d.get("url") or d.get("session_url"),
                             status="in_progress", simulated=False, result={"raw_status": d.get("status")})

    def fetch(self, reference: str) -> IdentityResult:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{self.base}/v2/session/{reference}/decision/", headers=self.headers)
            if r.status_code == 404:
                return IdentityResult(status="in_progress", result={})
            r.raise_for_status()
            d = r.json()
        raw = str(d.get("status") or d.get("decision", {}).get("status") or "").lower()
        status = {"approved": "verified", "verified": "verified", "declined": "failed", "rejected": "failed", "expired": "expired", "abandoned": "expired"}.get(raw, "in_progress")
        kyc = d.get("kyc") or d.get("id_verification") or {}
        result = {
            "raw_status": raw,
            "document_type": kyc.get("document_type"),
            "full_name": kyc.get("full_name") or kyc.get("name"),
            "date_of_birth": kyc.get("date_of_birth"),
            "document_number": (kyc.get("document_number") or "")[-4:].rjust(4, "•") if kyc.get("document_number") else None,
            "liveness": (d.get("liveness") or {}).get("status"),
            "face_match": (d.get("face_match") or {}).get("status"),
            "address": (d.get("poa") or {}).get("address"),
            "aml": d.get("aml"),
        }
        reason = None
        if status == "failed":
            reason = "; ".join(str(x) for x in (d.get("decline_reasons") or d.get("reasons") or [])) or "declined by provider"
        return IdentityResult(status=status, result=result, failure_reason=reason)


# ------------------------------------------------------------------ identity: simulation
class SimulatedIdentity:
    """Completes instantly. A subject whose name contains 'fail' is declined; everything else passes. Never counts as evidence."""
    name = "simulation"

    def start(self, *, subject_type: str, subject_name: str, vendor_ref: str, callback_url: str | None) -> IdentityStart:
        ref = "sim_" + hashlib.sha256(f"{vendor_ref}".encode()).hexdigest()[:20]
        failed = "fail" in subject_name.lower()
        result = {"raw_status": "declined" if failed else "approved", "document_type": "Driver Licence" if subject_type == "individual" else "ASIC extract",
                  "full_name": subject_name, "liveness": None if subject_type == "entity" else ("failed" if failed else "passed"), "note": "SIMULATED — not evidence of identity"}
        return IdentityStart(provider=self.name, reference=ref, url=None, status="failed" if failed else "verified", simulated=True, result=result)

    def fetch(self, reference: str) -> IdentityResult:
        return IdentityResult(status="verified", result={"note": "SIMULATED"})


# ------------------------------------------------------------------ screening: OpenSanctions
class OpenSanctionsScreening:
    """POST /match/{dataset} — PEP, sanctions and adverse-topic entities with scores. Live when OPENSANCTIONS_API_KEY is set."""
    name = "opensanctions"

    def screen(self, *, subject_type: str, name: str, dob: str | None = None, country: str | None = None) -> ScreeningResult:
        schema = "Company" if subject_type == "entity" else "Person"
        props: dict[str, list[str]] = {"name": [name]}
        if dob:
            props["birthDate"] = [dob]
        if country:
            props["country" if schema == "Company" else "nationality"] = [country.lower()]
        body = {"queries": {"q1": {"schema": schema, "properties": props}}}
        url = f"{settings.OPENSANCTIONS_BASE_URL.rstrip('/')}/match/{settings.OPENSANCTIONS_DATASET}"
        try:
            with httpx.Client(timeout=float(settings.OPENSANCTIONS_TIMEOUT)) as c:
                r = c.post(url, headers={"Authorization": f"ApiKey {settings.OPENSANCTIONS_API_KEY}", "Accept": "application/json"}, json=body, params={"threshold": settings.OPENSANCTIONS_THRESHOLD})
                r.raise_for_status()
                results = r.json().get("responses", {}).get("q1", {}).get("results", [])
        except (httpx.HTTPError, ValueError) as e:
            return ScreeningResult(provider=self.name, simulated=False, status="error", matches=[], error=f"{type(e).__name__}: {e}"[:300])
        matches = []
        for m in results:
            score = float(m.get("score") or 0)
            if score < float(settings.OPENSANCTIONS_THRESHOLD):
                continue
            props_ = m.get("properties") or {}
            matches.append({"id": m.get("id"), "name": m.get("caption"), "score": round(score * 100), "schema": m.get("schema"),
                            "datasets": (m.get("datasets") or [])[:6], "topics": props_.get("topics") or [], "countries": props_.get("country") or props_.get("nationality") or []})
        return ScreeningResult(provider=self.name, simulated=False, status="potential_match" if matches else "clear", matches=matches)


# ------------------------------------------------------------------ screening: simulation
class SimulatedScreening:
    """Deterministic: a name containing 'sanction' or 'pep' yields one synthetic potential match. Never counts as evidence."""
    name = "simulation"

    def screen(self, *, subject_type: str, name: str, dob: str | None = None, country: str | None = None) -> ScreeningResult:
        hit = any(k in name.lower() for k in ("sanction", "pep", "politically"))
        matches = [{"id": "sim-" + hashlib.sha256(name.encode()).hexdigest()[:10], "name": name.upper(), "score": 88, "schema": "Person" if subject_type != "entity" else "Company",
                    "datasets": ["simulation"], "topics": ["role.pep"] if "pep" in name.lower() or "politically" in name.lower() else ["sanction"], "countries": []}] if hit else []
        return ScreeningResult(provider=self.name, simulated=True, status="potential_match" if hit else "clear", matches=matches)


# ------------------------------------------------------------------ resolution
def identity_provider():
    if settings.VERIFY_PROVIDER_MODE == "simulate":
        return SimulatedIdentity()
    if settings.DIDIT_API_KEY and settings.DIDIT_BASE_URL and (settings.DIDIT_WORKFLOW_INDIVIDUAL or settings.DIDIT_WORKFLOW_KYB):
        return DiditIdentity()
    return SimulatedIdentity()


def screening_provider():
    if settings.VERIFY_PROVIDER_MODE == "simulate":
        return SimulatedScreening()
    if settings.OPENSANCTIONS_API_KEY:
        return OpenSanctionsScreening()
    return SimulatedScreening()


def provider_health() -> dict[str, Any]:
    return {
        "identity": {"provider": identity_provider().name, "live": identity_provider().name != "simulation"},
        "screening": {"provider": screening_provider().name, "live": screening_provider().name != "simulation"},
    }
