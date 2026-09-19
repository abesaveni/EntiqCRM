import { Navigate, useParams } from 'react-router-dom';
import { Hammer } from 'lucide-react';
import { getModule, type ModuleKey, type ModuleManifest } from '@entiq/modules';
import { useSession, isEntitled } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { ModuleIcon } from '@/lib/icons';

/**
 * Generic module entry. Order of checks mirrors the API middleware:
 *   1. does the module exist  2. is the tenant entitled (else upsell)  3. render.
 * While a module is being ported, it renders its manifest as a working placeholder.
 */
export function ModuleRoute() {
  const { key } = useParams();
  const tenant = useSession((s) => s.tenant);
  const subscriptions = useSession((s) => s.subscriptions);
  let m: ModuleManifest;
  try { m = getModule(key as ModuleKey); } catch { return <Navigate to="/" replace />; }
  if (!isEntitled({ tenant, subscriptions }, m.key)) return <UpsellPage module={m} />;
  return <PortingPlaceholder module={m} />;
}

export function PortingPlaceholder({ module: m }: { module: ModuleManifest }) {
  return (
    <div className="page">
      <PageHeader eyebrow={`Module ${String(m.number).padStart(2, '0')} · ${m.status === 'porting' ? 'being ported' : m.status}`} title={m.name} description={m.outcome} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-[6px] border bg-card p-5 lg:col-span-2">
          <div className="mb-3 flex items-center gap-2 text-[13px] font-medium text-muted-foreground"><Hammer className="size-4" /> Workspace</div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {m.nav.map((n) => <div key={n.path} className="rounded-[5px] border border-dashed px-3 py-6 text-center text-[13px] text-muted-foreground">{n.label}</div>)}
          </div>
        </div>
        <div className="space-y-4">
          <Info label="Provides" items={m.provides} />
          <Info label="Requires" items={m.requires.map((k) => getModule(k).shortName)} />
          <Info label="Richer with" items={m.enhances.map((k) => getModule(k).shortName)} />
          <Info label="Ported from" items={m.sourceRepos} />
          <div className="rounded-[6px] border bg-card p-4 text-[13px]">
            <div className="mb-1 flex items-center gap-2 font-medium"><ModuleIcon name={m.icon} className="size-4 text-primary" /> Pricing</div>
            <div className="text-muted-foreground">{m.pricing.commercial}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Info({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="rounded-[6px] border bg-card p-4 text-[13px]">
      <div className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{label}</div>
      <div className="flex flex-wrap gap-1.5">{items.map((i) => <span key={i} className="rounded-[4px] bg-muted px-2 py-0.5">{i}</span>)}</div>
    </div>
  );
}
