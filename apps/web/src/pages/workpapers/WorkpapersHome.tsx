import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { AlertTriangle, BookOpenCheck, FileCheck2, Plug, Plus } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule } from '@entiq/modules';
import { workpapers, PACK_TYPE_LABEL, WP_STATUS_LABEL, wpTone, type PackOut, type PackType, type WpOverview, type LedgerConnectionOut } from '@/api/workpapers';
import { crm, type ClientOut, type StaffOut } from '@/api/crm';
import { fmtCents } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

type View = 'open' | 'review' | 'signed_off' | 'lodged';

export function WorkpapersHome() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [ov, setOv] = useState<WpOverview | null>(null);
  const [rows, setRows] = useState<PackOut[] | null>(null);
  const [conns, setConns] = useState<LedgerConnectionOut[]>([]);
  const [view, setView] = useState<View>('open');
  const [newOpen, setNewOpen] = useState(false);
  const [connOpen, setConnOpen] = useState(false);

  const load = async () => {
    try {
      const [o, r, c] = await Promise.all([workpapers.overview(), workpapers.packs.list(view === 'open' ? { open: true } : { status: view === 'review' ? 'in_review' : view }), workpapers.ledger.connections()]);
      setOv(o); setRows(view === 'open' ? r.filter((p) => p.status !== 'in_review') : r); setConns(c);
    } catch (e) { toast.error('Could not load Workpapers', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('workpapers')) void load(); }, [view]);
  if (!entitled('workpapers')) return <UpsellPage module={getModule('workpapers')} />;

  return (
    <div className="page">
      <PageHeader eyebrow="Module 08" title="Workpapers" description="Prepare, review and sign off with the evidence attached. Figures come from the ledger; the rules flag material movements and missing evidence before anyone signs."
        actions={!readOnly && can('wp:prepare') && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setConnOpen(true)}><Plug className="mr-1.5 size-4" /> Ledger</Button><Button size="sm" onClick={() => setNewOpen(true)}><Plus className="mr-1.5 size-4" /> New pack</Button></div>} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat icon={<BookOpenCheck className="size-4" />} label="In progress" value={ov?.in_progress} />
        <Stat icon={<FileCheck2 className="size-4" />} label="In review" value={ov?.in_review} />
        <Stat icon={<AlertTriangle className="size-4" />} label="Blocking issues" value={ov?.blocking_issues} warn={!!ov && ov.blocking_issues > 0} />
        <Stat icon={<FileCheck2 className="size-4" />} label="Signed off · 30d" value={ov?.signed_off_30d} />
        <Stat icon={<FileCheck2 className="size-4" />} label="Lodged · 30d" value={ov?.lodged_30d} />
      </div>
      {ov && !ov.ledger_live && <p className="mb-4 rounded-[5px] border border-warn/50 bg-warn-bg/40 px-3 py-2 text-[12px]">No Xero credentials are configured, so ledger syncs use the simulation driver. Every figure it produces is labelled <em>simulated</em> on the pack and in Advisory.</p>}
      <Tabs value={view} onValueChange={(v) => setView(v as View)} className="mb-3"><TabsList><TabsTrigger value="open">In progress</TabsTrigger><TabsTrigger value="review">In review</TabsTrigger><TabsTrigger value="signed_off">Signed off</TabsTrigger><TabsTrigger value="lodged">Lodged</TabsTrigger></TabsList></Tabs>
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <ul className="divide-y">
          {rows?.map((p) => (
            <li key={p.id}><Link to={`/workpapers/${p.id}`} className="flex items-center gap-3 px-5 py-3 text-[13px] hover:bg-muted/50">
              <div className="w-[56px] shrink-0"><div className="h-1.5 w-full overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${p.items_total ? (p.items_done / p.items_total) * 100 : 0}%` }} /></div><div className="mt-0.5 text-[11px] tabular-nums text-muted-foreground">{p.items_done}/{p.items_total}</div></div>
              <div className="min-w-0 flex-1"><div className="truncate font-medium">{p.title}</div><div className="truncate text-[12px] text-muted-foreground">{p.client_name} · {PACK_TYPE_LABEL[p.pack_type]} · {p.preparer_name ?? 'unassigned'}{p.ledger_synced_at ? ` · ledger ${formatDistanceToNow(new Date(p.ledger_synced_at), { addSuffix: true })}${p.ledger_simulated ? ' (sim)' : ''}` : ' · no ledger sync'}</div></div>
              {p.blocking_issues > 0 && <StatusPill tone="error"><AlertTriangle className="size-3" /> {p.blocking_issues}</StatusPill>}
              {p.open_issues > p.blocking_issues && <StatusPill tone="warn">{p.open_issues - p.blocking_issues} to review</StatusPill>}
              <StatusPill tone={wpTone(p.status)}>{WP_STATUS_LABEL[p.status]}</StatusPill>
            </Link></li>
          ))}
          {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Nothing here.</li>}
          {!rows && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
        </ul>
      </div>
      <NewPackDialog open={newOpen} onOpenChange={setNewOpen} onDone={load} />
      <LedgerDialog open={connOpen} onOpenChange={setConnOpen} connections={conns} onDone={load} />
    </div>
  );
}

