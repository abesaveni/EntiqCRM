import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { AlertTriangle, Banknote, Plus, Receipt, Repeat, Trash2 } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { Textarea } from '@entiq/ui/textarea';
import { getModule } from '@entiq/modules';
import { practiceBilling, INVOICE_STATUS_LABEL, invoiceTone, type BillingOverview, type InvoiceOut, type LineIn, type ScheduleOut } from '@/api/practiceBilling';
import { crm, type ClientOut, type ContactOut } from '@/api/crm';
import { fmtCents } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

type View = 'unpaid' | 'all' | 'recurring' | 'aged';

export function PracticeBillingHome() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [ov, setOv] = useState<BillingOverview | null>(null);
  const [rows, setRows] = useState<InvoiceOut[] | null>(null);
  const [scheds, setScheds] = useState<ScheduleOut[]>([]);
  const [view, setView] = useState<View>('unpaid');
  const [newOpen, setNewOpen] = useState(false);
  const [schedOpen, setSchedOpen] = useState(false);

  const load = async () => {
    try {
      const [o, i, s] = await Promise.all([practiceBilling.overview(), practiceBilling.invoices.list(view === 'unpaid' ? { unpaid: true } : {}), practiceBilling.schedules.list()]);
      setOv(o); setRows(i); setScheds(s);
    } catch (e) { toast.error('Could not load Billing', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('billing')) void load(); }, [view]);
  if (!entitled('billing')) return <UpsellPage module={getModule('billing')} />;

  return (
    <div className="page">
      <PageHeader eyebrow="Module 19" title="Billing" description="What your clients owe you: invoices, payments, recurring fees from the engagement, and an aged view that says who to call."
        actions={!readOnly && can('billing:invoice') && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setSchedOpen(true)}><Repeat className="mr-1.5 size-4" /> Recurring fee</Button><Button size="sm" onClick={() => setNewOpen(true)}><Plus className="mr-1.5 size-4" /> New invoice</Button></div>} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat icon={<Banknote className="size-4" />} label="Outstanding" text={ov ? fmtCents(ov.outstanding_cents) : undefined} />
        <Stat icon={<AlertTriangle className="size-4" />} label="Overdue" text={ov ? fmtCents(ov.overdue_cents) : undefined} warn={!!ov && ov.overdue_cents > 0} />
        <Stat icon={<Receipt className="size-4" />} label="Invoiced · 30d" text={ov ? fmtCents(ov.invoiced_30d_cents) : undefined} />
        <Stat icon={<Banknote className="size-4" />} label="Collected · 30d" text={ov ? fmtCents(ov.paid_30d_cents) : undefined} />
        <Stat icon={<Repeat className="size-4" />} label="Recurring / year" text={ov ? fmtCents(ov.recurring_annualised_cents) : undefined} />
      </div>
      <Tabs value={view} onValueChange={(v) => setView(v as View)} className="mb-3"><TabsList><TabsTrigger value="unpaid">Unpaid</TabsTrigger><TabsTrigger value="all">All invoices</TabsTrigger><TabsTrigger value="recurring">Recurring</TabsTrigger><TabsTrigger value="aged">Aged</TabsTrigger></TabsList></Tabs>

      {(view === 'unpaid' || view === 'all') && (
        <div className="overflow-hidden rounded-[6px] border bg-card">
          <ul className="divide-y">
            {rows?.map((i) => (
              <li key={i.id}><Link to={`/billing/invoices/${i.id}`} className="flex items-center gap-3 px-5 py-2.5 text-[13px] hover:bg-muted/50">
                <Receipt className="size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1"><div className="truncate font-medium">{i.number} · {i.client_name}</div><div className="truncate text-[12px] text-muted-foreground">{i.period_label ? `${i.period_label} · ` : ''}issued {i.issued_on ? format(new Date(i.issued_on), 'd MMM yyyy') : '—'}{i.due_on ? ` · due ${format(new Date(i.due_on), 'd MMM')}` : ''}{i.reminders_sent ? ` · ${i.reminders_sent} reminder(s)` : ''}</div></div>
                {i.days_overdue > 0 && <StatusPill tone="error">{i.days_overdue}d overdue</StatusPill>}
                <span className="w-[110px] shrink-0 text-right tabular-nums">{fmtCents(i.total_cents)}</span>
                <span className="hidden w-[110px] shrink-0 text-right tabular-nums text-muted-foreground sm:inline">{i.balance_cents ? `${fmtCents(i.balance_cents)} due` : 'paid'}</span>
                <StatusPill tone={invoiceTone(i.status)}>{INVOICE_STATUS_LABEL[i.status]}</StatusPill>
              </Link></li>
            ))}
            {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">{view === 'unpaid' ? 'Nothing outstanding.' : 'No invoices yet.'}</li>}
          </ul>
        </div>
      )}

      {view === 'recurring' && (
        <div className="overflow-hidden rounded-[6px] border bg-card">
          <ul className="divide-y">
            {scheds.map((s) => (
              <li key={s.id} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
                <Repeat className="size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1"><div className="truncate font-medium">{s.name} <span className="font-normal text-muted-foreground">· <Link to={`/clients/${s.client_id}`} className="hover:underline">{s.client_name}</Link></span></div><div className="text-[12px] text-muted-foreground">{fmtCents(s.total_cents)} {s.frequency} · next {s.next_issue_on ? format(new Date(s.next_issue_on), 'd MMM yyyy') : '—'} · {fmtCents(s.annualised_cents)}/year{s.source === 'start' ? ' · from onboarding' : ''}</div></div>
                <StatusPill tone={s.is_active ? 'success' : 'neutral'}>{s.is_active ? 'active' : 'paused'}</StatusPill>
                {!readOnly && can('billing:invoice') && <Button size="sm" variant="ghost" onClick={() => void practiceBilling.schedules.toggle(s.id).then(load)}>{s.is_active ? 'Pause' : 'Resume'}</Button>}
              </li>
            ))}
            {scheds.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">No recurring fees. They are created automatically when a client is activated through Start.</li>}
            {scheds.length > 0 && !readOnly && can('billing:invoice') && <li className="flex items-center justify-between px-5 py-2 text-[12px] text-muted-foreground"><span>Invoices are raised on each schedule's day.</span><Button size="sm" variant="ghost" onClick={() => void practiceBilling.schedules.generate(false).then((r) => { toast.success(`${r.created} invoice(s) raised`); void load(); })}>Raise due now</Button></li>}
          </ul>
        </div>
      )}

      {view === 'aged' && (
        <div className="overflow-hidden rounded-[6px] border bg-card">
          <table className="w-full text-[13px]">
            <thead className="bg-muted/60 text-left text-[11px] uppercase tracking-[0.08em] text-muted-foreground"><tr><th className="px-5 py-2 font-medium">Client</th><th className="px-2 py-2 text-right font-medium">Current</th><th className="px-2 py-2 text-right font-medium">1–30</th><th className="px-2 py-2 text-right font-medium">31–60</th><th className="px-2 py-2 text-right font-medium">60+</th><th className="px-2 py-2 text-right font-medium">Total</th></tr></thead>
            <tbody className="divide-y">
              {ov?.aged.map((r) => (
                <tr key={r.client_id}>
                  <td className="px-5 py-2"><Link to={`/clients/${r.client_id}`} className="font-medium hover:underline">{r.client_name}</Link>{r.oldest_days > 0 && <span className="ml-2 text-[12px] text-muted-foreground">oldest {r.oldest_days}d</span>}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{r.current_cents ? fmtCents(r.current_cents) : '—'}</td>
                  <td className="px-2 py-2 text-right tabular-nums">{r.d30_cents ? fmtCents(r.d30_cents) : '—'}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-warn">{r.d60_cents ? fmtCents(r.d60_cents) : '—'}</td>
                  <td className="px-2 py-2 text-right tabular-nums text-error">{r.d90_cents ? fmtCents(r.d90_cents) : '—'}</td>
                  <td className="px-2 py-2 text-right font-medium tabular-nums">{fmtCents(r.total_cents)}</td>
                </tr>
              ))}
              {ov && ov.aged.length === 0 && <tr><td colSpan={6} className="px-5 py-10 text-center text-muted-foreground">Nothing outstanding.</td></tr>}
            </tbody>
          </table>
          {ov?.avg_days_to_pay != null && <p className="border-t px-5 py-2 text-[12px] text-muted-foreground">Clients pay in {ov.avg_days_to_pay} days on average.</p>}
        </div>
      )}

      <NewInvoiceDialog open={newOpen} onOpenChange={setNewOpen} onDone={load} />
      <NewScheduleDialog open={schedOpen} onOpenChange={setSchedOpen} onDone={load} />
    </div>
  );
}

function Stat({ icon, label, value, text, warn }: { icon: React.ReactNode; label: string; value?: number; text?: string; warn?: boolean }) {
  return <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[20px] font-semibold tabular-nums leading-tight ${warn ? 'text-warn' : ''}`}>{text ?? value ?? '—'}</div></div>;
}

export function NewInvoiceDialog({ open, onOpenChange, onDone, presetClient }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void>; presetClient?: ClientOut }) {
  const [clients, setClients] = useState<ClientOut[]>([]); const [contacts, setContacts] = useState<ContactOut[]>([]);
  const [clientId, setClientId] = useState(presetClient?.id ?? '');
  const [contactId, setContactId] = useState('');
  const [period, setPeriod] = useState('');
  const [terms, setTerms] = useState(14);
  const [notes, setNotes] = useState('');
  const [send, setSend] = useState(true);
  const [lines, setLines] = useState<Array<{ description: string; quantity: string; unit: string; gst: boolean }>>([{ description: '', quantity: '1', unit: '', gst: true }]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); }, [open]);
  useEffect(() => { if (presetClient) setClientId(presetClient.id); }, [presetClient?.id]);
  useEffect(() => { if (clientId) void crm.clients.contacts(clientId).then((c) => { setContacts(c); const p = c.find((x) => x.is_primary && x.email) ?? c.find((x) => x.email); setContactId(p?.id ?? ''); }).catch(() => undefined); }, [clientId]);
  const sub = lines.reduce((t, l) => t + Math.round(Number(l.quantity || 0) * Number(l.unit || 0) * 100), 0);
  const gst = lines.reduce((t, l) => t + (l.gst ? Math.round(Number(l.quantity || 0) * Number(l.unit || 0) * 100 * 0.1) : 0), 0);
  const submit = async () => {
    setBusy(true);
    try {
      const payload: LineIn[] = lines.filter((l) => l.description.trim() && Number(l.unit)).map((l) => ({ description: l.description.trim(), quantity: Number(l.quantity) || 1, unit_cents: Math.round(Number(l.unit) * 100), gst: l.gst }));
      await practiceBilling.invoices.create({ client_id: clientId, contact_id: contactId || null, lines: payload, period_label: period || null, terms_days: terms, notes: notes || null, send_now: send });
      toast.success(send ? 'Invoice sent' : 'Invoice drafted'); await onDone(); onOpenChange(false);
      setLines([{ description: '', quantity: '1', unit: '', gst: true }]); setPeriod(''); setNotes('');
    } catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[640px]">
      <DialogHeader><DialogTitle>New invoice</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid grid-cols-4 gap-3">
          <div className="col-span-2 grid gap-1.5"><Label>Client</Label>{presetClient ? <div className="rounded-[5px] border px-3 py-2">{presetClient.name}</div> : <Select value={clientId || 'none'} onValueChange={(v) => setClientId(v === 'none' ? '' : v)}><SelectTrigger><SelectValue placeholder="Choose" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select>}</div>
          <div className="grid gap-1.5"><Label>Period</Label><Input placeholder="Sep 2026" value={period} onChange={(e) => setPeriod(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label>Terms (days)</Label><Input type="number" min={0} max={180} value={terms} onChange={(e) => setTerms(Number(e.target.value) || 14)} /></div>
        </div>
        <div className="grid gap-1.5"><Label>Send to</Label><Select value={contactId || 'none'} onValueChange={(v) => setContactId(v === 'none' ? '' : v)}><SelectTrigger><SelectValue placeholder="Primary contact" /></SelectTrigger><SelectContent><SelectItem value="none">Primary contact</SelectItem>{contacts.filter((c) => c.email).map((c) => <SelectItem key={c.id} value={c.id}>{c.full_name} · {c.email}</SelectItem>)}</SelectContent></Select></div>
        <div>
          <div className="mb-1 flex items-center justify-between"><Label>Lines</Label><Button size="sm" variant="ghost" onClick={() => setLines((x) => [...x, { description: '', quantity: '1', unit: '', gst: true }])}><Plus className="mr-1 size-3.5" /> Add line</Button></div>
          {lines.map((l, i) => (
            <div key={i} className="mb-1.5 grid grid-cols-[1fr_70px_110px_auto_auto] items-center gap-2">
              <Input placeholder="Description" value={l.description} onChange={(e) => setLines((x) => x.map((y, j) => (j === i ? { ...y, description: e.target.value } : y)))} />
              <Input type="number" min={0} step="0.5" value={l.quantity} onChange={(e) => setLines((x) => x.map((y, j) => (j === i ? { ...y, quantity: e.target.value } : y)))} />
              <Input type="number" min={0} placeholder="Unit $" value={l.unit} onChange={(e) => setLines((x) => x.map((y, j) => (j === i ? { ...y, unit: e.target.value } : y)))} />
              <label className="flex items-center gap-1 text-[12px]"><input type="checkbox" className="accent-primary" checked={l.gst} onChange={(e) => setLines((x) => x.map((y, j) => (j === i ? { ...y, gst: e.target.checked } : y)))} /> GST</label>
              <Button size="icon" variant="ghost" className="size-8 text-muted-foreground" disabled={lines.length === 1} onClick={() => setLines((x) => x.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
            </div>
          ))}
          <div className="flex justify-end gap-6 pt-1 text-[12px] text-muted-foreground"><span>Subtotal {fmtCents(sub)}</span><span>GST {fmtCents(gst)}</span><span className="font-medium text-foreground">Total {fmtCents(sub + gst)}</span></div>
        </div>
        <div className="grid gap-1.5"><Label>Notes</Label><Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
        <label className="flex items-center gap-2"><input type="checkbox" className="accent-primary" checked={send} onChange={(e) => setSend(e.target.checked)} /> Email it to the client now</label>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button disabled={!clientId || sub === 0 || busy} onClick={() => void submit()}>{send ? 'Create & send' : 'Create draft'}</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function NewScheduleDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void> }) {
  const [clients, setClients] = useState<ClientOut[]>([]);
  const [f, setF] = useState({ client_id: '', name: '', frequency: 'monthly', amount: '', day_of_month: 1, terms_days: 14 });
  useEffect(() => { if (open) void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); }, [open]);
  const submit = async () => {
    try { await practiceBilling.schedules.create({ client_id: f.client_id, name: f.name.trim(), frequency: f.frequency, amount_cents: Math.round(Number(f.amount) * 100), day_of_month: f.day_of_month, terms_days: f.terms_days }); toast.success('Recurring fee added'); await onDone(); onOpenChange(false); }
    catch (e) { toast.error(describeError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[520px]">
      <DialogHeader><DialogTitle>Recurring fee</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid gap-1.5"><Label>Client</Label><Select value={f.client_id || 'none'} onValueChange={(v) => setF({ ...f, client_id: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Choose" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
        <div className="grid gap-1.5"><Label>What it is for</Label><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Monthly bookkeeping" /></div>
        <div className="grid grid-cols-4 gap-3">
          <div className="grid gap-1.5"><Label>Frequency</Label><Select value={f.frequency} onValueChange={(v) => setF({ ...f, frequency: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="monthly">Monthly</SelectItem><SelectItem value="quarterly">Quarterly</SelectItem><SelectItem value="annual">Annual</SelectItem></SelectContent></Select></div>
          <div className="grid gap-1.5"><Label>Amount ($ ex GST)</Label><Input type="number" min={0} value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label>Issue on day</Label><Input type="number" min={1} max={28} value={f.day_of_month} onChange={(e) => setF({ ...f, day_of_month: Number(e.target.value) || 1 })} /></div>
          <div className="grid gap-1.5"><Label>Terms (days)</Label><Input type="number" min={0} max={180} value={f.terms_days} onChange={(e) => setF({ ...f, terms_days: Number(e.target.value) || 14 })} /></div>
        </div>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={!f.client_id || !f.name.trim() || !Number(f.amount)} onClick={() => void submit()}>Add</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
