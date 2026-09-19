"""
Risk engine — rules_v1. Transparent, explainable, every point attributable to a factor.
Rating drives the ongoing-due-diligence cadence (AUSTRAC AML/CTF Rules Part 15 style):
High → 6 months, Medium → 12, Low → 24.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.models.crm import Client

HIGH_RISK_TAGS = ("cash", "crypto", "gaming", "gambling", "remittance", "precious", "bullion", "casino", "money service")
HIGH_RISK_COUNTRIES = {"IR", "KP", "MM", "SY", "YE", "AF", "RU", "BY"}  # illustrative FATF/DFAT-style list; practice may extend


@dataclass
class Factor:
    factor: str
    points: int
    note: str


@dataclass
class RiskOutcome:
    rating: str
    score: int
    factors: list[Factor]
    review_months: int

    @property
    def review_delta(self) -> timedelta:
        return timedelta(days=30 * self.review_months)

    def factors_json(self) -> list[dict]:
        return [{"factor": f.factor, "points": f.points, "note": f.note} for f in self.factors]


def assess(client: Client, *, contacts_total: int, contacts_verified: int, screenings: list, has_ownership_graph: bool) -> RiskOutcome:
    f: list[Factor] = []
    base = {"Individual": 10, "Company": 20, "Partnership": 20, "SMSF": 25, "Trust": 30, "Other": 20}.get(client.client_type, 20)
    f.append(Factor("entity_type", base, f"{client.client_type} baseline"))

    if client.country and client.country.upper() != "AU":
        pts = 30 if client.country.upper() in HIGH_RISK_COUNTRIES else 10
        f.append(Factor("jurisdiction", pts, f"Registered in {client.country.upper()}"))

    tags = " ".join(str(t).lower() for t in (client.tags or []))
    if any(k in tags for k in HIGH_RISK_TAGS):
        f.append(Factor("industry", 15, "Higher-risk industry tag"))

    confirmed = [s for s in screenings if s.status == "confirmed_match" or s.review_decision == "true_match"]
    pending = [s for s in screenings if s.status == "potential_match" and not s.review_decision]
    if confirmed:
        f.append(Factor("screening_confirmed", 40, f"{len(confirmed)} confirmed PEP/sanctions match{'es' if len(confirmed) != 1 else ''}"))
    elif pending:
        f.append(Factor("screening_pending", 15, f"{len(pending)} potential match{'es' if len(pending) != 1 else ''} awaiting review"))
    elif not screenings:
        f.append(Factor("screening_missing", 10, "No screening on record"))

    if contacts_total and contacts_verified < contacts_total:
        f.append(Factor("identity_gaps", 10, f"{contacts_total - contacts_verified} of {contacts_total} people not identity-verified"))
    if client.client_type in ("Company", "Trust", "SMSF", "Partnership") and not has_ownership_graph:
        f.append(Factor("ownership_unknown", 10, "Beneficial ownership not recorded"))

    score = sum(x.points for x in f)
    rating = "High" if score >= 60 else "Medium" if score >= 30 else "Low"
    months = {"High": 6, "Medium": 12, "Low": 24}[rating]
    return RiskOutcome(rating=rating, score=score, factors=f, review_months=months)
