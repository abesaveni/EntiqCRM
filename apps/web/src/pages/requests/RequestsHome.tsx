import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { AlertTriangle, Inbox, Plus, Timer } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Checkbox } from '@entiq/ui/checkbox';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { Textarea } from '@entiq/ui/textarea';
import { getModule } from '@entiq/modules';
import { requests, PACK_STATUS_LABEL, PURPOSE_LABEL, packTone, type PackOut, type Purpose, type RequestsOverview, type TemplateOut, type ItemIn } from '@/api/requests';
import { crm, type ClientOut, type ContactOut } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

type View = 'open' | 'review' | 'complete';

export function RequestsHome() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [ov, setOv] = useState<RequestsOverview | null>(null);
  const [rows, setRows] = useState<PackOut[] | null>(null);
  const [view, setView] = useState<View>('open');
  const [newOpen, setNewOpen] = useState(false);
  const load = async () => {
    try { const [o, r] = await Promise.all([requests.overview(), requests.packs.list(view === 'open' ? { open: true } : view === 'review' ? { open: true } : { status: 'complete' })]); setOv(o); setRows(view === 'review' ? r.filter((p) => p.status === 'submitted' || p.status === 'reviewing') : view === 'open' ? r.filter((p) => p.status !== 'submitted' && p.status !== 'reviewing') : r); }
    catch (e) { toast.error('Could not load Requests', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('requests')) void load(); }, [view]);
  if (!entitled('requests')) return <UpsellPage module={getModule('requests')} />;
  return (
    <div className="page">
      <PageHeader eyebrow="Module 06" title="Requests" description="Adaptive checklists sent as a secure link. Clients answer, upload or mark N/A; you review exceptions only, and accepted files land on the client record."
        actions={!readOnly && can('requests:create') && <Button size="sm" onClick={() => setNewOpen(true)}><Plus className="mr-1.5 size-4" /> New request</Button>} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat icon={<Inbox className="size-4" />} label="With clients" value={ov?.awaiting_client} />
        <Stat icon={<Inbox className="size-4" />} label="To review" value={ov?.awaiting_review} warn={!!ov && ov.awaiting_review > 0} />
        <Stat icon={<AlertTriangle className="size-4" />} label="Flagged items" value={ov?.exceptions} warn={!!ov && ov.exceptions > 0} />
        <Stat icon={<Timer className="size-4" />} label="Overdue" value={ov?.overdue} warn={!!ov && ov.overdue > 0} />
        <Stat icon={<Timer className="size-4" />} label="Avg days to submit" value={ov?.avg_days_to_submit ?? undefined} />
      </div>
      <Tabs value={view} onValueChange={(v) => setView(v as View)} className="mb-3"><TabsList><TabsTrigger value="open">With client</TabsTrigger><TabsTrigger value="review">To review</TabsTrigger><TabsTrigger value="complete">Complete</TabsTrigger></TabsList></Tabs>
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <ul className="divide-y">
          {rows?.map((p) => (
            <li key={p.id}><Link to={`/requests/${p.id}`} className="flex items-center gap-3 px-5 py-3 text-[13px] hover:bg-muted/50">
              <div className="w-[56px] shrink-0"><div className="h-1.5 w-full overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${p.items_total ? (p.items_done / p.items_total) * 100 : 0}%` }} /></div><div className="mt-0.5 text-[11px] tabular-nums text-muted-foreground">{p.items_done}/{p.items_total}</div></div>
              <div className="min-w-0 flex-1"><div className="truncate font-medium">{p.title}</div><div className="truncate text-[12px] text-muted-foreground">{p.client_name} · {p.contact_name ?? 'no contact'} · {PURPOSE_LABEL[p.purpose]} · updated {formatDistanceToNow(new Date(p.updated_at), { addSuffix: true })}</div></div>
              {p.exceptions > 0 && <StatusPill tone="warn"><AlertTriangle className="size-3" /> {p.exceptions} flagged</StatusPill>}
              {p.items_uploaded > 0 && <StatusPill tone="teal">{p.items_uploaded} to review</StatusPill>}
              <span className={`w-[90px] shrink-0 text-right text-[12px] ${p.overdue ? 'font-medium text-error' : 'text-muted-foreground'}`}>{p.due_on ? `${p.overdue ? 'overdue ' : 'due '}${format(new Date(p.due_on), 'd MMM')}` : ''}</span>
              <StatusPill tone={packTone(p.status)}>{PACK_STATUS_LABEL[p.status]}</StatusPill>
            </Link></li>
          ))}
          {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Nothing here.</li>}
          {!rows && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
        </ul>
      </div>
      <NewRequestDialog open={newOpen} onOpenChange={setNewOpen} onDone={load} />
    </div>
  );
}

