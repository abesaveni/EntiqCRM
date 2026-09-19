import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { AlertTriangle, Briefcase, CalendarClock, Plus, Repeat, UserX } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule } from '@entiq/modules';
import { practice, JOB_STATUS_LABEL, jobTone, fmtMinutes, type JobOut, type PracticeOverview, type PracticeMeta, type RecurringOut, type Frequency } from '@/api/practice';
import { crm, type ClientOut, type StaffOut } from '@/api/crm';
import { fmtCents } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, priorityTone } from '@/components/StatusPill';

type View = 'open' | 'mine' | 'review' | 'complete' | 'recurring';

export function PracticeHome() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [ov, setOv] = useState<PracticeOverview | null>(null);
  const [rows, setRows] = useState<JobOut[] | null>(null);
  const [rec, setRec] = useState<RecurringOut[] | null>(null);
  const [view, setView] = useState<View>('open');
  const [typeFilter, setTypeFilter] = useState('');
  const [meta, setMeta] = useState<PracticeMeta | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [recOpen, setRecOpen] = useState(false);

  const load = async () => {
    try {
      const [o, m] = await Promise.all([practice.overview(), meta ?? practice.meta()]);
      setOv(o); setMeta(m);
      if (view === 'recurring') setRec(await practice.recurring.list());
      else setRows(await practice.jobs.list(view === 'open' ? { open: true, job_type: typeFilter } : view === 'mine' ? { open: true, mine: true, job_type: typeFilter } : view === 'review' ? { status: 'review', job_type: typeFilter } : { status: 'complete', job_type: typeFilter }));
    } catch (e) { toast.error('Could not load Practice', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('practice')) void load(); }, [view, typeFilter]);
  if (!entitled('practice')) return <UpsellPage module={getModule('practice')} />;

  return (
    <div className="page">
      <PageHeader eyebrow="Module 09" title="Practice" description="Jobs, recurring compliance work, time and deadlines — the practice operating rhythm on top of the client list."
        actions={!readOnly && can('practice:jobs') && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setRecOpen(true)}><Repeat className="mr-1.5 size-4" /> Recurring</Button><Button size="sm" onClick={() => setNewOpen(true)}><Plus className="mr-1.5 size-4" /> New job</Button></div>} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-6">
        <Stat icon={<Briefcase className="size-4" />} label="Open jobs" value={ov?.open_jobs} />
        <Stat icon={<AlertTriangle className="size-4" />} label="Overdue" value={ov?.overdue} warn={!!ov && ov.overdue > 0} />
        <Stat icon={<CalendarClock className="size-4" />} label="Due in 7 days" value={ov?.due_7d} />
        <Stat icon={<UserX className="size-4" />} label="Unassigned" value={ov?.unassigned} warn={!!ov && ov.unassigned > 0} />
        <Stat icon={<Briefcase className="size-4" />} label="Waiting on client" value={ov?.waiting_client} />
        <Stat icon={<CalendarClock className="size-4" />} label="Hours this month" value={ov ? Math.round(ov.minutes_this_month / 60) : undefined} />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_300px]">
        <div>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <Tabs value={view} onValueChange={(v) => setView(v as View)}><TabsList><TabsTrigger value="open">Open</TabsTrigger><TabsTrigger value="mine">Mine</TabsTrigger><TabsTrigger value="review">In review</TabsTrigger><TabsTrigger value="complete">Complete</TabsTrigger><TabsTrigger value="recurring">Recurring</TabsTrigger></TabsList></Tabs>
            {view !== 'recurring' && meta && <Select value={typeFilter || 'all'} onValueChange={(v) => setTypeFilter(v === 'all' ? '' : v)}><SelectTrigger className="h-8 w-[180px]"><SelectValue placeholder="All types" /></SelectTrigger><SelectContent><SelectItem value="all">All types</SelectItem>{meta.job_types.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select>}
          </div>
          <div className="overflow-hidden rounded-[6px] border bg-card">
            {view === 'recurring' ? (
              <ul className="divide-y">
                {rec?.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
                    <Repeat className="size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1"><div className="truncate font-medium">{r.job_type} · {r.frequency} <span className="font-normal text-muted-foreground">· <Link to={`/clients/${r.client_id}`} className="hover:underline">{r.client_name}</Link></span></div><div className="text-[12px] text-muted-foreground">Next due {r.next_due_on ? format(new Date(r.next_due_on), 'd MMM yyyy') : '—'} · created {r.advance_days}d ahead · {r.assignee_name ?? 'unassigned'}{r.fee_cents ? ` · ${fmtCents(r.fee_cents)}` : ''}{r.last_period_label ? ` · last: ${r.last_period_label}` : ''}</div></div>
                    <StatusPill tone={r.is_active ? 'success' : 'neutral'}>{r.is_active ? 'active' : 'paused'}</StatusPill>
                    {!readOnly && can('practice:jobs') && <Button size="sm" variant="ghost" onClick={() => void practice.recurring.toggle(r.id).then(load).catch((e) => toast.error(describeError(e)))}>{r.is_active ? 'Pause' : 'Resume'}</Button>}
                  </li>
                ))}
                {rec && rec.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">No recurring schedules yet. Add one for BAS, IAS, annual returns…</li>}
                {rec && rec.length > 0 && !readOnly && can('practice:jobs') && <li className="flex items-center justify-between px-5 py-2 text-[12px] text-muted-foreground"><span>Jobs are created automatically each day inside their advance window.</span><Button size="sm" variant="ghost" onClick={() => void practice.recurring.generate().then((r) => { toast.success(`${r.created} job(s) created`); void load(); }).catch((e) => toast.error(describeError(e)))}>Generate due now</Button></li>}
              </ul>
            ) : (
              <ul className="divide-y">
                {rows?.map((j) => <JobRow key={j.id} j={j} />)}
                {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Nothing here.</li>}
                {!rows && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
              </ul>
            )}
          </div>
        </div>
        <div>
          <div className="mb-2 flex items-center justify-between"><h2 className="text-[15px] font-semibold">Coming up</h2><Link to="/practice/deadlines" className="text-[12px] text-muted-foreground hover:underline">All deadlines</Link></div>
          <ul className="divide-y rounded-[6px] border bg-card">
            {ov?.upcoming.map((d, i) => (
              <li key={i} className="flex items-start gap-3 px-4 py-2 text-[13px]">
                <span className={`w-[52px] shrink-0 text-[12px] tabular-nums ${d.overdue ? 'font-medium text-error' : 'text-muted-foreground'}`}>{format(new Date(d.on), 'd MMM')}</span>
                <div className="min-w-0 flex-1">{d.job_id ? <Link to={`/practice/jobs/${d.job_id}`} className="truncate font-medium hover:underline">{d.label}</Link> : <span className="truncate">{d.label}</span>}<div className="truncate text-[12px] text-muted-foreground">{d.client_name ?? (d.kind === 'statutory' ? 'ATO / statutory' : '')}{d.detail ? ` · ${d.detail}` : ''}</div></div>
              </li>
            ))}
            {ov && ov.upcoming.length === 0 && <li className="px-4 py-8 text-center text-[13px] text-muted-foreground">Nothing due in the next 3 weeks.</li>}
          </ul>
          {ov && Object.keys(ov.by_type).length > 0 && <div className="mt-4"><div className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Open by type</div><div className="flex flex-wrap gap-1.5 text-[12px]">{Object.entries(ov.by_type).map(([k, v]) => <button key={k} className="rounded-[4px] border bg-card px-2 py-0.5 hover:bg-muted" onClick={() => { setTypeFilter(k); setView('open'); }}>{k} <span className="font-medium tabular-nums">{v}</span></button>)}</div></div>}
          <Link to="/practice/team" className="mt-4 block text-[12px] text-muted-foreground hover:underline">Team workload →</Link>
        </div>
      </div>
      <NewJobDialog open={newOpen} onOpenChange={setNewOpen} onDone={load} meta={meta} />
      <NewRecurringDialog open={recOpen} onOpenChange={setRecOpen} onDone={async () => { setView('recurring'); await load(); }} meta={meta} />
    </div>
  );
}

