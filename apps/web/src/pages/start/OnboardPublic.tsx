import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { CheckCircle2, Circle, FileUp, Lock, ShieldAlert } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Checkbox } from '@entiq/ui/checkbox';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Textarea } from '@entiq/ui/textarea';
import { start, BASIS_LABEL, type PublicView, type EntityDetailsIn, type PartyIn, type EntityType } from '@/api/start';
import { ApiError } from '@/api/client';
import { fmtCents } from '@/api/platform';

const ENTITY_TYPES: EntityType[] = ['Company', 'Trust', 'Individual', 'Partnership', 'SMSF', 'Other'];
const ROLES: PartyIn['role'][] = ['Director', 'Secretary', 'Shareholder', 'Trustee', 'Beneficiary', 'Appointor', 'Partner', 'Member', 'Owner', 'Other'];

/** The prospect's onboarding — reached from the emailed magic link (/onboard/{token}), no login. Stages 1–7 plus the payment mandate. */
export function OnboardPublic() {
  const { token = '' } = useParams();
  const [v, setV] = useState<PublicView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { start.public.view(token).then(setV).catch((e: unknown) => setErr(describe(e))); }, [token]);
  const run = async (fn: () => Promise<PublicView>) => { setBusy(true); setActionErr(null); try { setV(await fn()); window.scrollTo({ top: 0 }); } catch (e) { setActionErr(describe(e)); } finally { setBusy(false); } };

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="border-b bg-card"><div className="mx-auto flex h-14 max-w-[880px] items-center gap-3 px-4"><img src="/favicon.svg" alt="" className="size-6" /><span className="text-[14px] font-semibold">{v?.practice_name ?? 'EnTIQ'}</span><span className="ml-auto text-[12px] text-muted-foreground">Client onboarding</span></div></header>
      <main className="mx-auto max-w-[880px] px-4 py-6">
        {err && <div className="rounded-[6px] border bg-card p-8 text-center"><ShieldAlert className="mx-auto mb-3 size-8 text-muted-foreground" /><h1 className="text-[18px] font-semibold">{err}</h1><p className="mt-2 text-[13px] text-muted-foreground">Ask the practice to send you a fresh link.</p></div>}
        {!v && !err && <p className="text-[13px] text-muted-foreground">Loading…</p>}
        {v && (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-[240px_1fr]">
            <aside>
              <h1 className="mb-1 text-[18px] font-semibold leading-tight">{v.prospect_name}</h1>
              <p className="mb-4 text-[12px] text-muted-foreground">{v.contact_name ? `Hi ${v.contact_name.split(' ')[0]} — ` : ''}complete the steps below. You can leave and come back with the same link.</p>
              <ol className="space-y-1">
                {v.stages.filter((s) => s.number <= 7).map((s) => (
                  <li key={s.number} className={`flex items-center gap-2 rounded-[5px] px-2 py-1.5 text-[13px] ${s.number === v.current_stage ? 'bg-muted font-medium' : ''}`}>
                    {s.status === 'completed' ? <CheckCircle2 className="size-4 text-success" /> : s.number === v.current_stage ? <Circle className="size-4 text-primary" /> : <Lock className="size-4 text-muted-foreground/40" />}
                    <span className={s.status === 'pending' && s.number !== v.current_stage ? 'text-muted-foreground' : ''}>{s.name}</span>
                  </li>
                ))}
                <li className="flex items-center gap-2 px-2 py-1.5 text-[13px] text-muted-foreground"><Lock className="size-4 opacity-40" /> Engagement, checks & activation — by the practice</li>
              </ol>
            </aside>
            <section className="rounded-[6px] border bg-card p-5">
              {actionErr && <p className="mb-3 rounded-[4px] border border-error/40 bg-error-bg/40 px-3 py-2 text-[12px] text-error">{actionErr}</p>}
              {v.status === 'activated' ? <Done title="You're all set" body={`${v.prospect_name} is now an active client of ${v.practice_name}. Welcome aboard.`} /> :
                v.current_stage === 2 ? <EntityStep v={v} busy={busy} onSubmit={(b) => run(() => start.public.stage2(token, b))} /> :
                v.current_stage === 3 ? <QuestionnaireStep v={v} busy={busy} onSubmit={(a) => run(() => start.public.stage3(token, a))} /> :
                v.current_stage === 4 ? <DocumentsStep v={v} token={token} busy={busy} run={run} /> :
                v.current_stage === 5 ? <PartiesStep v={v} busy={busy} onSubmit={(p, ok) => run(() => start.public.stage5(token, p, ok))} /> :
                v.current_stage === 6 ? <ServicesStep v={v} busy={busy} onSubmit={(ids) => run(() => start.public.stage6(token, ids))} /> :
                v.current_stage === 7 ? <ProposalStep v={v} busy={busy} onDecide={(name, ok) => run(() => start.public.stage7(token, name, ok))} /> :
                <PracticeSideStep v={v} token={token} busy={busy} run={run} />}
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

function describe(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { error?: string; message?: string } | null;
    const code = d?.error ?? '';
    return ({ invalid_link: 'This onboarding link is not valid.', expired: 'This onboarding link has expired.', withdrawn: 'This onboarding has been closed by the practice.' } as Record<string, string>)[code] ?? d?.message ?? e.message ?? 'Something went wrong.';
  }
  return 'Something went wrong.';
}

function Done({ title, body }: { title: string; body: string }) { return <div className="py-8 text-center"><CheckCircle2 className="mx-auto mb-3 size-8 text-success" /><h2 className="text-[18px] font-semibold">{title}</h2><p className="mt-1 text-[13px] text-muted-foreground">{body}</p></div>; }
function StepHeader({ n, title, body }: { n: number; title: string; body: string }) { return <div className="mb-4"><div className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Step {n} of 7</div><h2 className="text-[18px] font-semibold">{title}</h2><p className="text-[13px] text-muted-foreground">{body}</p></div>; }
function F({ label, children, id }: { label: string; children: React.ReactNode; id?: string }) { return <div className="grid gap-1.5 text-[13px]"><Label htmlFor={id}>{label}</Label>{children}</div>; }

function EntityStep({ v, busy, onSubmit }: { v: PublicView; busy: boolean; onSubmit: (b: EntityDetailsIn) => void }) {
  const prev = (v.data.entity_details ?? {}) as Partial<EntityDetailsIn>;
  const [f, setF] = useState<EntityDetailsIn>({ legal_name: prev.legal_name ?? v.prospect_name, trading_name: prev.trading_name ?? '', entity_type: (prev.entity_type as EntityType) ?? 'Company', abn: prev.abn ?? '', acn: prev.acn ?? '', tax_residency: prev.tax_residency ?? 'australia', gst_registered: prev.gst_registered ?? null, industry: prev.industry ?? '', address_line1: prev.address_line1 ?? '', suburb: prev.suburb ?? '', state: prev.state ?? '', postcode: prev.postcode ?? '', contact_name: prev.contact_name ?? v.contact_name ?? '', contact_email: prev.contact_email ?? '', contact_phone: prev.contact_phone ?? '' });
  const set = (k: keyof EntityDetailsIn, val: unknown) => setF((x) => ({ ...x, [k]: val }));
  const valid = f.legal_name.trim() && f.contact_name.trim() && /\S+@\S+\.\S+/.test(f.contact_email);
  return (
    <div>
      <StepHeader n={2} title="Your entity" body="Tell us who we are acting for. ABN/ACN help us match the registry." />
      <div className="grid gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_160px]"><F label="Legal name" id="e-legal"><Input id="e-legal" value={f.legal_name} onChange={(e) => set('legal_name', e.target.value)} /></F><F label="Structure"><Select value={f.entity_type} onValueChange={(x) => set('entity_type', x)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{ENTITY_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select></F></div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3"><F label="Trading name (optional)"><Input value={f.trading_name ?? ''} onChange={(e) => set('trading_name', e.target.value)} /></F><F label="ABN"><Input value={f.abn ?? ''} onChange={(e) => set('abn', e.target.value)} placeholder="51 824 753 556" /></F><F label="ACN (companies)"><Input value={f.acn ?? ''} onChange={(e) => set('acn', e.target.value)} /></F></div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3"><F label="Tax residency"><Select value={f.tax_residency} onValueChange={(x) => set('tax_residency', x)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="australia">Australian resident</SelectItem><SelectItem value="foreign">Foreign resident</SelectItem><SelectItem value="dual">Dual / mixed</SelectItem></SelectContent></Select></F><F label="Registered for GST?"><Select value={f.gst_registered == null ? 'unknown' : f.gst_registered ? 'yes' : 'no'} onValueChange={(x) => set('gst_registered', x === 'unknown' ? null : x === 'yes')}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="unknown">Not sure</SelectItem><SelectItem value="yes">Yes</SelectItem><SelectItem value="no">No</SelectItem></SelectContent></Select></F><F label="Industry"><Input value={f.industry ?? ''} onChange={(e) => set('industry', e.target.value)} /></F></div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[2fr_1fr_80px_100px]"><F label="Address"><Input value={f.address_line1 ?? ''} onChange={(e) => set('address_line1', e.target.value)} /></F><F label="Suburb"><Input value={f.suburb ?? ''} onChange={(e) => set('suburb', e.target.value)} /></F><F label="State"><Input value={f.state ?? ''} onChange={(e) => set('state', e.target.value)} /></F><F label="Postcode"><Input value={f.postcode ?? ''} onChange={(e) => set('postcode', e.target.value)} /></F></div>
        <div className="mt-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Your contact details</div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3"><F label="Full name"><Input value={f.contact_name} onChange={(e) => set('contact_name', e.target.value)} /></F><F label="Email"><Input type="email" value={f.contact_email} onChange={(e) => set('contact_email', e.target.value)} /></F><F label="Phone"><Input value={f.contact_phone ?? ''} onChange={(e) => set('contact_phone', e.target.value)} /></F></div>
      </div>
      <Button className="mt-5" disabled={!valid || busy} onClick={() => onSubmit({ ...f, trading_name: f.trading_name || null, abn: f.abn || null, acn: f.acn || null, industry: f.industry || null, address_line1: f.address_line1 || null, suburb: f.suburb || null, state: f.state || null, postcode: f.postcode || null, contact_phone: f.contact_phone || null })}>Continue</Button>
    </div>
  );
}

function QuestionnaireStep({ v, busy, onSubmit }: { v: PublicView; busy: boolean; onSubmit: (a: Record<string, unknown>) => void }) {
  const [a, setA] = useState<Record<string, unknown>>((v.data.questionnaire as Record<string, unknown>) ?? {});
  const missing = v.questionnaire.filter((q) => q.required && (a[q.key] === undefined || a[q.key] === '' || a[q.key] === null));
  return (
    <div>
      <StepHeader n={3} title="About the business" body="A few questions so we scope the right services and spot anything urgent." />
      <div className="grid gap-4">
        {v.questionnaire.map((q) => (
          <F key={q.key} label={`${q.label}${q.required ? '' : ' (optional)'}`}>
            {q.type === 'text' ? <Textarea rows={2} value={(a[q.key] as string) ?? ''} onChange={(e) => setA({ ...a, [q.key]: e.target.value })} /> :
              q.type === 'select' ? <Select value={(a[q.key] as string) ?? ''} onValueChange={(x) => setA({ ...a, [q.key]: x })}><SelectTrigger><SelectValue placeholder="Choose…" /></SelectTrigger><SelectContent>{q.options?.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}</SelectContent></Select> :
              <div className="flex gap-2">{[true, false].map((b) => <Button key={String(b)} type="button" size="sm" variant={a[q.key] === b ? 'default' : 'outline'} onClick={() => setA({ ...a, [q.key]: b })}>{b ? 'Yes' : 'No'}</Button>)}</div>}
          </F>
        ))}
      </div>
      <Button className="mt-5" disabled={missing.length > 0 || busy} onClick={() => onSubmit(a)}>Continue</Button>
      {missing.length > 0 && <p className="mt-2 text-[12px] text-muted-foreground">{missing.length} required answer{missing.length === 1 ? '' : 's'} remaining.</p>}
    </div>
  );
}

function DocumentsStep({ v, token, busy, run }: { v: PublicView; token: string; busy: boolean; run: (fn: () => Promise<PublicView>) => Promise<void> }) {
  const reqs = v.document_requests;
  const allRequired = reqs.filter((r) => r.required).every((r) => r.document_id);
  const awaitingPractice = v.status === 'awaiting_practice';
  return (
    <div>
      <StepHeader n={4} title="Documents" body="Upload what you have. PDF, images or spreadsheets are fine; each file is virus-scanned and stored securely." />
      <ul className="divide-y rounded-[5px] border">
        {reqs.map((r) => (
          <li key={r.key} className="flex items-center gap-3 px-3 py-2.5 text-[13px]">
            {r.document_id ? <CheckCircle2 className="size-4 text-success" /> : <Circle className="size-4 text-muted-foreground/50" />}
            <span className="flex-1">{r.label}{!r.required && <span className="text-muted-foreground"> · optional</span>}</span>
            <label className={`inline-flex cursor-pointer items-center gap-1.5 rounded-[5px] border px-2.5 py-1 text-[12px] hover:bg-muted ${busy ? 'opacity-50' : ''}`}><FileUp className="size-3.5" />{r.document_id ? 'Replace' : 'Upload'}<input type="file" className="hidden" disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) void run(() => start.public.upload(token, r.key, f)); }} /></label>
          </li>
        ))}
      </ul>
      {awaitingPractice ? <p className="mt-4 rounded-[4px] bg-muted px-3 py-2 text-[12px]">Thanks — your documents are with {v.practice_name} for verification. This step completes once they have checked them; you will be emailed when the next step is ready.</p>
        : <Button className="mt-5" disabled={!allRequired || busy} onClick={() => void run(() => start.public.stage4(token))}>I've uploaded everything</Button>}
    </div>
  );
}

function PartiesStep({ v, busy, onSubmit }: { v: PublicView; busy: boolean; onSubmit: (p: PartyIn[], ok: boolean) => void }) {
  const [rows, setRows] = useState<PartyIn[]>(((v.data.related_parties?.parties as PartyIn[]) ?? [{ name: v.contact_name ?? '', role: 'Director', email: '', ownership_pct: null, is_beneficial_owner: true }]));
  const [complete, setComplete] = useState(true);
  const upd = (i: number, k: keyof PartyIn, val: unknown) => setRows((r) => r.map((x, j) => (j === i ? { ...x, [k]: val } : x)));
  const valid = rows.length > 0 && rows.every((r) => r.name.trim());
  return (
    <div>
      <StepHeader n={5} title="Who is behind the entity" body="Directors, trustees, partners and anyone who owns 25% or more. We are required to identify beneficial owners." />
      <div className="space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="grid grid-cols-1 gap-2 rounded-[5px] border p-3 sm:grid-cols-[1fr_140px_1fr_80px_auto]">
            <Input placeholder="Full name" value={r.name} onChange={(e) => upd(i, 'name', e.target.value)} />
            <Select value={r.role} onValueChange={(x) => upd(i, 'role', x)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{ROLES.map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent></Select>
            <Input placeholder="Email (optional)" value={r.email ?? ''} onChange={(e) => upd(i, 'email', e.target.value || null)} />
            <Input type="number" placeholder="%" min={0} max={100} value={r.ownership_pct ?? ''} onChange={(e) => upd(i, 'ownership_pct', e.target.value === '' ? null : Number(e.target.value))} />
            <label className="flex items-center gap-1.5 text-[12px] whitespace-nowrap"><Checkbox checked={r.is_beneficial_owner} onCheckedChange={(x) => upd(i, 'is_beneficial_owner', !!x)} /> UBO</label>
            {rows.length > 1 && <button type="button" className="text-[12px] text-muted-foreground hover:text-error sm:col-span-5 text-left" onClick={() => setRows((x) => x.filter((_, j) => j !== i))}>Remove</button>}
          </div>
        ))}
      </div>
      <Button variant="outline" size="sm" className="mt-2" onClick={() => setRows((r) => [...r, { name: '', role: 'Shareholder', email: null, ownership_pct: null, is_beneficial_owner: false }])}>Add another person</Button>
      <label className="mt-4 flex items-start gap-2 text-[13px]"><Checkbox checked={complete} onCheckedChange={(x) => setComplete(!!x)} className="mt-0.5" /> I confirm everyone who owns or controls 25% or more is listed.</label>
      <Button className="mt-5" disabled={!valid || busy} onClick={() => onSubmit(rows.map((r) => ({ ...r, email: r.email || null })), complete)}>Continue</Button>
    </div>
  );
}

function ServicesStep({ v, busy, onSubmit }: { v: PublicView; busy: boolean; onSubmit: (ids: string[]) => void }) {
  const [sel, setSel] = useState<Set<string>>(new Set(((v.data.service_selection?.services ?? []) as { id: string }[]).map((s) => s.id)));
  const toggle = (id: string) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const groups = v.services.reduce<Record<string, typeof v.services>>((acc, s) => { (acc[s.category] ||= []).push(s); return acc; }, {});
  return (
    <div>
      <StepHeader n={6} title="Services you need" body="Pick what applies. Indicative fees are shown; the practice confirms them in your proposal." />
      <div className="space-y-4">
        {Object.entries(groups).map(([cat, items]) => (
          <div key={cat}>
            <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{cat}</div>
            <ul className="divide-y rounded-[5px] border">{items.map((s) => (
              <li key={s.id}><label className="flex cursor-pointer items-start gap-3 px-3 py-2.5 text-[13px] hover:bg-muted/50"><Checkbox checked={sel.has(s.id)} onCheckedChange={() => toggle(s.id)} className="mt-0.5" /><span className="flex-1"><span className="font-medium">{s.name}</span>{s.description && <span className="block text-[12px] text-muted-foreground">{s.description}</span>}</span><span className="tabular-nums text-muted-foreground">{fmtCents(s.amount_cents)} <span className="text-[11px]">{BASIS_LABEL[s.basis]}</span></span></label></li>
            ))}</ul>
          </div>
        ))}
      </div>
      <Button className="mt-5" disabled={sel.size === 0 || busy} onClick={() => onSubmit([...sel])}>Continue</Button>
    </div>
  );
}

function ProposalStep({ v, busy, onDecide }: { v: PublicView; busy: boolean; onDecide: (name: string, ok: boolean) => void }) {
  const [name, setName] = useState(v.contact_name ?? '');
  const p = v.proposal;
  if (!p) return <div><StepHeader n={7} title="Your proposal" body="" /><p className="rounded-[4px] bg-muted px-3 py-2 text-[13px]">{v.practice_name} is preparing your fee proposal. We will email you when it is ready to review — nothing more to do right now.</p></div>;
  if (p.declined_at) return <div><StepHeader n={7} title="Your proposal" body="" /><p className="rounded-[4px] bg-muted px-3 py-2 text-[13px]">You declined the proposal. {v.practice_name} has been notified and may issue a revised one.</p></div>;
  return (
    <div>
      <StepHeader n={7} title="Your proposal" body={`Issued by ${p.issued_by} · valid until ${p.valid_until.slice(0, 10)}`} />
      <div className="rounded-[5px] border">
        {p.lines.map((l, i) => <div key={i} className="flex items-center justify-between border-b px-3 py-2 text-[13px] last:border-0"><span>{l.name} <span className="text-[12px] text-muted-foreground">· {BASIS_LABEL[l.basis as keyof typeof BASIS_LABEL] ?? l.basis}</span></span><span className="tabular-nums">{fmtCents(l.amount_cents)}</span></div>)}
        <div className="flex justify-end gap-6 bg-muted/50 px-3 py-2 text-[12px] text-muted-foreground"><span>Subtotal {fmtCents(p.subtotal_cents)}</span><span>GST {fmtCents(p.gst_cents)}</span><span className="font-semibold text-foreground">Total {fmtCents(p.total_cents)}</span></div>
      </div>
      {p.terms && <p className="mt-3 whitespace-pre-wrap rounded-[4px] bg-muted/60 px-3 py-2 text-[12px]">{p.terms}</p>}
      <div className="mt-4 grid gap-1.5 text-[13px]"><Label htmlFor="acc-name">Your full name (as acceptance)</Label><Input id="acc-name" value={name} onChange={(e) => setName(e.target.value)} /></div>
      <div className="mt-4 flex gap-2"><Button disabled={!name.trim() || busy} onClick={() => onDecide(name.trim(), true)}>Accept proposal</Button><Button variant="outline" disabled={!name.trim() || busy} onClick={() => onDecide(name.trim(), false)}>Decline</Button></div>
    </div>
  );
}

function PracticeSideStep({ v, token, busy, run }: { v: PublicView; token: string; busy: boolean; run: (fn: () => Promise<PublicView>) => Promise<void> }) {
  const mandate = v.data.mandate as { method: string } | undefined;
  const [f, setF] = useState<{ method: 'direct_debit' | 'card' | 'invoice'; reference: string; account_name: string; accepted: boolean }>({ method: 'direct_debit', reference: '', account_name: v.prospect_name, accepted: false });
  return (
    <div>
      <div className="mb-4"><div className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Nearly there</div><h2 className="text-[18px] font-semibold">{v.practice_name} is finalising your engagement</h2><p className="text-[13px] text-muted-foreground">Your letter of engagement arrives by email for signature. Identity checks may also be requested. One thing you can do now:</p></div>
      {mandate ? <p className="rounded-[4px] bg-muted px-3 py-2 text-[13px]"><CheckCircle2 className="mr-1.5 inline size-4 text-success" /> Payment mandate recorded ({mandate.method.replace('_', ' ')}). Nothing more is needed from you.</p> : (
        <div className="rounded-[5px] border p-4">
          <div className="mb-2 font-medium text-[13px]">How would you like to pay fees?</div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <Select value={f.method} onValueChange={(x) => setF({ ...f, method: x as typeof f.method })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="direct_debit">Direct debit</SelectItem><SelectItem value="card">Card</SelectItem><SelectItem value="invoice">Pay by invoice</SelectItem></SelectContent></Select>
            <Input placeholder={f.method === 'direct_debit' ? 'BSB / account (last 4)' : f.method === 'card' ? 'Card last 4' : 'Billing email'} value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} />
            <Input placeholder="Account name" value={f.account_name} onChange={(e) => setF({ ...f, account_name: e.target.value })} />
          </div>
          <label className="mt-3 flex items-start gap-2 text-[12px] leading-5"><Checkbox checked={f.accepted} onCheckedChange={(x) => setF({ ...f, accepted: !!x })} className="mt-0.5" /> I authorise {v.practice_name} to collect agreed fees using this method and accept their payment terms.</label>
          <Button className="mt-3" disabled={!f.accepted || busy} onClick={() => void run(() => start.public.mandate(token, { method: f.method, reference: f.reference || null, account_name: f.account_name || null, accepted_terms: true }))}>Confirm payment method</Button>
          <p className="mt-2 text-[11px] text-muted-foreground">No card or bank details are stored here; a secure mandate is set up separately once billing is live.</p>
        </div>
      )}
    </div>
  );
}
