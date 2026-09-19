import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import type { ModuleManifest } from '@entiq/modules';
import type { Client } from '@/mock/data';
import { StatusPill, riskTone } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';

/**
 * The SUBSCRIBED state of each module's client-record panel. Today these render
 * indicative content; each module replaces its body with live data as it is ported.
 * The frame (title, icon, "open" link) is shared so every panel reads as one system.
 */
export function ModulePanel({ module, client }: { module: ModuleManifest; client: Client }) {
  return (
    <div className="flex h-full flex-col rounded-[6px] border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-[13px] font-semibold">
          <ModuleIcon name={module.icon} className="size-4 text-primary" />
          {module.panels[0]?.title ?? module.shortName}
        </div>
        <Link to={module.nav[0]?.path ?? `/m/${module.key}`} className="flex items-center gap-0.5 text-[12px] text-muted-foreground hover:text-foreground">
          Open <ArrowRight className="size-3" />
        </Link>
      </div>
      <div className="flex-1 text-[13px]">{body(module, client)}</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-dashed py-1.5 last:border-0">
      <span className="text-muted-foreground">{k}</span>
      <span className="text-right font-medium tabular-nums">{v}</span>
    </div>
  );
}

function body(m: ModuleManifest, c: Client) {
  switch (m.key) {
    case 'verify':
      return (
        <>
          <Row k="Risk rating" v={c.risk ? <StatusPill tone={riskTone(c.risk)}>{c.risk}</StatusPill> : <span className="text-warn">Not assessed</span>} />
          <Row k="Identity" v={c.risk ? 'Verified 12 Aug 2026' : '—'} />
          <Row k="Beneficial owners" v={c.risk ? '2 screened · clear' : '—'} />
          <Row k="Next re-screen" v={c.risk ? 'Aug 2027' : '—'} />
        </>
      );
    case 'workpapers':
      return (
        <>
          <Row k="Ledger" v={c.stage === 'Active' ? '$48,210 Cr' : '—'} />
          <Row k="Open workpapers" v={c.stage === 'Active' ? '3' : '0'} />
          <Row k="BAS" v={c.stage === 'Active' ? 'Q1 due 28 Oct' : '—'} />
          <Row k="Xero" v={c.stage === 'Active' ? 'Synced 2h ago' : 'Not linked'} />
        </>
      );
    case 'sign':
      return (
        <>
          <Row k="Agreements" v={c.stage === 'Active' ? '4 completed' : '0'} />
          <Row k="Awaiting signature" v={c.stage === 'Onboarding' ? '1 · engagement letter' : '0'} />
          <Row k="Last signed" v={c.stage === 'Active' ? 'FY26 engagement · 3 days ago' : '—'} />
        </>
      );
    case 'start':
      return c.stage === 'Onboarding' ? (
        <>
          <Row k="Lifecycle" v="Stage 6 of 11" />
          <Row k="Gates" v="KYC ✓ · AML ✓ · Sign · Mandate" />
          <Row k="Next" v="Fee proposal" />
        </>
      ) : (
        <p className="text-muted-foreground">Onboarding complete{c.stage === 'Lead' || c.stage === 'Proposal' ? ' — not started. Send an invitation to begin.' : '.'}</p>
      );
    case 'practice':
      return (
        <>
          <Row k="Open jobs" v={c.openTasks} />
          <Row k="Next deadline" v={c.stage === 'Active' ? 'BAS · 28 Oct' : '—'} />
          <Row k="Assigned" v={c.owner} />
        </>
      );
    case 'advisory':
      return (
        <>
          <Row k="Cash position" v={c.stage === 'Active' ? '$112,400' : '—'} />
          <Row k="90-day forecast" v={c.stage === 'Active' ? '+$8,900' : '—'} />
          <Row k="Next meeting" v={c.stage === 'Active' ? '14 Oct' : 'Not scheduled'} />
        </>
      );
    case 'requests':
      return (
        <>
          <Row k="Open request packs" v={c.stage === 'Onboarding' ? '1' : '0'} />
          <Row k="Outstanding items" v={c.stage === 'Onboarding' ? '3 of 9' : '—'} />
        </>
      );
    case 'documents':
      return (
        <>
          <Row k="Files" v={c.stage === 'Dormant' ? '61' : c.stage === 'Active' ? '38' : '4'} />
          <Row k="Under retention hold" v={c.type === 'Trust' ? '2' : '0'} />
        </>
      );
    case 'client':
      return (
        <>
          <Row k="Portal access" v={c.stage === 'Active' ? '2 users' : 'Not invited'} />
          <Row k="Pending approvals" v={c.stage === 'Active' ? '1' : '0'} />
        </>
      );
    case 'billing':
      return (
        <>
          <Row k="Outstanding" v={c.stage === 'Active' ? '$1,320.00' : '$0.00'} />
          <Row k="Last invoice" v={c.stage === 'Active' ? 'INV-2041 · paid' : '—'} />
        </>
      );
    case 'lending':
      return <p className="text-muted-foreground">No finance applications for this client.</p>;
    default:
      return <p className="text-muted-foreground">{m.outcome}</p>;
  }
}
