import { useEffect, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { AlertTriangle, ArrowLeft, Clock, Inbox, UserX } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Checkbox } from '@entiq/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { Textarea } from '@entiq/ui/textarea';
import { support, TICKET_STATUS_LABEL, ticketTone, priorityToneOf, slaTone, type Priority, type QueueStats, type TicketDetail, type TicketOut, type TicketStatus } from '@/api/support';
import { useSession, describeError } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

/** Control Centre → Support queue. Operators only: every practice's tickets, SLA state, assignment, internal notes. */
export function SupportQueue() {
  const isOperator = useSession((s) => s.user?.isOperator ?? false);
  const [stats, setStats] = useState<QueueStats | null>(null);
  const [rows, setRows] = useState<TicketOut[] | null>(null);
  const [status, setStatus] = useState('open');
  const [mine, setMine] = useState(false);
  const load = async () => { try { const [s, r] = await Promise.all([support.ops.stats(), support.ops.queue(status, mine)]); setStats(s); setRows(r); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (isOperator) void load(); }, [status, mine]);
  if (!isOperator) return <Navigate to="/" replace />;
  return (
    <div className="page">
      <PageHeader eyebrow="Control Centre" title="Support queue" description="Every practice's tickets in one place. Reply publicly or leave internal notes; the first public reply stops the response clock." />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-6">
        <Stat icon={<Inbox className="size-4" />} label="Open" value={stats?.open} /><Stat icon={<Clock className="size-4" />} label="Waiting on customer" value={stats?.pending} /><Stat icon={<UserX className="size-4" />} label="Unassigned" value={stats?.unassigned} warn={!!stats && stats.unassigned > 0} />
        <Stat icon={<AlertTriangle className="size-4" />} label="SLA breached" value={stats?.breached} warn={!!stats && stats.breached > 0} /><Stat icon={<AlertTriangle className="size-4" />} label="At risk" value={stats?.at_risk} warn={!!stats && stats.at_risk > 0} /><Stat icon={<Clock className="size-4" />} label="Median 1st response" value={stats?.median_first_response_minutes != null ? `${stats.median_first_response_minutes}m` : undefined} />
      </div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <Tabs value={status} onValueChange={setStatus}><TabsList><TabsTrigger value="open">Open</TabsTrigger><TabsTrigger value="pending">Pending</TabsTrigger><TabsTrigger value="resolved">Resolved</TabsTrigger><TabsTrigger value="all">All</TabsTrigger></TabsList></Tabs>
        <label className="flex items-center gap-2 text-[13px]"><Checkbox checked={mine} onCheckedChange={(v) => setMine(!!v)} /> Assigned to me</label>
      </div>
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <ul className="divide-y">
          {rows?.map((t) => <li key={t.id}><Link to={`/control/support/${t.id}`} className="flex items-center gap-3 px-5 py-3 text-[13px] hover:bg-muted/50"><StatusPill tone={slaTone(t.sla_state)} className="w-[76px] justify-center">{t.sla_state.replace('_', ' ')}</StatusPill><div className="min-w-0 flex-1"><div className="truncate font-medium">#{t.number} · {t.subject}</div><div className="truncate text-[12px] text-muted-foreground">{t.practice_name} · {t.created_by_name} · {t.category}{t.module_key ? ` · ${t.module_key}` : ''} · {formatDistanceToNow(new Date(t.created_at), { addSuffix: true })} · {t.assigned_operator_name ?? 'unassigned'}</div></div><StatusPill tone={priorityToneOf(t.priority)}>{t.priority}</StatusPill><StatusPill tone={ticketTone(t.status)}>{t.status}</StatusPill></Link></li>)}
          {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Queue is clear.</li>}
        </ul>
      </div>
    </div>
  );
}

function Stat({ icon, label, value, warn }: { icon: React.ReactNode; label: string; value: number | string | undefined; warn?: boolean }) {
  return <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[24px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{value ?? '—'}</div></div>;
}

export function SupportTicketOps() {
  const { id = '' } = useParams();
  const isOperator = useSession((s) => s.user?.isOperator ?? false);
  const [t, setT] = useState<TicketDetail | null>(null);
  const [ops, setOps] = useState<Array<{ id: string; name: string }>>([]);
  const [body, setBody] = useState('');
  const [internal, setInternal] = useState(false);
  const act = async (fn: () => Promise<TicketDetail>) => { try { setT(await fn()); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (isOperator) { void act(() => support.ops.get(id)); void support.ops.operators().then(setOps).catch(() => undefined); } }, [id]);
  if (!isOperator) return <Navigate to="/" replace />;
  if (!t) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;
  return (
    <div className="page">
      <Link to="/control/support" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Queue</Link>
      <PageHeader eyebrow={`#${t.number} · ${t.practice_name} · ${t.category}${t.module_key ? ` · ${t.module_key}` : ''}`} title={t.subject} description={`${t.created_by_name} · ${format(new Date(t.created_at), 'd MMM yyyy HH:mm')} · first response due ${t.first_response_due_at ? format(new Date(t.first_response_due_at), 'd MMM HH:mm') : '—'} · resolution due ${t.resolution_due_at ? format(new Date(t.resolution_due_at), 'd MMM HH:mm') : '—'}`}
        actions={<div className="flex items-center gap-2"><StatusPill tone={slaTone(t.sla_state)}>SLA {t.sla_state.replace('_', ' ')}</StatusPill>
          <Select value={t.priority} onValueChange={(v) => void act(() => support.ops.priority(t.id, v as Priority))}><SelectTrigger className="h-8 w-[110px]"><SelectValue /></SelectTrigger><SelectContent>{['low', 'medium', 'high', 'urgent'].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent></Select>
          <Select value={t.assigned_operator_name ? ops.find((o) => o.name === t.assigned_operator_name)?.id ?? 'none' : 'none'} onValueChange={(v) => void act(() => support.ops.assign(t.id, v === 'none' ? null : v))}><SelectTrigger className="h-8 w-[160px]"><SelectValue placeholder="Unassigned" /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{ops.map((o) => <SelectItem key={o.id} value={o.id}>{o.name}</SelectItem>)}</SelectContent></Select>
          <Select value={t.status} onValueChange={(v) => void act(() => support.ops.setStatus(t.id, v as TicketStatus))}><SelectTrigger className="h-8 w-[130px]"><SelectValue /></SelectTrigger><SelectContent>{(Object.keys(TICKET_STATUS_LABEL) as TicketStatus[]).map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent></Select></div>} />
      <div className="mx-auto max-w-[800px] space-y-3">
        <div className="rounded-[6px] border bg-card px-4 py-3 text-[13px]"><div className="mb-1 text-[11px] text-muted-foreground">{t.created_by_name} · {t.practice_name}</div><div className="whitespace-pre-wrap">{t.body}</div></div>
        {t.comments.map((c) => <div key={c.id} className={`rounded-[6px] border px-4 py-3 text-[13px] ${c.internal ? 'border-dashed border-warn/60 bg-warn-bg/30' : c.is_operator ? 'border-primary/40 bg-primary/5' : 'bg-card'}`}><div className="mb-1 text-[11px] text-muted-foreground">{c.author_name}{c.internal ? ' · internal note' : c.is_operator ? ' · operator' : ' · customer'} · {format(new Date(c.created_at), 'd MMM HH:mm')}</div><div className="whitespace-pre-wrap">{c.body}</div></div>)}
        <div className="rounded-[6px] border bg-card p-4">
          <Textarea rows={3} value={body} onChange={(e) => setBody(e.target.value)} placeholder={internal ? 'Internal note (customer never sees this)…' : 'Reply to the customer…'} />
          <div className="mt-2 flex items-center justify-between"><label className="flex items-center gap-2 text-[13px]"><Checkbox checked={internal} onCheckedChange={(v) => setInternal(!!v)} /> Internal note</label><Button size="sm" disabled={!body.trim()} onClick={() => void act(() => support.ops.comment(t.id, body.trim(), internal)).then(() => setBody(''))}>{internal ? 'Add note' : 'Send reply'}</Button></div>
        </div>
      </div>
    </div>
  );
}
