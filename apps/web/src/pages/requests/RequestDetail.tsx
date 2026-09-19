import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { AlertTriangle, ArrowLeft, BellRing, Check, Copy, Download, Plus, X, XCircle } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Input } from '@entiq/ui/input';
import { getModule } from '@entiq/modules';
import { requests, PACK_STATUS_LABEL, ITEM_STATUS_LABEL, PURPOSE_LABEL, packTone, itemTone, type PackDetail, type ItemOut } from '@/api/requests';
import { platform } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

export function RequestDetail() {
  const { id = '' } = useParams();
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [p, setP] = useState<PackDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [rejectFor, setRejectFor] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [addLabel, setAddLabel] = useState('');
  const load = async () => { try { setP(await requests.packs.get(id)); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('requests')) void load(); }, [id]);
  if (!entitled('requests')) return <UpsellPage module={getModule('requests')} />;
  if (!p) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;
  const act = async (key: string, fn: () => Promise<PackDetail>, ok?: string) => { setBusy(key); try { setP(await fn()); if (ok) toast.success(ok); } catch (e) { toast.error(describeError(e)); } finally { setBusy(null); } };
  const open = !['complete', 'cancelled'].includes(p.status);
  const canReview = !readOnly && can('requests:review') && open;
  const flagged = p.items.filter((i) => i.status === 'uploaded' && (i.classification.flags?.length ?? 0) > 0);
  const clean = p.items.filter((i) => i.status === 'uploaded' && !(i.classification.flags?.length));
  const download = async (i: ItemOut) => { if (!i.document_id) return; try { await platform.documents.download({ id: i.document_id, filename: i.document_filename ?? 'file' } as never); } catch (e) { toast.error(describeError(e)); } };

  return (
    <div className="page">
      <Link to="/requests" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Requests</Link>
      <PageHeader eyebrow={`${PURPOSE_LABEL[p.purpose]}${p.period_label ? ` · ${p.period_label}` : ''}`} title={p.title}
        description={`${p.client_name} · ${p.contact_name ?? 'no contact'}${p.contact_email ? ` <${p.contact_email}>` : ''}${p.due_on ? ` · due ${format(new Date(p.due_on), 'd MMM yyyy')}` : ''}${p.reminder_count ? ` · ${p.reminder_count} reminder${p.reminder_count === 1 ? '' : 's'}` : ''}`}
        actions={<div className="flex items-center gap-2">
          <StatusPill tone={packTone(p.status)} className="text-[12px]">{PACK_STATUS_LABEL[p.status]}</StatusPill>
          <Button size="sm" variant="outline" asChild><Link to={`/clients/${p.client_id}`}>Client</Link></Button>
          {open && !readOnly && can('requests:create') && (p.status === 'sent' || p.status === 'in_progress') && <Button size="sm" variant="outline" disabled={busy === 'remind'} onClick={() => void act('remind', () => requests.packs.remind(p.id), 'Reminder sent')}><BellRing className="mr-1.5 size-4" /> Remind</Button>}
          {open && !readOnly && can('requests:approve') && <Button size="sm" disabled={busy === 'complete' || p.items.some((i) => i.required && !['accepted', 'not_applicable'].includes(i.status))} onClick={() => void act('complete', () => requests.packs.complete(p.id), 'Request completed')}>Mark complete</Button>}
          {open && !readOnly && can('requests:create') && <Button size="sm" variant="outline" className="text-error hover:text-error" disabled={busy === 'cancel'} onClick={() => confirm('Cancel this request? The client link stops working.') && void act('cancel', () => requests.packs.cancel(p.id), 'Cancelled')}><XCircle className="mr-1.5 size-4" /> Cancel</Button>}
        </div>} />
      {p.request_url && <div className="mb-4 flex items-center gap-2 rounded-[5px] border bg-card px-3 py-2 text-[12px]"><span className="text-muted-foreground">Client link:</span><code className="min-w-0 flex-1 truncate font-mono text-[11px]">{p.request_url}</code><Button size="sm" variant="ghost" onClick={() => void navigator.clipboard?.writeText(p.request_url!)}><Copy className="size-3.5" /></Button></div>}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          {flagged.length > 0 && (
            <Card className="border-warn/50"><CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-[15px]"><AlertTriangle className="size-4 text-warn" /> Exceptions · {flagged.length}</CardTitle></CardHeader>
              <CardContent className="p-0"><ul className="divide-y">{flagged.map((i) => <ItemRow key={i.id} i={i} canReview={canReview} busy={busy} onAccept={() => void act(i.id, () => requests.packs.review(p.id, i.id, 'accept'), 'Accepted')} onReject={() => { setRejectFor(i.id); setReason(''); }} onDownload={() => void download(i)} rejectOpen={rejectFor === i.id} reason={reason} setReason={setReason} confirmReject={() => { void act(i.id, () => requests.packs.review(p.id, i.id, 'reject', reason.trim()), 'Sent back to the client'); setRejectFor(null); }} cancelReject={() => setRejectFor(null)} />)}</ul></CardContent>
            </Card>
          )}
          <Card>
            <CardHeader className="flex-row items-center justify-between pb-2"><CardTitle className="text-[15px]">Items · {p.items_done}/{p.items_total}{clean.length ? ` · ${clean.length} to review` : ''}</CardTitle>{canReview && clean.length > 1 && <Button size="sm" variant="outline" disabled={busy === 'bulk'} onClick={async () => { setBusy('bulk'); try { for (const i of clean) await requests.packs.review(p.id, i.id, 'accept'); await load(); toast.success(`${clean.length} accepted`); } catch (e) { toast.error(describeError(e)); } finally { setBusy(null); } }}>Accept all unflagged</Button>}</CardHeader>
            <CardContent className="p-0"><ul className="divide-y">{p.items.filter((i) => !flagged.includes(i)).map((i) => <ItemRow key={i.id} i={i} canReview={canReview} busy={busy} onAccept={() => void act(i.id, () => requests.packs.review(p.id, i.id, 'accept'), 'Accepted')} onReject={() => { setRejectFor(i.id); setReason(''); }} onDownload={() => void download(i)} rejectOpen={rejectFor === i.id} reason={reason} setReason={setReason} confirmReject={() => { void act(i.id, () => requests.packs.review(p.id, i.id, 'reject', reason.trim()), 'Sent back to the client'); setRejectFor(null); }} cancelReject={() => setRejectFor(null)} />)}</ul></CardContent>
            {open && !readOnly && can('requests:create') && <div className="flex gap-2 border-t px-4 py-3"><Input className="h-8" placeholder="Add another item (the client is notified)" value={addLabel} onChange={(e) => setAddLabel(e.target.value)} /><Button size="sm" disabled={!addLabel.trim() || busy === 'add'} onClick={() => { void act('add', () => requests.packs.addItems(p.id, [{ label: addLabel.trim(), category: 'other', required: true }]), 'Item added'); setAddLabel(''); }}><Plus className="mr-1 size-3.5" /> Add</Button></div>}
          </Card>
        </div>
        <div className="space-y-4">
          {p.questions.length > 0 && <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">Adaptive questions</CardTitle></CardHeader><CardContent className="text-[13px]"><ul className="divide-y">{p.questions.map((q) => <li key={q.key} className="flex justify-between py-1.5"><span>{q.label}</span><span className="text-muted-foreground">{q.answer === null ? '—' : q.answer ? 'Yes' : 'No'}</span></li>)}</ul></CardContent></Card>}
          <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">Timeline</CardTitle></CardHeader><CardContent className="grid gap-1.5 text-[13px]">
            <Row k="Created" v={`${p.created_by_name ?? 'System'} · ${format(new Date(p.created_at), 'd MMM')}`} /><Row k="Sent" v={p.sent_at ? formatDistanceToNow(new Date(p.sent_at), { addSuffix: true }) : '—'} /><Row k="Submitted" v={p.submitted_at ? formatDistanceToNow(new Date(p.submitted_at), { addSuffix: true }) : '—'} /><Row k="Completed" v={p.completed_at ? format(new Date(p.completed_at), 'd MMM yyyy') : '—'} /><Row k="Last reminder" v={p.last_reminded_at ? formatDistanceToNow(new Date(p.last_reminded_at), { addSuffix: true }) : '—'} />
          </CardContent></Card>
          {p.message && <Card><CardHeader className="pb-2"><CardTitle className="text-[13px] text-muted-foreground">Message to client</CardTitle></CardHeader><CardContent className="text-[13px]">{p.message}</CardContent></Card>}
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) { return <div className="flex justify-between border-b border-dashed py-1 last:border-0"><span className="text-muted-foreground">{k}</span><span>{v}</span></div>; }

function ItemRow({ i, canReview, busy, onAccept, onReject, onDownload, rejectOpen, reason, setReason, confirmReject, cancelReject }: { i: ItemOut; canReview: boolean; busy: string | null; onAccept: () => void; onReject: () => void; onDownload: () => void; rejectOpen: boolean; reason: string; setReason: (s: string) => void; confirmReject: () => void; cancelReject: () => void }) {
  const flags = i.classification.flags ?? [];
  return (
    <li className="px-4 py-2.5 text-[13px]">
      <div className="flex items-center gap-3">
        <StatusPill tone={itemTone(i.status)} className="w-[112px] justify-center">{ITEM_STATUS_LABEL[i.status]}</StatusPill>
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{i.label}{!i.required && <span className="font-normal text-muted-foreground"> · optional</span>} <span className="text-[11px] font-normal text-muted-foreground">{i.category}</span></div>
          <div className="truncate text-[12px] text-muted-foreground">
            {i.document_filename && <button className="hover:underline" onClick={onDownload}><Download className="mr-1 inline size-3" />{i.document_filename}</button>}
            {i.document_filename && i.classification.detected && <> · looks like <span className={flags.length ? 'text-warn' : ''}>{i.classification.detected}</span></>}
            {flags.map((f) => <span key={f} className="ml-1.5 rounded-[3px] border border-warn/50 px-1 text-[11px] text-warn">{f.replace(/_/g, ' ')}</span>)}
            {i.status === 'not_applicable' && <>Client says: {i.client_note}</>}
            {i.status === 'rejected' && <span className="text-error">Sent back: {i.rejection_reason}</span>}
            {i.reviewed_by_name && <> · {i.status} by {i.reviewed_by_name}</>}
          </div>
        </div>
        {canReview && (i.status === 'uploaded' || i.status === 'not_applicable') && <div className="flex gap-1"><Button size="sm" variant="outline" className="h-7" disabled={busy === i.id} onClick={onAccept}><Check className="mr-1 size-3.5" /> Accept</Button><Button size="sm" variant="ghost" className="h-7 text-error hover:text-error" onClick={onReject}><X className="mr-1 size-3.5" /> Reject</Button></div>}
        {canReview && i.status === 'accepted' && <Button size="sm" variant="ghost" className="h-7 text-[12px] text-muted-foreground" onClick={onReject}>Reopen</Button>}
      </div>
      {rejectOpen && <div className="mt-2 flex gap-2 pl-[124px]"><Input className="h-8" placeholder="What's wrong / what do you need instead? (the client sees this)" value={reason} onChange={(e) => setReason(e.target.value)} autoFocus /><Button size="sm" variant="destructive" disabled={reason.trim().length < 3} onClick={confirmReject}>Send back</Button><Button size="sm" variant="ghost" onClick={cancelReject}>Cancel</Button></div>}
    </li>
  );
}
