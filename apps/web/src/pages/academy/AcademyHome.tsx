import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { Award, BookOpen, GraduationCap, ShieldCheck, Users } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule } from '@entiq/modules';
import { academy, COMPLIANCE_LABEL, complianceTone, type AcademyOverview, type CertificateOut, type ComplianceRow, type CourseOut, type EnrolmentOut, type RequirementOut } from '@/api/academy';
import { crm, type StaffOut } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

type View = 'courses' | 'compliance' | 'team' | 'certificates';

export function AcademyHome() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [ov, setOv] = useState<AcademyOverview | null>(null);
  const [courses, setCourses] = useState<CourseOut[]>([]);
  const [rows, setRows] = useState<ComplianceRow[]>([]);
  const [reqs, setReqs] = useState<RequirementOut[]>([]);
  const [enrols, setEnrols] = useState<EnrolmentOut[]>([]);
  const [certs, setCerts] = useState<CertificateOut[]>([]);
  const [view, setView] = useState<View>('courses');
  const [assign, setAssign] = useState<CourseOut | null>(null);
  const [reqOpen, setReqOpen] = useState(false);

  const load = async () => {
    try {
      const [o, c] = await Promise.all([academy.overview(), academy.courses.list()]);
      setOv(o); setCourses(c);
      if (can('academy:report')) {
        const [r, q, e, ce] = await Promise.all([academy.compliance(), academy.requirements.list(), academy.enrolments.list(), academy.certificates()]);
        setRows(r); setReqs(q); setEnrols(e); setCerts(ce);
      }
    } catch (e) { toast.error('Could not load Academy', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('academy')) void load(); }, []);
  if (!entitled('academy')) return <UpsellPage module={getModule('academy')} />;

  return (
    <div className="page">
      <PageHeader eyebrow="Module 15" title="Academy" description="Training that produces evidence: courses with a pass mark, certificates that can be verified, and compliance requirements that keep themselves up to date."
        actions={<div className="flex gap-2">
          <Button size="sm" variant="outline" asChild><Link to="/academy/my"><GraduationCap className="mr-1.5 size-4" /> My learning</Link></Button>
          {!readOnly && can('academy:author') && courses.length === 0 && <Button size="sm" onClick={() => void academy.courses.seed().then(() => { toast.success('Catalogue loaded'); void load(); }).catch((e) => toast.error(describeError(e)))}>Load the standard catalogue</Button>}
          {!readOnly && can('academy:author') && courses.length > 0 && <Button size="sm" onClick={() => setReqOpen(true)}><ShieldCheck className="mr-1.5 size-4" /> New requirement</Button>}
        </div>} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat icon={<ShieldCheck className="size-4" />} label="Compliance" value={ov?.compliance_pct} suffix="%" warn={!!ov && ov.compliance_pct < 100} />
        <Stat icon={<BookOpen className="size-4" />} label="Courses" value={ov?.courses} />
        <Stat icon={<Users className="size-4" />} label="Open enrolments" value={ov?.enrolments_open} />
        <Stat icon={<Users className="size-4" />} label="Overdue" value={ov?.overdue} warn={!!ov && ov.overdue > 0} />
        <Stat icon={<Award className="size-4" />} label="Valid certificates" value={ov?.certificates_valid} />
      </div>
      <Tabs value={view} onValueChange={(v) => setView(v as View)} className="mb-3"><TabsList><TabsTrigger value="courses">Courses</TabsTrigger>{can('academy:report') && <><TabsTrigger value="compliance">Compliance</TabsTrigger><TabsTrigger value="team">Team</TabsTrigger><TabsTrigger value="certificates">Certificates</TabsTrigger></>}</TabsList></Tabs>

      {view === 'courses' && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {courses.map((c) => (
            <div key={c.id} className="flex flex-col rounded-[6px] border bg-card p-4">
              <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{c.category} · {c.minutes} min</div>
              <Link to={`/academy/courses/${c.id}`} className="text-[15px] font-semibold hover:underline">{c.title}</Link>
              <p className="mt-1 flex-1 text-[13px] text-muted-foreground">{c.summary}</p>
              <div className="mt-3 flex items-center justify-between text-[12px]">
                <span className="text-muted-foreground">{c.certificate ? `Certificate${c.valid_months ? ` · valid ${c.valid_months} months` : ''}` : 'No certificate'} · pass {c.pass_mark}%</span>
                {c.enrolled ? <StatusPill tone={c.my_status === 'completed' ? 'success' : 'info'}>{c.my_status === 'completed' ? 'completed' : `${c.my_progress}%`}</StatusPill> : null}
              </div>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="outline" asChild className="flex-1"><Link to={`/academy/courses/${c.id}`}>{c.enrolled ? 'Continue' : 'Start'}</Link></Button>
                {!readOnly && can('academy:enrol') && <Button size="sm" variant="ghost" onClick={() => setAssign(c)}>Assign</Button>}
              </div>
            </div>
          ))}
          {courses.length === 0 && <p className="py-14 text-center text-[13px] text-muted-foreground md:col-span-2 xl:col-span-3">No courses yet. Load the standard catalogue to start with AML/CTF, privacy, cyber and induction.</p>}
        </div>
      )}

      {view === 'compliance' && (
        <div className="space-y-5">
          <div className="overflow-hidden rounded-[6px] border bg-card">
            <table className="w-full text-[13px]">
              <thead className="bg-muted/60 text-left text-[11px] uppercase tracking-[0.08em] text-muted-foreground"><tr><th className="px-5 py-2 font-medium">Requirement</th><th className="px-2 py-2 font-medium">Applies to</th><th className="px-2 py-2 font-medium">Cycle</th><th className="px-2 py-2 text-right font-medium">Covered</th><th className="px-2 py-2 text-right font-medium">Due soon</th><th className="px-2 py-2 text-right font-medium">Overdue</th><th /></tr></thead>
              <tbody className="divide-y">
                {reqs.map((r) => (
                  <tr key={r.id} className={r.is_active ? '' : 'opacity-60'}>
                    <td className="px-5 py-2"><div className="font-medium">{r.name}</div><div className="text-[12px] text-muted-foreground">{r.course_title}{r.reference ? ` · ${r.reference}` : ''}</div></td>
                    <td className="px-2 py-2 text-[12px]">{r.roles.length ? r.roles.join(', ') : 'everyone'}</td>
                    <td className="px-2 py-2 text-[12px]">every {r.frequency_months} months</td>
                    <td className="px-2 py-2 text-right tabular-nums text-success">{r.covered}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-warn">{r.due_soon}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-error">{r.overdue}</td>
                    <td className="px-2 py-2 text-right">{!readOnly && can('academy:author') && <Button size="sm" variant="ghost" className="h-7 text-[12px]" onClick={() => void academy.requirements.toggle(r.id).then(load)}>{r.is_active ? 'Pause' : 'Resume'}</Button>}</td>
                  </tr>
                ))}
                {reqs.length === 0 && <tr><td colSpan={7} className="px-5 py-10 text-center text-muted-foreground">No requirements yet. Add one to track annual AML/CTF or privacy training.</td></tr>}
              </tbody>
            </table>
          </div>
          {rows.length > 0 && (
            <div>
              <div className="mb-2 flex items-center justify-between"><h2 className="text-[15px] font-semibold">Who is covered</h2>{!readOnly && can('academy:enrol') && <Button size="sm" variant="outline" onClick={() => void academy.enforce().then((r) => { toast.success(`${r.enrolled} enrolment(s) created`); void load(); })}>Enrol everyone outstanding</Button>}</div>
              <ul className="divide-y rounded-[6px] border bg-card">
                {rows.map((r, i) => (
                  <li key={i} className="flex items-center gap-3 px-5 py-2 text-[13px]">
                    <div className="min-w-0 flex-1"><div className="truncate font-medium">{r.member_name} <span className="font-normal text-muted-foreground">· {r.role}</span></div><div className="truncate text-[12px] text-muted-foreground">{r.course_title}{r.last_completed_on ? ` · last done ${format(new Date(r.last_completed_on), 'd MMM yyyy')}` : ''}{r.expires_on ? ` · expires ${format(new Date(r.expires_on), 'd MMM yyyy')}` : ''}</div></div>
                    {r.certificate_serial && <span className="hidden font-mono text-[11px] text-muted-foreground sm:inline">{r.certificate_serial}</span>}
                    <StatusPill tone={complianceTone(r.state)}>{COMPLIANCE_LABEL[r.state]}</StatusPill>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {view === 'team' && (
        <ul className="divide-y rounded-[6px] border bg-card">
          {enrols.map((e) => (
            <li key={e.id} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
              <div className="w-[56px] shrink-0"><div className="h-1.5 w-full overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${e.progress}%` }} /></div></div>
              <div className="min-w-0 flex-1"><div className="truncate font-medium">{e.member_name}</div><div className="truncate text-[12px] text-muted-foreground">{e.course_title} · {e.category}{e.due_on ? ` · due ${format(new Date(e.due_on), 'd MMM')}` : ''}{e.best_score != null ? ` · best ${e.best_score}%` : ''}</div></div>
              {e.overdue && <StatusPill tone="error">overdue</StatusPill>}
              <StatusPill tone={e.status === 'completed' ? 'success' : e.status === 'in_progress' ? 'info' : 'neutral'}>{e.status.replace('_', ' ')}</StatusPill>
            </li>
          ))}
          {enrols.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Nobody is enrolled yet.</li>}
        </ul>
      )}

      {view === 'certificates' && (
        <ul className="divide-y rounded-[6px] border bg-card">
          {certs.map((c) => (
            <li key={c.id} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
              <Award className={`size-4 ${c.expired || c.revoked ? 'text-muted-foreground' : 'text-success'}`} />
              <div className="min-w-0 flex-1"><div className="truncate font-medium">{c.member_name} — {c.course_title}</div><div className="truncate text-[12px] text-muted-foreground">{c.category} · {c.score}% · issued {format(new Date(c.issued_on), 'd MMM yyyy')}{c.expires_on ? ` · expires ${format(new Date(c.expires_on), 'd MMM yyyy')}` : ''} · <span className="font-mono">{c.serial}</span></div></div>
              <StatusPill tone={c.revoked ? 'error' : c.expired ? 'warn' : 'success'}>{c.revoked ? 'revoked' : c.expired ? 'expired' : 'valid'}</StatusPill>
            </li>
          ))}
          {certs.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">No certificates issued yet.</li>}
        </ul>
      )}

      <AssignDialog course={assign} onClose={() => setAssign(null)} onDone={load} />
      <RequirementDialog open={reqOpen} onOpenChange={setReqOpen} courses={courses} onDone={load} />
    </div>
  );
}

function Stat({ icon, label, value, warn, suffix }: { icon: React.ReactNode; label: string; value: number | undefined; warn?: boolean; suffix?: string }) {
  return <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[24px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{value ?? '—'}{value !== undefined && suffix ? <span className="text-[14px] font-normal text-muted-foreground">{suffix}</span> : null}</div></div>;
}

function AssignDialog({ course, onClose, onDone }: { course: CourseOut | null; onClose: () => void; onDone: () => Promise<void> }) {
  const [staff, setStaff] = useState<StaffOut[]>([]);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [all, setAll] = useState(true);
  const [days, setDays] = useState(30);
  useEffect(() => { if (course) void crm.staff().then(setStaff).catch(() => undefined); }, [course?.id]);
  if (!course) return null;
  const submit = async () => {
    try { const r = await academy.enrolments.assign({ course_id: course.id, all_staff: all, membership_ids: all ? [] : [...picked], due_in_days: days }); toast.success(`Assigned to ${r.length} member(s)`); await onDone(); onClose(); }
    catch (e) { toast.error(describeError(e)); }
  };
  return (
    <Dialog open={!!course} onOpenChange={(o) => !o && onClose()}><DialogContent className="max-w-[480px]">
      <DialogHeader><DialogTitle>Assign “{course.title}”</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <label className="flex items-center gap-2"><input type="checkbox" className="accent-primary" checked={all} onChange={(e) => setAll(e.target.checked)} /> Everyone in the practice</label>
        {!all && <ul className="max-h-[220px] divide-y overflow-y-auto rounded-[5px] border">{staff.map((s) => <li key={s.membership_id}><label className="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-muted/50"><input type="checkbox" className="accent-primary" checked={picked.has(s.membership_id)} onChange={() => setPicked((p) => { const n = new Set(p); n.has(s.membership_id) ? n.delete(s.membership_id) : n.add(s.membership_id); return n; })} />{s.name} <span className="text-[12px] text-muted-foreground">{s.role}</span></label></li>)}</ul>}
        <div className="grid gap-1.5"><Label>Due in (days)</Label><Input type="number" min={1} max={365} value={days} onChange={(e) => setDays(Number(e.target.value) || 30)} className="w-[120px]" /></div>
      </div>
      <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button disabled={!all && picked.size === 0} onClick={() => void submit()}>Assign</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function RequirementDialog({ open, onOpenChange, courses, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; courses: CourseOut[]; onDone: () => Promise<void> }) {
  const [f, setF] = useState({ course_id: '', frequency_months: 12, grace_days: 30, reference: '', roles: [] as string[] });
  const submit = async () => {
    try { await academy.requirements.create({ course_id: f.course_id, frequency_months: f.frequency_months, grace_days: f.grace_days, reference: f.reference || null, roles: f.roles }); toast.success('Requirement added'); await onDone(); onOpenChange(false); }
    catch (e) { toast.error(describeError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[480px]">
      <DialogHeader><DialogTitle>New compliance requirement</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid gap-1.5"><Label>Course</Label><Select value={f.course_id || 'none'} onValueChange={(v) => setF({ ...f, course_id: v === 'none' ? '' : v })}><SelectTrigger><SelectValue placeholder="Choose" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{courses.map((c) => <SelectItem key={c.id} value={c.id}>{c.title}</SelectItem>)}</SelectContent></Select></div>
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5"><Label>Every (months)</Label><Input type="number" min={1} max={120} value={f.frequency_months} onChange={(e) => setF({ ...f, frequency_months: Number(e.target.value) || 12 })} /></div>
          <div className="grid gap-1.5"><Label>Grace (days)</Label><Input type="number" min={0} max={365} value={f.grace_days} onChange={(e) => setF({ ...f, grace_days: Number(e.target.value) || 0 })} /></div>
        </div>
        <div className="grid gap-1.5"><Label>Applies to</Label><div className="flex gap-1.5">{['owner', 'admin', 'staff'].map((r) => <button key={r} type="button" className={`rounded-[4px] border px-2 py-0.5 text-[12px] ${f.roles.includes(r) ? 'border-primary bg-primary/10' : ''}`} onClick={() => setF({ ...f, roles: f.roles.includes(r) ? f.roles.filter((x) => x !== r) : [...f.roles, r] })}>{r}</button>)}<span className="self-center text-[12px] text-muted-foreground">{f.roles.length ? '' : 'everyone'}</span></div></div>
        <div className="grid gap-1.5"><Label>Reference</Label><Input placeholder="AML/CTF Act s.207 — ongoing training" value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></div>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={!f.course_id} onClick={() => void submit()}>Add requirement</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
