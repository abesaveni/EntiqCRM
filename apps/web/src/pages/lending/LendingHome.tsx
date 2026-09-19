import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { Banknote, CheckCircle2, ClipboardList, Plus, Timer } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Textarea } from '@entiq/ui/textarea';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule } from '@entiq/modules';
import { lending, PIPELINE, PURPOSE_LABEL, STAGE_LABEL, stageTone, type ApplicationOut, type LendingOverview, type LendingPurpose } from '@/api/lending';
import { crm, type ClientOut, type ContactOut } from '@/api/crm';
import { fmtCents } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

export function LendingHome() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [ov, setOv] = useState<LendingOverview | null>(null);
  const [rows, setRows] = useState<ApplicationOut[] | null>(null);
  const [view, setView] = useState<'pipeline' | 'all'>('pipeline');
  const [newOpen, setNewOpen] = useState(false);
  const load = async () => {
    try { const [o, r] = await Promise.all([lending.overview(), lending.applications.list(view === 'pipeline' ? { open: true } : {})]); setOv(o); setRows(r); }
    catch (e) { toast.error('Could not load Lending', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('lending')) void load(); }, [view]);
  if (!entitled('lending')) return <UpsellPage module={getModule('lending')} />;

  return (
    <div className="page">
      <PageHeader eyebrow="Module 20" title="Lending" description="Finance enquiries from first conversation to settlement: the client's documents come through Requests, serviceability from Advisory, and conditions gate the settlement."
        actions={!readOnly && can('lending:intake') && <Button size="sm" onClick={() => setNewOpen(true)}><Plus className="mr-1.5 size-4" /> New application</Button>} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat icon={<Banknote className="size-4" />} label="Active" value={ov?.active} />
        <Stat icon={<Banknote className="size-4" />} label="Pipeline value" text={ov ? fmtCents(ov.pipeline_value_cents) : undefined} />
        <Stat icon={<Timer className="size-4" />} label="With the client" value={ov?.awaiting_client} warn={!!ov && ov.awaiting_client > 0} />
        <Stat icon={<ClipboardList className="size-4" />} label="Open conditions" value={ov?.conditions_open} />
        <Stat icon={<CheckCircle2 className="size-4" />} label="Settled · 90d" text={ov ? `${ov.settled_90d} · ${fmtCents(ov.settled_value_90d_cents)}` : undefined} />
      </div>
      <Tabs value={view} onValueChange={(v) => setView(v as typeof view)} className="mb-3"><TabsList><TabsTrigger value="pipeline">Pipeline</TabsTrigger><TabsTrigger value="all">All applications</TabsTrigger></TabsList></Tabs>

      {view === 'pipeline' ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-4 xl:grid-cols-7">
          {PIPELINE.map((st) => {
            const inStage = (rows ?? []).filter((a) => a.stage === st);
            return (
              <div key={st} className="rounded-[6px] border bg-card p-2">
                <div className="mb-2 flex items-center justify-between px-1 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{STAGE_LABEL[st]}<span className="tabular-nums">{inStage.length}</span></div>
                <ul className="space-y-1.5">
                  {inStage.map((a) => (
                    <li key={a.id}><Link to={`/lending/${a.id}`} className="block rounded-[5px] border p-2 text-[12px] hover:bg-muted/50">
                      <div className="truncate font-medium">{a.client_name}</div>
                      <div className="truncate text-muted-foreground">{fmtCents(a.amount_cents)} · {PURPOSE_LABEL[a.purpose]}</div>
                      <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${a.readiness_pct}%` }} /></div>
                    </Link></li>
                  ))}
                  {inStage.length === 0 && <li className="px-1 py-3 text-center text-[11px] text-muted-foreground">—</li>}
                </ul>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="overflow-hidden rounded-[6px] border bg-card">
          <ul className="divide-y">
            {rows?.map((a) => (
              <li key={a.id}><Link to={`/lending/${a.id}`} className="flex items-center gap-3 px-5 py-3 text-[13px] hover:bg-muted/50">
                <Banknote className="size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1"><div className="truncate font-medium">{a.reference} · {a.client_name}</div><div className="truncate text-[12px] text-muted-foreground">{fmtCents(a.amount_cents)} {PURPOSE_LABEL[a.purpose]}{a.lender ? ` · ${a.lender}` : ''}{a.dscr ? ` · DSCR ${a.dscr}` : ''} · updated {formatDistanceToNow(new Date(a.updated_at), { addSuffix: true })}</div></div>
                {a.conditions_blocking > 0 && <StatusPill tone="warn">{a.conditions_blocking} conditions</StatusPill>}
                <span className="hidden w-[70px] text-right text-[12px] tabular-nums text-muted-foreground sm:inline">{a.readiness_pct}% ready</span>
                <StatusPill tone={stageTone(a.stage)}>{STAGE_LABEL[a.stage]}</StatusPill>
              </Link></li>
            ))}
            {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">No applications yet.</li>}
          </ul>
        </div>
      )}
      <NewApplicationDialog open={newOpen} onOpenChange={setNewOpen} onDone={load} />
    </div>
  );
}

function Stat({ icon, label, value, text, warn }: { icon: React.ReactNode; label: string; value?: number; text?: string; warn?: boolean }) {
  return <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[20px] font-semibold tabular-nums leading-tight ${warn ? 'text-warn' : ''}`}>{text ?? value ?? '—'}</div></div>;
}

export function NewApplicationDialog({ open, onOpenChange, onDone, presetClient }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void>; presetClient?: ClientOut }) {
  const entitled = useSession((s) => s.entitled);
  const [clients, setClients] = useState<ClientOut[]>([]); const [contacts, setContacts] = useState<ContactOut[]>([]);
  const [f, setF] = useState({ client_id: presetClient?.id ?? '', contact_id: '', purpose: 'equipment' as LendingPurpose, amount: '', term: '60', rate: '8.90', lender: '', description: '', send_request: true });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); }, [open]);
  useEffect(() => { if (presetClient) setF((x) => ({ ...x, client_id: presetClient.id })); }, [presetClient?.id]);
  useEffect(() => { if (f.client_id) void crm.clients.contacts(f.client_id).then((c) => { setContacts(c); const p = c.find((x) => x.is_primary && x.email) ?? c.find((x) => x.email); setF((x) => ({ ...x, contact_id: p?.id ?? '' })); }).catch(() => undefined); }, [f.client_id]);
  const submit = async () => {
    setBusy(true);
    try {
      await lending.applications.create({ client_id: f.client_id, contact_id: f.contact_id || null, purpose: f.purpose, amount_cents: Math.round(Number(f.amount || 0) * 100), term_months: Number(f.term) || null,
                                          rate_bps: f.rate ? Math.round(Number(f.rate) * 100) : null, lender: f.lender || null, description: f.description || null, send_request: f.send_request && entitled('requests') });
      toast.success('Application created'); await onDone(); onOpenChange(false);
    } catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[560px]">
      <DialogHeader><DialogTitle>New finance application</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5"><Label>Client</Label>{presetClient ? <div className="rounded-[5px] border px-3 py-2">{presetClient.name}</div> : <Select value={f.client_id || 'none'} onValueChange={(v) => setF({ ...f, client_id: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Choose" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select>}</div>
          <div className="grid gap-1.5"><Label>Contact</Label><Select value={f.contact_id || 'none'} onValueChange={(v) => setF({ ...f, contact_id: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Primary" /></SelectTrigger><SelectContent><SelectItem value="none">Primary contact</SelectItem>{contacts.filter((c) => c.email).map((c) => <SelectItem key={c.id} value={c.id}>{c.full_name}</SelectItem>)}</SelectContent></Select></div>
        </div>
        <div className="grid grid-cols-4 gap-3">
          <div className="grid gap-1.5"><Label>Purpose</Label><Select value={f.purpose} onValueChange={(v) => setF({ ...f, purpose: v as LendingPurpose })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(Object.keys(PURPOSE_LABEL) as LendingPurpose[]).map((p) => <SelectItem key={p} value={p}>{PURPOSE_LABEL[p]}</SelectItem>)}</SelectContent></Select></div>
          <div className="grid gap-1.5"><Label>Amount ($)</Label><Input type="number" min={0} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label>Term (months)</Label><Input type="number" min={1} value={f.term} onChange={(e) => setF({ ...f, term: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label>Rate (%)</Label><Input type="number" step="0.01" value={f.rate} onChange={(e) => setF({ ...f, rate: e.target.value })} /></div>
        </div>
        <div className="grid gap-1.5"><Label>Lender</Label><Input value={f.lender} onChange={(e) => setF({ ...f, lender: e.target.value })} placeholder="Who you expect to place it with" /></div>
        <div className="grid gap-1.5"><Label>What is being financed</Label><Textarea rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
        <label className={`flex items-center gap-2 ${entitled('requests') ? '' : 'opacity-60'}`}><input type="checkbox" className="accent-primary" checked={f.send_request && entitled('requests')} disabled={!entitled('requests')} onChange={(e) => setF({ ...f, send_request: e.target.checked })} /> Send the lending document checklist now{!entitled('requests') && ' (needs the Requests module)'}</label>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button disabled={!f.client_id || !Number(f.amount) || busy} onClick={() => void submit()}>Create</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
