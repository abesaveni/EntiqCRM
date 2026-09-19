import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { ArrowLeft, Check, CheckCircle2, Circle, Copy, Lock, Mail, RefreshCw, ShieldAlert, ShieldCheck, XCircle } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Checkbox } from '@entiq/ui/checkbox';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Textarea } from '@entiq/ui/textarea';
import { getModule } from '@entiq/modules';
import { start, STATUS_LABEL, onboardingTone, gateTone, BASIS_LABEL, type OnboardingDetail as Detail, type ProposalLine, type ServiceOut, type StageOut } from '@/api/start';
import { platform, fmtCents, type DocumentOut } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, riskTone } from '@/components/StatusPill';

export function OnboardingDetail() {
  const { id = '' } = useParams();
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [o, setO] = useState<Detail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);
  const [withdrawOpen, setWithdrawOpen] = useState(false);

  const load = async () => { try { setO(await start.onboardings.get(id)); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('start')) void load(); }, [id]);
  if (!entitled('start')) return <UpsellPage module={getModule('start')} />;
  if (!o) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;

  const act = async (key: string, fn: () => Promise<Detail>, ok?: string) => {
    setBusy(key);
    try { const d = await fn(); setO(d); if (d.invite_url) setInviteUrl(d.invite_url); if (ok) toast.success(ok); } catch (e) { toast.error(describeError(e)); } finally { setBusy(null); }
  };
  const open = !['activated', 'withdrawn'].includes(o.status);
  const stage = (n: number) => o.stages[n - 1];
  const canReview = !readOnly && can('start:review') && open;

  return (
    <div className="page">
      <Link to="/start" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Onboardings</Link>
      <PageHeader eyebrow={`${o.client_type} · owner ${o.owner_name ?? '—'}`} title={o.client_name}
        description={`${o.primary_contact_name ?? 'No contact'}${o.primary_contact_email ? ` <${o.primary_contact_email}>` : ''} · stage ${o.current_stage} of 11 · ${o.progress_pct}%`}
        actions={
          <div className="flex items-center gap-2">
            {o.risk_rating && <StatusPill tone={riskTone(o.risk_rating)}>Risk {o.risk_rating}</StatusPill>}
            <StatusPill tone={onboardingTone(o.status)} className="text-[12px]">{STATUS_LABEL[o.status]}</StatusPill>
            <Button size="sm" variant="outline" asChild><Link to={`/clients/${o.client_id}`}>Client record</Link></Button>
            {open && !readOnly && can('start:invite') && <Button size="sm" variant="outline" disabled={busy === 'invite'} onClick={() => void act('invite', () => start.onboardings.invite(o.id), 'Invitation re-sent')}><Mail className="mr-1.5 size-4" /> Re-send link</Button>}
            {open && !readOnly && can('start:review') && <Button size="sm" variant="outline" className="text-error hover:text-error" onClick={() => setWithdrawOpen(true)}><XCircle className="mr-1.5 size-4" /> Withdraw</Button>}
          </div>
        } />
      {inviteUrl && <div className="mb-4 flex items-center gap-2 rounded-[5px] border bg-card px-3 py-2 text-[12px]"><span className="text-muted-foreground">Magic link:</span><code className="min-w-0 flex-1 truncate font-mono text-[11px]">{inviteUrl}</code><Button size="sm" variant="ghost" onClick={() => void navigator.clipboard?.writeText(inviteUrl)}><Copy className="size-3.5" /></Button></div>}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[300px_1fr]">
        {/* Stage rail */}
        <ol className="space-y-1 rounded-[6px] border bg-card p-3">
          {o.stages.map((s) => (
            <li key={s.number} className={`flex items-start gap-2.5 rounded-[5px] px-2 py-1.5 text-[13px] ${s.number === o.current_stage && open ? 'bg-muted' : ''}`}>
              <span className="mt-0.5">{s.status === 'completed' ? <CheckCircle2 className="size-4 text-success" /> : s.status === 'blocked' ? <ShieldAlert className="size-4 text-error" /> : s.status === 'active' ? <Circle className="size-4 text-primary" /> : <Lock className="size-4 text-muted-foreground/50" />}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2"><span className={s.status === 'pending' ? 'text-muted-foreground' : 'font-medium'}>{s.number}. {s.name}</span><span className="text-[11px] text-muted-foreground">{s.actor}</span></div>
                <div className="text-[11px] text-muted-foreground">{s.status === 'completed' && s.completed_at ? `${s.completed_by ?? ''} · ${format(new Date(s.completed_at), 'd MMM HH:mm')}` : s.description}</div>
              </div>
            </li>
          ))}
        </ol>

        {/* Workspace for the current stage + record of the rest */}
        <div className="space-y-4">
          {o.status === 'activated' && <Card className="border-success/40"><CardContent className="flex items-center gap-3 p-5 text-[13px]"><CheckCircle2 className="size-6 text-success" /><div><div className="font-medium">Activated {o.activated_at ? formatDistanceToNow(new Date(o.activated_at), { addSuffix: true }) : ''}</div><div className="text-muted-foreground">The client is Active in the CRM; Practice has scheduled the selected services.</div></div></CardContent></Card>}
          {o.status === 'withdrawn' && <Card className="border-error/40"><CardContent className="p-5 text-[13px]"><div className="font-medium">Withdrawn</div><div className="text-muted-foreground">{o.withdraw_reason}</div></CardContent></Card>}

          {open && stage(o.current_stage).actor === 'prospect' && o.current_stage <= 7 && (
            <Card><CardContent className="p-5 text-[13px]">
              <div className="mb-1 font-medium">Waiting on the prospect — stage {o.current_stage}: {stage(o.current_stage).name}</div>
              <p className="text-muted-foreground">{stage(o.current_stage).description}. They complete this from their magic link; you can also record it on their behalf below (phone or walk-in onboarding).</p>
              {o.current_stage === 4 && <DocumentsReview o={o} canReview={canReview} busy={busy} act={act} />}
              {o.current_stage === 7 && <ProposalPanel o={o} canReview={canReview} busy={busy} act={act} />}
              {o.current_stage !== 4 && o.current_stage !== 7 && <p className="mt-3 text-[12px] text-muted-foreground">Stage {o.current_stage} is captured through the prospect form; use “Re-send link” to nudge them.</p>}
            </CardContent></Card>
          )}
          {open && o.current_stage === 8 && <EngagementPanel o={o} canReview={canReview} busy={busy} act={act} />}
          {open && o.current_stage === 9 && <GatesPanel o={o} canReview={canReview} busy={busy} act={act} />}
          {open && o.current_stage === 10 && <AcceptancePanel o={o} busy={busy} act={act} allowed={!readOnly && can('start:accept')} />}
          {open && o.current_stage === 11 && (
            <Card className="border-primary/40"><CardContent className="p-5 text-[13px]">
              <div className="mb-1 font-medium">Ready to activate</div>
              <p className="mb-3 text-muted-foreground">Activation moves the client to Active in the CRM, emails the prospect, records the metered event and hands the selected services to Practice (if subscribed) as recurring work.</p>
              <Button disabled={busy === 's11' || readOnly || !can('start:activate')} onClick={() => void act('s11', () => start.onboardings.stage11(o.id), 'Client activated')}>Activate client</Button>
            </CardContent></Card>
          )}

          {/* Captured data */}
          <DataCard title="Entity details" data={o.data.entity_details} />
          <DataCard title="Questionnaire" data={o.data.questionnaire} />
          {o.data.related_parties && <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">Related parties</CardTitle></CardHeader><CardContent className="text-[13px]"><ul className="divide-y">{(o.data.related_parties.parties as any[]).map((p, i) => <li key={i} className="flex justify-between py-1.5"><span>{p.name} <span className="text-muted-foreground">· {p.role}</span></span><span className="text-muted-foreground">{p.ownership_pct != null ? `${p.ownership_pct}%` : ''}{p.is_beneficial_owner ? ' · UBO' : ''}</span></li>)}</ul>{!o.data.related_parties.ownership_complete && <p className="mt-2 text-[12px] text-warn">Prospect did not confirm the ownership list is complete.</p>}</CardContent></Card>}
          {o.data.service_selection && <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">Selected services</CardTitle></CardHeader><CardContent className="text-[13px]"><ul className="divide-y">{(o.data.service_selection.services as ServiceOut[]).map((s) => <li key={s.id} className="flex justify-between py-1.5"><span>{s.name}</span><span className="tabular-nums text-muted-foreground">{fmtCents(s.amount_cents)} {BASIS_LABEL[s.basis]}</span></li>)}</ul></CardContent></Card>}
          {o.data.proposal && o.current_stage !== 7 && <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">Proposal · {fmtCents(o.data.proposal.total_cents)} inc GST</CardTitle></CardHeader><CardContent className="text-[13px] text-muted-foreground">{o.data.proposal.accepted_at ? `Accepted by ${o.data.proposal.accepted_by_name} ${formatDistanceToNow(new Date(o.data.proposal.accepted_at), { addSuffix: true })}` : o.data.proposal.declined_at ? 'Declined' : 'Issued, awaiting acceptance'}</CardContent></Card>}
          {o.gates.some((g) => g.status !== 'Not run') && o.current_stage !== 9 && <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">Checks</CardTitle></CardHeader><CardContent className="flex flex-wrap gap-1.5 text-[13px]">{o.gates.map((g) => <StatusPill key={g.gate} tone={gateTone(g.status)}>{g.label}: {g.status}{g.simulated ? ' (sim)' : ''}</StatusPill>)}</CardContent></Card>}
        </div>
      </div>
      <WithdrawDialog open={withdrawOpen} onOpenChange={setWithdrawOpen} onConfirm={(r) => act('withdraw', () => start.onboardings.withdraw(o.id, r), 'Withdrawn')} />
    </div>
  );
}

type Act = (key: string, fn: () => Promise<Detail>, ok?: string) => Promise<void>;

function DataCard({ title, data }: { title: string; data: Record<string, unknown> | undefined }) {
  if (!data) return null;
  return (
    <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">{title}</CardTitle></CardHeader>
      <CardContent className="grid grid-cols-1 gap-x-6 gap-y-1 text-[13px] sm:grid-cols-2">
        {Object.entries(data).filter(([, v]) => v !== null && v !== '' && v !== undefined).map(([k, v]) => <div key={k} className="flex justify-between gap-3 border-b border-dashed py-1"><span className="text-muted-foreground">{k.replace(/_/g, ' ')}</span><span className="text-right">{typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v)}</span></div>)}
      </CardContent>
    </Card>
  );
}

function DocumentsReview({ o, canReview, busy, act }: { o: Detail; canReview: boolean; busy: string | null; act: Act }) {
  const reqs = (o.data.document_requests ?? []) as Array<{ key: string; label: string; required: boolean; document_id: string | null; verified_by: string | null }>;
  const allRequired = reqs.filter((r) => r.required).every((r) => r.document_id);
  return (
    <div className="mt-3">
      <ul className="divide-y rounded-[5px] border">
        {reqs.map((r) => (
          <li key={r.key} className="flex items-center gap-3 px-3 py-2">
            {r.verified_by ? <ShieldCheck className="size-4 text-success" /> : r.document_id ? <Check className="size-4 text-primary" /> : <Circle className="size-4 text-muted-foreground/50" />}
            <span className="flex-1">{r.label}{!r.required && <span className="text-muted-foreground"> · optional</span>}</span>
            <span className="text-[12px] text-muted-foreground">{r.verified_by ? `verified by ${r.verified_by}` : r.document_id ? 'uploaded' : 'awaiting'}</span>
            {r.document_id && !r.verified_by && canReview && <Button size="sm" variant="outline" disabled={busy === r.key} onClick={() => void act(r.key, () => start.onboardings.verifyDoc(o.id, r.key), 'Verified')}>Verify</Button>}
          </li>
        ))}
      </ul>
      {canReview && <Button className="mt-3" disabled={!allRequired || busy === 's4'} onClick={() => void act('s4', () => start.onboardings.stage4(o.id), 'Documents stage complete')}>Verify remaining & complete stage</Button>}
      {!allRequired && <p className="mt-2 text-[12px] text-muted-foreground">Required documents are still outstanding from the prospect.</p>}
    </div>
  );
}

function ProposalPanel({ o, canReview, busy, act }: { o: Detail; canReview: boolean; busy: string | null; act: Act }) {
  const services = (o.data.service_selection?.services ?? []) as ServiceOut[];
  const [lines, setLines] = useState<ProposalLine[]>(() => (o.data.proposal?.lines as ProposalLine[]) ?? services.map((s) => ({ service_id: s.id, name: s.name, basis: s.basis, amount_cents: s.amount_cents, gst: s.gst })));
  const [terms, setTerms] = useState<string>(o.data.proposal?.terms ?? 'Fees are billed in advance and are exclusive of disbursements. Either party may end the engagement with 30 days notice.');
  const [acceptName, setAcceptName] = useState(o.primary_contact_name ?? '');
  const sub = lines.reduce((a, l) => a + l.amount_cents, 0); const gst = lines.reduce((a, l) => a + (l.gst ? Math.round(l.amount_cents * 0.1) : 0), 0);
  const issued = !!o.data.proposal;
  return (
    <div className="mt-3 space-y-3">
      <div className="rounded-[5px] border">
        {lines.map((l, i) => (
          <div key={i} className="grid grid-cols-[1fr_120px_130px] items-center gap-2 border-b px-3 py-1.5 last:border-0">
            <span>{l.name}</span><span className="text-[12px] text-muted-foreground">{BASIS_LABEL[l.basis as ServiceOut['basis']] ?? l.basis}</span>
            <Input type="number" className="h-8 text-right" value={(l.amount_cents / 100).toString()} disabled={issued || !canReview} onChange={(e) => setLines((ls) => ls.map((x, j) => (j === i ? { ...x, amount_cents: Math.round(Number(e.target.value || 0) * 100) } : x)))} />
          </div>
        ))}
        <div className="flex justify-end gap-6 px-3 py-2 text-[12px] text-muted-foreground"><span>Subtotal {fmtCents(sub)}</span><span>GST {fmtCents(gst)}</span><span className="font-medium text-foreground">Total {fmtCents(sub + gst)}</span></div>
      </div>
      <Textarea rows={2} value={terms} disabled={issued || !canReview} onChange={(e) => setTerms(e.target.value)} />
      {!issued && canReview && <Button disabled={busy === 'prop' || lines.length === 0} onClick={() => void act('prop', () => start.onboardings.proposal(o.id, { lines, terms }), 'Proposal issued and emailed')}>Issue proposal</Button>}
      {issued && (
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <StatusPill tone={o.data.proposal.declined_at ? 'error' : 'info'}>{o.data.proposal.declined_at ? 'Declined by prospect' : `Issued ${formatDistanceToNow(new Date(o.data.proposal.issued_at), { addSuffix: true })} · awaiting acceptance`}</StatusPill>
          {canReview && <><Input className="h-8 w-[200px]" placeholder="Accepted by (name)" value={acceptName} onChange={(e) => setAcceptName(e.target.value)} /><Button size="sm" variant="outline" disabled={!acceptName.trim() || busy === 's7'} onClick={() => void act('s7', () => start.onboardings.stage7(o.id, acceptName.trim(), true), 'Acceptance recorded')}>Record acceptance</Button></>}
          {canReview && o.data.proposal.declined_at && <Button size="sm" variant="outline" onClick={() => { /* re-open editing */ }} disabled>Re-issue: adjust lines above after reload</Button>}
        </div>
      )}
    </div>
  );
}

function EngagementPanel({ o, canReview, busy, act }: { o: Detail; canReview: boolean; busy: string | null; act: Act }) {
  const entitled = useSession((s) => s.entitled);
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [docId, setDocId] = useState('');
  const [requireId, setRequireId] = useState(false);
  const [message, setMessage] = useState('Please review and sign your letter of engagement.');
  useEffect(() => { void platform.documents.list(o.client_id).then(setDocs).catch(() => undefined); }, [o.client_id]);
  const upload = async (f: File | undefined) => { if (!f) return; try { const d = await platform.documents.upload(f, { clientId: o.client_id, kind: 'agreement' }); setDocs((x) => [d, ...x]); setDocId(d.id); } catch (e) { toast.error(describeError(e)); } };
  if (!entitled('sign')) return <Card className="border-warn/50"><CardContent className="p-5 text-[13px]"><div className="font-medium">Stage 8 needs the Sign module</div><p className="text-muted-foreground">The letter of engagement is sent for signature through EnTIQ Sign. <Link to="/hq/modules/sign" className="text-primary hover:underline">Add Sign</Link> to continue.</p></CardContent></Card>;
  return (
    <Card><CardContent className="space-y-3 p-5 text-[13px]">
      <div className="font-medium">Stage 8 — send the letter of engagement</div>
      <p className="text-muted-foreground">Pick (or upload) the compiled letter. It is sent to {o.primary_contact_name ?? 'the primary contact'} through Sign; the signed copy is sealed and the stage-9 signature gate reads it.</p>
      <div className="flex gap-2">
        <Select value={docId || 'none'} onValueChange={(v) => setDocId(v === 'none' ? '' : v)}><SelectTrigger className="flex-1"><SelectValue placeholder="Choose a document" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{docs.map((d) => <SelectItem key={d.id} value={d.id}>{d.filename}</SelectItem>)}</SelectContent></Select>
        <label className="inline-flex cursor-pointer items-center rounded-[5px] border px-3 text-[13px] hover:bg-muted"><input type="file" className="hidden" onChange={(e) => void upload(e.target.files?.[0])} />Upload</label>
      </div>
      <Textarea rows={2} value={message} onChange={(e) => setMessage(e.target.value)} />
      <label className={`flex items-center gap-2 ${entitled('verify') ? '' : 'opacity-60'}`}><Checkbox checked={requireId} disabled={!entitled('verify')} onCheckedChange={(v) => setRequireId(!!v)} /> Require a verified identity before signing{!entitled('verify') && ' (needs Verify)'}</label>
      {canReview && <Button disabled={!docId || busy === 's8'} onClick={() => void act('s8', () => start.onboardings.stage8(o.id, { document_id: docId, message, require_identity: requireId }), 'Engagement letter sent for signature')}>Send for signature</Button>}
    </CardContent></Card>
  );
}

function GatesPanel({ o, canReview, busy, act }: { o: Detail; canReview: boolean; busy: string | null; act: Act }) {
  const [mandate, setMandate] = useState<{ method: 'direct_debit' | 'card' | 'invoice'; reference: string; account_name: string }>({ method: 'direct_debit', reference: '', account_name: o.client_name });
  return (
    <Card><CardContent className="space-y-3 p-5 text-[13px]">
      <div className="flex items-center justify-between"><div className="font-medium">Stage 9 — external checks</div>{canReview && <Button size="sm" variant="outline" disabled={busy === 'gates'} onClick={() => void act('gates', () => start.onboardings.runGates(o.id), 'Checks refreshed')}><RefreshCw className="mr-1.5 size-4" /> Run checks</Button>}</div>
      <p className="text-muted-foreground">Nothing is re-implemented here: identity and screening come from Verify, the signature from Sign, and the mandate from the prospect. Simulated results pass the gate but are flagged so acceptance can weigh them.</p>
      <ul className="divide-y rounded-[5px] border">
        {o.gates.map((g) => (
          <li key={g.gate} className="flex items-start gap-3 px-3 py-2">
            <StatusPill tone={gateTone(g.status)} className="mt-0.5 w-[84px] justify-center">{g.status}</StatusPill>
            <div className="min-w-0 flex-1"><div className="font-medium">{g.label}{g.simulated && <span className="ml-1.5 text-[11px] font-normal text-muted-foreground">simulated</span>}</div><div className="text-[12px] text-muted-foreground">{g.detail ?? 'Not run yet'}</div></div>
            {g.gate === 'kyc' || g.gate === 'aml' ? <Button size="sm" variant="ghost" asChild><Link to={`/verify/clients/${o.client_id}`}>Open Verify</Link></Button> : g.gate === 'esign' && o.sign_agreement_id ? <Button size="sm" variant="ghost" asChild><Link to={`/sign/agreements/${o.sign_agreement_id}`}>Open Sign</Link></Button> : null}
          </li>
        ))}
      </ul>
      {o.gates.find((g) => g.gate === 'mandate')?.status !== 'Passed' && canReview && (
        <div className="rounded-[5px] border p-3">
          <div className="mb-2 text-[12px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Record payment mandate on the prospect's behalf</div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <Select value={mandate.method} onValueChange={(v) => setMandate({ ...mandate, method: v as typeof mandate.method })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="direct_debit">Direct debit</SelectItem><SelectItem value="card">Card</SelectItem><SelectItem value="invoice">Invoice (net 14)</SelectItem></SelectContent></Select>
            <Input placeholder="Reference" value={mandate.reference} onChange={(e) => setMandate({ ...mandate, reference: e.target.value })} />
            <Input placeholder="Account name" value={mandate.account_name} onChange={(e) => setMandate({ ...mandate, account_name: e.target.value })} />
          </div>
          <Button size="sm" className="mt-2" disabled={busy === 'mandate'} onClick={() => void act('mandate', () => start.onboardings.mandate(o.id, { ...mandate, accepted_terms: true }), 'Mandate recorded')}>Record mandate</Button>
        </div>
      )}
    </CardContent></Card>
  );
}

function AcceptancePanel({ o, busy, act, allowed }: { o: Detail; busy: string | null; act: Act; allowed: boolean }) {
  const [f, setF] = useState({ partner_signoff: false, margin_ok: false, risk_signoff: false, notes: '' });
  const sim = o.gates.filter((g) => g.simulated).map((g) => g.label);
  return (
    <Card><CardContent className="space-y-3 p-5 text-[13px]">
      <div className="font-medium">Stage 10 — internal acceptance</div>
      {sim.length > 0 && <p className="rounded-[4px] border border-warn/50 bg-warn-bg/40 px-3 py-2 text-[12px]">Some checks passed on simulated providers ({sim.join(', ')}). Confirm you accept that before signing off.</p>}
      <div className="grid gap-2">
        <label className="flex items-center gap-2"><Checkbox checked={f.partner_signoff} onCheckedChange={(v) => setF({ ...f, partner_signoff: !!v })} disabled={!allowed} /> Partner has reviewed the engagement and approves acceptance</label>
        <label className="flex items-center gap-2"><Checkbox checked={f.margin_ok} onCheckedChange={(v) => setF({ ...f, margin_ok: !!v })} disabled={!allowed} /> Fee proposal meets the practice's margin policy{o.proposal_total_cents != null && <span className="text-muted-foreground"> ({fmtCents(o.proposal_total_cents)} inc GST)</span>}</label>
        <label className="flex items-center gap-2"><Checkbox checked={f.risk_signoff} onCheckedChange={(v) => setF({ ...f, risk_signoff: !!v })} disabled={!allowed} /> Client risk rating{o.risk_rating ? ` (${o.risk_rating})` : ''} reviewed and accepted</label>
      </div>
      <Textarea rows={2} placeholder="Acceptance notes" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} disabled={!allowed} />
      <Button disabled={!allowed || !(f.partner_signoff && f.margin_ok && f.risk_signoff) || busy === 's10'} onClick={() => void act('s10', () => start.onboardings.stage10(o.id, { ...f, notes: f.notes || null }), 'Accepted')}>Record acceptance</Button>
      {!allowed && <p className="text-[12px] text-muted-foreground">Acceptance needs the start:accept permission (owners and admins).</p>}
    </CardContent></Card>
  );
}

function WithdrawDialog({ open, onOpenChange, onConfirm }: { open: boolean; onOpenChange: (o: boolean) => void; onConfirm: (reason: string) => Promise<void> }) {
  const [reason, setReason] = useState('');
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[460px]">
      <DialogHeader><DialogTitle>Withdraw this onboarding?</DialogTitle></DialogHeader>
      <p className="text-[13px] text-muted-foreground">The magic link stops working and the client moves to Lost in the pipeline. Everything captured so far is kept on the record.</p>
      <div className="grid gap-1.5 text-[13px]"><Label htmlFor="wd">Reason</Label><Input id="wd" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Chose another firm" /></div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="destructive" disabled={reason.trim().length < 2} onClick={() => { void onConfirm(reason.trim()); onOpenChange(false); }}>Withdraw</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
