import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { ArrowLeft, Clock, Repeat } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Checkbox } from '@entiq/ui/checkbox';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Textarea } from '@entiq/ui/textarea';
import { getModule } from '@entiq/modules';
import { practice, JOB_STATUS_LABEL, jobTone, fmtMinutes, type JobOut, type JobStatus, type TimeOut } from '@/api/practice';
import { crm, type StaffOut } from '@/api/crm';
import { fmtCents } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, priorityTone } from '@/components/StatusPill';

const NEXT: Record<JobStatus, JobStatus[]> = { not_started: ['in_progress', 'cancelled'], in_progress: ['waiting_client', 'review', 'complete', 'cancelled'], waiting_client: ['in_progress', 'review'], review: ['in_progress', 'complete'], complete: ['in_progress'], cancelled: ['not_started'] };

export function JobDetail() {
  const { id = '' } = useParams();
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [j, setJ] = useState<JobOut | null>(null);
  const [time, setTime] = useState<TimeOut[]>([]);
  const [staff, setStaff] = useState<StaffOut[]>([]);
  const [t, setT] = useState({ worked_on: new Date().toISOString().slice(0, 10), hours: '1', note: '', billable: true });
  const [notes, setNotes] = useState('');

  const load = async () => { try { const [job, tt] = await Promise.all([practice.jobs.get(id), practice.jobs.time(id)]); setJ(job); setTime(tt); setNotes(job.notes ?? ''); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('practice')) { void load(); void crm.staff().then(setStaff).catch(() => undefined); } }, [id]);
  if (!entitled('practice')) return <UpsellPage module={getModule('practice')} />;
  if (!j) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;

  const edit = !readOnly && can('practice:jobs');
  const patch = async (b: Parameters<typeof practice.jobs.patch>[1], ok?: string) => { try { setJ(await practice.jobs.patch(j.id, b)); if (ok) toast.success(ok); } catch (e) { toast.error(describeError(e)); } };
  const toggle = (key: string) => void patch({ checklist: j.checklist.map((c) => (c.key === key ? { ...c, done: !c.done } : c)) });
  const addTime = async () => { try { await practice.jobs.addTime(j.id, { worked_on: t.worked_on, minutes: Math.round(Number(t.hours) * 60), note: t.note || null, billable: t.billable }); setT({ ...t, hours: '1', note: '' }); await load(); } catch (e) { toast.error(describeError(e)); } };
  const done = j.checklist.filter((c) => c.done).length;

  return (
    <div className="page">
      <Link to="/practice" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Jobs</Link>
      <PageHeader eyebrow={`${j.job_type}${j.period_label ? ` · ${j.period_label}` : ''} · ${j.source}`} title={j.title}
        description={<><Link to={`/clients/${j.client_id}`} className="hover:underline">{j.client_name}</Link>{j.due_on ? ` · due ${format(new Date(j.due_on), 'd MMM yyyy')}` : ''}{j.lodgement_due ? ` · lodgement ${format(new Date(j.lodgement_due), 'd MMM yyyy')}` : ''}</> as unknown as string}
        actions={<div className="flex items-center gap-2">{j.recurring_job_id && <StatusPill><Repeat className="size-3" /> recurring</StatusPill>}<StatusPill tone={priorityTone(j.priority)}>{j.priority}</StatusPill><StatusPill tone={jobTone(j.status)} className="text-[12px]">{JOB_STATUS_LABEL[j.status]}</StatusPill></div>} />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <Card>
            <CardHeader className="flex-row items-center justify-between pb-3"><CardTitle className="text-[15px]">Checklist · {done}/{j.checklist.length}</CardTitle>{edit && <div className="flex gap-1.5">{NEXT[j.status].map((s) => <Button key={s} size="sm" variant={s === 'complete' ? 'default' : 'outline'} onClick={() => void practice.jobs.setStatus(j.id, s).then(setJ).catch((e) => toast.error(describeError(e)))}>{JOB_STATUS_LABEL[s]}</Button>)}</div>}</CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y">{j.checklist.map((c) => <li key={c.key} className="flex items-center gap-3 px-6 py-2.5 text-[13px]"><Checkbox checked={c.done} disabled={!edit} onCheckedChange={() => toggle(c.key)} /><span className={c.done ? 'text-muted-foreground line-through' : ''}>{c.label}</span></li>)}{j.checklist.length === 0 && <li className="px-6 py-6 text-center text-[13px] text-muted-foreground">No checklist for this job type.</li>}</ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-[15px]"><Clock className="size-4 text-primary" /> Time · {fmtMinutes(j.actual_minutes)}{j.budget_minutes ? ` of ${fmtMinutes(j.budget_minutes)} budget` : ''}</CardTitle></CardHeader>
            <CardContent>
              {j.budget_minutes ? <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-muted"><div className={`h-full ${j.actual_minutes > j.budget_minutes ? 'bg-error' : 'bg-primary'}`} style={{ width: `${Math.min(100, (j.actual_minutes / j.budget_minutes) * 100)}%` }} /></div> : null}
              {!readOnly && can('practice:time') && <div className="mb-3 grid grid-cols-[130px_80px_1fr_auto_auto] items-end gap-2 text-[13px]"><div className="grid gap-1"><Label className="text-[11px]">Date</Label><Input type="date" value={t.worked_on} onChange={(e) => setT({ ...t, worked_on: e.target.value })} /></div><div className="grid gap-1"><Label className="text-[11px]">Hours</Label><Input type="number" min={0.25} step={0.25} value={t.hours} onChange={(e) => setT({ ...t, hours: e.target.value })} /></div><div className="grid gap-1"><Label className="text-[11px]">Note</Label><Input value={t.note} onChange={(e) => setT({ ...t, note: e.target.value })} /></div><label className="flex items-center gap-1.5 pb-2 text-[12px]"><Checkbox checked={t.billable} onCheckedChange={(v) => setT({ ...t, billable: !!v })} /> billable</label><Button size="sm" disabled={!t.hours || Number(t.hours) <= 0} onClick={() => void addTime()}>Add</Button></div>}
              <ul className="divide-y text-[13px]">{time.map((x) => <li key={x.id} className="flex items-center gap-3 py-1.5"><span className="w-[80px] text-[12px] tabular-nums text-muted-foreground">{format(new Date(x.worked_on), 'd MMM')}</span><span className="w-[60px] tabular-nums">{fmtMinutes(x.minutes)}</span><span className="min-w-0 flex-1 truncate text-muted-foreground">{x.member_name}{x.note ? ` — ${x.note}` : ''}</span>{!x.billable && <StatusPill>non-billable</StatusPill>}</li>)}{time.length === 0 && <li className="py-3 text-center text-muted-foreground">No time recorded.</li>}</ul>
            </CardContent>
          </Card>
        </div>
        <div className="space-y-4">
          <Card><CardHeader className="pb-3"><CardTitle className="text-[15px]">Details</CardTitle></CardHeader>
            <CardContent className="grid gap-3 text-[13px]">
              <div className="grid gap-1.5"><Label>Assignee</Label><Select value={j.assignee_membership_id ?? 'none'} disabled={!edit || !can('practice:assign')} onValueChange={(v) => void patch({ assignee_membership_id: v === 'none' ? null : v }, 'Reassigned')}><SelectTrigger><SelectValue placeholder="Unassigned" /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{staff.map((s) => <SelectItem key={s.membership_id} value={s.membership_id}>{s.name}</SelectItem>)}</SelectContent></Select></div>
              <div className="grid grid-cols-2 gap-3"><div className="grid gap-1.5"><Label>Due</Label><Input type="date" value={j.due_on ?? ''} disabled={!edit} onChange={(e) => void patch({ due_on: e.target.value || null })} /></div><div className="grid gap-1.5"><Label>Priority</Label><Select value={j.priority} disabled={!edit} onValueChange={(v) => void patch({ priority: v as JobOut['priority'] })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{['Low', 'Normal', 'High'].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent></Select></div></div>
              <Row k="Reviewer" v={j.reviewer_name ?? '—'} /><Row k="Fee" v={j.fee_cents != null ? fmtCents(j.fee_cents) : '—'} /><Row k="Started" v={j.started_at ? formatDistanceToNow(new Date(j.started_at), { addSuffix: true }) : '—'} /><Row k="Completed" v={j.completed_at ? format(new Date(j.completed_at), 'd MMM yyyy') : '—'} />
              <div className="grid gap-1.5"><Label>Notes</Label><Textarea rows={4} value={notes} disabled={!edit} onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== (j.notes ?? '') && void patch({ notes: notes || null })} /></div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) { return <div className="flex justify-between border-b border-dashed py-1 last:border-0"><span className="text-muted-foreground">{k}</span><span>{v}</span></div>; }