export function JobRow({ j }: { j: JobOut }) {
  return (
    <li>
      <Link to={`/practice/jobs/${j.id}`} className="flex items-center gap-3 px-5 py-2.5 text-[13px] hover:bg-muted/50">
        <Briefcase className="size-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{j.title} <span className="font-normal text-muted-foreground">· {j.client_name}</span></div>
          <div className="truncate text-[12px] text-muted-foreground">{j.job_type}{j.period_label ? ` · ${j.period_label}` : ''} · {j.assignee_name ?? 'Unassigned'}{j.budget_minutes ? ` · ${fmtMinutes(j.actual_minutes)} / ${fmtMinutes(j.budget_minutes)}` : j.actual_minutes ? ` · ${fmtMinutes(j.actual_minutes)}` : ''}{j.checklist.length ? ` · ${j.checklist.filter((c) => c.done).length}/${j.checklist.length} ✓` : ''}</div>
        </div>
        {j.priority !== 'Normal' && <StatusPill tone={priorityTone(j.priority)}>{j.priority}</StatusPill>}
        <StatusPill tone={jobTone(j.status)}>{JOB_STATUS_LABEL[j.status]}</StatusPill>
        <span className={`w-[92px] shrink-0 text-right text-[12px] ${j.overdue ? 'font-medium text-error' : 'text-muted-foreground'}`}>{j.due_on ? `${j.overdue ? 'overdue ' : 'due '}${format(new Date(j.due_on), 'd MMM')}` : 'no due date'}</span>
      </Link>
    </li>
  );
}

