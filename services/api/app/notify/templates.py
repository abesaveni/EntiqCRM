"""
Email templates. Plain text first (it is what gets read), HTML as a light wrapper.
No tracking, no images, one accent colour. Every template returns (subject, text, html).
"""
from __future__ import annotations

from html import escape

TEAL = "#0E7C9E"


def _wrap(title: str, paragraphs: list[str], cta: tuple[str, str] | None = None, footer: str | None = None) -> str:
    body = "".join(f'<p style="margin:0 0 14px;font:15px/1.5 Inter,Segoe UI,sans-serif;color:#201f1e">{p}</p>' for p in paragraphs)
    button = (
        f'<p style="margin:22px 0"><a href="{escape(cta[1])}" style="display:inline-block;background:{TEAL};color:#fff;text-decoration:none;'
        f'font:600 14px Inter,Segoe UI,sans-serif;padding:11px 18px;border-radius:6px">{escape(cta[0])}</a></p>'
        if cta else ""
    )
    foot = f'<p style="margin:26px 0 0;font:12px/1.5 Inter,Segoe UI,sans-serif;color:#8a8886">{footer}</p>' if footer else ""
    return (
        f'<div style="background:#f7f8fa;padding:32px 16px"><div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:28px">'
        f'<div style="font:700 18px Inter,Segoe UI,sans-serif;color:#0b1220;margin-bottom:18px">EnTIQ</div>'
        f'<h1 style="margin:0 0 16px;font:600 20px/1.3 Inter,Segoe UI,sans-serif;color:#201f1e">{escape(title)}</h1>{body}{button}{foot}</div></div>'
    )


def invitation(*, practice: str, inviter: str, role: str, accept_url: str) -> tuple[str, str, str]:
    subject = f"{inviter} invited you to {practice} on EnTIQ"
    text = f"{inviter} has invited you to join {practice} on EnTIQ as {role}.\n\nSet up your login here (link expires in 72 hours):\n{accept_url}\n\nIf you were not expecting this, ignore this email."
    html = _wrap(f"You're invited to {practice}", [f"<strong>{escape(inviter)}</strong> has invited you to join <strong>{escape(practice)}</strong> on EnTIQ as <strong>{escape(role)}</strong>.", "One login covers every module the practice uses."], ("Join the practice", accept_url), "The link expires in 72 hours. If you weren't expecting this, you can ignore it.")
    return subject, text, html


def welcome(*, name: str, practice: str, trial_ends: str, amount_inc_gst: str, app_url: str) -> tuple[str, str, str]:
    subject = f"Welcome to EnTIQ — {practice} is set up"
    text = (f"Hi {name},\n\n{practice} is live on EnTIQ. Your 15-day trial runs until {trial_ends}; on the following day your card is charged {amount_inc_gst} for the base plan. Cancel any time before then and nothing is charged.\n\n"
            f"Fastest way to get value today: import your client list from Xero or MYOB — {app_url}/clients/import\n\nThe EnTIQ team")
    html = _wrap(f"{practice} is set up", [f"Hi {escape(name)},", f"Your 15-day trial runs until <strong>{escape(trial_ends)}</strong>. The following day your card is charged <strong>{escape(amount_inc_gst)}</strong> for the base plan. Cancel any time before then and nothing is charged.", "Fastest way to get value today: import your client list from Xero or MYOB."], ("Import your clients", f"{app_url}/clients/import"))
    return subject, text, html


def trial_reminder(*, name: str, practice: str, days_left: int, charge_date: str, amount_inc_gst: str, app_url: str, card_last4: str | None) -> tuple[str, str, str]:
    subject = f"{days_left} day{'s' if days_left != 1 else ''} left in your EnTIQ trial"
    card = f" to your card ending {card_last4}" if card_last4 else ""
    text = (f"Hi {name},\n\nYour EnTIQ trial for {practice} ends in {days_left} day{'s' if days_left != 1 else ''}. On {charge_date} we'll charge {amount_inc_gst}{card} for the base plan.\n\n"
            f"Want to keep going? Nothing to do. Want to stop? Cancel from Practice HQ before {charge_date} and nothing is charged: {app_url}/hq/modules\n\nThe EnTIQ team")
    html = _wrap(subject, [f"Hi {escape(name)},", f"Your trial for <strong>{escape(practice)}</strong> ends in <strong>{days_left} day{'s' if days_left != 1 else ''}</strong>. On {escape(charge_date)} we'll charge <strong>{escape(amount_inc_gst)}</strong>{escape(card)} for the base plan.", "Want to keep going? Nothing to do. Want to stop? Cancel from Practice HQ before then and nothing is charged."], ("Manage plan", f"{app_url}/hq/modules"))
    return subject, text, html


