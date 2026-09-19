"""
Ledger providers for Workpapers, in the same shape as the Verify providers: a live driver used when
credentials exist, a simulation driver otherwise, and a `simulated` flag that follows every figure
through the pack, the UI and the sign-off seal.

Xero is the live target. With no XERO_CLIENT_ID/SECRET configured (none exist in this estate yet) the
simulation driver produces a coherent, deterministic trial balance per client and period so the whole
workpaper flow — variances, materiality, issues, review, sign-off — is exercisable end to end.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from app.core.config import settings

# Xero OAuth 2.0 endpoints, for when credentials arrive
XERO_AUTHORIZE = "https://login.xero.com/identity/connect/authorize"
XERO_TOKEN = "https://identity.xero.com/connect/token"
XERO_CONNECTIONS = "https://api.xero.com/connections"
XERO_REPORTS = "https://api.xero.com/api.xro/2.0/Reports"
XERO_SCOPES = "offline_access accounting.reports.read accounting.transactions.read accounting.contacts.read"


@dataclass
class LedgerLine:
    account_code: str
    label: str
    section: str          # Assets · Liabilities · Equity · Income · Expenses
    value_cents: int
    prior_cents: int | None = None


@dataclass
class LedgerResult:
    lines: list[LedgerLine]
    simulated: bool
    source: str
    organisation: str | None = None
    detail: dict[str, Any] | None = None


class LedgerProvider(Protocol):
    name: str
    def authorize_url(self, state: str) -> str | None: ...
    def trial_balance(self, *, client_name: str, period_end: date | None, external_tenant_id: str | None, token: str | None) -> LedgerResult: ...


# ------------------------------------------------------------------ live (Xero)
class XeroLedger:
    name = "xero"

    def authorize_url(self, state: str) -> str:
        from urllib.parse import urlencode
        return f"{XERO_AUTHORIZE}?" + urlencode({"response_type": "code", "client_id": settings.XERO_CLIENT_ID, "redirect_uri": settings.XERO_REDIRECT_URI, "scope": XERO_SCOPES, "state": state})

    def trial_balance(self, *, client_name: str, period_end: date | None, external_tenant_id: str | None, token: str | None) -> LedgerResult:
        import httpx
        if not token or not external_tenant_id:
            raise RuntimeError("Xero connection is not authorised")
        params = {"date": (period_end or date.today()).isoformat()}
        r = httpx.get(f"{XERO_REPORTS}/TrialBalance", params=params, headers={"Authorization": f"Bearer {token}", "Xero-tenant-id": external_tenant_id, "Accept": "application/json"}, timeout=float(settings.XERO_TIMEOUT))
        r.raise_for_status()
        payload = r.json()
        lines: list[LedgerLine] = []
        for report in payload.get("Reports", []):
            for row in report.get("Rows", []):
                for sub in row.get("Rows", []) if row.get("RowType") == "Section" else []:
                    cells = sub.get("Cells", [])
                    if len(cells) < 3:
                        continue
                    label = str(cells[0].get("Value") or "")
                    debit = _cents(cells[1].get("Value"))
                    credit = _cents(cells[2].get("Value"))
                    section = _section_for(row.get("Title") or "", label)
                    lines.append(LedgerLine(account_code=str(sub.get("Cells", [{}])[0].get("Attributes", [{}])[0].get("Value", "") or ""), label=label, section=section, value_cents=debit - credit))
        return LedgerResult(lines=lines, simulated=False, source="xero", organisation=external_tenant_id, detail={"rows": len(lines)})


def _cents(v: Any) -> int:
    try:
        return int(round(float(v or 0) * 100))
    except (TypeError, ValueError):
        return 0


def _section_for(title: str, label: str) -> str:
    t = f"{title} {label}".lower()
    if any(w in t for w in ("asset", "bank", "receivable", "inventor", "plant", "equipment")):
        return "Assets"
    if any(w in t for w in ("liabilit", "payable", "loan", "gst", "payg", "provision")):
        return "Liabilities"
    if any(w in t for w in ("equity", "capital", "retained", "drawings")):
        return "Equity"
    if any(w in t for w in ("income", "revenue", "sales")):
        return "Income"
    return "Expenses"


# ------------------------------------------------------------------ simulation
_SIM_CHART: list[tuple[str, str, str, float, float]] = [
    # code, label, section, share of scale (current), share (prior)
    ("090", "Business bank account", "Assets", 0.09, 0.07),
    ("091", "Business savings", "Assets", 0.04, 0.05),
    ("610", "Accounts receivable", "Assets", 0.14, 0.12),
    ("630", "Inventory", "Assets", 0.06, 0.07),
    ("710", "Plant and equipment", "Assets", 0.18, 0.19),
    ("711", "Less accumulated depreciation", "Assets", -0.05, -0.04),
    ("800", "Accounts payable", "Liabilities", -0.08, -0.07),
    ("820", "GST payable", "Liabilities", -0.03, -0.025),
    ("825", "PAYG withholding payable", "Liabilities", -0.015, -0.012),
    ("830", "Provision for income tax", "Liabilities", -0.02, -0.018),
    ("900", "Loan — equipment finance", "Liabilities", -0.10, -0.13),
    ("960", "Retained earnings", "Equity", -0.16, -0.14),
    ("970", "Owner's capital", "Equity", -0.02, -0.02),
    ("200", "Sales", "Income", -1.00, -0.88),
    ("260", "Other revenue", "Income", -0.04, -0.03),
    ("300", "Cost of goods sold", "Expenses", 0.52, 0.47),
    ("400", "Advertising", "Expenses", 0.02, 0.018),
    ("404", "Bank fees", "Expenses", 0.002, 0.002),
    ("408", "Cleaning", "Expenses", 0.006, 0.006),
    ("412", "Consulting & accounting", "Expenses", 0.012, 0.010),
    ("420", "Entertainment", "Expenses", 0.004, 0.006),
    ("429", "General expenses", "Expenses", 0.015, 0.014),
    ("433", "Insurance", "Expenses", 0.011, 0.010),
    ("437", "Interest expense", "Expenses", 0.009, 0.011),
    ("445", "Light, power, heating", "Expenses", 0.008, 0.007),
    ("449", "Motor vehicle expenses", "Expenses", 0.017, 0.015),
    ("453", "Office expenses", "Expenses", 0.007, 0.007),
    ("461", "Printing & stationery", "Expenses", 0.003, 0.003),
    ("469", "Rent", "Expenses", 0.06, 0.058),
    ("477", "Wages and salaries", "Expenses", 0.22, 0.20),
    ("478", "Superannuation", "Expenses", 0.024, 0.022),
    ("485", "Subscriptions", "Expenses", 0.005, 0.004),
    ("489", "Telephone & internet", "Expenses", 0.004, 0.004),
    ("493", "Travel", "Expenses", 0.010, 0.006),
    ("497", "Depreciation", "Expenses", 0.014, 0.013),
]


class SimulatedLedger:
    name = "simulation"

    def authorize_url(self, state: str) -> str | None:
        return None

    def trial_balance(self, *, client_name: str, period_end: date | None, external_tenant_id: str | None, token: str | None) -> LedgerResult:
        # Deterministic per client + period: the same pack re-synced gives the same numbers.
        seed = int(hashlib.sha256(f"{client_name}|{period_end}".encode()).hexdigest()[:8], 16)
        scale = 400_000_00 + (seed % 2_600_000) * 100          # $400k–$3m turnover, in cents
        lines: list[LedgerLine] = []
        for i, (code, label, section, cur, prior) in enumerate(_SIM_CHART):
            jitter = 0.9 + ((seed >> (i % 16)) % 21) / 100     # ±10%, stable per account
            value = int(cur * scale * jitter)
            prior_v = int(prior * scale * (0.95 + ((seed >> ((i + 3) % 16)) % 11) / 100))
            lines.append(LedgerLine(account_code=code, label=label, section=section, value_cents=value, prior_cents=prior_v))
        # A real trial balance balances. Put the residual into retained earnings so the pack's
        # out-of-balance rule only fires on genuinely broken data.
        plug = next(l for l in lines if l.account_code == "960")
        plug.value_cents -= sum(l.value_cents for l in lines)
        plug.prior_cents -= sum((l.prior_cents or 0) for l in lines)
        return LedgerResult(lines=lines, simulated=True, source="simulation", organisation=f"{client_name} (simulated ledger)", detail={"accounts": len(lines), "note": "Figures are generated, not from a real ledger."})


def provider_for(name: str) -> LedgerProvider:
    if name == "xero" and settings.XERO_CLIENT_ID and settings.XERO_CLIENT_SECRET and settings.LEDGER_PROVIDER_MODE != "simulate":
        return XeroLedger()
    return SimulatedLedger()


def live_available() -> bool:
    return bool(settings.XERO_CLIENT_ID and settings.XERO_CLIENT_SECRET and settings.LEDGER_PROVIDER_MODE != "simulate")
