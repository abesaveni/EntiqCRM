import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Plus } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { verify, IDENTITY_LABEL, SCREENING_LABEL, type ClientVerifyOut } from '@/api/verify';
import { sign, STATUS_LABEL, agreementTone, type AgreementOut } from '@/api/sign';
import { NewAgreementDialog } from '@/pages/sign/NewAgreementDialog';
import { start as startApi, STATUS_LABEL as START_STATUS, onboardingTone, type OnboardingOut } from '@/api/start';
import { NewOnboardingDialog } from '@/pages/start/StartHome';
import { practice as practiceApi, JOB_STATUS_LABEL, jobTone, type JobOut } from '@/api/practice';
import { NewJobDialog } from '@/pages/practice/PracticeHome';
import { requests as requestsApi, PACK_STATUS_LABEL, packTone, type PackOut } from '@/api/requests';
import { NewRequestDialog } from '@/pages/requests/RequestsHome';
import { clientPortalStaff, type PortalContactOut } from '@/api/portal';
import { crm } from '@/api/crm';
import { toast } from 'sonner';
import { describeError } from '@/state/session';
import { useSession } from '@/state/session';
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
        <Link to={module.key === 'verify' ? `/verify/clients/${client.id}` : module.nav[0]?.path ?? `/m/${module.key}`} className="flex items-center gap-0.5 text-[12px] text-muted-foreground hover:text-foreground">Open <ArrowRight className="size-3" /></Link>
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
    case 'verify': return <VerifyPanel client={c} />;
    case 'sign': return <SignPanel client={c} />;
    case 'start': return <StartPanel client={c} />;
    case 'practice': return <PracticePanel client={c} />;
    case 'requests': return <RequestsPanel client={c} />;
    case 'client': return <ClientPortalPanel client={c} />;
    case 'workpapers': return active ? <><Row k="Ledger" v="Not linked" /><Row k="Open workpapers" v="0" /><Row k="Xero" v="Connect in Practice HQ" /></> : <Pending what="Ledger and workpapers" />;
    case 'advisory': return active ? <><Row k="Cash position" v="—" /><Row k="Next meeting" v="Not scheduled" /></> : <Pending what="Cash position and forecasts" />;
    case 'documents': return <><Row k="Files on record" v={c.document_count} /><p className="mt-2 text-muted-foreground">Folders, OCR and storage tiers arrive with the Documents module; base attachments are always available on the record.</p></>;
    case 'billing': return <><Row k="Outstanding" v="$0.00" /><Row k="Last invoice" v="—" /></>;
    case 'lending': return <p className="text-muted-foreground">No finance applications for this client.</p>;
    default: return <p className="text-muted-foreground">{m.outcome}</p>;
  }
}

/** Live Verify panel: reads the module's own view of this client (parties, entity, rating). */
function VerifyPanel({ client: c }: { client: ClientOut }) {
  const [d, setD] = useState<ClientVerifyOut | null>(null);
  useEffect(() => { void verify.client(c.id).then(setD).catch(() => setD(null)); }, [c.id, c.risk_rating, c.risk_assessed_at]);
  if (!d) return <p className="text-muted-foreground">Loading checks…</p>;
  const verified = d.parties.filter((p) => p.identity_status === 'verified').length;
  const hits = d.screenings.filter((s) => s.status === 'potential_match').length + (d.entity_screening?.status === 'potential_match' ? 1 : 0);
  return (
    <>
      <Row k="Risk rating" v={d.risk ? <StatusPill tone={riskTone(d.risk.rating)}>{d.risk.rating}</StatusPill> : <span className="text-warn">Not assessed</span>} />
      <Row k="Parties verified" v={`${verified} of ${d.parties.length}`} />
      <Row k="Entity screening" v={SCREENING_LABEL[d.entity_screening?.status ?? 'none']} />
      {hits > 0 && <Row k="Hits to review" v={<span className="text-warn">{hits}</span>} />}
      {d.risk && <Row k="Next review" v={fmtDate(d.risk.next_review_at)} />}
      {d.parties.some((p) => p.identity_status !== 'verified') && <p className="mt-2 text-[12px] text-muted-foreground">{d.parties.filter((p) => p.identity_status !== 'verified').slice(0, 2).map((p) => `${p.name}: ${IDENTITY_LABEL[p.identity_status].toLowerCase()}`).join(' · ')}</p>}
      <Link to={`/verify/clients/${c.id}`} className="mt-3 inline-block text-[12px] text-primary hover:underline">Run checks →</Link>
    </>
  );
}

