import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { ArrowRight, AlertTriangle, CheckSquare, Clock, Sparkles, Upload } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Button } from '@entiq/ui/button';
import { Checkbox } from '@entiq/ui/checkbox';
import { getModule, purchasableModules } from '@entiq/modules';
import { crm, type HomeOut } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, riskTone } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';

/** Role-based home — blueprint §2: work due, risks, approvals, recent activity, next best actions. */
export function Home() {
  const user = useSession((s) => s.user);
  const entitled = useSession((s) => s.entitled);
  const entitlements = useSession((s) => s.entitlements);
  void entitlements;
  const [data, setData] = useState<HomeOut | null>(null);

  const load = async () => { try { setData(await crm.home()); } catch (e) { toast.error('Could not load home', { description: describeError(e) }); } };
  useEffect(() => { void load(); }, []);

  const nextAdd = purchasableModules().filter((m) => m.status !== 'planned' && !entitled(m.key)).slice(0, 3);
  const complete = async (id: string) => { try { await crm.tasks.complete(id); await load(); } catch (e) { toast.error(describeError(e)); } };

  return (
    <div className="page">
      <PageHeader
        eyebrow={new Date().toLocaleDateString('en-AU', { weekday: 'long', day: 'numeric', month: 'long' })}
        title={`Good ${greeting()}, ${user?.name.split(' ')[0]}`}
        description="What needs you today, across every module you have."
      />

      {data && data.total_clients === 0 && (
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-[6px] border border-primary/30 bg-accent px-5 py-4">
          <div>
            <div className="text-[15px] font-semibold text-accent-foreground">Start with your client list</div>
            <div className="text-[13px] text-accent-foreground/80">Import your Xero or MYOB contacts export — most practices are working within two minutes.</div>
          </div>
          <div className="flex gap-2">
            <Button asChild><Link to="/clients/import"><Upload className="mr-1.5 size-4" /> Import clients</Link></Button>
            <Button asChild variant="outline"><Link to="/clients">Add one manually</Link></Button>
          </div>
        </div>
      )}

      <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Overdue tasks" value={data?.overdue_tasks} tone={data?.overdue_tasks ? 'error' : 'neutral'} to="/tasks" />
        <Stat label="Due this week" value={data?.due_this_week} to="/tasks" />
        <Stat label="Elevated-risk clients" value={data?.elevated_risk} tone={data?.elevated_risk ? 'warn' : 'neutral'} to="/clients?risk=elevated" />
        <Stat label="In pipeline" value={data?.in_pipeline} to="/pipeline" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between pb-3">
            <CardTitle className="flex items-center gap-2 text-[15px]"><CheckSquare className="size-4 text-primary" /> Work due</CardTitle>
            <Button asChild variant="ghost" size="sm"><Link to="/tasks">All tasks <ArrowRight className="ml-1 size-3.5" /></Link></Button>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y">
              {data?.tasks.map((t) => (
                <li key={t.id} className="flex items-center gap-3 px-6 py-2.5">
                  <Checkbox aria-label={`Complete ${t.title}`} onCheckedChange={() => void complete(t.id)} />
                  <span className={`size-2 shrink-0 rounded-full ${t.overdue ? 'bg-error' : t.priority === 'High' ? 'bg-warn' : 'bg-muted-foreground/40'}`} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px]">{t.title}</div>
                    <div className="truncate text-[12px] text-muted-foreground">{t.client_id ? <Link to={`/clients/${t.client_id}`} className="hover:underline">{t.client_name}</Link> : 'Practice'}{t.assignee_name ? ` · ${t.assignee_name}` : ''}</div>
                  </div>
                  {t.due_at && <span className={`shrink-0 text-[12px] ${t.overdue ? 'font-medium text-error' : 'text-muted-foreground'}`}>{t.overdue ? 'overdue ' : 'due '}{formatDistanceToNow(new Date(t.due_at), { addSuffix: !t.overdue })}</span>}
                </li>
              ))}
              {data && data.tasks.length === 0 && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">Nothing due. Add tasks from any client record.</li>}
              {!data && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">Loading…</li>}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-[15px]"><AlertTriangle className="size-4 text-warn" /> Risks</CardTitle></CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y">
              {data?.risks.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 px-6 py-2.5">
                  <Link to={`/clients/${c.id}`} className="min-w-0 truncate text-[13px] hover:underline">{c.name}</Link>
                  <StatusPill tone={riskTone(c.risk_rating)}>{c.risk_rating}</StatusPill>
                </li>
              ))}
              {data && data.risks.length === 0 && (
                <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">
                  {entitled('verify') ? 'No elevated-risk clients.' : <>Risk ratings come from <Link to="/hq/modules/verify" className="text-warn hover:underline">Verify</Link>.</>}
                </li>
              )}
            </ul>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-[15px]"><Clock className="size-4 text-primary" /> Recent activity</CardTitle></CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y">
              {data?.recent.map((a) => {
                const m = getModule(a.module_key);
                return (
                  <li key={a.id} className="flex items-start gap-3 px-6 py-2.5">
                    <ModuleIcon name={m.icon} className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px]">{a.summary}</div>
                      <div className="text-[12px] text-muted-foreground">{a.client_id && <><Link to={`/clients/${a.client_id}`} className="hover:underline">{a.client_name}</Link> · </>}{m.shortName} · {a.actor_label}</div>
                    </div>
                    <span className="shrink-0 text-[12px] text-muted-foreground">{formatDistanceToNow(new Date(a.occurred_at), { addSuffix: true })}</span>
                  </li>
                );
              })}
              {data && data.recent.length === 0 && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">No activity yet.</li>}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-[15px]"><Sparkles className="size-4 text-primary" /> Next best actions</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-[13px]">
            {data?.tasks.find((t) => t.overdue) && <Action to="/tasks" text={`Clear "${data.tasks.find((t) => t.overdue)!.title}" — it is overdue.`} />}
            {data && data.in_pipeline > 0 && <Action to="/pipeline" text={`${data.in_pipeline} client${data.in_pipeline === 1 ? '' : 's'} in the pipeline — review stages.`} />}
            {nextAdd.map((m) => <Action key={m.key} to={`/hq/modules/${m.key}`} text={`Add ${m.shortName}: ${m.outcome}`} upsell />)}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = 'neutral', to }: { label: string; value: number | undefined; tone?: 'neutral' | 'warn' | 'error'; to: string }) {
  const color = tone === 'error' ? 'text-error' : tone === 'warn' ? 'text-warn' : 'text-foreground';
  return (
    <Link to={to} className="rounded-[6px] border bg-card px-5 py-4 transition-colors hover:bg-secondary">
      <div className="text-[12px] text-muted-foreground">{label}</div>
      <div className={`mt-1 text-[26px] font-semibold leading-none tabular-nums ${color}`}>{value ?? '–'}</div>
    </Link>
  );
}

function Action({ to, text, upsell }: { to: string; text: string; upsell?: boolean }) {
  return <Link to={to} className={`block rounded-[5px] border px-3 py-2 leading-[19px] transition-colors hover:bg-secondary ${upsell ? 'border-dashed border-warn/50 text-muted-foreground' : ''}`}>{text}</Link>;
}

function greeting() { const h = new Date().getHours(); return h < 12 ? 'morning' : h < 17 ? 'afternoon' : 'evening'; }
