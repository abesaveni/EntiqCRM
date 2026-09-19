import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { Activity, AlertTriangle, CalendarClock, ListChecks, TrendingUp } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule } from '@entiq/modules';
import { advisory, healthTone, severityTone, type ActionOut, type AdvisoryOverview, type AlertOut, type MeetingOut } from '@/api/advisory';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

type View = 'attention' | 'alerts' | 'actions' | 'meetings';

export function AdvisoryHome() {
  const entitled = useSession((s) => s.entitled);
  const [ov, setOv] = useState<AdvisoryOverview | null>(null);
  const [alerts, setAlerts] = useState<AlertOut[]>([]);
  const [actions, setActions] = useState<ActionOut[]>([]);
  const [meetings, setMeetings] = useState<MeetingOut[]>([]);
  const [view, setView] = useState<View>('attention');
  const load = async () => {
    try { const [o, a, ac, m] = await Promise.all([advisory.overview(), advisory.alerts.list({ status: 'open' }), advisory.actions.list({ status: 'open' }), advisory.meetings.list()]); setOv(o); setAlerts(a); setActions(ac); setMeetings(m); }
    catch (e) { toast.error('Could not load Advisory', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('advisory')) void load(); }, []);
  if (!entitled('advisory')) return <UpsellPage module={getModule('advisory')} />;

  return (
    <div className="page">
      <PageHeader eyebrow="Module 10" title="Advisory" description="The numbers, what they mean, and who is doing what about it. Snapshots come from Workpapers; alerts and meetings turn them into owned actions." />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat icon={<TrendingUp className="size-4" />} label="Average health" value={ov?.avg_health_score ?? undefined} suffix="/100" />
        <Stat icon={<AlertTriangle className="size-4" />} label="Needs action" value={ov?.action_alerts} warn={!!ov && ov.action_alerts > 0} />
        <Stat icon={<ListChecks className="size-4" />} label="Open actions" value={ov?.open_actions} />
        <Stat icon={<ListChecks className="size-4" />} label="Overdue actions" value={ov?.overdue_actions} warn={!!ov && ov.overdue_actions > 0} />
        <Stat icon={<CalendarClock className="size-4" />} label="Meetings held · 90d" value={ov?.meetings_held_90d} />
      </div>
      <Tabs value={view} onValueChange={(v) => setView(v as View)} className="mb-3"><TabsList><TabsTrigger value="attention">Needs attention</TabsTrigger><TabsTrigger value="alerts">Alerts</TabsTrigger><TabsTrigger value="actions">Actions</TabsTrigger><TabsTrigger value="meetings">Meetings</TabsTrigger></TabsList></Tabs>

      {view === 'attention' && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {ov?.attention.map((a) => (
            <Card key={a.client_id} className={a.health_band === 'needs_action' ? 'border-error/40' : 'border-warn/40'}>
              <CardHeader className="flex-row items-center justify-between pb-2"><CardTitle className="text-[15px]"><Link to={`/advisory/clients/${a.client_id}`} className="hover:underline">{a.client_name}</Link></CardTitle><StatusPill tone={healthTone(a.health_band)}>{a.health_score ?? '—'}/100</StatusPill></CardHeader>
              <CardContent className="text-[13px]"><ul className="list-disc pl-4 text-muted-foreground">{a.alerts.map((t) => <li key={t}>{t}</li>)}</ul><div className="mt-2 text-[12px] text-muted-foreground">As at {format(new Date(a.as_at), 'd MMM yyyy')}</div></CardContent>
            </Card>
          ))}
          {ov && ov.attention.length === 0 && <p className="py-14 text-center text-[13px] text-muted-foreground md:col-span-2">Nothing needs attention. Take a snapshot for a client to see where they stand.</p>}
        </div>
      )}
      {view === 'alerts' && (
        <ul className="divide-y rounded-[6px] border bg-card">
          {alerts.map((a) => (
            <li key={a.id} className="px-5 py-3 text-[13px]">
              <div className="flex items-start gap-3"><StatusPill tone={severityTone(a.severity)} className="mt-0.5 w-[70px] justify-center">{a.severity}</StatusPill>
                <div className="min-w-0 flex-1"><div className="font-medium"><Link to={`/advisory/clients/${a.client_id}`} className="hover:underline">{a.client_name}</Link> — {a.title}</div><div className="text-[12px] text-muted-foreground">{a.detail}</div>{a.recommendation && <div className="mt-1 text-[12px]"><span className="text-muted-foreground">Suggested: </span>{a.recommendation}</div>}</div>
                <Button size="sm" variant="ghost" onClick={() => { const r = prompt('Dismiss this alert — why?'); if (r) void advisory.alerts.dismiss(a.id, r).then(load).catch((e) => toast.error(describeError(e))); }}>Dismiss</Button>
              </div>
            </li>
          ))}
          {alerts.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">No open alerts.</li>}
        </ul>
      )}
      {view === 'actions' && (
        <ul className="divide-y rounded-[6px] border bg-card">
          {actions.map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
              <div className="min-w-0 flex-1"><div className="truncate font-medium">{a.title}</div><div className="truncate text-[12px] text-muted-foreground"><Link to={`/advisory/clients/${a.client_id}`} className="hover:underline">{a.client_name}</Link> · {a.owner_side === 'practice' ? a.owner_name ?? 'us' : `client${a.owner_name ? ` (${a.owner_name})` : ''}`}{a.due_on ? ` · due ${format(new Date(a.due_on), 'd MMM')}` : ''}</div></div>
              {a.overdue && <StatusPill tone="error">overdue</StatusPill>}
              <StatusPill tone={a.owner_side === 'practice' ? 'info' : 'teal'}>{a.owner_side}</StatusPill>
              <Button size="sm" variant="outline" onClick={() => void advisory.actions.patch(a.id, { status: 'done' }).then(load).catch((e) => toast.error(describeError(e)))}>Done</Button>
            </li>
          ))}
          {actions.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">No open actions.</li>}
        </ul>
      )}
      {view === 'meetings' && (
        <ul className="divide-y rounded-[6px] border bg-card">
          {meetings.map((m) => (
            <li key={m.id}><Link to={`/advisory/meetings/${m.id}`} className="flex items-center gap-3 px-5 py-2.5 text-[13px] hover:bg-muted/50">
              <Activity className="size-4 text-muted-foreground" />
              <div className="min-w-0 flex-1"><div className="truncate font-medium">{m.title}</div><div className="truncate text-[12px] text-muted-foreground">{m.client_name} · {m.scheduled_for ? format(new Date(m.scheduled_for), 'd MMM yyyy') : 'unscheduled'} · {m.action_count} action(s){m.held_at ? ` · held ${formatDistanceToNow(new Date(m.held_at), { addSuffix: true })}` : ''}</div></div>
              <StatusPill tone={m.status === 'published' ? 'success' : m.status === 'held' ? 'teal' : m.status === 'prepared' ? 'info' : 'neutral'}>{m.status}</StatusPill>
            </Link></li>
          ))}
          {meetings.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">No meetings yet. Open a client to schedule one.</li>}
        </ul>
      )}
    </div>
  );
}

function Stat({ icon, label, value, warn, suffix }: { icon: React.ReactNode; label: string; value: number | undefined; warn?: boolean; suffix?: string }) {
  return <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[24px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{value ?? '—'}{value !== undefined && suffix ? <span className="text-[13px] font-normal text-muted-foreground">{suffix}</span> : null}</div></div>;
}
