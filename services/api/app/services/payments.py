"""
The payment gateway for EnTIQ's own subscription billing, in the same shape as the Verify and Ledger
providers: a live Stripe driver used when keys exist, a simulation driver otherwise, and a result that
says plainly which one ran.

No Stripe keys exist in this estate yet. With BILLING_MODE=simulate (or no key) the simulation driver
records the charge without moving money and the billing ledger says so. The moment STRIPE_SECRET_KEY
is set and BILLING_MODE=stripe, the same call goes to Stripe with no other change: the lifecycle job,
the ledger, the emails and the dunning states are already written for it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings

STRIPE_API = "https://api.stripe.com/v1"


@dataclass
class ChargeResult:
    ok: bool
    simulated: bool
    provider: str
    reference: str | None = None            # PaymentIntent id
    status: str | None = None               # succeeded · requires_action · failed
    failure_code: str | None = None
    failure_message: str | None = None
    detail: dict[str, Any] | None = None

    @property
    def needs_action(self) -> bool:
        return self.status in ("requires_action", "requires_payment_method", "requires_confirmation")


class SimulatedGateway:
    """Records the intent to charge. Money never moves; every result is flagged `simulated`."""
    name = "simulation"

    def ensure_customer(self, *, tenant_name: str, email: str, existing_id: str | None) -> str | None:
        return existing_id

    def charge(self, *, amount_cents: int, currency: str, customer_id: str | None, description: str, idempotency_key: str) -> ChargeResult:
        return ChargeResult(ok=True, simulated=True, provider="simulation", reference=f"sim_{idempotency_key[:24]}", status="succeeded",
                            detail={"note": "No payment provider configured — the charge was recorded, not taken.", "amount_cents": amount_cents})


class StripeGateway:
    """Live Stripe. Off-session charges against the card captured at signup."""
    name = "stripe"

    def _post(self, path: str, data: dict[str, Any], *, idempotency_key: str | None = None) -> dict[str, Any]:
        import httpx
        headers = {"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}", "Content-Type": "application/x-www-form-urlencoded"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        r = httpx.post(f"{STRIPE_API}{path}", data=data, headers=headers, timeout=float(settings.STRIPE_TIMEOUT))
        payload = r.json()
        if r.status_code >= 400:
            err = payload.get("error", {})
            raise StripeError(err.get("code") or "stripe_error", err.get("message") or r.text, payload)
        return payload

    def ensure_customer(self, *, tenant_name: str, email: str, existing_id: str | None) -> str | None:
        if existing_id:
            return existing_id
        return self._post("/customers", {"name": tenant_name, "email": email, "metadata[source]": "entiq"}).get("id")

    def charge(self, *, amount_cents: int, currency: str, customer_id: str | None, description: str, idempotency_key: str) -> ChargeResult:
        if not customer_id:
            return ChargeResult(ok=False, simulated=False, provider="stripe", status="failed", failure_code="no_customer", failure_message="No Stripe customer for this practice")
        try:
            pi = self._post("/payment_intents", {
                "amount": str(amount_cents), "currency": currency.lower(), "customer": customer_id, "description": description,
                "confirm": "true", "off_session": "true", "automatic_payment_methods[enabled]": "true",
            }, idempotency_key=idempotency_key)
        except StripeError as e:
            return ChargeResult(ok=False, simulated=False, provider="stripe", status="failed", failure_code=e.code, failure_message=e.message, detail=e.payload)
        status = pi.get("status")
        return ChargeResult(ok=status == "succeeded", simulated=False, provider="stripe", reference=pi.get("id"), status=status,
                            failure_code=(pi.get("last_payment_error") or {}).get("code"), failure_message=(pi.get("last_payment_error") or {}).get("message"),
                            detail={"amount_cents": amount_cents, "currency": currency})


class StripeError(Exception):
    def __init__(self, code: str, message: str, payload: dict[str, Any] | None = None):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.payload = code, message, payload


def gateway():
    """Live Stripe only when a key exists AND the mode says to use it — never a surprise charge."""
    if settings.BILLING_MODE == "stripe" and settings.stripe_enabled:
        return StripeGateway()
    return SimulatedGateway()


def live() -> bool:
    return isinstance(gateway(), StripeGateway)
