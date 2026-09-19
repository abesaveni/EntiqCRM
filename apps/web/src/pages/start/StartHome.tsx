import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { Plus, Rocket, Timer, UserCheck, Users } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule } from '@entiq/modules';
import { start, STATUS_LABEL, onboardingTone, type OnboardingOut, type StartOverview, type EntityType } from '@/api/start';
import { crm, CLIENT_TYPES, type ClientOut } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

type View = 'open' | 'activated' | 'withdrawn';

export function StartHome() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [ov, setOv] = useState<StartOverview | null>(null);
  const [rows, setRows] = useState<OnboardingOut[] | null>(null);
  const [view, setView] = useState<View>('open');
  const [newOpen, setNewOpen] = useState(false);

  const load = async () => {
    try { const [o, r] = await Promise.all([start.overview(), start.onboardings.list(view === 'open' ? {} : { status: view })]); setOv(o); setRows(r); }
    catch (e) { toast.error('Could not load Start', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('start')) void load(); }, [view]);
  if (!entitled('start')) return <UpsellPage module={getModule('start')} />;

  return (
    <div className="page">
      <PageHeader eyebrow="Module 03" title="Start" description="Prospect to activated client in 11 server-enforced stages: the prospect does stages 1–7 from a magic link, the practice does 8–11."
        actions={!readOnly && can('start:invite') && <Button size="sm" onClick={() => setNewOpen(true)}><Plus className="mr-1.5 size-4" /> New onboarding</Button>} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat icon={<Rocket className="size-4" />} label="In flight" value={ov?.active} />
        <Stat icon={<Users className="size-4" />} label="With the prospect" value={ov?.awaiting_prospect} />
        <Stat icon={<UserCheck className="size-4" />} label="Waiting on us" value={ov?.awaiting_practice} warn={!!ov && ov.awaiting_practice > 0} />
        <Stat icon={<Rocket className="size-4" />} label="Activated · 30d" value={ov?.activated_30d} />
        <Stat icon={<Timer className="size-4" />} label="Median days to activate" value={ov?.median_days_to_activate ?? undefined} />
      </div>
      {ov && Object.keys(ov.by_stage).length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5 text-[12px]">{Object.entries(ov.by_stage).map(([k, v]) => <span key={k} className="rounded-[4px] border bg-card px-2 py-0.5">{k} <span className="font-medium tabular-nums">{v}</span></span>)}</div>
      )}
      <Tabs value={view} onValueChange={(v) => setView(v as View)} className="mb-3"><TabsList><TabsTrigger value="open">Open</TabsTrigger><TabsTrigger value="activated">Activated</TabsTrigger><TabsTrigger value="withdrawn">Withdrawn</TabsTrigger></TabsList></Tabs>
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <ul className="divide-y">
          {rows?.map((o) => (
            <li key={o.id}>
              <Link to={`/start/onboardings/${o.id}`} className="flex items-center gap-3 px-5 py-3 text-[13px] hover:bg-muted/50">
                <div className="w-[64px] shrink-0"><div className="h-1.5 w-full overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${o.progress_pct}%` }} /></div><div className="mt-0.5 text-[11px] tabular-nums text-muted-foreground">stage {o.current_stage}/11</div></div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{o.client_name} <span className="font-normal text-muted-foreground">· {o.client_type}</span></div>
                  <div className="truncate text-[12px] text-muted-foreground">{o.primary_contact_name ?? 'No contact'}{o.primary_contact_email ? ` <${o.primary_contact_email}>` : ''} · {o.owner_name ?? 'Unowned'} · updated {formatDistanceToNow(new Date(o.updated_at), { addSuffix: true })}</div>
                </div>
                {o.proposal_total_cents != null && <span className="hidden text-[12px] tabular-nums text-muted-foreground sm:inline">${(o.proposal_total_cents / 100).toLocaleString('en-AU', { minimumFractionDigits: 0 })} inc GST</span>}
                <StatusPill tone={onboardingTone(o.status)}>{STATUS_LABEL[o.status]}</StatusPill>
              </Link>
            </li>
          ))}
          {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">{view === 'open' ? 'No onboardings in flight. Invite a prospect to begin.' : 'Nothing here yet.'}</li>}
          {!rows && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
        </ul>
      </div>
      <NewOnboardingDialog open={newOpen} onOpenChange={setNewOpen} onDone={load} />
    </div>
  );
}

