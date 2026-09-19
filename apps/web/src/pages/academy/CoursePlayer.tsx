import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { Award, ArrowLeft, CheckCircle2, Circle, GraduationCap, PlayCircle } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { getModule } from '@entiq/modules';
import { academy, COMPLIANCE_LABEL, complianceTone, type AttemptOut, type CourseDetail, type MyLearning } from '@/api/academy';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

export function CoursePlayer() {
  const { id = '' } = useParams();
  const entitled = useSession((s) => s.entitled);
  const [c, setC] = useState<CourseDetail | null>(null);
  const [at, setAt] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [result, setResult] = useState<AttemptOut | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => { try { const d = await academy.courses.get(id); setC(d); const first = d.lessons.findIndex((l) => !l.completed); setAt(first === -1 ? 0 : first); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('academy')) void load(); }, [id]);
  if (!entitled('academy')) return <UpsellPage module={getModule('academy')} />;
  if (!c) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;
  const lesson = c.lessons[at];
  const done = c.lessons.filter((l) => l.completed).length;

  const start = async () => { try { setC(await academy.courses.start(id)); } catch (e) { toast.error(describeError(e)); } };
  const complete = async () => {
    setBusy(true);
    try { await academy.courses.completeLesson(id, lesson.id); await load(); if (at < c.lessons.length - 1) setAt(at + 1); toast.success('Lesson complete'); }
    catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };
  const submit = async () => {
    setBusy(true);
    try { const r = await academy.courses.attempt(id, lesson.id, answers); setResult(r); if (r.passed) { toast.success(r.certificate_serial ? `Passed — certificate ${r.certificate_serial}` : `Passed with ${r.score}%`); await load(); } else toast.error(`${r.score}% — the pass mark is ${r.pass_mark}%`); }
    catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };

  return (
    <div className="page">
      <Link to="/academy" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Academy</Link>
      <PageHeader eyebrow={`${c.category} · ${c.minutes} min · pass ${c.pass_mark}%`} title={c.title} description={c.summary ?? undefined}
        actions={c.enrolment ? <StatusPill tone={c.enrolment.status === 'completed' ? 'success' : 'info'} className="text-[12px]">{c.enrolment.status === 'completed' ? 'Completed' : `${c.enrolment.progress}% complete`}</StatusPill> : <Button size="sm" onClick={() => void start()}><PlayCircle className="mr-1.5 size-4" /> Start course</Button>} />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[260px_1fr]">
        <ol className="space-y-1 rounded-[6px] border bg-card p-3">
          {c.lessons.map((l, i) => (
            <li key={l.id}>
              <button className={`flex w-full items-start gap-2 rounded-[5px] px-2 py-1.5 text-left text-[13px] ${i === at ? 'bg-muted font-medium' : ''}`} onClick={() => { setAt(i); setResult(null); }}>
                {l.completed ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> : <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground/50" />}
                <span className="min-w-0 flex-1"><span className="block truncate">{l.title}</span><span className="block text-[11px] text-muted-foreground">{l.kind} · {l.minutes} min</span></span>
              </button>
            </li>
          ))}
          <li className="px-2 pt-2 text-[11px] text-muted-foreground">{done} of {c.lessons.length} complete</li>
        </ol>

        <div>
          {lesson && (
            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-[16px]">{lesson.title}</CardTitle></CardHeader>
              <CardContent className="text-[14px] leading-6">
                {lesson.kind === 'reading' && <div className="whitespace-pre-wrap">{lesson.body}</div>}
                {lesson.kind === 'video' && (lesson.video_url ? <a href={lesson.video_url} target="_blank" rel="noreferrer" className="text-primary hover:underline">Open the video</a> : <p className="text-muted-foreground">No video linked.</p>)}
                {lesson.kind === 'quiz' && (
                  <div className="space-y-5">
                    {lesson.questions.map((q, qi) => {
                      const fb = result?.feedback.find((f) => f.id === q.id);
                      return (
                        <div key={q.id}>
                          <div className="mb-2 font-medium">{qi + 1}. {q.text}{q.points > 1 && <span className="ml-1 text-[12px] font-normal text-muted-foreground">({q.points} points)</span>}</div>
                          <div className="space-y-1.5">
                            {q.options.map((o) => {
                              const picked = (answers[q.id] ?? []).includes(o);
                              const isRight = fb?.expected.includes(o);
                              return (
                                <label key={o} className={`flex cursor-pointer items-center gap-2 rounded-[5px] border px-3 py-1.5 text-[13px] ${result ? (isRight ? 'border-success/50 bg-success-bg/30' : picked ? 'border-error/50 bg-error-bg/30' : '') : picked ? 'border-primary bg-primary/5' : 'hover:bg-muted/50'}`}>
                                  <input type="radio" name={q.id} className="accent-primary" checked={picked} disabled={!!result} onChange={() => setAnswers({ ...answers, [q.id]: [o] })} />
                                  {o}
                                </label>
                              );
                            })}
                          </div>
                          {fb && !fb.correct && <p className="mt-1 text-[12px] text-error">Correct answer: {fb.expected.join(', ')}</p>}
                        </div>
                      );
                    })}
                    {result && <div className={`rounded-[5px] border px-3 py-2 text-[13px] ${result.passed ? 'border-success/50 bg-success-bg/30' : 'border-error/50 bg-error-bg/30'}`}>{result.correct} of {result.total} correct · {result.score}% — {result.passed ? 'passed' : `the pass mark is ${result.pass_mark}%`}{result.certificate_serial ? ` · certificate ${result.certificate_serial}` : ''}</div>}
                  </div>
                )}
                <div className="mt-6 flex items-center gap-2">
                  {lesson.kind === 'quiz'
                    ? (result && !result.passed ? <Button onClick={() => { setResult(null); setAnswers({}); }}>Try again</Button>
                      : !result && <Button disabled={busy || lesson.questions.some((q) => !(answers[q.id] ?? []).length)} onClick={() => void submit()}>Submit answers</Button>)
                    : !lesson.completed && <Button disabled={busy} onClick={() => void complete()}>Mark complete & continue</Button>}
                  {at > 0 && <Button variant="ghost" onClick={() => { setAt(at - 1); setResult(null); }}>Previous</Button>}
                  {at < c.lessons.length - 1 && <Button variant="ghost" onClick={() => { setAt(at + 1); setResult(null); }}>Next</Button>}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

export function MyLearningPage() {
  const entitled = useSession((s) => s.entitled);
  const [d, setD] = useState<MyLearning | null>(null);
  useEffect(() => { if (entitled('academy')) void academy.my().then(setD).catch((e) => toast.error(describeError(e))); }, []);
  if (!entitled('academy')) return <UpsellPage module={getModule('academy')} />;
  if (!d) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;
  return (
    <div className="page">
      <PageHeader eyebrow="Academy" title="My learning" description="What you have been assigned, what you have completed, and the certificates that prove it." />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-[15px]"><GraduationCap className="size-4 text-primary" /> Assigned</CardTitle></CardHeader>
          <CardContent className="p-0"><ul className="divide-y">
            {d.enrolments.map((e) => (
              <li key={e.id} className="flex items-center gap-3 px-6 py-2.5 text-[13px]">
                <div className="w-[48px] shrink-0"><div className="h-1.5 w-full overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${e.progress}%` }} /></div></div>
                <div className="min-w-0 flex-1"><Link to={`/academy/courses/${e.course_id}`} className="truncate font-medium hover:underline">{e.course_title}</Link><div className="text-[12px] text-muted-foreground">{e.category}{e.due_on ? ` · due ${format(new Date(e.due_on), 'd MMM yyyy')}` : ''}</div></div>
                {e.overdue && <StatusPill tone="error">overdue</StatusPill>}
                <StatusPill tone={e.status === 'completed' ? 'success' : e.status === 'in_progress' ? 'info' : 'neutral'}>{e.status.replace('_', ' ')}</StatusPill>
              </li>
            ))}
            {d.enrolments.length === 0 && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">Nothing assigned. Browse the <Link to="/academy" className="text-primary hover:underline">catalogue</Link>.</li>}
          </ul></CardContent>
        </Card>
        <div className="space-y-5">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-[15px]"><Award className="size-4 text-primary" /> My certificates</CardTitle></CardHeader>
            <CardContent className="p-0"><ul className="divide-y">
              {d.certificates.map((c) => <li key={c.id} className="flex items-center gap-3 px-6 py-2 text-[13px]"><div className="min-w-0 flex-1"><div className="truncate font-medium">{c.course_title}</div><div className="text-[12px] text-muted-foreground">{c.score}% · {format(new Date(c.issued_on), 'd MMM yyyy')}{c.expires_on ? ` → ${format(new Date(c.expires_on), 'd MMM yyyy')}` : ''} · <span className="font-mono">{c.serial}</span></div></div><StatusPill tone={c.expired ? 'warn' : 'success'}>{c.expired ? 'expired' : 'valid'}</StatusPill></li>)}
              {d.certificates.length === 0 && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">No certificates yet.</li>}
            </ul></CardContent>
          </Card>
          {d.compliance.length > 0 && (
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-[15px]">My compliance</CardTitle></CardHeader>
              <CardContent className="p-0"><ul className="divide-y">
                {d.compliance.map((r, i) => <li key={i} className="flex items-center gap-3 px-6 py-2 text-[13px]"><div className="min-w-0 flex-1"><div className="truncate">{r.requirement_name}</div><div className="text-[12px] text-muted-foreground">{r.expires_on ? `expires ${format(new Date(r.expires_on), 'd MMM yyyy')}` : 'not started'}</div></div><StatusPill tone={complianceTone(r.state)}>{COMPLIANCE_LABEL[r.state]}</StatusPill></li>)}
              </ul></CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
