import { Link } from 'react-router-dom';
import { Lock, ArrowRight } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import type { ModuleManifest } from '@entiq/modules';
import { ModuleIcon } from '@/lib/icons';

/**
 * The unsubscribed state of any module surface. Rendered in the SAME slot the
 * module's real content would occupy, so the gap between what a practice sees
 * and what it owns is the sales pitch — with no separate marketing code path.
 */
export function UpsellPanel({ module, message, compact }: { module: ModuleManifest; message?: string; compact?: boolean }) {
  return (
    <div className="flex h-full flex-col justify-between rounded-[6px] border border-dashed border-warn/60 bg-warn-bg/40 p-4">
      <div>
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
            <ModuleIcon name={module.icon} className="size-4 text-warn" />
            {module.shortName}
          </div>
          <span className="inline-flex items-center gap-1 text-[11px] font-medium uppercase tracking-[0.06em] text-warn">
            <Lock className="size-3" /> not subscribed
          </span>
        </div>
        {!compact && <p className="text-[13px] leading-[19px] text-muted-foreground">{message ?? module.outcome}</p>}
      </div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="text-[12px] text-muted-foreground">{module.pricing.unit}</span>
        <Button asChild size="sm" variant="outline" className="border-warn/60 text-warn hover:bg-warn-bg hover:text-warn">
          <Link to={`/hq/modules/${module.key}`}>
            Add {module.shortName} <ArrowRight className="ml-1 size-3.5" />
          </Link>
        </Button>
      </div>
    </div>
  );
}

/** Full-page version for a route the tenant cannot enter. */
export function UpsellPage({ module }: { module: ModuleManifest }) {
  return (
    <div className="page">
      <div className="mx-auto max-w-[640px] rounded-[6px] border border-dashed border-warn/60 bg-card p-8 text-center">
        <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-[8px] bg-warn-bg text-warn">
          <ModuleIcon name={module.icon} className="size-6" />
        </div>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.08em] text-warn">Not included in your plan</div>
        <h1 className="mb-2">{module.name}</h1>
        <p className="mx-auto mb-6 max-w-[52ch] text-muted-foreground">{module.outcome}</p>
        <div className="mb-6 text-[13px] text-muted-foreground">{module.pricing.commercial}</div>
        <div className="flex justify-center gap-2">
          <Button asChild>
            <Link to={`/hq/modules/${module.key}`}>Add {module.shortName}</Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/hq/modules">See all modules</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