/** Live Sign panel: this client's agreements, and a shortcut to send one. */
function SignPanel({ client: c }: { client: ClientOut }) {
  const readOnly = useSession((s) => s.readOnly);
  const can = useSession((s) => s.can);
  const [rows, setRows] = useState<AgreementOut[] | null>(null);
  const [open, setOpen] = useState(false);
  const load = () => sign.agreements.list({ client_id: c.id }).then(setRows).catch(() => setRows([]));
  useEffect(() => { void load(); }, [c.id]);
  if (!rows) return <p className="text-muted-foreground">Loading agreements…</p>;
  const awaiting = rows.filter((a) => a.status === 'sent' || a.status === 'partially_signed');
  return (
    <>
      <Row k="Agreements" v={rows.length} />
      <Row k="Awaiting signature" v={awaiting.length ? <span className="text-warn">{awaiting.length}</span> : 0} />
      <ul className="mt-2 space-y-1">
        {rows.slice(0, 3).map((a) => <li key={a.id} className="flex items-center justify-between gap-2 text-[12px]"><Link to={`/sign/agreements/${a.id}`} className="truncate hover:underline">{a.title}</Link><StatusPill tone={agreementTone(a.status)}>{STATUS_LABEL[a.status]}</StatusPill></li>)}
      </ul>
      {!readOnly && can('sign:send') && <Button size="sm" variant="outline" className="mt-3" onClick={() => setOpen(true)}><Plus className="mr-1 size-3.5" /> Send for signature</Button>}
      <NewAgreementDialog open={open} onOpenChange={setOpen} onDone={async () => { await load(); }} presetClient={c} />
    </>
  );
}

/** Live Start panel: this client's onboarding, or the way to begin one. */
function StartPanel({ client: c }: { client: ClientOut }) {
  const readOnly = useSession((s) => s.readOnly);
  const can = useSession((s) => s.can);
  const [rows, setRows] = useState<OnboardingOut[] | null>(null);
  const [open, setOpen] = useState(false);
  const load = () => startApi.onboardings.list({ open: false }).then((all) => setRows(all.filter((o) => o.client_id === c.id))).catch(() => setRows([]));
  useEffect(() => { void load(); }, [c.id]);
  if (!rows) return <p className="text-muted-foreground">Loading…</p>;
  const cur = rows.find((o) => !['activated', 'withdrawn'].includes(o.status)) ?? rows[0];
  if (!cur) return (
    <>
      <p className="text-muted-foreground">{c.stage === 'Active' ? 'Already an active client — no onboarding needed.' : 'Not started. Invite the primary contact to begin the 11-stage onboarding.'}</p>
      {c.stage !== 'Active' && !readOnly && can('start:invite') && <Button size="sm" variant="outline" className="mt-3" onClick={() => setOpen(true)}><Plus className="mr-1 size-3.5" /> Start onboarding</Button>}
      <NewOnboardingDialog open={open} onOpenChange={setOpen} onDone={async () => { await load(); }} presetClient={c} />
    </>
  );
  return (
    <>
      <Row k="Status" v={<StatusPill tone={onboardingTone(cur.status)}>{START_STATUS[cur.status]}</StatusPill>} />
      <Row k="Stage" v={`${cur.current_stage} of 11 · ${cur.progress_pct}%`} />
      {cur.proposal_total_cents != null && <Row k="Proposal" v={`$${(cur.proposal_total_cents / 100).toLocaleString('en-AU')} inc GST`} />}
      <Link to={`/start/onboardings/${cur.id}`} className="mt-3 inline-block text-[12px] text-primary hover:underline">Open onboarding →</Link>
    </>
  );
}

/** Live Practice panel: open jobs for this client and a shortcut to raise one. */
function PracticePanel({ client: c }: { client: ClientOut }) {
  const readOnly = useSession((s) => s.readOnly);
  const can = useSession((s) => s.can);
  const [rows, setRows] = useState<JobOut[] | null>(null);
  const [open, setOpen] = useState(false);
  const load = () => practiceApi.jobs.list({ client_id: c.id }).then(setRows).catch(() => setRows([]));
  useEffect(() => { void load(); }, [c.id]);
  if (!rows) return <p className="text-muted-foreground">Loading…</p>;
  const openJobs = rows.filter((j) => !['complete', 'cancelled'].includes(j.status));
  return (
    <>
      <Row k="Open jobs" v={openJobs.length} />
      <Row k="Overdue" v={openJobs.filter((j) => j.overdue).length ? <span className="text-error">{openJobs.filter((j) => j.overdue).length}</span> : 0} />
      <ul className="mt-2 space-y-1">{openJobs.slice(0, 3).map((j) => <li key={j.id} className="flex items-center justify-between gap-2 text-[12px]"><Link to={`/practice/jobs/${j.id}`} className="truncate hover:underline">{j.title}</Link><StatusPill tone={jobTone(j.status)}>{JOB_STATUS_LABEL[j.status]}</StatusPill></li>)}</ul>
      {!readOnly && can('practice:jobs') && <Button size="sm" variant="outline" className="mt-3" onClick={() => setOpen(true)}><Plus className="mr-1 size-3.5" /> New job</Button>}
      <NewJobDialog open={open} onOpenChange={setOpen} onDone={async () => { await load(); }} meta={null} presetClient={c} />
    </>
  );
}

