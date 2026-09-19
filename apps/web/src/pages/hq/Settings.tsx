import { toast } from 'sonner';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Switch } from '@entiq/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { useSession, type LifecycleStatus } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';

export function Settings() {
  const tenant = useSession((s) => s.tenant)!;
  const simulate = useSession((s) => s.simulateTenantStatus);

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

        <section className="rounded-[6px] border border-dashed bg-card p-5">
          <h2 className="mb-1 text-[15px]">Demo controls</h2>
          <p className="mb-4 text-[13px] text-muted-foreground">Frontend-only: simulate the subscription lifecycle to see how the shell responds. Removed when billing goes live.</p>
          <div className="flex flex-wrap gap-2">
            {(['trialing', 'active', 'past_due', 'suspended', 'cancelled'] as LifecycleStatus[]).map((s) => (
              <Button key={s} size="sm" variant={tenant.status === s ? 'default' : 'outline'} onClick={() => simulate(s)}>{s.replace('_', ' ')}</Button>
            ))}
          </div>
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
