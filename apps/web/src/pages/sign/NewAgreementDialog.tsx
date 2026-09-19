import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Plus, Trash2, Upload } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Checkbox } from '@entiq/ui/checkbox';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Textarea } from '@entiq/ui/textarea';
import { crm, type ClientOut, type ContactOut } from '@/api/crm';
import { platform, type DocumentOut } from '@/api/platform';
import { sign, KIND_LABEL, type AgreementKind } from '@/api/sign';
import { useSession, describeError } from '@/state/session';

type SignerRow = { name: string; email: string; contact_id: string | null };

/**
 * Prepare and send an agreement. Pick a client (its contacts pre-fill signers), pick or upload the document,
 * add signers, optionally require verified identity (needs Verify), send.
 */
export function NewAgreementDialog({ open, onOpenChange, onDone, presetClient }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void>; presetClient?: ClientOut }) {
  const entitled = useSession((s) => s.entitled);
  const [clients, setClients] = useState<ClientOut[]>([]);
  const [clientId, setClientId] = useState(presetClient?.id ?? '');
  const [contacts, setContacts] = useState<ContactOut[]>([]);
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [docId, setDocId] = useState('');
  const [title, setTitle] = useState('');
  const [kind, setKind] = useState<AgreementKind>('engagement_letter');
  const [message, setMessage] = useState('');
  const [signers, setSigners] = useState<SignerRow[]>([{ name: '', email: '', contact_id: null }]);
  const [requireId, setRequireId] = useState(false);
  const [expires, setExpires] = useState(30);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { if (open) void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); }, [open]);
  useEffect(() => {
    if (!clientId) { setContacts([]); setDocs([]); return; }
    void Promise.all([crm.clients.contacts(clientId), platform.documents.list(clientId)]).then(([c, d]) => {
      setContacts(c); setDocs(d);
      const withEmail = c.filter((x) => x.email);
      if (withEmail.length && signers.every((s) => !s.name && !s.email)) setSigners(withEmail.slice(0, 2).map((x) => ({ name: x.full_name, email: x.email ?? '', contact_id: x.id })));
    }).catch(() => undefined);
  }, [clientId]);
  useEffect(() => { if (presetClient) setClientId(presetClient.id); }, [presetClient?.id]);
  useEffect(() => { if (!title && kind) { const c = clients.find((x) => x.id === clientId); if (c) setTitle(`${KIND_LABEL[kind]} — ${c.name}`); } }, [clientId, kind, clients]);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try { const d = await platform.documents.upload(file, { clientId: clientId || undefined, kind: 'agreement' }); setDocs((x) => [d, ...x]); setDocId(d.id); toast.success(`${file.name} uploaded`); }
    catch (e) { toast.error('Upload failed', { description: describeError(e) }); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ''; }
  };
  const pickContact = (i: number, cid: string) => {
    const c = contacts.find((x) => x.id === cid);
    setSigners((rows) => rows.map((r, j) => (j === i ? (c ? { name: c.full_name, email: c.email ?? '', contact_id: c.id } : { ...r, contact_id: null }) : r)));
  };
  const valid = title.trim() && docId && signers.length > 0 && signers.every((s) => s.name.trim() && /\S+@\S+\.\S+/.test(s.email));

  const submit = async () => {
    setBusy(true);
    try {
      await sign.agreements.create({ title: title.trim(), document_id: docId, client_id: clientId || null, kind, message: message.trim() || null, signers: signers.map((s) => ({ name: s.name.trim(), email: s.email.trim(), contact_id: s.contact_id })), require_identity: requireId, expires_in_days: expires, send_now: true });
      toast.success('Sent for signature'); await onDone(); onOpenChange(false);
      setTitle(''); setDocId(''); setMessage(''); setSigners([{ name: '', email: '', contact_id: null }]); setRequireId(false);
    } catch (e) { toast.error('Could not send', { description: describeError(e) }); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[640px]">
      <DialogHeader><DialogTitle>New agreement</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5"><Label>Client</Label><Select value={clientId || 'none'} onValueChange={(v) => setClientId(v === 'none' ? '' : v)} disabled={!!presetClient}><SelectTrigger><SelectValue placeholder="No client" /></SelectTrigger><SelectContent><SelectItem value="none">No client</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
          <div className="grid gap-1.5"><Label>Type</Label><Select value={kind} onValueChange={(v) => setKind(v as AgreementKind)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(Object.keys(KIND_LABEL) as AgreementKind[]).map((k) => <SelectItem key={k} value={k}>{KIND_LABEL[k]}</SelectItem>)}</SelectContent></Select></div>
        </div>
        <div className="grid gap-1.5"><Label htmlFor="na-title">Title</Label><Input id="na-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="FY27 Engagement Letter" /></div>
        <div className="grid gap-1.5">
          <Label>Document</Label>
          <div className="flex gap-2">
            <Select value={docId || 'none'} onValueChange={(v) => setDocId(v === 'none' ? '' : v)}><SelectTrigger className="flex-1"><SelectValue placeholder="Choose a document on the record" /></SelectTrigger><SelectContent><SelectItem value="none">Choose…</SelectItem>{docs.map((d) => <SelectItem key={d.id} value={d.id}>{d.filename}</SelectItem>)}</SelectContent></Select>
            <input ref={fileRef} type="file" className="hidden" accept=".pdf,.doc,.docx,.txt,application/pdf" onChange={(e) => void upload(e.target.files?.[0])} />
            <Button variant="outline" onClick={() => fileRef.current?.click()} disabled={busy}><Upload className="mr-1.5 size-4" /> Upload</Button>
          </div>
          <p className="text-[12px] text-muted-foreground">The document is placed under retention hold once sent; signers see exactly these bytes and the certificate records their hash.</p>
        </div>
        <div className="grid gap-1.5">
          <div className="flex items-center justify-between"><Label>Signers · in signing order</Label><Button variant="ghost" size="sm" onClick={() => setSigners((r) => [...r, { name: '', email: '', contact_id: null }])} disabled={signers.length >= 10}><Plus className="mr-1 size-3.5" /> Add</Button></div>
          <div className="space-y-2">
            {signers.map((s, i) => (
              <div key={i} className="grid grid-cols-[auto_1fr_1fr_auto] items-center gap-2">
                {contacts.length > 0 ? (
                  <Select value={s.contact_id ?? 'manual'} onValueChange={(v) => pickContact(i, v === 'manual' ? '' : v)}><SelectTrigger className="w-[130px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="manual">Type in</SelectItem>{contacts.map((c) => <SelectItem key={c.id} value={c.id}>{c.full_name}</SelectItem>)}</SelectContent></Select>
                ) : <span className="w-[34px] text-center text-[12px] tabular-nums text-muted-foreground">{i + 1}.</span>}
                <Input value={s.name} placeholder="Full name" onChange={(e) => setSigners((r) => r.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
                <Input value={s.email} placeholder="Email" type="email" onChange={(e) => setSigners((r) => r.map((x, j) => (j === i ? { ...x, email: e.target.value } : x)))} />
                <Button variant="ghost" size="icon" className="size-8 text-muted-foreground" disabled={signers.length === 1} onClick={() => setSigners((r) => r.filter((_, j) => j !== i))}><Trash2 className="size-4" /></Button>
              </div>
            ))}
          </div>
        </div>
        <div className="grid gap-1.5"><Label htmlFor="na-msg">Message to signers</Label><Textarea id="na-msg" rows={2} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Optional note included in the email." /></div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5"><Label htmlFor="na-exp">Link expires in (days)</Label><Input id="na-exp" type="number" min={1} max={365} value={expires} onChange={(e) => setExpires(Math.max(1, Math.min(365, Number(e.target.value) || 30)))} /></div>
          <label className={`flex items-start gap-2 rounded-[5px] border p-3 ${entitled('verify') ? '' : 'opacity-60'}`}>
            <Checkbox checked={requireId} onCheckedChange={(v) => setRequireId(!!v)} disabled={!entitled('verify')} className="mt-0.5" />
            <span><span className="font-medium">Require verified identity</span><br /><span className="text-[12px] text-muted-foreground">{entitled('verify') ? 'Signers linked to a contact must hold a current Verify identity check before they can sign.' : 'Needs the Verify module.'}</span></span>
          </label>
        </div>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button onClick={() => void submit()} disabled={!valid || busy}>{busy ? 'Sending…' : 'Send for signature'}</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
