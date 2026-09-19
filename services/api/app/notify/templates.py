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


def sign_request(*, name: str, practice: str, title: str, message: str | None, url: str, expires: str | None, reminder: bool = False) -> tuple[str, str, str]:
    subject = f"{'Reminder: ' if reminder else ''}{practice} has sent you {title} to sign"
    note = f"\n\nMessage from {practice}:\n{message}" if message else ""
    exp = f" The link expires on {expires}." if expires else ""
    text = f"Hi {name},\n\n{practice} has sent you \"{title}\" to review and sign electronically.{note}\n\nReview and sign:\n{url}\n{exp}\n\nIf you did not expect this, you can ignore it or decline from the link."
    html = _wrap(f"{title}", [f"Hi {escape(name)},", f"<strong>{escape(practice)}</strong> has sent you <strong>{escape(title)}</strong> to review and sign electronically.", *([f"<em>{escape(message)}</em>"] if message else []), f"Nothing to install — open the link, read the document, and sign with your name or a drawn signature.{escape(exp)}"], ("Review and sign", url), "If you did not expect this, you can ignore it or decline from the link.")
    return subject, text, html


def sign_completed(*, name: str, title: str, practice: str, sealed: str) -> tuple[str, str, str]:
    subject = f"Signed: {title}"
    text = f"Hi {name},\n\nAll parties have signed \"{title}\" with {practice}. The agreement is sealed.\n\nSeal (SHA-256): {sealed}\n\nKeep this email with your copy of the document; the seal lets anyone confirm it has not changed since signing.\n\nEnTIQ Sign"
    html = _wrap(subject, [f"Hi {escape(name)},", f"All parties have signed <strong>{escape(title)}</strong> with {escape(practice)}. The agreement is sealed.", f"<span style=\"font:12px monospace\">Seal: {escape(sealed)}</span>"], None, "Keep this with your copy of the document; the seal lets anyone confirm it has not changed since signing.")
    return subject, text, html


def task_assigned(*, name: str, title: str, client_name: str | None, assigned_by: str, app_url: str) -> tuple[str, str, str]:
    subject = f"Task for you: {title}"
    where = f" for {client_name}" if client_name else ""
    text = f"Hi {name},\n\n{assigned_by} assigned you a task{where}:\n\n  {title}\n\nOpen tasks: {app_url}/tasks\n\nThe EnTIQ team"
    html = _wrap(subject, [f"Hi {escape(name)},", f"<strong>{escape(assigned_by)}</strong> assigned you a task{escape(where)}:", f"<strong>{escape(title)}</strong>"], ("Open tasks", f"{app_url}/tasks"))
    return subject, text, html


def start_invitation(*, name: str, practice: str, prospect: str, url: str, expires: str) -> tuple[str, str, str]:
    subject = f"{practice} — let's get {prospect} set up"
    text = (f"Hi {name},\n\n{practice} has invited you to complete onboarding for {prospect}. It takes about 15 minutes: confirm your entity details, "
            f"answer a short questionnaire, upload a few documents and choose the services you need.\n\nStart here (link valid until {expires}):\n{url}\n\n"
            f"You can stop and come back any time using the same link.\n\n{practice}")
    html = _wrap(f"Let's get {prospect} set up", [f"Hi {escape(name)},", f"<strong>{escape(practice)}</strong> has invited you to complete onboarding for <strong>{escape(prospect)}</strong>. It takes about 15 minutes: confirm your entity details, answer a short questionnaire, upload a few documents and choose the services you need.", "You can stop and come back any time using the same link."], ("Start onboarding", url), f"The link is valid until {escape(expires)}.")
    return subject, text, html


def start_proposal(*, name: str, practice: str, total: str, url: str, valid_until: str) -> tuple[str, str, str]:
    subject = f"Your proposal from {practice} is ready"
    text = f"Hi {name},\n\n{practice} has issued your fee proposal: {total} inc GST. Open your onboarding link to review the line items and accept. The proposal is valid until {valid_until}.\n\n{practice}"
    html = _wrap(subject, [f"Hi {escape(name)},", f"<strong>{escape(practice)}</strong> has issued your fee proposal: <strong>{escape(total)} inc GST</strong>.", "Open your onboarding link (from our earlier email) to review the line items and accept."], None, f"The proposal is valid until {escape(valid_until)}.")
    return subject, text, html


def start_activated(*, name: str, practice: str, prospect: str) -> tuple[str, str, str]:
    subject = f"Welcome aboard — {prospect} is now a client of {practice}"
    text = f"Hi {name},\n\nOnboarding is complete and {prospect} is now an active client of {practice}. Your engagement letter is signed and your services are scheduled. We'll be in touch with next steps.\n\n{practice}"
    html = _wrap("Welcome aboard", [f"Hi {escape(name)},", f"Onboarding is complete and <strong>{escape(prospect)}</strong> is now an active client of <strong>{escape(practice)}</strong>.", "Your engagement letter is signed and your services are scheduled. We'll be in touch with next steps."])
    return subject, text, html