function Stat({ icon, label, value, warn }: { icon: React.ReactNode; label: string; value: number | undefined; warn?: boolean }) {
  return (
    <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}>
      <div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div>
      <div className={`text-[24px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{value ?? '—'}</div>
    </div>
  );
}

export function NewOnboardingDialog({ open, onOpenChange, onDone, presetClient }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void>; presetClient?: ClientOut }) {
  const [mode, setMode] = useState<'new' | 'existing'>(presetClient ? 'existing' : 'new');
  const [clients, setClients] = useState<ClientOut[]>([]);
  const [clientId, setClientId] = useState(presetClient?.id ?? '');
  const [name, setName] = useState(''); const [type, setType] = useState<EntityType>('Company'); const [first, setFirst] = useState(''); const [last, setLast] = useState(''); const [email, setEmail] = useState('');
  const [send, setSend] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  useEffect(() => { if (open && !presetClient) void crm.clients.list({ size: 200, stage: 'Lead' }).then((p) => setClients(p.items)).catch(() => undefined); }, [open]);
  useEffect(() => { if (presetClient) { setClientId(presetClient.id); setMode('existing'); } }, [presetClient?.id]);

  const submit = async () => {
    setBusy(true);
    try {
      const d = mode === 'existing' ? await start.onboardings.create({ client_id: clientId, send_invitation: send }) : await start.onboardings.create({ prospect_name: name.trim(), entity_type: type, contact_first_name: first.trim(), contact_last_name: last.trim() || null, contact_email: email.trim(), send_invitation: send });
      await onDone();
      if (d.invite_url) { setResult(d.invite_url); toast.success('Invitation sent'); } else { toast.success('Onboarding created'); onOpenChange(false); }
    } catch (e) { toast.error('Could not start onboarding', { description: describeError(e) }); } finally { setBusy(false); }
  };
  const valid = mode === 'existing' ? !!clientId : name.trim() && first.trim() && /\S+@\S+\.\S+/.test(email);
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) setResult(null); }}><DialogContent className="max-w-[540px]">
      <DialogHeader><DialogTitle>New onboarding</DialogTitle></DialogHeader>
      {result ? (
        <div className="grid gap-3 text-[13px]">
          <p>The invitation email is queued. The prospect's magic link (also useful for a walk-in on a tablet):</p>
          <code className="break-all rounded-[4px] bg-muted px-2 py-1.5 font-mono text-[11px]">{result}</code>
          <DialogFooter><Button variant="outline" onClick={() => void navigator.clipboard?.writeText(result)}>Copy link</Button><Button onClick={() => onOpenChange(false)}>Done</Button></DialogFooter>
        </div>
      ) : (
        <div className="grid gap-3 text-[13px]">
          {!presetClient && <Tabs value={mode} onValueChange={(v) => setMode(v as typeof mode)}><TabsList className="grid w-full grid-cols-2"><TabsTrigger value="new">New prospect</TabsTrigger><TabsTrigger value="existing">Existing lead</TabsTrigger></TabsList></Tabs>}
          {mode === 'existing' ? (
            <div className="grid gap-1.5"><Label>Client</Label>{presetClient ? <div className="rounded-[5px] border px-3 py-2">{presetClient.name}</div> : <Select value={clientId || 'none'} onValueChange={(v) => setClientId(v === 'none' ? '' : v)}><SelectTrigger><SelectValue placeholder="Choose a lead" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select>}<p className="text-[12px] text-muted-foreground">The invitation goes to the client's primary contact email.</p></div>
          ) : (<>
            <div className="grid grid-cols-[1fr_140px] gap-3">
              <div className="grid gap-1.5"><Label htmlFor="no-name">Prospect / entity name</Label><Input id="no-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus /></div>
              <div className="grid gap-1.5"><Label>Type</Label><Select value={type} onValueChange={(v) => setType(v as EntityType)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{CLIENT_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5"><Label htmlFor="no-first">Contact first name</Label><Input id="no-first" value={first} onChange={(e) => setFirst(e.target.value)} /></div>
              <div className="grid gap-1.5"><Label htmlFor="no-last">Last name</Label><Input id="no-last" value={last} onChange={(e) => setLast(e.target.value)} /></div>
            </div>
            <div className="grid gap-1.5"><Label htmlFor="no-email">Contact email</Label><Input id="no-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} /></div>
          </>)}
          <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" className="accent-primary" checked={send} onChange={(e) => setSend(e.target.checked)} /> Send the invitation email now</label>
          <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button onClick={() => void submit()} disabled={!valid || busy}>{busy ? 'Creating…' : send ? 'Create & invite' : 'Create draft'}</Button></DialogFooter>
        </div>
      )}
    </DialogContent></Dialog>
  );
}
