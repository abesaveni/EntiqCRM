import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { AlertTriangle, ArrowLeft, Check, FileUp, Paperclip, RefreshCw, ShieldCheck, Undo2 } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Textarea } from '@entiq/ui/textarea';
import { getModule } from '@entiq/modules';
import { workpapers, PACK_TYPE_LABEL, WP_STATUS_LABEL, WP_ITEM_LABEL, wpTone, wpItemTone, type PackDetail as Detail, type WpItem } from '@/api/workpapers';
import { platform, fmtCents, type DocumentOut } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

export function PackDetail() {
  const { id = '' } = useParams();
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [p, setP] = useState<Detail | null>(null);
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [section, setSection] = useState<string | null>(null);
  const [editing, setEditing] = useState<WpItem | null>(null);
  const [lodgeOpen, setLodgeOpen] = useState(false);

  const load = async () => { try { const d = await workpapers.packs.get(id); setP(d); void platform.documents.list(d.client_id).then(setDocs).catch(() => undefined); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('workpapers')) void load(); }, [id]);
  if (!entitled('workpapers')) return <UpsellPage module={getModule('workpapers')} />;
  if (!p) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;

  const act = async (key: string, fn: () => Promise<Detail>, ok?: string) => { setBusy(key); try { setP(await fn()); if (ok) toast.success(ok); } catch (e) { toast.error(describeError(e)); } finally { setBusy(null); } };
  const open = !['signed_off', 'lodged', 'archived'].includes(p.status);
  const canPrepare = !readOnly && can('wp:prepare') && open;
  const canReview = !readOnly && can('wp:review') && open;
  const shown = section ? p.items.filter((i) => i.section === section) : p.items;
  const openIssues = p.issues.filter((i) => i.status === 'open');

  return (
    <div className="page">
      <Link to="/workpapers" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Workpapers</Link>
      <PageHeader eyebrow={`${PACK_TYPE_LABEL[p.pack_type]}${p.period_label ? ` · ${p.period_label}` : ''}`} title={p.title}
        description={`${p.client_name} · prepared by ${p.preparer_name ?? '—'}${p.reviewer_name ? `, reviewed by ${p.reviewer_name}` : ''} · materiality ${p.materiality_cents ? fmtCents(p.materiality_cents) : '—'}${p.ledger_synced_at ? ` · ledger ${p.ledger_source}${p.ledger_simulated ? ' (simulated)' : ''} ${format(new Date(p.ledger_synced_at), 'd MMM HH:mm')}` : ''}`}
        actions={<div className="flex flex-wrap items-center gap-2">
          <StatusPill tone={wpTone(p.status)} className="text-[12px]">{WP_STATUS_LABEL[p.status]}</StatusPill>
          {canPrepare && <Button size="sm" variant="outline" disabled={busy === 'sync'} onClick={() => void act('sync', async () => { const r = await workpapers.packs.sync(p.id); toast.message(r.message); return r.pack; }, 'Ledger synced')}><RefreshCw className="mr-1.5 size-4" /> Sync ledger</Button>}
          {canPrepare && <Button size="sm" variant="outline" disabled={busy === 'checks'} onClick={() => void act('checks', () => workpapers.packs.checks(p.id), 'Checks run')}>Run checks</Button>}
          {canPrepare && p.status !== 'in_review' && <Button size="sm" disabled={busy === 'submit'} onClick={() => void act('submit', () => workpapers.packs.submit(p.id), 'Sent for review')}>Submit for review</Button>}
          {!readOnly && can('wp:signoff') && open && <Button size="sm" disabled={busy === 'sign'} onClick={() => void act('sign', () => workpapers.packs.signOff(p.id), 'Signed off')}><ShieldCheck className="mr-1.5 size-4" /> Sign off</Button>}
          {!readOnly && can('wp:signoff') && p.status === 'signed_off' && <Button size="sm" variant="outline" disabled={busy === 'reopen'} onClick={() => void act('reopen', () => workpapers.packs.reopen(p.id), 'Reopened')}><Undo2 className="mr-1.5 size-4" /> Reopen</Button>}
          {!readOnly && can('wp:lodge') && p.status === 'signed_off' && <Button size="sm" onClick={() => setLodgeOpen(true)}>Record lodgement</Button>}
        </div>} />

      {p.seal_sha256 && <div className="mb-4 rounded-[5px] border border-success/40 bg-success-bg/30 px-3 py-2 text-[12px]"><ShieldCheck className="mr-1.5 inline size-3.5 text-success" /> Signed off {p.signed_off_at ? format(new Date(p.signed_off_at), 'd MMM yyyy HH:mm') : ''} by {p.signed_off_by_name} · seal <span className="font-mono">{p.seal_sha256.slice(0, 24)}…</span>{p.lodgement_ref ? ` · lodged ${p.lodgement_ref}` : ''}</div>}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1fr_320px]">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            <button className={`rounded-[4px] border px-2 py-0.5 text-[12px] ${section === null ? 'border-primary bg-primary/10' : ''}`} onClick={() => setSection(null)}>All · {p.items.length}</button>
            {p.sections.map((s) => <button key={s} className={`rounded-[4px] border px-2 py-0.5 text-[12px] ${section === s ? 'border-primary bg-primary/10' : ''}`} onClick={() => setSection(s)}>{s} · {p.items.filter((i) => i.section === s).length}{p.totals[s] !== undefined ? ` · ${fmtCents(p.totals[s])}` : ''}</button>)}
          </div>
          <div className="overflow-hidden rounded-[6px] border bg-card">
            <table className="w-full text-[13px]">
              <thead className="bg-muted/60 text-left text-[11px] uppercase tracking-[0.08em] text-muted-foreground"><tr><th className="px-4 py-2 font-medium">Item</th><th className="px-2 py-2 text-right font-medium">This year</th><th className="px-2 py-2 text-right font-medium">Last year</th><th className="px-2 py-2 text-right font-medium">Movement</th><th className="px-2 py-2 font-medium">Evidence</th><th className="px-2 py-2 font-medium">Status</th></tr></thead>
              <tbody className="divide-y">
                {shown.map((i) => (
                  <tr key={i.id} className={`hover:bg-muted/40 ${canPrepare ? 'cursor-pointer' : ''}`} onClick={() => canPrepare && setEditing(i)}>
                    <td className="px-4 py-2"><div className="font-medium">{i.label}</div><div className="text-[11px] text-muted-foreground">{i.section}{i.account_code ? ` · ${i.account_code}` : ''}{i.workings ? ' · workings recorded' : ''}{i.query ? ` · query: ${i.query}` : ''}</div></td>
                    <td className="px-2 py-2 text-right tabular-nums">{i.value_cents != null ? fmtCents(i.value_cents) : '—'}</td>
                    <td className="px-2 py-2 text-right tabular-nums text-muted-foreground">{i.prior_cents != null ? fmtCents(i.prior_cents) : '—'}</td>
                    <td className={`px-2 py-2 text-right tabular-nums ${i.material ? 'font-medium text-warn' : 'text-muted-foreground'}`}>{i.variance_cents != null ? `${i.variance_cents > 0 ? '+' : ''}${fmtCents(i.variance_cents)}${i.variance_pct != null ? ` (${i.variance_pct > 0 ? '+' : ''}${i.variance_pct.toFixed(0)}%)` : ''}` : '—'}</td>
                    <td className="px-2 py-2 text-[12px]">{i.document_filename ? <span className="inline-flex items-center gap-1 text-primary"><Paperclip className="size-3" />{i.document_filename.slice(0, 18)}</span> : <span className="text-muted-foreground">—</span>}</td>
                    <td className="px-2 py-2"><StatusPill tone={wpItemTone(i.status)}>{WP_ITEM_LABEL[i.status]}</StatusPill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-4">
          <Card className={p.blocking_issues ? 'border-error/40' : ''}>
            <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-[15px]"><AlertTriangle className={`size-4 ${p.blocking_issues ? 'text-error' : 'text-muted-foreground'}`} /> Issues · {openIssues.length}</CardTitle></CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y">
                {openIssues.map((x) => (
                  <li key={x.id} className="px-4 py-2.5 text-[13px]">
                    <div className="flex items-start gap-2"><StatusPill tone={x.blocking ? 'error' : 'warn'} className="mt-0.5">{x.blocking ? 'blocking' : x.severity}</StatusPill><div className="min-w-0 flex-1"><div className="font-medium">{x.title}</div><div className="text-[12px] text-muted-foreground">{x.detail}{x.auto ? ' · raised by the rules' : x.raised_by_name ? ` · ${x.raised_by_name}` : ''}</div></div></div>
                    {canPrepare && <ResolveRow packId={p.id} issueId={x.id} canWaive={can('wp:signoff')} onDone={(d) => setP(d)} />}
                  </li>
                ))}
                {openIssues.length === 0 && <li className="px-4 py-6 text-center text-[13px] text-muted-foreground">Nothing outstanding.</li>}
              </ul>
            </CardContent>
          </Card>
          {canReview && <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">Raise a query</CardTitle></CardHeader><CardContent><QueryForm packId={p.id} items={p.items} onDone={(d) => setP(d)} /></CardContent></Card>}
          {p.notes && <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">Notes</CardTitle></CardHeader><CardContent className="whitespace-pre-wrap text-[13px]">{p.notes}</CardContent></Card>}
        </div>
      </div>

      <ItemDialog item={editing} packId={p.id} docs={docs} clientId={p.client_id} canReview={canReview} onClose={() => setEditing(null)} onDone={(d) => { setP(d); setEditing(null); }} onUploaded={(doc) => setDocs((x) => [doc, ...x])} />
      <LodgeDialog open={lodgeOpen} onOpenChange={setLodgeOpen} onConfirm={(ref) => act('lodge', () => workpapers.packs.lodge(p.id, ref), 'Lodgement recorded')} />
    </div>
  );
}

function ResolveRow({ packId, issueId, canWaive, onDone }: { packId: string; issueId: string; canWaive: boolean; onDone: (d: Detail) => void }) {
  const [txt, setTxt] = useState('');
  const [busy, setBusy] = useState(false);
  const go = async (waive: boolean) => { setBusy(true); try { onDone(await workpapers.packs.resolveIssue(packId, issueId, txt.trim() || (waive ? 'Waived at sign-off' : 'Resolved'), waive)); setTxt(''); } catch (e) { toast.error(describeError(e)); } finally { setBusy(false); } };
  return (
    <div className="mt-2 flex gap-1.5">
      <Input className="h-7 text-[12px]" placeholder="How was it resolved?" value={txt} onChange={(e) => setTxt(e.target.value)} />
      <Button size="sm" variant="outline" className="h-7" disabled={busy} onClick={() => void go(false)}><Check className="size-3.5" /></Button>
      {canWaive && <Button size="sm" variant="ghost" className="h-7 text-[12px]" disabled={busy} onClick={() => void go(true)}>Waive</Button>}
    </div>
  );
}

function QueryForm({ packId, items, onDone }: { packId: string; items: WpItem[]; onDone: (d: Detail) => void }) {
  const [itemId, setItemId] = useState('');
  const [title, setTitle] = useState('');
  const [blocking, setBlocking] = useState(true);
  const submit = async () => { try { onDone(await workpapers.packs.raiseIssue(packId, { item_id: itemId || null, kind: 'query', title: title.trim(), blocking })); setTitle(''); toast.success('Query raised'); } catch (e) { toast.error(describeError(e)); } };
  return (
    <div className="grid gap-2 text-[13px]">
      <Select value={itemId || 'none'} onValueChange={(v) => setItemId(v === 'none' ? '' : v)}><SelectTrigger className="h-8"><SelectValue placeholder="Whole pack" /></SelectTrigger><SelectContent><SelectItem value="none">Whole pack</SelectItem>{items.map((i) => <SelectItem key={i.id} value={i.id}>{i.label}</SelectItem>)}</SelectContent></Select>
      <Textarea rows={2} placeholder="What needs to change before sign-off?" value={title} onChange={(e) => setTitle(e.target.value)} />
      <div className="flex items-center justify-between"><label className="flex items-center gap-2 text-[12px]"><input type="checkbox" className="accent-primary" checked={blocking} onChange={(e) => setBlocking(e.target.checked)} /> Blocks sign-off</label><Button size="sm" disabled={title.trim().length < 3} onClick={() => void submit()}>Raise query</Button></div>
    </div>
  );
}

function ItemDialog({ item, packId, docs, clientId, canReview, onClose, onDone, onUploaded }: { item: WpItem | null; packId: string; docs: DocumentOut[]; clientId: string; canReview: boolean; onClose: () => void; onDone: (d: Detail) => void; onUploaded: (d: DocumentOut) => void }) {
  const [workings, setWorkings] = useState('');
  const [docId, setDocId] = useState('');
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (item) { setWorkings(item.workings ?? ''); setDocId(item.document_id ?? ''); setValue(item.value_cents != null ? String(item.value_cents / 100) : ''); } }, [item?.id]);
  if (!item) return null;
  const save = async (status?: string) => {
    setBusy(true);
    try { onDone(await workpapers.packs.patchItem(packId, item.id, { workings: workings || null, document_id: docId || null, value_cents: value === '' ? null : Math.round(Number(value) * 100), ...(status ? { status: status as WpItem['status'] } : {}) })); toast.success('Saved'); }
    catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };
  const upload = async (f: File | undefined) => { if (!f) return; try { const d = await platform.documents.upload(f, { clientId, kind: 'workpaper' }); onUploaded(d); setDocId(d.id); } catch (e) { toast.error(describeError(e)); } };
  return (
    <Dialog open={!!item} onOpenChange={(o) => !o && onClose()}><DialogContent className="max-w-[560px]">
      <DialogHeader><DialogTitle>{item.label}</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="flex flex-wrap gap-4 text-[12px] text-muted-foreground">
          <span>Section: {item.section}</span>{item.account_code && <span>Account: {item.account_code}</span>}
          {item.prior_cents != null && <span>Last year: {fmtCents(item.prior_cents)}</span>}
          {item.variance_cents != null && <span className={item.material ? 'text-warn' : ''}>Movement: {fmtCents(item.variance_cents)}{item.variance_pct != null ? ` (${item.variance_pct.toFixed(0)}%)` : ''}</span>}
        </div>
        <div className="grid gap-1.5"><Label>Value ($)</Label><Input type="number" value={value} onChange={(e) => setValue(e.target.value)} /></div>
        <div className="grid gap-1.5"><Label>Workings</Label><Textarea rows={4} value={workings} onChange={(e) => setWorkings(e.target.value)} placeholder="How the figure was agreed, what was checked, any judgement applied." /></div>
        <div className="grid gap-1.5"><Label>Evidence</Label><div className="flex gap-2">
          <Select value={docId || 'none'} onValueChange={(v) => setDocId(v === 'none' ? '' : v)}><SelectTrigger className="flex-1"><SelectValue placeholder="No document" /></SelectTrigger><SelectContent><SelectItem value="none">No document</SelectItem>{docs.map((d) => <SelectItem key={d.id} value={d.id}>{d.filename}</SelectItem>)}</SelectContent></Select>
          <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-[5px] border px-3 text-[13px] hover:bg-muted"><FileUp className="size-4" /> Upload<input type="file" className="hidden" onChange={(e) => void upload(e.target.files?.[0])} /></label>
        </div></div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="outline" disabled={busy} onClick={() => void save('prepared')}>Save as prepared</Button>
        {canReview && <Button disabled={busy} onClick={() => void save('reviewed')}>Mark reviewed</Button>}
      </DialogFooter>
    </DialogContent></Dialog>
  );
}

function LodgeDialog({ open, onOpenChange, onConfirm }: { open: boolean; onOpenChange: (o: boolean) => void; onConfirm: (ref: string) => Promise<void> }) {
  const [ref, setRef] = useState('');
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[420px]">
      <DialogHeader><DialogTitle>Record lodgement</DialogTitle></DialogHeader>
      <div className="grid gap-1.5 text-[13px]"><Label htmlFor="lodge-ref">ATO / ASIC reference</Label><Input id="lodge-ref" value={ref} onChange={(e) => setRef(e.target.value)} placeholder="ATO-2026-884412" /></div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={ref.trim().length < 2} onClick={() => { void onConfirm(ref.trim()); onOpenChange(false); setRef(''); }}>Record</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
