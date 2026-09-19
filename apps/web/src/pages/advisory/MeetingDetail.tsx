import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { ArrowLeft, Plus, Send, Trash2, Wand2 } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Textarea } from '@entiq/ui/textarea';
import { getModule } from '@entiq/modules';
import { advisory, healthTone, KPI_LABEL, KPI_SUFFIX, type ActionIn, type MeetingDetail as Detail } from '@/api/advisory';
import { crm, type StaffOut } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

export function MeetingDetail() {
  const { id = '' } = useParams();
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [m, setM] = useState<Detail | null>(null);
  const [staff, setStaff] = useState<StaffOut[]>([]);
  const [summary, setSummary] = useState('');
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [actions, setActions] = useState<Array<{ title: string; owner_side: 'practice' | 'client'; owner: string; due_on: string }>>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const load = async () => { try { const d = await advisory.meetings.get(id); setM(d); setSummary(d.summary ?? ''); setDecisions(Object.fromEntries(d.agenda.filter((a) => a.decision).map((a) => [a.title, a.decision!]))); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('advisory')) { void load(); void crm.staff().then(setStaff).catch(() => undefined); } }, [id]);
  if (!entitled('advisory')) return <UpsellPage module={getModule('advisory')} />;
  if (!m) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;

  const act = async (key: string, fn: () => Promise<Detail>, ok?: string) => { setBusy(key); try { const d = await fn(); setM(d); setSummary(d.summary ?? ''); if (ok) toast.success(ok); } catch (e) { toast.error(describeError(e)); } finally { setBusy(null); } };
  const canRun = !readOnly && can('advisory:meet');
  const held = m.status === 'held' || m.status === 'published';

  const hold = () => act('hold', () => advisory.meetings.hold(m.id, {
    summary: summary.trim(), decisions,
    actions: actions.filter((a) => a.title.trim()).map<ActionIn>((a) => ({ client_id: m.client_id, title: a.title.trim(), owner_side: a.owner_side, owner_membership_id: a.owner_side === 'practice' ? a.owner || null : null, owner_label: a.owner_side === 'client' ? a.owner || null : null, due_on: a.due_on || null })),
  }), 'Meeting recorded');

  return (
    <div className="page">
      <Link to={`/advisory/clients/${m.client_id}`} className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> {m.client_name}</Link>
      <PageHeader eyebrow={`${m.kind} meeting`} title={m.title} description={`${m.scheduled_for ? format(new Date(m.scheduled_for), 'd MMM yyyy') : 'unscheduled'}${m.prepared_by_name ? ` · prepared by ${m.prepared_by_name}` : ''}${m.held_at ? ` · held ${format(new Date(m.held_at), 'd MMM yyyy')}` : ''}`}
        actions={<div className="flex items-center gap-2">
          <StatusPill tone={m.status === 'published' ? 'success' : m.status === 'held' ? 'teal' : m.status === 'prepared' ? 'info' : 'neutral'} className="text-[12px]">{m.status}</StatusPill>
          {canRun && !held && <Button size="sm" variant="outline" disabled={busy === 'prep'} onClick={() => void act('prep', () => advisory.meetings.prepare(m.id), 'Agenda built from the numbers')}><Wand2 className="mr-1.5 size-4" /> Build agenda</Button>}
          {canRun && !held && <Button size="sm" disabled={busy === 'hold' || summary.trim().length < 2} onClick={() => void hold()}>Record meeting</Button>}
          {!readOnly && can('advisory:publish') && held && m.status !== 'published' && <Button size="sm" disabled={busy === 'pub'} onClick={() => void act('pub', () => advisory.meetings.publish(m.id), 'Summary sent to the client')}><Send className="mr-1.5 size-4" /> Publish to client</Button>}
        </div>} />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_300px]">
        <div className="space-y-4">
          {m.agenda.length === 0 && <Card><CardContent className="py-10 text-center text-[13px] text-muted-foreground">No agenda yet. {canRun && 'Build one from the latest snapshot, alerts and outstanding actions.'}</CardContent></Card>}
          {m.agenda.map((a, i) => (
            <Card key={i}>
              <CardHeader className="pb-2"><CardTitle className="text-[15px]">{a.title}{a.source !== 'manual' && <span className="ml-2 text-[11px] font-normal uppercase tracking-[0.08em] text-muted-foreground">{a.source}</span>}</CardTitle></CardHeader>
              <CardContent className="text-[13px]">
                {a.note && <p className="whitespace-pre-wrap text-muted-foreground">{a.note}</p>}
                {held ? (a.decision && <p className="mt-2 rounded-[4px] bg-muted px-3 py-2"><span className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">Decision</span><br />{a.decision}</p>)
                  : canRun && <Input className="mt-2 h-8" placeholder="Decision / outcome" value={decisions[a.title] ?? ''} onChange={(e) => setDecisions({ ...decisions, [a.title]: e.target.value })} />}
              </CardContent>
            </Card>
          ))}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-[15px]">Summary</CardTitle></CardHeader>
            <CardContent>{held ? <p className="whitespace-pre-wrap text-[13px]">{m.summary}</p> : <Textarea rows={4} value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="What was discussed and agreed, in the client's words." disabled={!canRun} />}</CardContent>
          </Card>
          {!held && canRun && (
            <Card>
              <CardHeader className="flex-row items-center justify-between pb-2"><CardTitle className="text-[15px]">Actions to agree</CardTitle><Button size="sm" variant="ghost" onClick={() => setActions((x) => [...x, { title: '', owner_side: 'practice', owner: '', due_on: '' }])}><Plus className="mr-1 size-3.5" /> Add</Button></CardHeader>
              <CardContent className="space-y-2 text-[13px]">
                {actions.map((a, i) => (
                  <div key={i} className="grid grid-cols-[1fr_120px_1fr_130px_auto] items-center gap-2">
                    <Input placeholder="What will be done" value={a.title} onChange={(e) => setActions((x) => x.map((y, j) => (j === i ? { ...y, title: e.target.value } : y)))} />
                    <Select value={a.owner_side} onValueChange={(v) => setActions((x) => x.map((y, j) => (j === i ? { ...y, owner_side: v as 'practice' | 'client', owner: '' } : y)))}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="practice">We do it</SelectItem><SelectItem value="client">Client does it</SelectItem></SelectContent></Select>
                    {a.owner_side === 'practice' ? <Select value={a.owner || 'none'} onValueChange={(v) => setActions((x) => x.map((y, j) => (j === i ? { ...y, owner: v === 'none' ? '' : v } : y)))}><SelectTrigger><SelectValue placeholder="Who" /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{staff.map((s) => <SelectItem key={s.membership_id} value={s.membership_id}>{s.name}</SelectItem>)}</SelectContent></Select>
                      : <Input placeholder="Client contact" value={a.owner} onChange={(e) => setActions((x) => x.map((y, j) => (j === i ? { ...y, owner: e.target.value } : y)))} />}
                    <Input type="date" value={a.due_on} onChange={(e) => setActions((x) => x.map((y, j) => (j === i ? { ...y, due_on: e.target.value } : y)))} />
                    <Button size="icon" variant="ghost" className="size-8 text-muted-foreground" onClick={() => setActions((x) => x.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
                  </div>
                ))}
                {actions.length === 0 && <p className="text-muted-foreground">Add what each side committed to; practice-owned actions also appear as tasks.</p>}
              </CardContent>
            </Card>
          )}
          {held && m.actions.length > 0 && (
            <Card><CardHeader className="pb-2"><CardTitle className="text-[15px]">Agreed actions</CardTitle></CardHeader>
              <CardContent className="p-0"><ul className="divide-y">{m.actions.map((a) => <li key={a.id} className="flex items-center gap-3 px-6 py-2 text-[13px]"><div className="min-w-0 flex-1"><div className="font-medium">{a.title}</div><div className="text-[12px] text-muted-foreground">{a.owner_side === 'practice' ? a.owner_name ?? 'us' : `client${a.owner_name ? ` (${a.owner_name})` : ''}`}{a.due_on ? ` · due ${format(new Date(a.due_on), 'd MMM')}` : ''}</div></div><StatusPill tone={a.status === 'done' ? 'success' : a.overdue ? 'error' : 'neutral'}>{a.status}</StatusPill></li>)}</ul></CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          {m.snapshot && (
            <Card><CardHeader className="pb-2"><CardTitle className="flex items-center justify-between text-[15px]">Position <StatusPill tone={healthTone(m.snapshot.health_band)}>{m.snapshot.health_score ?? '—'}/100</StatusPill></CardTitle></CardHeader>
              <CardContent className="text-[13px]">
                <div className="text-[12px] text-muted-foreground">As at {format(new Date(m.snapshot.as_at), 'd MMM yyyy')}{m.snapshot.simulated ? ' · simulated ledger' : ''}</div>
                <ul className="mt-2 divide-y">{Object.entries(m.snapshot.kpis).slice(0, 6).map(([k, v]) => <li key={k} className="flex justify-between py-1"><span className="text-muted-foreground">{KPI_LABEL[k] ?? k}</span><span className="tabular-nums">{v}{KPI_SUFFIX[k] ?? ''}</span></li>)}</ul>
              </CardContent>
            </Card>
          )}
          {m.alerts.length > 0 && <Card><CardHeader className="pb-2"><CardTitle className="text-[15px]">Open alerts</CardTitle></CardHeader><CardContent className="space-y-1.5 text-[13px]">{m.alerts.map((a) => <div key={a.id}><StatusPill tone={a.severity === 'action' ? 'error' : 'warn'}>{a.severity}</StatusPill> <span className="ml-1">{a.title}</span></div>)}</CardContent></Card>}
        </div>
      </div>
    </div>
  );
}