/** Live Requests panel. */
function RequestsPanel({ client: c }: { client: ClientOut }) {
  const readOnly = useSession((s) => s.readOnly);
  const can = useSession((s) => s.can);
  const [rows, setRows] = useState<PackOut[] | null>(null);
  const [open, setOpen] = useState(false);
  const load = () => requestsApi.packs.list({ client_id: c.id }).then(setRows).catch(() => setRows([]));
  useEffect(() => { void load(); }, [c.id]);
  if (!rows) return <p className="text-muted-foreground">Loading…</p>;
  const openPacks = rows.filter((p) => !['complete', 'cancelled'].includes(p.status));
  return (
    <>
      <Row k="Open requests" v={openPacks.length} />
      <Row k="Awaiting review" v={openPacks.filter((p) => p.status === 'submitted' || p.status === 'reviewing').length} />
      {openPacks.some((p) => p.exceptions > 0) && <Row k="Flagged items" v={<span className="text-warn">{openPacks.reduce((a, p) => a + p.exceptions, 0)}</span>} />}
      <ul className="mt-2 space-y-1">{openPacks.slice(0, 3).map((p) => <li key={p.id} className="flex items-center justify-between gap-2 text-[12px]"><Link to={`/requests/${p.id}`} className="truncate hover:underline">{p.title}</Link><StatusPill tone={packTone(p.status)}>{PACK_STATUS_LABEL[p.status]}</StatusPill></li>)}</ul>
      {!readOnly && can('requests:create') && <Button size="sm" variant="outline" className="mt-3" onClick={() => setOpen(true)}><Plus className="mr-1 size-3.5" /> New request</Button>}
      <NewRequestDialog open={open} onOpenChange={setOpen} onDone={async () => { await load(); }} presetClient={c} />
    </>
  );
}

/** Live Client portal panel: who has access, invite / revoke per contact. */
function ClientPortalPanel({ client: c }: { client: ClientOut }) {
  const readOnly = useSession((s) => s.readOnly);
  const can = useSession((s) => s.can);
  const [rows, setRows] = useState<PortalContactOut[] | null>(null);
  const load = () => clientPortalStaff.contacts(c.id).then(setRows).catch(() => setRows([]));
  useEffect(() => { void load(); }, [c.id]);
  if (!rows) return <p className="text-muted-foreground">Loading…</p>;
  const withAccess = rows.filter((r) => r.has_portal_access);
  return (
    <>
      <Row k="Portal access" v={withAccess.length ? `${withAccess.length} of ${rows.length} contacts` : 'Not invited'} />
      <ul className="mt-2 space-y-1">
        {rows.filter((r) => r.email).slice(0, 4).map((r) => (
          <li key={r.contact_id} className="flex items-center justify-between gap-2 text-[12px]"><span className="truncate">{r.name}{r.has_portal_access ? <span className="text-success"> · active</span> : ''}</span>
            {!readOnly && (r.has_portal_access ? (can('client:manage') && <button className="text-muted-foreground hover:text-error" onClick={() => void clientPortalStaff.revoke(r.contact_id).then(load).catch((e) => toast.error(describeError(e)))}>revoke</button>) : (can('client:invite') && <button className="text-primary hover:underline" onClick={() => void clientPortalStaff.invite(r.contact_id).then(() => { toast.success('Invitation sent'); void load(); }).catch((e) => toast.error(describeError(e)))}>invite</button>))}
          </li>
        ))}
        {rows.every((r) => !r.email) && <li className="text-[12px] text-muted-foreground">Add a contact with an email to invite them.</li>}
      </ul>
      <Link to="/client" className="mt-3 inline-block text-[12px] text-primary hover:underline">Manage portal →</Link>
    </>
  );
}