def trial_ended_active(*, name: str, practice: str, amount_inc_gst: str, period_end: str, simulated: bool, app_url: str) -> tuple[str, str, str]:
    subject = f"Your EnTIQ plan for {practice} is active"
    charged = "We have recorded" if simulated else "We have charged"
    text = f"Hi {name},\n\nYour trial has ended and {practice} is now on the EnTIQ base plan. {charged} {amount_inc_gst} for the month to {period_end}.\n\nInvoices and modules: {app_url}/hq/modules\n\nThe EnTIQ team"
    html = _wrap(subject, [f"Hi {escape(name)},", f"Your trial has ended and <strong>{escape(practice)}</strong> is now on the EnTIQ base plan. {charged} <strong>{escape(amount_inc_gst)}</strong> for the month to {escape(period_end)}."], ("View plan and invoices", f"{app_url}/hq/modules"))
    return subject, text, html


def payment_failed(*, name: str, practice: str, amount_inc_gst: str, grace_days: int, app_url: str) -> tuple[str, str, str]:
    subject = f"Payment for {practice} did not go through"
    text = f"Hi {name},\n\nWe couldn't charge {amount_inc_gst} for {practice}. We'll retry for {grace_days} days; after that the practice becomes read-only until payment is restored. Nothing is deleted.\n\nUpdate your card: {app_url}/hq/modules\n\nThe EnTIQ team"
    html = _wrap(subject, [f"Hi {escape(name)},", f"We couldn't charge <strong>{escape(amount_inc_gst)}</strong> for <strong>{escape(practice)}</strong>. We'll retry for {grace_days} days; after that the practice becomes read-only until payment is restored. <strong>Nothing is deleted.</strong>"], ("Update card", f"{app_url}/hq/modules"))
    return subject, text, html


def suspended(*, name: str, practice: str, app_url: str) -> tuple[str, str, str]:
    subject = f"{practice} is now read-only"
    text = f"Hi {name},\n\nPayment for {practice} is more than 7 days overdue, so the practice is now read-only. Your records are intact and nothing has been deleted. Pay to restore full access: {app_url}/hq/modules\n\nThe EnTIQ team"
    html = _wrap(subject, [f"Hi {escape(name)},", f"Payment for <strong>{escape(practice)}</strong> is more than 7 days overdue, so the practice is now <strong>read-only</strong>. Your records are intact and nothing has been deleted."], ("Restore access", f"{app_url}/hq/modules"))
    return subject, text, html


def cancelled(*, name: str, practice: str, export_days: int, app_url: str) -> tuple[str, str, str]:
    subject = f"{practice} has been cancelled — {export_days}-day export window"
    text = f"Hi {name},\n\n{practice} has been cancelled. You have {export_days} days to export your data: {app_url}/account-closed\n\nAfter that, records are retained to meet our compliance obligations but are no longer accessible in the app.\n\nThe EnTIQ team"
    html = _wrap(subject, [f"Hi {escape(name)},", f"<strong>{escape(practice)}</strong> has been cancelled. You have <strong>{export_days} days</strong> to export your data.", "After that, records are retained to meet our compliance obligations but are no longer accessible in the app."], ("Export data", f"{app_url}/account-closed"))
    return subject, text, html


def task_assigned(*, name: str, title: str, client_name: str | None, assigned_by: str, app_url: str) -> tuple[str, str, str]:
    subject = f"Task for you: {title}"
    where = f" for {client_name}" if client_name else ""
    text = f"Hi {name},\n\n{assigned_by} assigned you a task{where}:\n\n  {title}\n\nOpen tasks: {app_url}/tasks\n\nThe EnTIQ team"
    html = _wrap(subject, [f"Hi {escape(name)},", f"<strong>{escape(assigned_by)}</strong> assigned you a task{escape(where)}:", f"<strong>{escape(title)}</strong>"], ("Open tasks", f"{app_url}/tasks"))
    return subject, text, html