function Stat({ icon, label, value, warn }: { icon: React.ReactNode; label: string; value: number | undefined; warn?: boolean }) {
  return <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[24px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{value ?? '—'}</div></div>;
}

export function NewJobDialog({ open, onOpenChange, onDone, meta, presetClient }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void>; meta: PracticeMeta | null; presetClient?: ClientOut }) {
  const [clients, setClients] = useState<ClientOut[]>([]); const [staff, setStaff] = useState<StaffOut[]>([]);
  const [f, setF] = useState({ client_id: presetClient?.id ?? '', title: '', job_type: 'BAS', period_label: '', due_on: '', lodgement_due: '', priority: 'Normal' as 'Low' | 'Normal' | 'High', assignee: '', budget_hours: '', fee: '' });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); void crm.staff().then(setStaff).catch(() => undefined); } }, [open]);
  useEffect(() => { if (presetClient) setF((x) => ({ ...x, client_id: presetClient.id })); }, [presetClient?.id]);
  useEffect(() => { const c = clients.find((x) => x.id === f.client_id) ?? presetClient; if (c && !f.title) setF((x) => ({ ...x, title: `${x.job_type}${x.period_label ? ` ${x.period_label}` : ''} — ${c.name}` })); }, [f.client_id, f.job_type, f.period_label, clients]);
  const submit = async () => {
    setBusy(true);
    try { await practice.jobs.create({ client_id: f.client_id, title: f.title.trim(), job_type: f.job_type, period_label: f.period_label || null, due_on: f.due_on || null, lodgement_due: f.lodgement_due || null, priority: f.priority, assignee_membership_id: f.assignee || null, budget_minutes: f.budget_hours ? Math.round(Number(f.budget_hours) * 60) : null, fee_cents: f.fee ? Math.round(Number(f.fee) * 100) : null }); toast.success('Job created'); await onDone(); onOpenChange(false); setF((x) => ({ ...x, title: '', period_label: '', due_on: '', lodgement_due: '' })); }
    catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[560px]">
      <DialogHeader><DialogTitle>New job</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid grid-cols-[1fr_160px] gap-3">
          <div className="grid gap-1.5"><Label>Client</Label>{presetClient ? <div className="rounded-[5px] border px-3 py-2">{presetClient.name}</div> : <Select value={f.client_id || 'none'} onValueChange={(v) => setF({ ...f, client_id: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Choose" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select>}</div>
          <div className="grid gap-1.5"><Label>Type</Label><Select value={f.job_type} onValueChange={(v) => setF({ ...f, job_type: v, title: '' })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(meta?.job_types ?? ['BAS']).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select></div>
        </div>
        <div className="grid gap-1.5"><Label htmlFor="nj-title">Title</Label><Input id="nj-title" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></div>
        <div className="grid grid-cols-3 gap-3">
          <div className="grid gap-1.5"><Label>Period</Label><Input placeholder="Q1 FY27" value={f.period_label} onChange={(e) => setF({ ...f, period_label: e.target.value, title: '' })} /></div>
          <div className="grid gap-1.5"><Label>Due (internal)</Label><Input type="date" value={f.due_on} onChange={(e) => setF({ ...f, due_on: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label>Lodgement due</Label><Input type="date" value={f.lodgement_due} onChange={(e) => setF({ ...f, lodgement_due: e.target.value })} /></div>
        </div>
        <div className="grid grid-cols-4 gap-3">
          <div className="grid gap-1.5 col-span-2"><Label>Assign to</Label><Select value={f.assignee || 'none'} onValueChange={(v) => setF({ ...f, assignee: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Unassigned" /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{staff.map((s) => <SelectItem key={s.membership_id} value={s.membership_id}>{s.name}</SelectItem>)}</SelectContent></Select></div>
          <div className="grid gap-1.5"><Label>Budget (h)</Label><Input type="number" min={0} step={0.5} value={f.budget_hours} onChange={(e) => setF({ ...f, budget_hours: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label>Fee ($)</Label><Input type="number" min={0} value={f.fee} onChange={(e) => setF({ ...f, fee: e.target.value })} /></div>
        </div>
        <div className="grid gap-1.5"><Label>Priority</Label><Select value={f.priority} onValueChange={(v) => setF({ ...f, priority: v as typeof f.priority })}><SelectTrigger className="w-[160px]"><SelectValue /></SelectTrigger><SelectContent>{['Low', 'Normal', 'High'].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent></Select></div>
        {meta?.default_checklists[f.job_type] && <p className="text-[12px] text-muted-foreground">Checklist: {meta.default_checklists[f.job_type].join(' · ')}</p>}
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button disabled={!f.client_id || !f.title.trim() || busy} onClick={() => void submit()}>Create job</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function NewRecurringDialog({ open, onOpenChange, onDone, meta }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void>; meta: PracticeMeta | null }) {
  const [clients, setClients] = useState<ClientOut[]>([]); const [staff, setStaff] = useState<StaffOut[]>([]);
  const [f, setF] = useState({ client_id: '', job_type: 'BAS', frequency: 'quarterly' as Frequency, month_offset: 1, day_of_month: 28, advance_days: 14, assignee: '', fee: '' });
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); void crm.staff().then(setStaff).catch(() => undefined); } }, [open]);
  const submit = async () => {
    setBusy(true);
    try { await practice.recurring.create({ client_id: f.client_id, job_type: f.job_type, frequency: f.frequency, month_offset: f.month_offset, day_of_month: f.day_of_month, advance_days: f.advance_days, assignee_membership_id: f.assignee || null, fee_cents: f.fee ? Math.round(Number(f.fee) * 100) : null }); toast.success('Recurring schedule added'); await onDone(); onOpenChange(false); }
    catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[520px]">
      <DialogHeader><DialogTitle>Recurring work</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid gap-1.5"><Label>Client</Label><Select value={f.client_id || 'none'} onValueChange={(v) => setF({ ...f, client_id: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Choose" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5"><Label>Type</Label><Select value={f.job_type} onValueChange={(v) => setF({ ...f, job_type: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(meta?.job_types ?? ['BAS']).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select></div>
          <div className="grid gap-1.5"><Label>Frequency</Label><Select value={f.frequency} onValueChange={(v) => setF({ ...f, frequency: v as Frequency })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(meta?.frequencies ?? ['quarterly']).map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent></Select></div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div className="grid gap-1.5"><Label>Due: months after period</Label><Input type="number" min={0} max={12} value={f.month_offset} onChange={(e) => setF({ ...f, month_offset: Number(e.target.value) })} /></div>
          <div className="grid gap-1.5"><Label>Day of month</Label><Input type="number" min={1} max={28} value={f.day_of_month} onChange={(e) => setF({ ...f, day_of_month: Number(e.target.value) })} /></div>
          <div className="grid gap-1.5"><Label>Create days ahead</Label><Input type="number" min={0} max={120} value={f.advance_days} onChange={(e) => setF({ ...f, advance_days: Number(e.target.value) })} /></div>
        </div>
        <div className="grid grid-cols-[1fr_120px] gap-3">
          <div className="grid gap-1.5"><Label>Assign to</Label><Select value={f.assignee || 'none'} onValueChange={(v) => setF({ ...f, assignee: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Unassigned" /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{staff.map((s) => <SelectItem key={s.membership_id} value={s.membership_id}>{s.name}</SelectItem>)}</SelectContent></Select></div>
          <div className="grid gap-1.5"><Label>Fee ($)</Label><Input type="number" min={0} value={f.fee} onChange={(e) => setF({ ...f, fee: e.target.value })} /></div>
        </div>
        <p className="text-[12px] text-muted-foreground">Quarterly BAS with “1 month after, day 28” gives 28 Oct / 28 Feb / 28 Apr / 28 Jul. Periods follow the Australian financial year.</p>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button disabled={!f.client_id || busy} onClick={() => void submit()}>Add schedule</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
