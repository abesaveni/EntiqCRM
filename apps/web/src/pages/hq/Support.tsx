import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { ArrowLeft, LifeBuoy, Plus, Star } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Textarea } from '@entiq/ui/textarea';
import { MANIFESTS } from '@entiq/modules';
import { support, TICKET_STATUS_LABEL, ticketTone, priorityToneOf, type Priority, type TicketCategory, type TicketDetail, type TicketOut } from '@/api/support';
import { useSession, describeError } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

/** Practice HQ → Help & support: raise tickets with EnTIQ, follow replies. Available to every member on every plan. */
export function SupportPage() {
  const readOnly = useSession((s) => s.readOnly);
  const [rows, setRows] = useState<TicketOut[] | null>(null);
  const [open, setOpen] = useState(false);
  const load = async () => { try { setRows(await support.mine()); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { void load(); }, []);
  return (
    <div className="page">
      <PageHeader eyebrow="Practice HQ" title="Help & support" description="Talk to EnTIQ. Urgent and high-priority tickets get a first response within 30 minutes and 2 hours; everything else within a business day."
        actions={!readOnly && <Button size="sm" onClick={() => setOpen(true)}><Plus className="mr-1.5 size-4" /> New ticket</Button>} />
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <ul className="divide-y">
          {rows?.map((t) => <li key={t.id}><Link to={`/hq/support/${t.id}`} className="flex items-center gap-3 px-5 py-3 text-[13px] hover:bg-muted/50"><LifeBuoy className="size-4 shrink-0 text-muted-foreground" /><div className="min-w-0 flex-1"><div className="truncate font-medium">#{t.number} · {t.subject}</div><div className="truncate text-[12px] text-muted-foreground">{t.category} · {t.created_by_name} · {formatDistanceToNow(new Date(t.updated_at), { addSuffix: true })}{t.assigned_operator_name ? ` · with ${t.assigned_operator_name}` : ''}</div></div><StatusPill tone={priorityToneOf(t.priority)}>{t.priority}</StatusPill><StatusPill tone={ticketTone(t.status)}>{TICKET_STATUS_LABEL[t.status]}</StatusPill></Link></li>)}
          {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">No tickets. If something is wrong or unclear, raise one — it goes straight to the EnTIQ team.</li>}
          {!rows && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
        </ul>
      </div>
      <NewTicketDialog open={open} onOpenChange={setOpen} onDone={load} />
    </div>
  );
}

function NewTicketDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void> }) {
  const [f, setF] = useState({ subject: '', body: '', category: 'question' as TicketCategory, priority: 'medium' as Priority, module_key: '' });
  const [busy, setBusy] = useState(false);
  const submit = async () => { setBusy(true); try { await support.raise({ ...f, module_key: f.module_key || null }); toast.success('Ticket raised — check your email for the acknowledgement'); await onDone(); onOpenChange(false); setF({ subject: '', body: '', category: 'question', priority: 'medium', module_key: '' }); } catch (e) { toast.error(describeError(e)); } finally { setBusy(false); } };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[540px]">
      <DialogHeader><DialogTitle>New support ticket</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid gap-1.5"><Label htmlFor="st-subject">Subject</Label><Input id="st-subject" value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} autoFocus /></div>
        <div className="grid grid-cols-3 gap-3">
          <div className="grid gap-1.5"><Label>Category</Label><Select value={f.category} onValueChange={(v) => setF({ ...f, category: v as TicketCategory })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{['question', 'problem', 'billing', 'feature', 'onboarding', 'security'].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></div>
          <div className="grid gap-1.5"><Label>Priority</Label><Select value={f.priority} onValueChange={(v) => setF({ ...f, priority: v as Priority })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{['low', 'medium', 'high', 'urgent'].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></div>
          <div className="grid gap-1.5"><Label>Module</Label><Select value={f.module_key || 'none'} onValueChange={(v) => setF({ ...f, module_key: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="—" /></SelectTrigger><SelectContent><SelectItem value="none">General</SelectItem>{MANIFESTS.filter((m) => m.status !== 'internal').map((m) => <SelectItem key={m.key} value={m.key}>{m.shortName}</SelectItem>)}</SelectContent></Select></div>
        </div>
        <div className="grid gap-1.5"><Label htmlFor="st-body">What happened?</Label><Textarea id="st-body" rows={5} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} placeholder="What you were doing, what you expected, what you saw. Client names are fine — this stays within EnTIQ." /></div>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button disabled={f.subject.trim().length < 3 || f.body.trim().length < 5 || busy} onClick={() => void submit()}>Raise ticket</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

export function SupportTicketPage() {
  const { id = '' } = useParams();
  const readOnly = useSession((s) => s.readOnly);
  const [t, setT] = useState<TicketDetail | null>(null);
  const [body, setBody] = useState('');
  const [rating, setRating] = useState(0);
  const load = () => support.get(id).then(setT).catch((e) => toast.error(describeError(e)));
  useEffect(() => { void load(); }, [id]);
  if (!t) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;
  return (
    <div className="page">
      <Link to="/hq/support" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Support</Link>
      <PageHeader eyebrow={`Ticket #${t.number} · ${t.category} · ${t.priority}`} title={t.subject} description={`Raised by ${t.created_by_name ?? '—'} ${formatDistanceToNow(new Date(t.created_at), { addSuffix: true })}${t.assigned_operator_name ? ` · handled by ${t.assigned_operator_name}` : ''}`}
        actions={<StatusPill tone={ticketTone(t.status)} className="text-[12px]">{TICKET_STATUS_LABEL[t.status]}</StatusPill>} />
      <div className="mx-auto max-w-[760px] space-y-3">
        <div className="rounded-[6px] border bg-card px-4 py-3 text-[13px]"><div className="mb-1 text-[11px] text-muted-foreground">{t.created_by_name} · {format(new Date(t.created_at), 'd MMM yyyy HH:mm')}</div><div className="whitespace-pre-wrap">{t.body}</div></div>
        {t.comments.map((c) => <div key={c.id} className={`rounded-[6px] border px-4 py-3 text-[13px] ${c.is_operator ? 'border-primary/40 bg-primary/5' : 'bg-card'}`}><div className="mb-1 text-[11px] text-muted-foreground">{c.author_name}{c.is_operator ? ' · EnTIQ Support' : ''} · {format(new Date(c.created_at), 'd MMM yyyy HH:mm')}</div><div className="whitespace-pre-wrap">{c.body}</div></div>)}
        {t.status !== 'closed' && !readOnly && (
          <div className="rounded-[6px] border bg-card p-4">
            <Textarea rows={3} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Reply…" />
            <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
              <Button size="sm" disabled={!body.trim()} onClick={() => void support.comment(t.id, body.trim()).then((d) => { setT(d); setBody(''); }).catch((e) => toast.error(describeError(e)))}>Send reply</Button>
              <div className="flex items-center gap-2 text-[12px] text-muted-foreground"><span>Solved?</span>{[1, 2, 3, 4, 5].map((n) => <button key={n} onClick={() => setRating(n)} aria-label={`${n} stars`}><Star className={`size-4 ${n <= rating ? 'fill-warn text-warn' : ''}`} /></button>)}<Button size="sm" variant="outline" onClick={() => void support.close(t.id, rating || undefined).then(setT).catch((e) => toast.error(describeError(e)))}>Close ticket</Button></div>
            </div>
          </div>
        )}
        {t.status === 'closed' && <p className="text-center text-[12px] text-muted-foreground">Closed {t.closed_at ? format(new Date(t.closed_at), 'd MMM yyyy') : ''}{t.satisfaction ? ` · rated ${t.satisfaction}/5` : ''}</p>}
      </div>
    </div>
  );
}
