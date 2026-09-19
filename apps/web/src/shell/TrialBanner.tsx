import { Link } from 'react-router-dom';
import { CreditCard, AlertTriangle, Lock } from 'lucide-react';
import { useSession, trialDaysLeft, fmtAud, monthlyBaseExGst, GST_RATE } from '@/state/session';

/**
 * Lifecycle banner. Trial: days remaining + what will be charged. Past due / suspended:
 * the access consequence, stated plainly. Nothing shown for `active`.
 */
export function TrialBanner() {
  const tenant = useSession((s) => s.tenant);
  if (!tenant) return null;

  const base = monthlyBaseExGst();
  const incGst = base * (1 + GST_RATE);
  const { freeMode, trialDays } = useSession.getState().pricing;

  if (tenant.status === 'trialing') {
    const days = trialDaysLeft(tenant);
    return (
      <div className="flex items-center gap-3 border-b border-primary/25 bg-accent px-4 py-2 text-[13px] text-accent-foreground">
        <CreditCard className="size-4 shrink-0" />
        <span className="flex-1">
          {freeMode ? (
            <>This environment is <strong>free while we test</strong> — nothing is charged, with or without a card on file. Your trial converts to an active plan on day {trialDays + 1} at $0.</>
          ) : (
            <>
              <strong>{days} day{days === 1 ? '' : 's'}</strong> left in your trial. On day {trialDays + 1}{' '}
              {tenant.cardLast4 ? <>your card ending {tenant.cardLast4} is charged</> : <>we will charge your payment method</>}{' '}
              <strong>{fmtAud(incGst)}</strong> ({fmtAud(base)} + GST) for the base plan. Cancel any time before then and nothing is charged.
            </>
          )}
        </span>
        <Link to="/hq/modules" className="font-medium underline-offset-2 hover:underline">Manage plan</Link>
      </div>
    );
  }
  if (tenant.status === 'past_due') {
    return (
      <div className="flex items-center gap-3 border-b border-warn/40 bg-warn-bg px-4 py-2 text-[13px] text-warn">
        <AlertTriangle className="size-4 shrink-0" />
        <span className="flex-1">Your last payment failed. We will retry for 7 days; after that the practice becomes read-only. Update your card to keep full access.</span>
        <Link to="/hq/modules" className="font-medium underline-offset-2 hover:underline">Update card</Link>
      </div>
    );
  }
  if (tenant.status === 'suspended') {
    return (
      <div className="flex items-center gap-3 border-b border-warn/40 bg-warn-bg px-4 py-2 text-[13px] text-warn">
        <Lock className="size-4 shrink-0" />
        <span className="flex-1">This practice is <strong>read-only</strong> — payment is 7+ days overdue. Your records are intact and nothing has been deleted. Pay to restore access.</span>
        <Link to="/hq/modules" className="font-medium underline-offset-2 hover:underline">Pay now</Link>
      </div>
    );
  }
  return null;
}
