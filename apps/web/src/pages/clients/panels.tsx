import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import type { ModuleManifest } from '@entiq/modules';
import type { ClientOut } from '@/api/crm';
import { StatusPill, riskTone } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';
import { fmtDate } from '@/api/crm';

/**
 * The SUBSCRIBED state of each module's client-record panel. Verify's panel reads the
 * real risk rating the module writes onto the client; the others show what they will
 * surface once ported, drawn from the record itself rather than invented figures.
 */
export function ModulePanel({ module, client }: { module: ModuleManifest; client: ClientOut }) {
  return (
    <div className="flex h-full flex-col rounded-[6px] border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-[13px] font-semibold"><ModuleIcon name={module.icon} className="size-4 text-primary" />{module.panels[0]?.title ?? module.shortName}</div>
        <Link to={module.nav[0]?.path ?? `/m/${module.key}`} className="flex items-center gap-0.5 text-[12px] text-muted-foreground hover:text-foreground">Open <ArrowRight className="size-3" /></Link>
      </div>
      <div className="flex-1 text-[13px]">{body(module, client)}</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="flex items-baseline justify-between gap-3 border-b border-dashed py-1.5 last:border-0"><span className="text-muted-foreground">{k}</span><span className="text-right font-medium tabular-nums">{v}</span></div>;
}

const Pending = ({ what }: { what: string }) => <p className="text-muted-foreground">{what} will appear here once this client has activity in the module.</p>;

function body(m: ModuleManifest, c: ClientOut) {
  const active = c.stage === 'Active' || c.stage === 'Review';
  switch (m.key) {
    case 'verify':
      return c.risk_rating ? (
        <>
          <Row k="Risk rating" v={<StatusPill tone={riskTone(c.risk_rating)}>{c.risk_rating}</StatusPill>} />
          <Row k="Assessed" v={fmtDate(c.risk_assessed_at)} />
          <Row k="Next re-screen" v={c.risk_assessed_at ? fmtDate(new Date(new Date(c.risk_assessed_at).getTime() + 365 * 86_400_000).toISOString()) : '—'} />
        </>
      ) : (
        <>
          <Row k="Risk rating" v={<span className="text-warn">Not assessed</span>} />
          <Row k="Identity" v="Not verified" />
          <p className="mt-2 text-muted-foreground">Run a verification to rate this {c.client_type.toLowerCase()} and screen its people.</p>
        </>
      );
    case 'workpapers': return active ? <><Row k="Ledger" v="Not linked" /><Row k="Open workpapers" v="0" /><Row k="Xero" v="Connect in Practice HQ" /></> : <Pending what="Ledger and workpapers" />;
    case 'sign': return <><Row k="Agreements" v="0" /><Row k="Awaiting signature" v="0" /><p className="mt-2 text-muted-foreground">Send an engagement letter or declaration for signature.</p></>;
    case 'start': return c.stage === 'Onboarding' ? <><Row k="Lifecycle" v="In progress" /><Row k="Gates" v="KYC · AML · Sign · Mandate" /></> : c.stage === 'Lead' || c.stage === 'Proposal' ? <p className="text-muted-foreground">Not started — send an invitation to begin the 11-stage onboarding.</p> : <p className="text-muted-foreground">Onboarding complete.</p>;
    case 'practice': return <><Row k="Open jobs" v="0" /><Row k="Open tasks" v={c.open_task_count} /><Row k="Owner" v={c.owner_name ?? 'Unassigned'} /></>;
    case 'advisory': return active ? <><Row k="Cash position" v="—" /><Row k="Next meeting" v="Not scheduled" /></> : <Pending what="Cash position and forecasts" />;
    case 'requests': return <><Row k="Open request packs" v="0" /><p className="mt-2 text-muted-foreground">Send an adaptive document checklist.</p></>;
    case 'documents': return <><Row k="Files" v="0" /><Row k="Under retention hold" v="0" /></>;
    case 'client': return <><Row k="Portal access" v={c.primary_contact?.has_portal_access ? 'Invited' : 'Not invited'} /><Row k="Pending approvals" v="0" /></>;
    case 'billing': return <><Row k="Outstanding" v="$0.00" /><Row k="Last invoice" v="—" /></>;
    case 'lending': return <p className="text-muted-foreground">No finance applications for this client.</p>;
    default: return <p className="text-muted-foreground">{m.outcome}</p>;
  }
}