function Stat({ icon, label, value, warn }: { icon: React.ReactNode; label: string; value: number | undefined; warn?: boolean }) {
  return <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[24px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{value ?? '—'}</div></div>;
}

export function NewPackDialog({ open, onOpenChange, onDone, presetClient }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void>; presetClient?: ClientOut }) {
  const [clients, setClients] = useState<ClientOut[]>([]); const [staff, setStaff] = useState<StaffOut[]>([]);
  const [f, setF] = useState({ client_id: presetClient?.id ?? '', pack_type: 'financial_statements' as PackType, period_label: '', period_end: '', reviewer: '', materiality: '5000' });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); void crm.staff().then(setStaff).catch(() => undefined); } }, [open]);
  useEffect(() => { if (presetClient) setF((x) => ({ ...x, client_id: presetClient.id })); }, [presetClient?.id]);
  const submit = async () => {
    setBusy(true);
    try { await workpapers.packs.create({ client_id: f.client_id, pack_type: f.pack_type, period_label: f.period_label || null, period_end: f.period_end || null, reviewer_membership_id: f.reviewer || null, materiality_cents: Math.round(Number(f.materiality || 1000) * 100) }); toast.success('Pack created'); await onDone(); onOpenChange(false); }
    catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[540px]">
      <DialogHeader><DialogTitle>New workpaper pack</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5"><Label>Client</Label>{presetClient ? <div className="rounded-[5px] border px-3 py-2">{presetClient.name}</div> : <Select value={f.client_id || 'none'} onValueChange={(v) => setF({ ...f, client_id: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Choose" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select>}</div>
          <div className="grid gap-1.5"><Label>Type</Label><Select value={f.pack_type} onValueChange={(v) => setF({ ...f, pack_type: v as PackType })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(Object.keys(PACK_TYPE_LABEL) as PackType[]).map((t) => <SelectItem key={t} value={t}>{PACK_TYPE_LABEL[t]}</SelectItem>)}</SelectContent></Select></div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="grid gap-1.5"><Label>Period</Label><Input placeholder="FY26" value={f.period_label} onChange={(e) => setF({ ...f, period_label: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label>Period end</Label><Input type="date" value={f.period_end} onChange={(e) => setF({ ...f, period_end: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label>Materiality ($)</Label><Input type="number" min={0} value={f.materiality} onChange={(e) => setF({ ...f, materiality: e.target.value })} /></div>
        </div>
        <div className="grid gap-1.5"><Label>Reviewer</Label><Select value={f.reviewer || 'none'} onValueChange={(v) => setF({ ...f, reviewer: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Unassigned" /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{staff.map((s) => <SelectItem key={s.membership_id} value={s.membership_id}>{s.name}</SelectItem>)}</SelectContent></Select></div>
        <p className="text-[12px] text-muted-foreground">The standard checklist for this pack type is added automatically; sync the ledger to bring in the trial balance.</p>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button disabled={!f.client_id || busy} onClick={() => void submit()}>Create pack</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function LedgerDialog({ open, onOpenChange, connections, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; connections: LedgerConnectionOut[]; onDone: () => Promise<void> }) {
  const [clients, setClients] = useState<ClientOut[]>([]);
  const [clientId, setClientId] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); }, [open]);
  const connect = async () => {
    setBusy(true);
    try { const r = await workpapers.ledger.connect(clientId); toast.success(r.message); if (r.authorize_url) window.open(r.authorize_url, '_blank'); await onDone(); }
    catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[560px]">
      <DialogHeader><DialogTitle>Ledger connections</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <ul className="divide-y rounded-[5px] border">
          {connections.map((c) => <li key={c.id} className="flex items-center gap-3 px-3 py-2"><div className="min-w-0 flex-1"><div className="truncate font-medium">{c.client_name}</div><div className="text-[12px] text-muted-foreground">{c.provider} · {c.external_name ?? c.status}{c.last_sync_at ? ` · synced ${format(new Date(c.last_sync_at), 'd MMM HH:mm')}` : ''}</div></div><StatusPill tone={c.simulated ? 'neutral' : c.status === 'connected' ? 'success' : 'warn'}>{c.simulated ? 'simulated' : c.status}</StatusPill></li>)}
          {connections.length === 0 && <li className="px-3 py-6 text-center text-muted-foreground">No ledgers connected.</li>}
        </ul>
        <div className="grid gap-1.5"><Label>Connect a client's ledger</Label><Select value={clientId || 'none'} onValueChange={(v) => setClientId(v === 'none' ? '' : v)}><SelectTrigger><SelectValue placeholder="Choose a client" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
        <p className="text-[12px] text-muted-foreground">Xero is the live target. Until its credentials are configured in Practice HQ → Integrations, connections run in simulation and produce a coherent but generated trial balance.</p>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button><Button disabled={!clientId || busy} onClick={() => void connect()}>Connect</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
