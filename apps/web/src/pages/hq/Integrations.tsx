import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { CheckCircle2, CircleSlash, FlaskConical, TriangleAlert } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { getModule, type ModuleKey } from '@entiq/modules';
import { platform, type IntegrationOut } from '@/api/platform';
import type { IntegrationSummary } from '@/api/platform';
import { describeError } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';

const TONE = { connected: 'success', simulated: 'warn', attention: 'warn', not_connected: 'neutral' } as const;
const LABEL = { connected: 'Connected', simulated: 'Simulated', attention: 'Needs attention', not_connected: 'Not connected' } as const;
const ICON = { connected: CheckCircle2, simulated: FlaskConical, attention: TriangleAlert, not_connected: CircleSlash };

/**
 * Integration hub — what is actually configured on the server this app is talking to, not a brochure.
 * Anything running on a simulation driver says so here and everywhere its results appear.
 */
export function Integrations() {
  const [rows, setRows] = useState<IntegrationOut[] | null>(null);
  const [summary, setSummary] = useState<IntegrationSummary | null>(null);
  useEffect(() => {
    void Promise.all([platform.integrations.list(), platform.integrations.summary()])
      .then(([r, s]) => { setRows(r); setSummary(s); })
      .catch((e) => toast.error('Could not load integrations', { description: describeError(e) }));
  }, []);

  const platformRows = (rows ?? []).filter((r) => r.scope === 'platform');
  const practiceRows = (rows ?? []).filter((r) => r.scope === 'practice');

  return (
    <div className="page">
      <PageHeader eyebrow="Practice HQ" title="Integration hub" description="Connect once, use everywhere. Each connection is available to every module you hold that needs it — and anything still running in simulation is labelled, here and on the records it touches."
        actions={summary && <StatusPill tone={summary.production_ready ? 'success' : 'warn'} className="text-[12px]">{summary.connected} live · {summary.simulated} simulated</StatusPill>} />

      {summary && !summary.production_ready && (
        <div className="mb-5 rounded-[6px] border border-warn/50 bg-warn-bg/40 px-4 py-3 text-[13px]">
          <div className="mb-1 font-medium">This environment is not production-ready yet.</div>
          <p className="text-muted-foreground">Still to be configured: <span className="font-mono text-[12px]">{summary.blocking.join(', ')}</span>. Until then the affected modules run on simulation drivers, and every result they produce is marked <em>simulated</em> so nothing generated can be mistaken for a real check, charge or ledger.</p>
        </div>
      )}

      <Section title="Connected by your practice" hint="You set these up per client, from the module that uses them." rows={practiceRows} />
      <Section title="Provided by EnTIQ" hint="Platform credentials. Your practice inherits them; there is nothing to set up here." rows={platformRows} />

      {!rows && <p className="text-[13px] text-muted-foreground">Loading…</p>}
    </div>
  );
}

function Section({ title, hint, rows }: { title: string; hint: string; rows: IntegrationOut[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="mb-6">
      <div className="mb-2"><h2 className="text-[15px] font-semibold">{title}</h2><p className="text-[12px] text-muted-foreground">{hint}</p></div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {rows.map((i) => {
          const Icon = ICON[i.status];
          return (
            <div key={i.key} className={`flex flex-col rounded-[6px] border bg-card p-4 ${i.status === 'attention' ? 'border-warn/50' : ''}`}>
              <div className="mb-2 flex items-start justify-between gap-3">
                <div><div className="font-semibold">{i.name}</div><div className="text-[12px] text-muted-foreground">{i.category}</div></div>
                <StatusPill tone={TONE[i.status]}><Icon className="size-3" /> {LABEL[i.status]}</StatusPill>
              </div>
              <p className="mb-2 flex-1 text-[13px] text-muted-foreground">{i.detail}</p>
              {i.missing.length > 0 && <p className="mb-2 text-[12px]"><span className="text-muted-foreground">Needs: </span><span className="font-mono">{i.missing.join(', ')}</span></p>}
              {i.connections > 0 && <p className="mb-2 text-[12px] text-muted-foreground">{i.connections} connection{i.connections === 1 ? '' : 's'}{i.last_activity ? ` · last activity ${formatDistanceToNow(new Date(i.last_activity), { addSuffix: true })}` : ''}</p>}
              <div className="flex items-center justify-between gap-3 border-t pt-3">
                <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                  {i.used_by.length ? <>Used by{i.used_by.map((k) => { const m = getModule(k as ModuleKey); return <span key={k} title={m.name} className="inline-flex"><ModuleIcon name={m.icon} className="size-3.5" /></span>; })}</> : <span>Not used by any module you hold</span>}
                </div>
                {i.key === 'xero' ? <Button size="sm" variant="outline" asChild><Link to="/workpapers">Connect a ledger</Link></Button>
                  : i.configurable_here ? <Button size="sm" variant="outline" disabled>Manage</Button>
                  : <span className="text-[11px] uppercase tracking-[0.08em] text-muted-foreground">platform</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
