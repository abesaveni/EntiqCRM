import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Check, CreditCard, ShieldCheck } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { useSession, fmtAud, monthlyBaseExGst, GST_RATE } from '@/state/session';

/**
 * Practice sign-up — card at signup, $0 charged, first charge on day 16.
 * Decisions (19 Sep 2026): card upfront; $99 + GST; reminders day 10 & 14; one-click cancel; cancel in trial = never charged.
 * Card fields are a placeholder for Stripe Elements — no card data is ever handled by this app directly.
 */
export function SignUp() {
  const navigate = useNavigate();
  const signUp = useSession((s) => s.signUp);
  const [step, setStep] = useState<1 | 2>(1);
  const [f, setF] = useState({ practiceName: '', abn: '', fullName: '', email: '', password: '', card: '', exp: '', cvc: '' });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const base = monthlyBaseExGst();

  const step1Ok = f.practiceName.trim().length > 1 && f.fullName.trim().length > 1 && /.+@.+\..+/.test(f.email) && f.password.length >= 12;
  const cardDigits = f.card.replace(/\D/g, '');
  const step2Ok = cardDigits.length >= 15 && /^\d{2}\s?\/\s?\d{2}$/.test(f.exp) && /^\d{3,4}$/.test(f.cvc);

  const submit = () => {
    signUp({ practiceName: f.practiceName.trim(), abn: f.abn.trim() || undefined, fullName: f.fullName.trim(), email: f.email.trim(), cardLast4: cardDigits.slice(-4) });
    navigate('/clients', { replace: true });
  };

  return (
    <div className="grid min-h-full grid-cols-1 lg:grid-cols-[1fr_440px]">
      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-[440px]">
          <Link to="/" className="mb-8 flex items-center gap-2.5"><img src="/favicon.svg" alt="" className="size-8" /><span className="text-[17px] font-semibold tracking-tight">EnTIQ</span></Link>
          <div className="mb-1 text-[12px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Step {step} of 2</div>
          <h1 className="mb-1">{step === 1 ? 'Create your practice' : 'Add a payment method'}</h1>
          <p className="mb-6 text-muted-foreground">{step === 1 ? 'One login for every module. You can invite your team afterwards.' : `Nothing is charged for 15 days. On day 16 we charge ${fmtAud(base * (1 + GST_RATE))} for the base plan. Cancel before then and nothing is charged — ever.`}</p>

          {step === 1 ? (
            <div className="space-y-4">
              <Field id="practice" label="Practice name" value={f.practiceName} onChange={set('practiceName')} placeholder="Ashfield Partners" autoFocus />
              <Field id="abn" label="ABN (optional)" value={f.abn} onChange={set('abn')} placeholder="62 114 887 302" />
              <Field id="name" label="Your name" value={f.fullName} onChange={set('fullName')} placeholder="Priya Nair" />
              <Field id="email" label="Work email" type="email" value={f.email} onChange={set('email')} placeholder="priya@ashfieldpartners.com.au" />
              <Field id="pw" label="Password" type="password" value={f.password} onChange={set('password')} placeholder="At least 12 characters" hint="12+ characters with upper, lower, number and symbol." />
              <Button className="w-full" disabled={!step1Ok} onClick={() => setStep(2)}>Continue</Button>
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
                <Button className="flex-1" disabled={!step2Ok} onClick={submit}>Start 15-day trial</Button>
              </div>
              <p className="text-center text-[12px] text-muted-foreground">By continuing you agree to the EnTIQ terms and privacy policy.</p>
            </div>
          )}
        </div>
      </div>

      <aside className="hidden flex-col justify-between bg-sidebar px-10 py-12 text-sidebar-foreground lg:flex">
        <div>
          <div className="mb-6 text-[11px] font-medium uppercase tracking-[0.1em] text-sidebar-foreground/50">Base plan</div>
          <div className="mb-1 text-[34px] font-semibold leading-none tracking-tight text-white">{fmtAud(base)}<span className="text-[15px] font-normal text-sidebar-foreground/70"> + GST / month</span></div>
          <div className="mb-8 text-[13px] text-sidebar-foreground/60">{fmtAud(base * (1 + GST_RATE))} inc GST · after a 15-day free trial</div>
          <ul className="space-y-3 text-[14px]">
            {['One client record shared by every module', 'Contacts, entities, relationships and timeline', 'Pipeline, tasks and notes', 'Unlimited users, roles and access control', 'Import your client list from Xero or MYOB in minutes', 'Add modules — Verify, Sign, Workpapers, Support — any time'].map((t) => (
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