function Stat({ icon, label, value, warn }: { icon: React.ReactNode; label: string; value: number | undefined; warn?: boolean }) {
  return <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[24px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{value ?? '—'}</div></div>;
}

export function NewRequestDialog({ open, onOpenChange, onDone, presetClient }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void>; presetClient?: ClientOut }) {
  const [clients, setClients] = useState<ClientOut[]>([]); const [contacts, setContacts] = useState<ContactOut[]>([]); const [templates, setTemplates] = useState<TemplateOut[]>([]);
  const [f, setF] = useState({ client_id: presetClient?.id ?? '', contact_id: '', purpose: 'tax_return' as Purpose, period_label: '', message: '', due_in_days: 14, use_template: true });
  const [extra, setExtra] = useState<ItemIn[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  useEffect(() => { if (open) { void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); void requests.templates().then(setTemplates).catch(() => undefined); } }, [open]);
  useEffect(() => { if (presetClient) setF((x) => ({ ...x, client_id: presetClient.id })); }, [presetClient?.id]);
  useEffect(() => { if (f.client_id) void crm.clients.contacts(f.client_id).then((c) => { setContacts(c); const prim = c.find((x) => x.is_primary && x.email) ?? c.find((x) => x.email); setF((x) => ({ ...x, contact_id: prim?.id ?? '' })); }).catch(() => undefined); }, [f.client_id]);
  const tpl = templates.find((t) => t.purpose === f.purpose);
  const client = clients.find((c) => c.id === f.client_id) ?? presetClient;
  const submit = async () => {
    setBusy(true);
    try { const d = await requests.packs.create({ client_id: f.client_id, contact_id: f.contact_id || null, purpose: f.purpose, period_label: f.period_label || null, message: f.message || null, due_in_days: f.due_in_days, use_template: f.use_template, items: extra.filter((i) => i.label.trim()), send_now: true }); await onDone(); setResult(d.request_url); toast.success('Request sent'); }
    catch (e) { toast.error('Could not send', { description: describeError(e) }); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) { setResult(null); setExtra([]); } }}><DialogContent className="max-w-[600px]">
      <DialogHeader><DialogTitle>New request</DialogTitle></DialogHeader>
      {result ? (<div className="grid gap-3 text-[13px]"><p>Sent. The client's secure link (useful if they call and ask):</p><code className="break-all rounded-[4px] bg-muted px-2 py-1.5 font-mono text-[11px]">{result}</code><DialogFooter><Button variant="outline" onClick={() => void navigator.clipboard?.writeText(result)}>Copy link</Button><Button onClick={() => onOpenChange(false)}>Done</Button></DialogFooter></div>) : (
        <div className="grid gap-3 text-[13px]">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5"><Label>Client</Label>{presetClient ? <div className="rounded-[5px] border px-3 py-2">{presetClient.name}</div> : <Select value={f.client_id || 'none'} onValueChange={(v) => setF({ ...f, client_id: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Choose" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select>}</div>
            <div className="grid gap-1.5"><Label>Send to</Label><Select value={f.contact_id || 'none'} onValueChange={(v) => setF({ ...f, contact_id: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Contact" /></SelectTrigger><SelectContent><SelectItem value="none">Primary contact</SelectItem>{contacts.filter((c) => c.email).map((c) => <SelectItem key={c.id} value={c.id}>{c.full_name} · {c.email}</SelectItem>)}</SelectContent></Select></div>
          </div>
          <div className="grid grid-cols-[1fr_120px_110px] gap-3">
            <div className="grid gap-1.5"><Label>Purpose</Label><Select value={f.purpose} onValueChange={(v) => setF({ ...f, purpose: v as Purpose })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(Object.keys(PURPOSE_LABEL) as Purpose[]).map((p) => <SelectItem key={p} value={p}>{PURPOSE_LABEL[p]}</SelectItem>)}</SelectContent></Select></div>
            <div className="grid gap-1.5"><Label>Period</Label><Input placeholder="FY26" value={f.period_label} onChange={(e) => setF({ ...f, period_label: e.target.value })} /></div>
            <div className="grid gap-1.5"><Label>Due in (days)</Label><Input type="number" min={1} max={365} value={f.due_in_days} onChange={(e) => setF({ ...f, due_in_days: Math.max(1, Number(e.target.value) || 14) })} /></div>
          </div>
          {tpl && tpl.items.length > 0 && (
            <div className="rounded-[5px] border p-3">
              <label className="flex items-center gap-2 text-[13px]"><Checkbox checked={f.use_template} onCheckedChange={(v) => setF({ ...f, use_template: !!v })} /> Use the {tpl.label.toLowerCase()} checklist{client ? ` for a ${client.client_type}` : ''}</label>
              {f.use_template && <p className="mt-1.5 text-[12px] text-muted-foreground">{tpl.items.filter((i) => !i.conditional && (!i.entity_types.length || !client || i.entity_types.includes(client.client_type))).map((i) => i.label).join(' · ')}{tpl.questions.length ? ` · +${tpl.questions.length} adaptive question${tpl.questions.length === 1 ? '' : 's'}` : ''}</p>}
            </div>
          )}
          <div className="grid gap-1.5">
            <div className="flex items-center justify-between"><Label>Extra items</Label><Button size="sm" variant="ghost" onClick={() => setExtra((x) => [...x, { label: '', category: 'other', required: true }])}><Plus className="mr-1 size-3.5" /> Add</Button></div>
            {extra.map((i, idx) => <div key={idx} className="grid grid-cols-[1fr_130px_auto] gap-2"><Input placeholder="What do you need?" value={i.label} onChange={(e) => setExtra((x) => x.map((y, j) => (j === idx ? { ...y, label: e.target.value } : y)))} /><Select value={i.category ?? 'other'} onValueChange={(v) => setExtra((x) => x.map((y, j) => (j === idx ? { ...y, category: v as ItemIn['category'] } : y)))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{['identity', 'financial', 'tax', 'bank', 'payroll', 'legal', 'property', 'other'].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select><label className="flex items-center gap-1.5 text-[12px]"><Checkbox checked={i.required ?? true} onCheckedChange={(v) => setExtra((x) => x.map((y, j) => (j === idx ? { ...y, required: !!v } : y)))} /> required</label></div>)}
          </div>
          <div className="grid gap-1.5"><Label>Message</Label><Textarea rows={2} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} placeholder="Optional note in the email and on the request page." /></div>
          <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button disabled={!f.client_id || busy || (!f.use_template && !extra.some((i) => i.label.trim()))} onClick={() => void submit()}>{busy ? 'Sending…' : 'Send request'}</Button></DialogFooter>
        </div>
      )}
    </DialogContent></Dialog>
  );
}
