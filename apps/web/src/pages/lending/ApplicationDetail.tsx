import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { ArrowLeft, Check, ClipboardList, Plus, Send } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Textarea } from '@entiq/ui/textarea';
import { getModule } from '@entiq/modules';
import { lending, PIPELINE, PURPOSE_LABEL, STAGE_LABEL, fmtRate, stageTone, type ApplicationDetail as Detail, type LendingStage } from '@/api/lending';
import { fmtCents } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

export function ApplicationDetail() {
  const { id = '' } = useParams();
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [a, setA] = useState<Detail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [cond, setCond] = useState({ title: '', kind: 'precedent' as 'precedent' | 'subsequent', owner_side: 'client' as 'client' | 'practice' | 'lender', due_on: '' });
  const [serv, setServ] = useState({ ebitda: '', existing: '', notes: '' });

  const load = async () => { try { setA(await lending.applications.get(id)); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('lending')) void load(); }, [id]);
  if (!entitled('lending')) return <UpsellPage module={getModule('lending')} />;
  if (!a) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;

  const act = async (key: string, fn: () => Promise<Detail>, ok?: string) => { setBusy(key); try { setA(await fn()); if (ok) toast.success(ok); } catch (e) { toast.error(describeError(e)); } finally { setBusy(null); } };
  const open = !['settled', 'declined', 'withdrawn'].includes(a.stage);
  const canEdit = !readOnly && can('lending:intake') && open;
  const next = PIPELINE[Math.min(PIPELINE.indexOf(a.stage as never) + 1, PIPELINE.length - 1)] as LendingStage;

  return (
    <div className="page">
      <Link to="/lending" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Lending</Link>
      <PageHeader eyebrow={`${a.reference} · ${PURPOSE_LABEL[a.purpose]}`} title={`${fmtCents(a.amount_cents)} — ${a.client_name}`}
        description={`${a.term_months ?? '—'} months at ${fmtRate(a.rate_bps)}${a.repayment_cents ? ` · ${fmtCents(a.repayment_cents)}/month` : ''}${a.lender ? ` · ${a.lender}` : ''}${a.dscr ? ` · DSCR ${a.dscr}` : ''} · ${a.readiness_pct}% ready`}
        actions={<div className="flex flex-wrap items-center gap-2">
          <StatusPill tone={stageTone(a.stage)} className="text-[12px]">{STAGE_LABEL[a.stage]}</StatusPill>
          <Button size="sm" variant="outline" asChild><Link to={`/clients/${a.client_id}`}>Client</Link></Button>
          {a.request_pack_id && <Button size="sm" variant="outline" asChild><Link to={`/requests/${a.request_pack_id}`}>Documents</Link></Button>}
          {open && canEdit && a.stage !== 'settled' && <Button size="sm" disabled={busy === 'next'} onClick={() => void act('next', () => lending.applications.setStage(a.id, next), `Moved to ${STAGE_LABEL[next]}`)}>Move to {STAGE_LABEL[next]}</Button>}
          {open && !readOnly && can('lending:approve') && <Button size="sm" variant="outline" className="text-error hover:text-error" onClick={() => { const r = prompt('Decline — reason?'); if (r) void act('decl', () => lending.applications.setStage(a.id, 'declined', r), 'Declined'); }}>Decline</Button>}
        </div>} />

      {/* pipeline strip */}
      <ol className="mb-5 flex flex-wrap gap-1 text-[12px]">
        {PIPELINE.map((st, i) => <li key={st} className={`rounded-[4px] border px-2 py-1 ${a.stage === st ? 'border-primary bg-primary/10 font-medium' : i < a.stage_index ? 'text-muted-foreground line-through' : 'text-muted-foreground'}`}>{STAGE_LABEL[st]}</li>)}
      </ol>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          {a.documents_outstanding.length > 0 && (
            <Card className="border-warn/50"><CardHeader className="pb-2"><CardTitle className="text-[15px]">Waiting on the client</CardTitle></CardHeader>
              <CardContent className="text-[13px]"><ul className="list-disc pl-4 text-muted-foreground">{a.documents_outstanding.map((d) => <li key={d}>{d}</li>)}</ul>
                {a.request_pack_id ? <Button size="sm" variant="outline" className="mt-3" asChild><Link to={`/requests/${a.request_pack_id}`}>Open the request</Link></Button>
                  : canEdit && <Button size="sm" className="mt-3" onClick={() => void act('req', () => lending.applications.openRequest(a.id), 'Checklist sent')}><Send className="mr-1.5 size-4" /> Send the checklist</Button>}
              </CardContent>
            </Card>
          )}
          {!a.request_pack_id && a.documents_outstanding.length === 0 && canEdit && (
            <Card><CardContent className="flex items-center justify-between py-4 text-[13px]"><span className="text-muted-foreground">No document checklist has been sent for this application.</span><Button size="sm" variant="outline" onClick={() => void act('req', () => lending.applications.openRequest(a.id), 'Checklist sent')}><Send className="mr-1.5 size-4" /> Send checklist</Button></CardContent></Card>
          )}

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-[15px]">Serviceability</CardTitle></CardHeader>
            <CardContent className="text-[13px]">
              {Object.keys(a.serviceability).length > 0 && (
                <ul className="mb-3 divide-y">
                  {a.serviceability.ebitda_cents != null && <Row k="EBITDA" v={`${fmtCents(a.serviceability.ebitda_cents as number)}${a.serviceability.ebitda_source ? ` · ${a.serviceability.ebitda_source}` : ''}`} />}
                  {a.serviceability.existing_repayments_cents != null && <Row k="Existing repayments" v={`${fmtCents(a.serviceability.existing_repayments_cents as number)} / month`} />}
                  {a.repayment_cents != null && <Row k="Proposed repayment" v={`${fmtCents(a.repayment_cents)} / month`} />}
                  {a.dscr != null && <Row k="Debt service cover" v={<span className={a.dscr >= 1.5 ? 'text-success' : a.dscr >= 1.2 ? 'text-warn' : 'text-error'}>{a.dscr}×</span>} />}
                  {a.serviceability.notes ? <Row k="Notes" v={String(a.serviceability.notes)} /> : null}
                </ul>
              )}
              {canEdit && (
                <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
                  <div className="grid gap-1"><Label className="text-[11px]">EBITDA ($, blank = from Advisory)</Label><Input type="number" value={serv.ebitda} onChange={(e) => setServ({ ...serv, ebitda: e.target.value })} /></div>
                  <div className="grid gap-1"><Label className="text-[11px]">Existing repayments ($/mo)</Label><Input type="number" value={serv.existing} onChange={(e) => setServ({ ...serv, existing: e.target.value })} /></div>
                  <Button size="sm" disabled={busy === 'assess'} onClick={() => void act('assess', () => lending.applications.assess(a.id, { ebitda_cents: serv.ebitda ? Math.round(Number(serv.ebitda) * 100) : null, existing_repayments_cents: serv.existing ? Math.round(Number(serv.existing) * 100) : null, notes: serv.notes || null, use_snapshot: true }), 'Assessed')}>Assess</Button>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between pb-2"><CardTitle className="flex items-center gap-2 text-[15px]"><ClipboardList className="size-4 text-primary" /> Conditions · {a.conditions_open} open</CardTitle></CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y">
                {a.conditions.map((c) => (
                  <li key={c.id} className="flex items-start gap-3 px-6 py-2.5 text-[13px]">
                    <StatusPill tone={c.status !== 'open' ? 'success' : c.kind === 'precedent' ? 'warn' : 'neutral'} className="mt-0.5">{c.status === 'open' ? c.kind : c.status}</StatusPill>
                    <div className="min-w-0 flex-1"><div className="font-medium">{c.title}</div><div className="text-[12px] text-muted-foreground">{c.owner_side}{c.due_on ? ` · due ${format(new Date(c.due_on), 'd MMM')}` : ''}{c.note ? ` · ${c.note}` : ''}{c.satisfied_by_name ? ` · by ${c.satisfied_by_name}` : ''}</div></div>
                    {c.status === 'open' && canEdit && <Button size="sm" variant="outline" className="h-7" onClick={() => void act(c.id, () => lending.applications.satisfyCondition(a.id, c.id, { note: 'Received and filed' }), 'Condition satisfied')}><Check className="size-3.5" /></Button>}
                  </li>
                ))}
                {a.conditions.length === 0 && <li className="px-6 py-6 text-center text-[13px] text-muted-foreground">No conditions recorded.</li>}
              </ul>
              {!readOnly && can('lending:approve') && open && (
                <div className="grid grid-cols-[1fr_130px_130px_130px_auto] items-end gap-2 border-t px-6 py-3">
                  <Input className="h-8" placeholder="Add a condition" value={cond.title} onChange={(e) => setCond({ ...cond, title: e.target.value })} />
                  <Select value={cond.kind} onValueChange={(v) => setCond({ ...cond, kind: v as typeof cond.kind })}><SelectTrigger className="h-8"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="precedent">Precedent</SelectItem><SelectItem value="subsequent">Subsequent</SelectItem></SelectContent></Select>
                  <Select value={cond.owner_side} onValueChange={(v) => setCond({ ...cond, owner_side: v as typeof cond.owner_side })}><SelectTrigger className="h-8"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="client">Client</SelectItem><SelectItem value="practice">Practice</SelectItem><SelectItem value="lender">Lender</SelectItem></SelectContent></Select>
                  <Input className="h-8" type="date" value={cond.due_on} onChange={(e) => setCond({ ...cond, due_on: e.target.value })} />
                  <Button size="sm" disabled={cond.title.trim().length < 3} onClick={() => { void act('cond', () => lending.applications.addCondition(a.id, { title: cond.title.trim(), kind: cond.kind, owner_side: cond.owner_side, due_on: cond.due_on || null }), 'Condition added'); setCond({ ...cond, title: '', due_on: '' }); }}><Plus className="size-3.5" /></Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          {a.stage === 'conditions' && a.conditions_blocking === 0 && !readOnly && can('lending:settle') && (
            <Card className="border-success/40"><CardContent className="py-4 text-[13px]"><div className="mb-2 font-medium">All conditions precedent are cleared.</div><Button size="sm" onClick={() => void act('settle', () => lending.applications.setStage(a.id, 'settled', 'Settled'), 'Settled')}>Record settlement</Button></CardContent></Card>
          )}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-[15px]">History</CardTitle></CardHeader>
            <CardContent className="p-0"><ol className="divide-y">
              {a.events.map((e) => <li key={e.id} className="px-4 py-2 text-[13px]"><div className="text-[11px] tabular-nums text-muted-foreground">{format(new Date(e.at), 'd MMM yyyy HH:mm')}</div><div>{e.to_stage ? `${e.from_stage ?? '—'} → ${STAGE_LABEL[e.to_stage as LendingStage] ?? e.to_stage}` : e.kind.replace(/_/g, ' ')}{e.note ? ` — ${e.note}` : ''}</div><div className="text-[12px] text-muted-foreground">{e.actor_label}</div></li>)}
            </ol></CardContent>
          </Card>
          {a.description && <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">What is being financed</CardTitle></CardHeader><CardContent className="text-[13px]">{a.description}</CardContent></Card>}
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) { return <li className="flex justify-between gap-3 py-1.5"><span className="text-muted-foreground">{k}</span><span className="text-right">{v}</span></li>; }
