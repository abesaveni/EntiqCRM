import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { format, isSameMonth } from 'date-fns';
import { toast } from 'sonner';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule } from '@entiq/modules';
import { practice, fmtMinutes, type DeadlineOut, type TeamMember } from '@/api/practice';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

export function Deadlines() {
  const entitled = useSession((s) => s.entitled);
  const [days, setDays] = useState('90');
  const [rows, setRows] = useState<DeadlineOut[] | null>(null);
  useEffect(() => { if (entitled('practice')) void practice.deadlines(Number(days)).then(setRows).catch((e) => toast.error(describeError(e))); }, [days]);
  if (!entitled('practice')) return <UpsellPage module={getModule('practice')} />;
  const months: DeadlineOut[][] = [];
  for (const d of rows ?? []) { const last = months[months.length - 1]; if (last && isSameMonth(new Date(last[0].on), new Date(d.on))) last.push(d); else months.push([d]); }
  return (
    <div className="page">
      <PageHeader eyebrow="Practice" title="Deadlines" description="Your jobs' due dates merged with the ATO/ASIC statutory calendar. Agent lodgement concessions vary — treat statutory rows as the standard dates."
        actions={<Tabs value={days} onValueChange={setDays}><TabsList><TabsTrigger value="30">30 days</TabsTrigger><TabsTrigger value="90">90 days</TabsTrigger><TabsTrigger value="180">6 months</TabsTrigger><TabsTrigger value="365">Year</TabsTrigger></TabsList></Tabs>} />
      <div className="space-y-5">
        {months.map((grp) => (
          <div key={grp[0].on}>
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{format(new Date(grp[0].on), 'MMMM yyyy')}</div>
            <ul className="divide-y rounded-[6px] border bg-card">
              {grp.map((d, i) => (
                <li key={i} className="flex items-start gap-3 px-5 py-2 text-[13px]">
                  <span className={`w-[44px] shrink-0 text-[12px] tabular-nums ${d.overdue ? 'font-medium text-error' : 'text-muted-foreground'}`}>{format(new Date(d.on), 'EEE d')}</span>
                  <div className="min-w-0 flex-1">{d.job_id ? <Link to={`/practice/jobs/${d.job_id}`} className="font-medium hover:underline">{d.label}</Link> : <span>{d.label}</span>}<div className="text-[12px] text-muted-foreground">{d.client_name ? <Link to={`/clients/${d.client_id}`} className="hover:underline">{d.client_name}</Link> : null}{d.client_name && d.detail ? ' · ' : ''}{d.detail}</div></div>
                  <StatusPill tone={d.kind === 'job' ? (d.overdue ? 'error' : 'info') : 'neutral'}>{d.kind === 'job' ? (d.overdue ? 'overdue' : 'job') : 'statutory'}</StatusPill>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {rows && rows.length === 0 && <p className="py-14 text-center text-[13px] text-muted-foreground">Nothing in this window.</p>}
      </div>
    </div>
  );
}

export function Team() {
  const entitled = useSession((s) => s.entitled);
  const [rows, setRows] = useState<TeamMember[] | null>(null);
  useEffect(() => { if (entitled('practice')) void practice.team().then(setRows).catch((e) => toast.error(describeError(e))); }, []);
  if (!entitled('practice')) return <UpsellPage module={getModule('practice')} />;
  const maxOpen = Math.max(1, ...(rows ?? []).map((r) => r.open_jobs));
  return (
    <div className="page">
      <PageHeader eyebrow="Practice" title="Team" description="Who is carrying what: open jobs, overdue, time logged this month and open budget." />
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <table className="w-full text-[13px]">
          <thead className="bg-muted/60 text-left text-[11px] uppercase tracking-[0.08em] text-muted-foreground"><tr><th className="px-5 py-2 font-medium">Member</th><th className="px-3 py-2 font-medium">Open jobs</th><th className="px-3 py-2 font-medium">Overdue</th><th className="px-3 py-2 font-medium">This month</th><th className="px-3 py-2 font-medium">Open budget</th></tr></thead>
          <tbody className="divide-y">
            {rows?.map((r) => (
              <tr key={r.membership_id}>
                <td className="px-5 py-2.5"><div className="font-medium">{r.name}</div><div className="text-[12px] text-muted-foreground">{r.role}</div></td>
                <td className="px-3 py-2.5"><div className="flex items-center gap-2"><div className="h-1.5 w-[120px] overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary" style={{ width: `${(r.open_jobs / maxOpen) * 100}%` }} /></div><span className="tabular-nums">{r.open_jobs}</span></div></td>
                <td className={`px-3 py-2.5 tabular-nums ${r.overdue_jobs ? 'font-medium text-error' : 'text-muted-foreground'}`}>{r.overdue_jobs}</td>
                <td className="px-3 py-2.5 tabular-nums">{fmtMinutes(r.minutes_this_month)}</td>
                <td className="px-3 py-2.5 tabular-nums text-muted-foreground">{fmtMinutes(r.budget_minutes_open)}</td>
              </tr>
            ))}
            {rows && rows.length === 0 && <tr><td colSpan={5} className="px-5 py-10 text-center text-muted-foreground">No team members.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
