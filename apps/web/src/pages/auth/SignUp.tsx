import { useEffect, useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Check, CreditCard, ShieldCheck, Sparkles } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { api, type PricingOut } from '@/api/client';
import { useSession, fmtAud, describeError } from '@/state/session';

/**
 * Practice sign-up. In production: card at signup, $0 charged, first charge on day 16.
 * The plan, and whether a card is required at all, come from the server (`GET /pricing`), so a
 * testing environment with a $0 base plan lets people straight through — and says so plainly
 * rather than pretending a charge is coming.
 */
export function SignUp() {
  const navigate = useNavigate();
  const signUp = useSession((s) => s.signUp);
  const status = useSession((s) => s.status);
  const [plan, setPlan] = useState<PricingOut | null>(null);
  const [step, setStep] = useState<1 | 2>(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [f, setF] = useState({ practiceName: '', abn: '', fullName: '', email: '', password: '', card: '', exp: '', cvc: '' });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });

  useEffect(() => { void api.pricing().then(setPlan).catch(() => undefined); }, []);

  const base = (plan?.base_plan_cents ?? 9900) / 100;
  const incGst = (plan?.base_plan_inc_gst_cents ?? 10890) / 100;
  const trialDays = plan?.trial_days ?? 15;
  const requireCard = plan?.require_card ?? true;
  const freeMode = plan?.free_mode ?? false;
  const steps = requireCard ? 2 : 1;

  const step1Ok = f.practiceName.trim().length > 1 && f.fullName.trim().length > 1 && /.+@.+\..+/.test(f.email) && f.password.length >= 12;
  const cardDigits = f.card.replace(/\D/g, '');
  const cardComplete = cardDigits.length >= 15 && /^\d{2}\s?\/\s?\d{2}$/.test(f.exp) && /^\d{3,4}$/.test(f.cvc);

  const submit = async (withCard: boolean) => {
    setBusy(true); setError(null);
    try {
      await signUp({
        practiceName: f.practiceName.trim(), abn: f.abn.trim() || undefined, fullName: f.fullName.trim(), email: f.email.trim(), password: f.password,
        ...(withCard && cardComplete ? { cardLast4: cardDigits.slice(-4), cardBrand: 'card' } : {}),
      });
      navigate('/clients', { replace: true });
    } catch (err) {
      const msg = describeError(err);
      setError(msg);
      if (msg.toLowerCase().includes('password') || msg.toLowerCase().includes('email')) setStep(1);
    } finally { setBusy(false); }
  };

  if (status === 'authenticated') return <Navigate to="/" replace />;

  return (
    <div className="grid min-h-full grid-cols-1 lg:grid-cols-[1fr_440px]">
      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[440px]">
          <Link to="/" className="mb-8 flex items-center gap-2.5"><img src="/favicon.svg" alt="" className="size-8" /><span className="text-[17px] font-semibold tracking-tight">EnTIQ</span></Link>
          <div className="mb-1 text-[12px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Step {step} of {steps}</div>
          <h1 className="mb-1">{step === 1 ? 'Create your practice' : 'Add a payment method'}</h1>
          <p className="mb-6 text-muted-foreground">
            {step === 1
              ? freeMode
                ? 'One login for every module. This environment is free while we test — no card, nothing charged.'
                : 'One login for every module. You can invite your team afterwards.'
              : `Nothing is charged for ${trialDays} days. On day ${trialDays + 1} we charge ${fmtAud(incGst)} for the base plan. Cancel before then and nothing is charged — ever.`}
          </p>

          {freeMode && step === 1 && (
            <div className="mb-5 flex items-start gap-2 rounded-[6px] border border-primary/30 bg-accent px-3 py-2 text-[13px] text-accent-foreground">
              <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
              <span>Testing mode: the base plan is <strong>$0</strong> and no payment method is needed. Everything else — the trial, modules, invoices, the whole lifecycle — behaves exactly as it will in production.</span>
            </div>
          )}

          {step === 1 ? (
            <div className="space-y-4">
              <Field id="practice" label="Practice name" value={f.practiceName} onChange={set('practiceName')} placeholder="Ashfield Partners" autoFocus />
              <Field id="abn" label="ABN (optional)" value={f.abn} onChange={set('abn')} placeholder="62 114 887 302" />
              <Field id="name" label="Your name" value={f.fullName} onChange={set('fullName')} placeholder="Priya Nair" />
              <Field id="email" label="Work email" type="email" value={f.email} onChange={set('email')} placeholder="priya@ashfieldpartners.com.au" />
              <Field id="pw" label="Password" type="password" value={f.password} onChange={set('password')} placeholder="At least 12 characters" hint="12+ characters with upper, lower, number and symbol." />
              {requireCard
                ? <Button className="w-full" disabled={!step1Ok} onClick={() => setStep(2)}>Continue</Button>
                : <Button className="w-full" disabled={!step1Ok || busy} onClick={() => void submit(false)}>{busy ? 'Creating practice…' : freeMode ? 'Create my practice' : `Start ${trialDays}-day trial`}</Button>}
              <p className="text-center text-[13px] text-muted-foreground">Already have a practice? <Link to="/login" className="text-primary hover:underline">Sign in</Link></p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="rounded-[6px] border bg-card p-4">
                <div className="mb-3 flex items-center gap-2 text-[13px] font-medium"><CreditCard className="size-4 text-primary" /> Card details</div>
                <div className="space-y-3">
                  <Field id="card" label="Card number" value={f.card} onChange={set('card')} placeholder="4242 4242 4242 4242" inputMode="numeric" />
                  <div className="grid grid-cols-2 gap-3">
                    <Field id="exp" label="Expiry" value={f.exp} onChange={set('exp')} placeholder="MM / YY" inputMode="numeric" />
                    <Field id="cvc" label="CVC" value={f.cvc} onChange={set('cvc')} placeholder="123" inputMode="numeric" />
                  </div>
                </div>
                <div className="mt-3 flex items-center gap-1.5 text-[12px] text-muted-foreground"><ShieldCheck className="size-3.5" /> Handled by Stripe. EnTIQ never stores card numbers.</div>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => setStep(1)}>Back</Button>
                <Button className="flex-1" disabled={!cardComplete || busy} onClick={() => void submit(true)}>{busy ? 'Creating practice…' : `Start ${trialDays}-day trial`}</Button>
              </div>
              <p className="text-center text-[12px] text-muted-foreground">By continuing you agree to the EnTIQ terms and privacy policy.</p>
            </div>
          )}
          {error && <div role="alert" className="mt-4 rounded-[5px] border border-error/40 bg-error-bg px-3 py-2 text-[13px] text-error">{error}</div>}
        </div>
      </div>

      <aside className="hidden flex-col justify-between bg-sidebar px-10 py-12 text-sidebar-foreground lg:flex">
        <div>
          <div className="mb-6 text-[11px] font-medium uppercase tracking-[0.1em] text-sidebar-foreground/50">Base plan</div>
          {freeMode ? (
            <>
              <div className="mb-1 text-[34px] font-semibold leading-none tracking-tight text-white">Free<span className="text-[15px] font-normal text-sidebar-foreground/70"> while testing</span></div>
              <div className="mb-8 text-[13px] text-sidebar-foreground/60">No card, no charge. $99 + GST per month when this goes live.</div>
            </>
          ) : (
            <>
              <div className="mb-1 text-[34px] font-semibold leading-none tracking-tight text-white">{fmtAud(base)}<span className="text-[15px] font-normal text-sidebar-foreground/70"> + GST / month</span></div>
              <div className="mb-8 text-[13px] text-sidebar-foreground/60">{fmtAud(incGst)} inc GST · after a {trialDays}-day free trial</div>
            </>
          )}
          <ul className="space-y-3 text-[14px]">
            {['One client record shared by every module', 'Contacts, entities, relationships and timeline', 'Pipeline, tasks and notes', 'Unlimited users, roles and access control', 'Import your client list from Xero or MYOB in minutes', 'Add modules — Verify, Sign, Workpapers, Advisory — any time'].map((t) => (
              <li key={t} className="flex gap-2.5"><Check className="mt-0.5 size-4 shrink-0 text-primary" /><span>{t}</span></li>
            ))}
          </ul>
        </div>
        <div className="text-[12px] leading-5 text-sidebar-foreground/50">
          Built for Australian accounting, tax and advisory firms. Your records are retained to AUSTRAC standards regardless of subscription status — nothing is ever deleted on a billing event.
        </div>
      </aside>
    </div>
  );
}

function Field({ id, label, hint, ...rest }: { id: string; label: string; hint?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} {...rest} />
      {hint && <div className="text-[12px] text-muted-foreground">{hint}</div>}
    </div>
  );
}