def request_sent(*, name: str, practice: str, title: str, message: str | None, url: str, due: str | None, items: list[str], reminder: bool = False) -> tuple[str, str, str]:
    subject = f"{'Reminder: ' if reminder else ''}{practice} needs some information — {title}"
    lst = "".join(f"  • {i}\n" for i in items[:15]) + (f"  … and {len(items) - 15} more\n" if len(items) > 15 else "")
    note = f"\n\n{message}" if message else ""
    text = f"Hi {name},\n\n{practice} has asked for the following{' (still outstanding)' if reminder else ''}:{note}\n\n{lst}\nUpload securely here{f' by {due}' if due else ''}:\n{url}\n\nYou can mark anything that does not apply, and come back to the same link any time."
    html = _wrap(title, [f"Hi {escape(name)},", f"<strong>{escape(practice)}</strong> has asked for the following{' (still outstanding)' if reminder else ''}:", *([f"<em>{escape(message)}</em>"] if message else []), "<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items[:15]) + "</ul>", "You can mark anything that does not apply, and come back to the same link any time."], ("Upload securely", url), f"Please respond by {escape(due)}." if due else None)
    return subject, text, html


def request_item_rejected(*, name: str, practice: str, title: str, item: str, reason: str, url: str) -> tuple[str, str, str]:
    subject = f"{practice}: one item needs another look — {item}"
    text = f"Hi {name},\n\nThanks for what you sent for {title}. One item needs another look:\n\n  • {item}\n    {reason}\n\nRe-upload here:\n{url}\n\n{practice}"
    html = _wrap(subject, [f"Hi {escape(name)},", f"Thanks for what you sent for <strong>{escape(title)}</strong>. One item needs another look:", f"<strong>{escape(item)}</strong> — {escape(reason)}"], ("Re-upload", url))
    return subject, text, html


def portal_invite(*, name: str, practice: str, client: str, url: str) -> tuple[str, str, str]:
    subject = f"{practice} has set up your client portal"
    text = f"Hi {name},\n\n{practice} has given you access to a secure portal for {client}: documents, requests, agreements and messages in one place, no password needed.\n\nSign in here (link valid for 14 days; after that use “email me a link” on the portal page):\n{url}\n\n{practice}"
    html = _wrap("Your client portal is ready", [f"Hi {escape(name)},", f"<strong>{escape(practice)}</strong> has given you access to a secure portal for <strong>{escape(client)}</strong>: documents, requests, agreements and messages in one place — no password needed."], ("Open the portal", url), "This link is valid for 14 days. Afterwards, use “email me a link” on the portal page.")
    return subject, text, html


def portal_login(*, name: str, practice: str, client: str, url: str) -> tuple[str, str, str]:
    subject = f"Your sign-in link for {practice}"
    text = f"Hi {name},\n\nHere is your one-time sign-in link for the {client} portal (valid 30 minutes):\n{url}\n\nIf you did not request this, ignore this email."
    html = _wrap("Sign in to your portal", [f"Hi {escape(name)},", f"Here is your one-time sign-in link for the <strong>{escape(client)}</strong> portal at {escape(practice)}."], ("Sign in", url), "Valid for 30 minutes. If you did not request this, ignore this email.")
    return subject, text, html


def portal_message(*, name: str, practice: str, author: str, body: str, url: str) -> tuple[str, str, str]:
    subject = f"New message from {practice}"
    text = f"Hi {name},\n\n{author} at {practice} wrote:\n\n{body}\n\nReply in your portal:\n{url}"
    html = _wrap(subject, [f"Hi {escape(name)},", f"<strong>{escape(author)}</strong> at {escape(practice)} wrote:", f"<em>{escape(body)}</em>"], ("Reply in the portal", url))
    return subject, text, html


def support_ack(*, name: str, number: int, subject: str, priority: str, first_response_hours: float) -> tuple[str, str, str]:
    subj = f"[#{number}] We have your request: {subject}"
    text = f"Hi {name},\n\nThanks — your support request #{number} ({priority} priority) is in the queue. Our first response is due within {first_response_hours} hours.\n\nEnTIQ Support"
    html = _wrap(f"Ticket #{number} received", [f"Hi {escape(name)},", f"Your support request <strong>#{number}</strong> ({escape(priority)} priority) is in the queue. Our first response is due within <strong>{first_response_hours} hours</strong>."])
    return subj, text, html


def support_reply(*, name: str, number: int, subject: str, author: str, body: str, url: str) -> tuple[str, str, str]:
    subj = f"[#{number}] {author} replied: {subject}"
    text = f"Hi {name},\n\n{author} from EnTIQ Support replied on #{number}:\n\n{body}\n\nView and reply:\n{url}"
    html = _wrap(f"Reply on ticket #{number}", [f"Hi {escape(name)},", f"<strong>{escape(author)}</strong> from EnTIQ Support replied:", f"<em>{escape(body)}</em>"], ("View ticket", url))
    return subj, text, html

