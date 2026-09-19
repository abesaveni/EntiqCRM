import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@entiq/ui/button';
import { platform, type OutboundOut } from '@/api/platform';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Switch } from '@entiq/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { useSession, describeError, type LifecycleStatus } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';

export function Settings() {
  const tenant = useSession((s) => s.tenant)!;
  const simulate = useSession((s) => s.simulateLifecycle);
  const refresh = useSession((s) => s.refresh);
  const [outbound, setOutbound] = useState<OutboundOut[] | null>(null);
  const loadOutbound = () => platform.dev.outbound(30).then(setOutbound).catch((e) => toast.error(describeError(e)));

  return (
    <div className="page">
      <PageHeader eyebrow="Practice HQ" title="Practice settings" description="Profile, branding, security and data policies for this practice." />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-[6px] border bg-card p-5">
          <h2 className="mb-4 text-[15px]">Practice profile</h2>
          <div className="space-y-4">
            <Field id="name" label="Practice name" defaultValue={tenant.name} />
            <Field id="abn" label="ABN" defaultValue={tenant.abn ?? ''} />
            <div className="grid gap-1.5"><Label>Timezone</Label>
              <Select defaultValue="Australia/Sydney"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{['Australia/Sydney', 'Australia/Melbourne', 'Australia/Brisbane', 'Australia/Perth', 'Australia/Adelaide', 'Australia/Hobart', 'Australia/Darwin'].map((z) => <SelectItem key={z} value={z}>{z}</SelectItem>)}</SelectContent></Select>
            </div>
            <Field id="domain" label="Practice URL" defaultValue={`${tenant.slug}.entiq.com.au`} disabled />
            <Button size="sm" onClick={() => toast.success('Profile saved')}>Save</Button>
          </div>
        </section>

        <section className="rounded-[6px] border bg-card p-5">
          <h2 className="mb-4 text-[15px]">Security &amp; sessions</h2>
          <div className="space-y-4 text-[13px]">
            <Toggle label="Require MFA for every user" desc="TOTP or passkey at sign-in." defaultChecked />
            <Toggle label="Step-up for privileged actions" desc="Re-authenticate before changing access, plans or integrations." defaultChecked />
            <Toggle label="Session follows the person" desc="Sign-out on one device signs out everywhere." defaultChecked />
            <div className="grid gap-1.5"><Label>Idle timeout</Label>
              <Select defaultValue="30"><SelectTrigger className="w-40"><SelectValue /></SelectTrigger><SelectContent>{['15', '30', '60', '120'].map((m) => <SelectItem key={m} value={m}>{m} minutes</SelectItem>)}</SelectContent></Select>
            </div>
          </div>
        </section>

        <section className="rounded-[6px] border bg-card p-5">
          <h2 className="mb-1 text-[15px]">Data, retention &amp; privacy</h2>
          <p className="mb-4 text-[13px] text-muted-foreground">Retention outlives the subscription. AML/CTF records are held for 7 years regardless of plan status; nothing is deleted on a billing event.</p>
          <div className="space-y-4 text-[13px]">
            <Toggle label="Legal hold on signed agreements" desc="Executed documents cannot be deleted by any user." defaultChecked disabled />
            <Toggle label="Client data export on cancellation" desc="30-day self-service export window." defaultChecked disabled />
            <Toggle label="Allow staff to download client documents" desc="Off = view in browser only." defaultChecked />
          </div>
        </section>

        <section className="rounded-[6px] border border-dashed bg-card p-5 lg:col-span-2">
          <h2 className="mb-1 text-[15px]">Demo controls</h2>
          <p className="mb-4 text-[13px] text-muted-foreground">Non-production only. Set a lifecycle state directly, or move the clock and run the real hourly job to see reminders, conversion and dunning happen the way they will in production.</p>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-[13px]"><span className="w-24 text-muted-foreground">Set state</span>
            {(['trialing', 'active', 'past_due', 'suspended', 'cancelled'] as LifecycleStatus[]).map((s) => (
              <Button key={s} size="sm" variant={tenant.status === s ? 'default' : 'outline'} onClick={() => void simulate(s).catch((e) => toast.error(describeError(e)))}>{s.replace('_', ' ')}</Button>
            ))}
          </div>
          <div className="mb-3 flex flex-wrap items-center gap-2 text-[13px]"><span className="w-24 text-muted-foreground">Move clock</span>
            <Button size="sm" variant="outline" onClick={() => void platform.dev.timeTravel({ trial_ends_in_days: 4 }).then(refresh).catch((e) => toast.error(describeError(e)))}>Trial: 4 days left</Button>
            <Button size="sm" variant="outline" onClick={() => void platform.dev.timeTravel({ trial_ends_in_days: 0.5 }).then(refresh).catch((e) => toast.error(describeError(e)))}>Trial: last day</Button>
            <Button size="sm" variant="outline" onClick={() => void platform.dev.timeTravel({ trial_ends_in_days: -0.1 }).then(refresh).catch((e) => toast.error(describeError(e)))}>Trial ended</Button>
            <Button size="sm" variant="outline" onClick={() => void platform.dev.timeTravel({ status_changed_days_ago: 8 }).then(refresh).catch((e) => toast.error(describeError(e)))}>Status 8 days old</Button>
            <Button size="sm" variant="outline" onClick={() => void platform.dev.timeTravel({ status_changed_days_ago: 31 }).then(refresh).catch((e) => toast.error(describeError(e)))}>Status 31 days old</Button>
          </div>
          <div className="mb-4 flex flex-wrap items-center gap-2 text-[13px]"><span className="w-24 text-muted-foreground">Run job</span>
            <Button size="sm" onClick={() => void platform.dev.runLifecycle().then(async (r) => { await refresh(); toast.success('Lifecycle job ran', { description: JSON.stringify(r.stats) }); void loadOutbound(); }).catch((e) => toast.error(describeError(e)))}>Run lifecycle job now</Button>
            <Button size="sm" variant="outline" onClick={() => void loadOutbound()}>Show outbound emails</Button>
          </div>
          {outbound && (
            <div className="rounded-[5px] border text-[12px]">
              <div className="border-b bg-secondary/50 px-3 py-1.5 font-medium">Outbound emails · {outbound.length} {outbound.some((m) => m.status === 'skipped') && <span className="ml-2 font-normal text-muted-foreground">(delivery is off outside production — set EMAIL_DELIVERY_ENABLED=true to send)</span>}</div>
              <ul className="divide-y">
                {outbound.map((m) => (
                  <li key={m.id} className="px-3 py-2">
                    <details><summary className="flex cursor-pointer items-center gap-2"><span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${m.status === 'sent' ? 'bg-success-bg text-success' : m.status === 'failed' ? 'bg-error-bg text-error' : 'bg-muted text-muted-foreground'}`}>{m.status}</span><span className="font-medium">{m.subject}</span><span className="ml-auto text-muted-foreground">→ {m.to_address} · {m.template}</span></summary>
                      <pre className="mt-2 whitespace-pre-wrap rounded bg-secondary/50 p-3 font-sans text-[12px] leading-5">{m.body_text}</pre></details>
                  </li>
                ))}
                {outbound.length === 0 && <li className="px-3 py-4 text-center text-muted-foreground">Nothing queued yet.</li>}
              </ul>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Field({ id, label, defaultValue, disabled }: { id: string; label: string; defaultValue: string; disabled?: boolean }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} defaultValue={defaultValue} disabled={disabled} />
    </div>
  );
}

function Toggle({ label, desc, defaultChecked, disabled }: { label: string; desc: string; defaultChecked?: boolean; disabled?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div><div className="font-medium">{label}</div><div className="text-muted-foreground">{desc}</div></div>
      <Switch defaultChecked={defaultChecked} disabled={disabled} />
    </div>
  );
}
