import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { ArrowLeft, BellRing, Download, FileSignature, Link2, ShieldCheck, XCircle } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { getModule } from '@entiq/modules';
import { sign, KIND_LABEL, STATUS_LABEL, agreementTone, signerTone, type AgreementDetail as Detail, type ChainCheck } from '@/api/sign';
import { fmtDate } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

const EVENT_LABEL: Record<string, string> = { created: 'Drafted', sent: 'Sent', reminded: 'Reminder sent', viewed: 'Opened', consented: 'Consented to e-sign', identity_checked: 'Identity evidence attached', signed: 'Signed', declined: 'Declined', completed: 'Completed & sealed', voided: 'Voided' };

export function AgreementDetail() {
  const { id = '' } = useParams();
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [a, setA] = useState<Detail | null>(null);
  const [chain, setChain] = useState<ChainCheck | null>(null);
  const [voidOpen, setVoidOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = async () => { try { setA(await sign.agreements.get(id)); setChain(null); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('sign')) void load(); }, [id]);
  if (!entitled('sign')) return <UpsellPage module={getModule('sign')} />;
  if (!a) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;

  const act = async (fn: () => Promise<unknown>, ok: string) => { setBusy(true); try { await fn(); toast.success(ok); await load(); } catch (e) { toast.error(describeError(e)); } finally { setBusy(false); } };
  const open = ['draft', 'sent', 'partially_signed'].includes(a.status);

  return (
    <div className="page">
      <Link to="/sign" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Agreements</Link>
      <PageHeader eyebrow={`${KIND_LABEL[a.kind]}${a.client_name ? ` · ${a.client_name}` : ''}`} title={a.title}
        description={`${a.document_filename ?? 'Document'} · created by ${a.created_by_name ?? 'System'} ${formatDistanceToNow(new Date(a.created_at), { addSuffix: true })}${a.expires_at && open ? ` · link expires ${fmtDate(a.expires_at)}` : ''}`}
        actions={
          <div className="flex items-center gap-2">
            <StatusPill tone={agreementTone(a.status)} className="text-[12px]">{STATUS_LABEL[a.status]}</StatusPill>
            {a.status === 'completed' && <Button size="sm" onClick={() => void sign.agreements.certificate(a).catch((e) => toast.error(describeError(e)))}><Download className="mr-1.5 size-4" /> Certificate</Button>}
            {a.status === 'draft' && !readOnly && can('sign:send') && <Button size="sm" disabled={busy} onClick={() => void act(() => sign.agreements.send(a.id), 'Sent for signature')}>Send</Button>}
            {(a.status === 'sent' || a.status === 'partially_signed') && !readOnly && can('sign:send') && <Button size="sm" variant="outline" disabled={busy} onClick={() => void act(() => sign.agreements.remind(a.id), 'Reminders sent')}><BellRing className="mr-1.5 size-4" /> Remind</Button>}
            {open && !readOnly && can('sign:void') && <Button size="sm" variant="outline" className="text-error hover:text-error" onClick={() => setVoidOpen(true)}><XCircle className="mr-1.5 size-4" /> Void</Button>}
          </div>
        } />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          <Card>
            <CardHeader className="pb-3"><CardTitle className="text-[15px]">Signers</CardTitle></CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y">
                {a.signers.map((s) => (
                  <li key={s.id} className="flex items-center gap-3 px-6 py-3 text-[13px]">
                    <span className="w-5 text-center tabular-nums text-muted-foreground">{s.order}</span>
                    <div className="min-w-0 flex-1"><div className="truncate font-medium">{s.name}{s.identity_verified && <span title="Identity verified via Verify" className="ml-1.5 inline-flex align-middle text-success"><ShieldCheck className="size-3.5" /></span>}</div><div className="truncate text-[12px] text-muted-foreground">{s.email}{s.signed_at ? ` · signed ${format(new Date(s.signed_at), 'd MMM yyyy HH:mm')} (${s.signature_kind})` : s.viewed_at ? ` · opened ${formatDistanceToNow(new Date(s.viewed_at), { addSuffix: true })}` : ''}{s.decline_reason ? ` · “${s.decline_reason}”` : ''}</div></div>
                    <StatusPill tone={signerTone(s.status)}>{s.status}</StatusPill>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between pb-3">
              <CardTitle className="text-[15px]">Evidence trail · {a.events.length}</CardTitle>
              <Button size="sm" variant="outline" onClick={() => void sign.agreements.verifyChain(a.id).then(setChain).catch((e) => toast.error(describeError(e)))}><Link2 className="mr-1.5 size-4" /> Verify chain</Button>
            </CardHeader>
            <CardContent className="p-0">
              {chain && <div className={`mx-6 mb-3 rounded-[5px] border px-3 py-2 text-[12px] ${chain.ok && chain.matches_agreement !== false ? 'border-success/40 bg-success-bg/40 text-success' : 'border-error/40 bg-error-bg/40 text-error'}`}>{chain.ok ? `Chain intact — ${chain.events} events, head ${chain.head?.slice(0, 16)}…${chain.matches_agreement === false ? ' (does not match the stored head!)' : ''}` : `Chain BROKEN at event ${chain.first_break}`}</div>}
              <ol className="divide-y">
                {a.events.map((e) => (
                  <li key={e.id} className="grid grid-cols-[150px_1fr] gap-3 px-6 py-2 text-[13px]">
                    <span className="text-[12px] tabular-nums text-muted-foreground">{format(new Date(e.at), 'd MMM yyyy HH:mm:ss')}</span>
                    <div className="min-w-0"><span className="font-medium">{EVENT_LABEL[e.kind] ?? e.kind}</span>{e.signer_name && <span className="text-muted-foreground"> · {e.signer_name}</span>}{e.ip && <span className="text-muted-foreground"> · {e.ip}</span>}<div className="truncate font-mono text-[11px] text-muted-foreground">{e.hash}</div></div>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className={a.status === 'completed' ? 'border-success/40' : ''}>
            <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-[15px]"><FileSignature className="size-4 text-primary" /> Seal</CardTitle></CardHeader>
            <CardContent className="space-y-3 text-[13px]">
              <Field k="Document SHA-256" v={a.document_sha256} mono />
              {a.status === 'completed' ? (<>
                <Field k="Sealed SHA-256" v={a.sealed_sha256} mono />
                <Field k="Completed" v={a.completed_at ? format(new Date(a.completed_at), 'd MMM yyyy HH:mm') : '—'} />
                <p className="text-[12px] leading-5 text-muted-foreground">Anyone with the document and the certificate can recompute both hashes to prove nothing changed after signing. Download the certificate to keep with the executed copy.</p>
              </>) : a.status === 'voided' ? <p className="text-muted-foreground">Voided {a.voided_at ? fmtDate(a.voided_at) : ''}: {a.void_reason}</p> : <p className="text-muted-foreground">The seal is produced when the last signer completes.</p>}
              {a.require_identity && <StatusPill tone="teal"><ShieldCheck className="size-3" /> Verified identity required</StatusPill>}
            </CardContent>
          </Card>
          {a.message && <Card><CardHeader className="pb-2"><CardTitle className="text-[13px] text-muted-foreground">Message to signers</CardTitle></CardHeader><CardContent className="text-[13px]">{a.message}</CardContent></Card>}
        </div>
      </div>

      <VoidDialog open={voidOpen} onOpenChange={setVoidOpen} onConfirm={(reason) => act(() => sign.agreements.void(a.id, reason), 'Agreement voided')} />
    </div>
  );
}

function Field({ k, v, mono }: { k: string; v: string | null | undefined; mono?: boolean }) {
  return <div><div className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{k}</div><div className={`break-all ${mono ? 'font-mono text-[11px]' : ''}`}>{v ?? '—'}</div></div>;
}

function VoidDialog({ open, onOpenChange, onConfirm }: { open: boolean; onOpenChange: (o: boolean) => void; onConfirm: (reason: string) => Promise<void> }) {
  const [reason, setReason] = useState('');
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[460px]">
      <DialogHeader><DialogTitle>Void this agreement?</DialogTitle></DialogHeader>
      <p className="text-[13px] text-muted-foreground">All signing links stop working immediately. The record and its evidence trail are kept.</p>
      <div className="grid gap-1.5 text-[13px]"><Label htmlFor="void-reason">Reason</Label><Input id="void-reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Superseded by a corrected version" /></div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button variant="destructive" disabled={reason.trim().length < 2} onClick={() => { void onConfirm(reason.trim()); onOpenChange(false); setReason(''); }}>Void agreement</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
