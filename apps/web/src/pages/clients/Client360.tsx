import { Link, useParams, Navigate } from 'react-router-dom';
import { formatDistanceToNow, isPast } from 'date-fns';
import { Mail, Phone, Plus, MoreHorizontal } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule, panelContributors, type ModuleManifest } from '@entiq/modules';
import { useSession, isEntitled } from '@/state/session';
import { ACTIVITY, CLIENTS, CONTACTS, TASKS } from '@/mock/data';
import { StatusPill, riskTone, stageTone } from '@/components/StatusPill';
import { UpsellPanel } from '@/components/Upsell';
import { ModuleIcon } from '@/lib/icons';
import { ModulePanel } from './panels';

/**
 * The client record as a COMPOSITION SURFACE.
 *
 * Left: what the base plan always provides — identity, contacts, entities,
 * timeline, tasks, notes. Right: one slot per contributing module. A subscribed
 * module fills its slot with live data; an unsubscribed one renders an upsell
 * tile in the same slot. Same layout code either way.
 */
export function Client360() {
  const { id } = useParams();
  const client = CLIENTS.find((c) => c.id === id);
  const tenant = useSession((s) => s.tenant);
  const subscriptions = useSession((s) => s.subscriptions);
  if (!client) return <Navigate to="/clients" replace />;

  const contacts = CONTACTS.filter((p) => p.clientId === client.id);
  const timeline = ACTIVITY.filter((a) => a.clientId === client.id).sort((a, b) => +new Date(b.at) - +new Date(a.at));
  const tasks = TASKS.filter((t) => t.clientId === client.id && !t.done);
  const contributors = panelContributors();
  const entitled = (m: ModuleManifest) => isEntitled({ tenant, subscriptions }, m.key);

  return (
    <div className="page">
      {/* header — CRM core */}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-1 text-[12px] text-muted-foreground"><Link to="/clients" className="hover:underline">Clients</Link> / {client.type}</div>
          <h1 className="truncate">{client.name}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[13px] text-muted-foreground">
            {client.abn && <span>ABN {client.abn}</span>}
            {client.acn && <span>· ACN {client.acn}</span>}
            <span>· client since {new Date(client.since).toLocaleDateString('en-AU', { month: 'short', year: 'numeric' })}</span>
            <span>· owner {client.owner}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <StatusPill tone={stageTone(client.stage)}>{client.stage}</StatusPill>
            {client.risk && isEntitled({ tenant, subscriptions }, 'verify') && <StatusPill tone={riskTone(client.risk)}>Risk · {client.risk}</StatusPill>}
            {client.tags.map((t) => <StatusPill key={t}>{t}</StatusPill>)}
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" size="sm"><Plus className="mr-1.5 size-4" /> Task</Button>
          <Button variant="outline" size="sm"><Plus className="mr-1.5 size-4" /> Note</Button>
          <Button variant="outline" size="icon" className="size-8"><MoreHorizontal className="size-4" /></Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        {/* LEFT — always present */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex-row items-center justify-between pb-3">
              <CardTitle className="text-[15px]">Contacts &amp; roles</CardTitle>
              <span className="text-[12px] text-muted-foreground">{contacts.length} people · {client.entities} entities</span>
            </CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y">
                {contacts.map((p) => (
                  <li key={p.id} className="flex items-center gap-3 px-6 py-2.5">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-[12px] font-semibold">{p.name.split(' ').map((s) => s[0]).slice(0, 2).join('')}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-[13px] font-medium">{p.name}{p.primary && <StatusPill tone="teal">Primary</StatusPill>}</div>
                      <div className="text-[12px] text-muted-foreground">{p.role}</div>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <Button variant="ghost" size="icon" className="size-8" asChild><a href={`mailto:${p.email}`} aria-label="Email"><Mail className="size-4" /></a></Button>
                      {p.phone && <Button variant="ghost" size="icon" className="size-8" asChild><a href={`tel:${p.phone}`} aria-label="Call"><Phone className="size-4" /></a></Button>}
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-0">
              <Tabs defaultValue="timeline">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-[15px]">Activity</CardTitle>
                  <TabsList className="h-8">
                    <TabsTrigger value="timeline" className="text-[12px]">Timeline</TabsTrigger>
                    <TabsTrigger value="tasks" className="text-[12px]">Tasks · {tasks.length}</TabsTrigger>
                    <TabsTrigger value="notes" className="text-[12px]">Notes</TabsTrigger>
                  </TabsList>
                </div>
                <TabsContent value="timeline" className="-mx-6 mt-3 border-t">
                  <ul className="divide-y">
                    {timeline.map((a) => {
                      const m = getModule(a.module);
                      return (
                        <li key={a.id} className="flex items-start gap-3 px-6 py-3">
                          <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-[4px] bg-muted"><ModuleIcon name={m.icon} className="size-3.5 text-muted-foreground" /></span>
                          <div className="min-w-0 flex-1">
                            <div className="text-[13px]">{a.summary}</div>
                            <div className="text-[12px] text-muted-foreground">{m.shortName} · {a.actor} · {formatDistanceToNow(new Date(a.at), { addSuffix: true })}</div>
                          </div>
                        </li>
                      );
                    })}
                    {timeline.length === 0 && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">No activity yet.</li>}
                  </ul>
                </TabsContent>
                <TabsContent value="tasks" className="-mx-6 mt-3 border-t">
                  <ul className="divide-y">
                    {tasks.map((t) => (
                      <li key={t.id} className="flex items-center gap-3 px-6 py-2.5 text-[13px]">
                        <span className={`size-2 rounded-full ${isPast(new Date(t.due)) ? 'bg-error' : 'bg-muted-foreground/40'}`} />
                        <span className="flex-1">{t.title}</span>
                        <span className="text-[12px] text-muted-foreground">{t.owner} · {formatDistanceToNow(new Date(t.due), { addSuffix: true })}</span>
                      </li>
                    ))}
                    {tasks.length === 0 && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">Nothing open.</li>}
                  </ul>
                </TabsContent>
                <TabsContent value="notes" className="-mx-6 mt-3 border-t px-6 py-8 text-center text-[13px] text-muted-foreground">
                  No notes yet — add the first one.
                </TabsContent>
              </Tabs>
            </CardHeader>
            <CardContent className="hidden" />
          </Card>
        </div>

        {/* RIGHT — contributed by modules */}
        <div>
          <div className="mb-2 flex items-center justify-between px-0.5">
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">From your modules</span>
            <Link to="/hq/modules" className="text-[12px] text-muted-foreground hover:underline">Manage</Link>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
            {contributors.map((m) => (
              <div key={m.key} className="min-h-[150px]">
                {entitled(m) ? <ModulePanel module={m} client={client} /> : <UpsellPanel module={m} message={m.panels[0]?.upsell} />}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
