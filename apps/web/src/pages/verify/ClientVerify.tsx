import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { ArrowLeft, ExternalLink, Fingerprint, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { getModule } from '@entiq/modules';
import { verify, IDENTITY_LABEL, SCREENING_LABEL, type ClientVerifyOut, type PartyStatus, type RiskOut } from '@/api/verify';
import { fmtDate } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, riskTone } from '@/components/StatusPill';
import { ProviderBadge, verificationTone } from './VerifyHome';
import { ReviewDialog, screeningTone } from './Screening';

/** Every check for one client: parties (identity + screening), the entity itself, and the risk rating with its reasoning. */
export function ClientVerify() {
  const { id = '' } = useParams();
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [data, setData] = useState<ClientVerifyOut | null>(null);
  const [history, setHistory] = useState<RiskOut[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [reviewing, setReviewing] = useState<ClientVerifyOut['screenings'][number] | null>(null);

  const load = async () => {
    try { const [d, h] = await Promise.all([verify.client(id), verify.risk.history(id)]); setData(d); setHistory(h); }
    catch (e) { toast.error('Could not load checks', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('verify')) void load(); }, [id]);
  if (!entitled('verify')) return <UpsellPage module={getModule('verify')} />;
  if (!data) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;

  const run = async (key: string, fn: () => Promise<unknown>, ok: string) => {
    setBusy(key);
    try { await fn(); toast.success(ok); await load(); } catch (e) { toast.error(describeError(e)); } finally { setBusy(null); }
  };
  const canRun = !readOnly && can('verify:run');
  const partyVerification = (p: PartyStatus) => data.verifications.find((v) => v.contact_id === p.contact_id && v.status !== 'cancelled');
  const partyScreening = (p: PartyStatus) => data.screenings.find((s) => s.contact_id === p.contact_id);

  return (
    <div className="page">
      <Link to={`/clients/${id}`} className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Back to {data.client_name}</Link>
      <PageHeader eyebrow={`Verify · ${data.client_type}`} title={data.client_name}
        description="Identity checks and AML screening for the entity and each related party, and the risk rating derived from them."
        actions={<ProviderBadge providers={data.providers} />} />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          {/* Parties */}
          <Card>
            <CardHeader className="flex-row items-center justify-between pb-3"><CardTitle className="text-[15px]">Related parties · {data.parties.length}</CardTitle></CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y">
                {data.parties.map((p) => { const v = partyVerification(p); const s = partyScreening(p); return (
                  <li key={p.contact_id} className="grid grid-cols-1 gap-2 px-6 py-3 text-[13px] md:grid-cols-[1fr_auto_auto] md:items-center">
                    <div className="min-w-0"><div className="truncate font-medium">{p.name}</div><div className="text-[12px] text-muted-foreground">{p.role ?? 'Contact'}</div></div>
                    <div className="flex items-center gap-2">
                      <StatusPill tone={p.identity_status === 'verified' ? 'success' : p.identity_status === 'failed' ? 'error' : p.identity_status === 'in_progress' ? 'info' : 'neutral'}><Fingerprint className="size-3" /> {IDENTITY_LABEL[p.identity_status]}{p.identity_simulated ? ' (sim)' : ''}</StatusPill>
                      <StatusPill tone={screeningTone(p.screening_status)}><Search className="size-3" /> {SCREENING_LABEL[p.screening_status]}{p.screening_simulated ? ' (sim)' : ''}</StatusPill>
                    </div>
                    <div className="flex items-center justify-end gap-1.5">
                      {v?.status === 'in_progress' && v.verification_url && <Button size="sm" variant="ghost" asChild><a href={v.verification_url} target="_blank" rel="noreferrer"><ExternalLink className="mr-1 size-3.5" /> Link</a></Button>}
                      {v?.status === 'in_progress' && canRun && <Button size="sm" variant="ghost" disabled={busy === `r${p.contact_id}`} onClick={() => void run(`r${p.contact_id}`, () => verify.verifications.refresh(v.id), 'Status refreshed')}><RefreshCw className="mr-1 size-3.5" /> Refresh</Button>}
                      {canRun && p.identity_status !== 'in_progress' && <Button size="sm" variant="outline" disabled={busy === `v${p.contact_id}`} onClick={() => void run(`v${p.contact_id}`, () => verify.verifications.start(id, { subject_type: 'individual', contact_id: p.contact_id }), 'Identity verification started')}>{p.identity_status === 'verified' ? 'Re-verify' : 'Verify identity'}</Button>}
                      {canRun && <Button size="sm" variant="outline" disabled={busy === `s${p.contact_id}`} onClick={() => void run(`s${p.contact_id}`, () => verify.screenings.run(id, { contact_id: p.contact_id }), 'Screening complete')}>{s ? 'Re-screen' : 'Screen'}</Button>}
                      {s?.status === 'potential_match' && can('verify:review') && !readOnly && <Button size="sm" onClick={() => setReviewing(s)}>Review hit</Button>}
                    </div>
                  </li>
                ); })}
                {data.parties.length === 0 && <li className="px-6 py-10 text-center text-[13px] text-muted-foreground">No contacts on this client yet. Add directors, trustees or beneficial owners on the client record, then verify them here.</li>}
              </ul>
            </CardContent>
          </Card>

          {/* Entity */}
          <Card>
            <CardHeader className="flex-row items-center justify-between pb-3">
              <CardTitle className="text-[15px]">The {data.client_type.toLowerCase()} itself</CardTitle>
              <div className="flex gap-1.5">
                {canRun && data.client_type !== 'Individual' && <Button size="sm" variant="outline" disabled={busy === 'ev'} onClick={() => void run('ev', () => verify.verifications.start(id, { subject_type: 'entity' }), 'Entity verification started')}>{data.entity_verification ? 'Re-verify entity' : 'Verify entity (KYB)'}</Button>}
                {canRun && <Button size="sm" variant="outline" disabled={busy === 'es'} onClick={() => void run('es', () => verify.screenings.run(id, {}), 'Entity screened')}>{data.entity_screening ? 'Re-screen' : 'Screen entity'}</Button>}
              </div>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-3 text-[13px] sm:grid-cols-2">
              <div className="rounded-[5px] border p-3">
                <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Entity verification</div>
                {data.entity_verification ? <><StatusPill tone={verificationTone(data.entity_verification.status)}>{data.entity_verification.status.replace('_', ' ')}{data.entity_verification.simulated ? ' (sim)' : ''}</StatusPill><div className="mt-1.5 text-[12px] text-muted-foreground">{data.entity_verification.provider} · {formatDistanceToNow(new Date(data.entity_verification.created_at), { addSuffix: true })}{data.entity_verification.failure_reason ? ` · ${data.entity_verification.failure_reason}` : ''}</div></> : <span className="text-muted-foreground">Not run{data.client_type === 'Individual' ? ' — individuals are verified as parties above' : ''}.</span>}
              </div>
              <div className="rounded-[5px] border p-3">
                <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Entity screening</div>
                {data.entity_screening ? <><div className="flex items-center gap-2"><StatusPill tone={screeningTone(data.entity_screening.status)}>{SCREENING_LABEL[data.entity_screening.status]}{data.entity_screening.simulated ? ' (sim)' : ''}</StatusPill>{data.entity_screening.status === 'potential_match' && can('verify:review') && !readOnly && <Button size="sm" variant="ghost" onClick={() => setReviewing(data.entity_screening)}>Review</Button>}</div><div className="mt-1.5 text-[12px] text-muted-foreground">{data.entity_screening.match_count} match{data.entity_screening.match_count === 1 ? '' : 'es'} · {data.entity_screening.provider} · {formatDistanceToNow(new Date(data.entity_screening.screened_at), { addSuffix: true })}</div></> : <span className="text-muted-foreground">Not screened.</span>}
              </div>
            </CardContent>
          </Card>

          {/* History */}
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-[15px]">Rating history</CardTitle></CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y">
                {history.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 px-6 py-2.5 text-[13px]">
                    <StatusPill tone={riskTone(r.rating)}>{r.rating}</StatusPill><span className="tabular-nums text-muted-foreground">{r.score} pts</span>
                    <div className="min-w-0 flex-1 truncate text-[12px] text-muted-foreground">{r.factors.map((f) => f.label).join(' · ')}</div>
                    <span className="shrink-0 text-[12px] text-muted-foreground">{r.assessed_by_name ?? 'System'} · {fmtDate(r.assessed_at)}</span>
                  </li>
                ))}
                {history.length === 0 && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">Not yet assessed.</li>}
              </ul>
            </CardContent>
          </Card>
        </div>

        {/* Risk */}
        <div className="space-y-4">
          <Card className={data.risk?.rating === 'High' ? 'border-error/50' : ''}>
            <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-[15px]"><ShieldCheck className="size-4 text-primary" /> Risk rating</CardTitle></CardHeader>
            <CardContent className="text-[13px]">
              {data.risk ? (
                <>
                  <div className="mb-3 flex items-end justify-between"><div className="text-[28px] font-semibold leading-none"><StatusPill tone={riskTone(data.risk.rating)} className="text-[15px] px-3 py-1">{data.risk.rating}</StatusPill></div><div className="text-right text-[12px] text-muted-foreground">score {data.risk.score}<br />{data.risk.method}</div></div>
                  <ul className="divide-y rounded-[5px] border">
                    {data.risk.factors.map((f) => <li key={f.factor} className="flex items-start justify-between gap-2 px-3 py-2"><div><div>{f.label}</div>{f.detail && <div className="text-[12px] text-muted-foreground">{f.detail}</div>}</div><span className={`shrink-0 tabular-nums ${f.points > 0 ? 'text-error' : f.points < 0 ? 'text-success' : 'text-muted-foreground'}`}>{f.points > 0 ? '+' : ''}{f.points}</span></li>)}
                  </ul>
                  <div className="mt-3 text-[12px] text-muted-foreground">Assessed {fmtDate(data.risk.assessed_at)} by {data.risk.assessed_by_name ?? 'System'} · next review {fmtDate(data.risk.next_review_at)}</div>
                  {data.risk.notes && <p className="mt-2 rounded-[4px] bg-muted px-3 py-2 text-[12px]">{data.risk.notes}</p>}
                </>
              ) : <p className="text-muted-foreground">Not rated yet. Run the checks above, then assess — the rating is explained factor by factor and written onto the CRM record.</p>}
              {canRun && <Button className="mt-4 w-full" variant={data.risk ? 'outline' : 'default'} disabled={busy === 'risk'} onClick={() => void run('risk', () => verify.risk.assess(id), 'Risk assessed')}>{data.risk ? 'Re-assess now' : 'Assess risk'}</Button>}
            </CardContent>
          </Card>
          <p className="px-1 text-[12px] leading-5 text-muted-foreground">Scores: 0–29 Low · 30–59 Medium · 60+ High. Confirmed screening matches, unreviewed hits, unverified parties and unknown ownership all add points; the rules version is recorded with every assessment.</p>
        </div>
      </div>

      <ReviewDialog s={reviewing} onClose={() => setReviewing(null)} onDone={load} />
    </div>
  );
}
