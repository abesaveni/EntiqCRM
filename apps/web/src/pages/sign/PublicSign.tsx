import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { CheckCircle2, Download, FileText, ShieldAlert, ShieldCheck } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Checkbox } from '@entiq/ui/checkbox';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { Textarea } from '@entiq/ui/textarea';
import { sign, KIND_LABEL, type PublicSignerView } from '@/api/sign';
import { ApiError } from '@/api/client';

const CONSENT = 'I agree to sign this document electronically and understand that my electronic signature is as binding as a handwritten one (Electronic Transactions Act 1999).';

/**
 * The signer's page — reached only from the emailed link (/s/{token}), no EnTIQ login.
 * Read the document, consent, sign by typing or drawing, or decline with a reason.
 */
export function PublicSign() {
  const { token = '' } = useParams();
  const [v, setV] = useState<PublicSignerView | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [mode, setMode] = useState<'typed' | 'drawn'>('typed');
  const [consent, setConsent] = useState(false);
  const [declining, setDeclining] = useState(false);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionErr, setActionErr] = useState<string | null>(null);
  const pad = useRef<SignaturePadHandle>(null);

  useEffect(() => {
    sign.public.view(token).then((x) => { setV(x); setName(x.signer_name); }).catch((e: unknown) => setErr(e instanceof ApiError ? describe(e) : 'This link could not be opened.'));
  }, [token]);

  const submit = async () => {
    if (!v) return;
    setBusy(true); setActionErr(null);
    try {
      const data = mode === 'typed' ? name.trim() : pad.current?.toDataURL() ?? '';
      if (mode === 'drawn' && (!data || pad.current?.isEmpty())) { setActionErr('Draw your signature first.'); return; }
      setV(await sign.public.sign(token, { full_name: name.trim(), signature_kind: mode, signature_data: data, consent }));
    } catch (e) { setActionErr(e instanceof ApiError ? describe(e) : 'Could not sign — try again.'); } finally { setBusy(false); }
  };
  const decline = async () => {
    setBusy(true); setActionErr(null);
    try { setV(await sign.public.decline(token, reason.trim())); setDeclining(false); } catch (e) { setActionErr(e instanceof ApiError ? describe(e) : 'Could not decline — try again.'); } finally { setBusy(false); }
  };

  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="border-b bg-card"><div className="mx-auto flex h-14 max-w-[960px] items-center gap-3 px-4"><img src="/favicon.svg" alt="" className="size-6" /><span className="text-[14px] font-semibold">EnTIQ Sign</span>{v && <span className="ml-auto truncate text-[12px] text-muted-foreground">on behalf of {v.practice_name}</span>}</div></header>
      <main className="mx-auto max-w-[960px] px-4 py-6">
        {err && <div className="rounded-[6px] border bg-card p-8 text-center"><ShieldAlert className="mx-auto mb-3 size-8 text-muted-foreground" /><h1 className="text-[18px] font-semibold">{err}</h1><p className="mt-2 text-[13px] text-muted-foreground">If you were expecting to sign something, ask the practice to send a fresh link.</p></div>}
        {!v && !err && <p className="text-[13px] text-muted-foreground">Loading…</p>}
        {v && (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-[1fr_360px]">
            <section className="min-w-0">
              <div className="mb-3"><div className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{KIND_LABEL[v.kind]} · from {v.practice_name}</div><h1 className="text-[22px] font-semibold leading-tight">{v.title}</h1>{v.message && <p className="mt-2 rounded-[5px] border-l-2 border-primary bg-muted/60 px-3 py-2 text-[13px]">{v.message}</p>}</div>
              <div className="overflow-hidden rounded-[6px] border bg-card">
                <div className="flex items-center justify-between border-b px-4 py-2 text-[12px] text-muted-foreground"><span className="flex items-center gap-1.5 truncate"><FileText className="size-3.5" /> {v.document_filename}</span><a href={sign.public.documentUrl(token)} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-foreground"><Download className="size-3.5" /> Open / download</a></div>
                {v.document_content_type === 'application/pdf' ? <iframe title="Document" src={sign.public.documentUrl(token)} className="h-[70vh] w-full bg-white" /> : <div className="p-10 text-center text-[13px] text-muted-foreground">Preview not available for this file type — use “Open / download” to read it before signing.</div>}
              </div>
              <p className="mt-2 break-all font-mono text-[11px] text-muted-foreground">SHA-256 {v.document_sha256}</p>
            </section>

            <aside className="space-y-4">
              {v.signer_status === 'signed' ? (
                <div className="rounded-[6px] border border-success/40 bg-card p-5"><CheckCircle2 className="mb-2 size-7 text-success" /><h2 className="text-[16px] font-semibold">Signed — thank you</h2><p className="mt-1 text-[13px] text-muted-foreground">{v.agreement_status === 'completed' ? 'Everyone has signed. A completion email with the seal is on its way.' : 'We will email you a sealed copy once the remaining parties have signed.'}</p></div>
              ) : v.signer_status === 'declined' || v.agreement_status === 'declined' ? (
                <div className="rounded-[6px] border bg-card p-5"><h2 className="text-[16px] font-semibold">Declined</h2><p className="mt-1 text-[13px] text-muted-foreground">{v.practice_name} has been told. Nothing further is needed from you.</p></div>
              ) : (
                <div className="rounded-[6px] border bg-card p-5">
                  <h2 className="text-[16px] font-semibold">Sign as {v.signer_name}</h2>
                  <p className="mb-4 text-[12px] text-muted-foreground">{v.signer_email}{v.expires_at ? ` · link valid until ${new Date(v.expires_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}` : ''}</p>
                  {v.require_identity && (
                    <div className={`mb-4 flex items-start gap-2 rounded-[5px] border p-3 text-[12px] ${v.identity_ok ? 'border-success/40' : 'border-warn/50 bg-warn-bg/40'}`}>{v.identity_ok ? <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" /> : <ShieldAlert className="mt-0.5 size-4 shrink-0 text-warn" />}<span>{v.identity_ok ? 'Your identity has been verified with this practice — you can sign.' : `${v.practice_name} requires a verified identity before you can sign this document. Please complete the identity check they sent you, then return to this link.`}</span></div>
                  )}
                  {!declining ? (<>
                    <div className="grid gap-1.5 text-[13px]"><Label htmlFor="ps-name">Your full legal name</Label><Input id="ps-name" value={name} onChange={(e) => setName(e.target.value)} /></div>
                    <Tabs value={mode} onValueChange={(m) => setMode(m as typeof mode)} className="mt-3">
                      <TabsList className="grid w-full grid-cols-2"><TabsTrigger value="typed">Type</TabsTrigger><TabsTrigger value="drawn">Draw</TabsTrigger></TabsList>
                      <TabsContent value="typed"><div className="flex h-[96px] items-center justify-center rounded-[5px] border bg-white px-3 font-[cursive] text-[28px] italic text-foreground">{name.trim() || <span className="text-[13px] not-italic text-muted-foreground">Your typed signature appears here</span>}</div></TabsContent>
                      <TabsContent value="drawn"><SignaturePad ref={pad} /></TabsContent>
                    </Tabs>
                    <label className="mt-4 flex items-start gap-2 text-[12px] leading-5"><Checkbox checked={consent} onCheckedChange={(c) => setConsent(!!c)} className="mt-0.5" /><span>{CONSENT}</span></label>
                    {actionErr && <p className="mt-3 text-[12px] text-error">{actionErr}</p>}
                    <Button className="mt-4 w-full" disabled={busy || !consent || !name.trim() || (v.require_identity && !v.identity_ok)} onClick={() => void submit()}>{busy ? 'Signing…' : 'Sign document'}</Button>
                    <button type="button" className="mt-3 w-full text-[12px] text-muted-foreground hover:text-foreground" onClick={() => setDeclining(true)}>I need to decline</button>
                  </>) : (<>
                    <div className="grid gap-1.5 text-[13px]"><Label htmlFor="ps-reason">Why are you declining?</Label><Textarea id="ps-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. the entity name is wrong" /></div>
                    {actionErr && <p className="mt-3 text-[12px] text-error">{actionErr}</p>}
                    <div className="mt-3 flex gap-2"><Button variant="outline" className="flex-1" onClick={() => setDeclining(false)} disabled={busy}>Back</Button><Button variant="destructive" className="flex-1" disabled={busy || reason.trim().length < 2} onClick={() => void decline()}>Decline</Button></div>
                  </>)}
                </div>
              )}
              {v.other_signers.length > 0 && <div className="rounded-[6px] border bg-card p-4 text-[13px]"><div className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Other signers</div><ul className="space-y-1">{v.other_signers.map((o) => <li key={o.name} className="flex justify-between"><span>{o.name}</span><span className="text-muted-foreground">{o.status}</span></li>)}</ul></div>}
              <p className="px-1 text-[11px] leading-5 text-muted-foreground">Your name, the time, your IP address and the document hash are recorded as evidence of signing. This page is provided by EnTIQ on behalf of {v.practice_name}.</p>
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}

function describe(e: ApiError): string {
  const code = typeof e.detail === 'object' && e.detail && 'error' in e.detail ? String((e.detail as { error: string }).error) : '';
  return ({ invalid_link: 'This signing link is not valid or has already been used.', agreement_voided: 'This agreement was withdrawn by the practice.', agreement_declined: 'This agreement was declined.', agreement_expired: 'This signing link has expired.', identity_required: 'A verified identity is required before signing.', consent_required: 'Please tick the consent box.', already_signed: 'You have already signed.', already_declined: 'You have already declined.' } as Record<string, string>)[code] ?? e.message ?? 'Something went wrong.';
}

// ------------------------------------------------------------------ drawn signature
import { forwardRef, useImperativeHandle } from 'react';

type SignaturePadHandle = { toDataURL: () => string; isEmpty: () => boolean; clear: () => void };

const SignaturePad = forwardRef<SignaturePadHandle>(function SignaturePad(_, ref) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const strokes = useRef(0);
  const [, force] = useState(0);

  useImperativeHandle(ref, () => ({
    toDataURL: () => canvas.current?.toDataURL('image/png') ?? '',
    isEmpty: () => strokes.current === 0,
    clear: () => { const c = canvas.current; if (!c) return; c.getContext('2d')?.clearRect(0, 0, c.width, c.height); strokes.current = 0; force((n) => n + 1); },
  }));

  const pos = (e: React.PointerEvent<HTMLCanvasElement>) => { const c = canvas.current!; const r = c.getBoundingClientRect(); return { x: (e.clientX - r.left) * (c.width / r.width), y: (e.clientY - r.top) * (c.height / r.height) }; };
  const down = (e: React.PointerEvent<HTMLCanvasElement>) => { const ctx = canvas.current?.getContext('2d'); if (!ctx) return; drawing.current = true; const p = pos(e); ctx.lineWidth = 2.2; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#111'; ctx.beginPath(); ctx.moveTo(p.x, p.y); canvas.current?.setPointerCapture(e.pointerId); };
  const move = (e: React.PointerEvent<HTMLCanvasElement>) => { if (!drawing.current) return; const ctx = canvas.current?.getContext('2d'); if (!ctx) return; const p = pos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); };
  const up = () => { if (!drawing.current) return; drawing.current = false; strokes.current += 1; force((n) => n + 1); };

  return (
    <div>
      <canvas ref={canvas} width={640} height={192} className="h-[96px] w-full touch-none rounded-[5px] border bg-white" onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerLeave={up} />
      <div className="mt-1 flex justify-between text-[11px] text-muted-foreground"><span>Draw with your mouse or finger</span><button type="button" className="hover:text-foreground" onClick={() => { const c = canvas.current; if (!c) return; c.getContext('2d')?.clearRect(0, 0, c.width, c.height); strokes.current = 0; force((n) => n + 1); }}>Clear</button></div>
    </div>
  );
});
