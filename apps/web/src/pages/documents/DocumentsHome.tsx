import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { Archive, FileText, FolderPlus, Search, ShieldAlert, Tag } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule } from '@entiq/modules';
import { documentsModule, TEXT_SOURCE_LABEL, type DocsOverview, type DocumentRow, type FolderOut, type PolicyOut, type RetentionRow } from '@/api/documentsModule';
import { crm, type ClientOut } from '@/api/crm';
import { platform, fmtBytes } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

type View = 'library' | 'retention' | 'policies';

export function DocumentsHome() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [ov, setOv] = useState<DocsOverview | null>(null);
  const [rows, setRows] = useState<DocumentRow[] | null>(null);
  const [folders, setFolders] = useState<FolderOut[]>([]);
  const [policies, setPolicies] = useState<PolicyOut[]>([]);
  const [retention, setRetention] = useState<RetentionRow[]>([]);
  const [clients, setClients] = useState<ClientOut[]>([]);
  const [view, setView] = useState<View>('library');
  const [q, setQ] = useState('');
  const [clientId, setClientId] = useState('');
  const [folderId, setFolderId] = useState('');
  const [filing, setFiling] = useState<DocumentRow | null>(null);

  const search = async () => { try { setRows(await documentsModule.search({ q: q || null, client_id: clientId || null, folder_id: folderId || null, limit: 200 })); } catch (e) { toast.error(describeError(e)); } };
  const load = async () => {
    try {
      const [o, f] = await Promise.all([documentsModule.overview(), documentsModule.folders(clientId || undefined)]);
      setOv(o); setFolders(f); await search();
      if (view === 'policies') setPolicies(await documentsModule.policies());
      if (view === 'retention') setRetention(await documentsModule.retention(180));
    } catch (e) { toast.error('Could not load Documents', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('documents')) { void load(); void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); } }, [view, clientId]);
  if (!entitled('documents')) return <UpsellPage module={getModule('documents')} />;

  return (
    <div className="page">
      <PageHeader eyebrow="Module 07" title="Documents" description="Every file the practice holds, in one searchable place: filed into folders, tagged, indexed where we can read the text, and kept for exactly as long as the policy says."
        actions={!readOnly && can('documents:retain') && <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => void documentsModule.reindex().then((r) => { toast.success(`${r.indexed} document(s) indexed`); void load(); })}>Re-index</Button></div>} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat icon={<FileText className="size-4" />} label="Documents" value={ov?.documents} />
        <Stat icon={<Archive className="size-4" />} label="Storage" text={ov ? fmtBytes(ov.bytes_total) : undefined} />
        <Stat icon={<Search className="size-4" />} label="Searchable" value={ov?.searchable} />
        <Stat icon={<ShieldAlert className="size-4" />} label="Needs OCR" value={ov?.needs_ocr} />
        <Stat icon={<Archive className="size-4" />} label="Retention due" value={ov?.retention_due} warn={!!ov && ov.retention_due > 0} />
      </div>
      <Tabs value={view} onValueChange={(v) => setView(v as View)} className="mb-3"><TabsList><TabsTrigger value="library">Library</TabsTrigger><TabsTrigger value="retention">Retention</TabsTrigger><TabsTrigger value="policies">Policies</TabsTrigger></TabsList></Tabs>

      {view === 'library' && (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[240px_1fr]">
          <div>
            <div className="mb-2 flex items-center justify-between"><span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Folders</span>{!readOnly && can('documents:upload') && clientId && folders.length === 0 && <Button size="sm" variant="ghost" className="h-6 text-[11px]" onClick={() => void documentsModule.standardFolders(clientId).then(() => { toast.success('Standard folders created'); void load(); })}><FolderPlus className="mr-1 size-3" /> Standard set</Button>}</div>
            <Select value={clientId || 'all'} onValueChange={(v) => { setClientId(v === 'all' ? '' : v); setFolderId(''); }}><SelectTrigger className="mb-2 h-8"><SelectValue placeholder="All clients" /></SelectTrigger><SelectContent><SelectItem value="all">All clients</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select>
            <ul className="rounded-[6px] border bg-card p-1 text-[13px]">
              <li><button className={`w-full rounded-[4px] px-2 py-1 text-left ${folderId === '' ? 'bg-muted font-medium' : ''}`} onClick={() => { setFolderId(''); void search(); }}>All documents</button></li>
              {folders.map((f) => <li key={f.id}><button className={`w-full truncate rounded-[4px] px-2 py-1 text-left ${folderId === f.id ? 'bg-muted font-medium' : ''}`} style={{ paddingLeft: `${8 + f.depth * 12}px` }} onClick={() => { setFolderId(f.id); void search(); }}>{f.name} <span className="text-[11px] text-muted-foreground">{f.document_count || ''}</span></button></li>)}
              {folders.length === 0 && <li className="px-2 py-3 text-center text-[12px] text-muted-foreground">{clientId ? 'No folders yet.' : 'Pick a client to see its folders.'}</li>}
            </ul>
          </div>
          <div>
            <form className="mb-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); void search(); }}>
              <Input placeholder="Search file names, descriptions and document text…" value={q} onChange={(e) => setQ(e.target.value)} />
              <Button type="submit" variant="outline"><Search className="size-4" /></Button>
            </form>
            <div className="overflow-hidden rounded-[6px] border bg-card">
              <ul className="divide-y">
                {rows?.map((d) => (
                  <li key={d.id} className="flex items-start gap-3 px-5 py-2.5 text-[13px]">
                    <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2"><span className="truncate font-medium">{d.filename}</span>{d.retention_hold && <StatusPill tone="warn">hold</StatusPill>}{d.visible_to_client && <StatusPill tone="teal">shared</StatusPill>}{d.tags.map((t) => <span key={t} className="rounded-[3px] bg-muted px-1.5 py-0.5 text-[11px]"><Tag className="mr-0.5 inline size-2.5" />{t}</span>)}</div>
                      <div className="truncate text-[12px] text-muted-foreground">{d.client_name ? <Link to={`/clients/${d.client_id}`} className="hover:underline">{d.client_name}</Link> : 'Practice'} · {d.folder_path ?? 'unfiled'} · {d.kind} · {fmtBytes(d.size_bytes)} · {TEXT_SOURCE_LABEL[d.text_source]} · {format(new Date(d.created_at), 'd MMM yyyy')}{d.retain_until ? ` · keep until ${format(new Date(d.retain_until), 'MMM yyyy')}` : ''}</div>
                      {d.snippet && <div className="mt-1 rounded-[4px] bg-muted/60 px-2 py-1 text-[12px] text-muted-foreground">{d.snippet}</div>}
                    </div>
                    <Button size="sm" variant="ghost" className="h-7 text-[12px]" onClick={() => void platform.documents.download({ id: d.id, filename: d.filename } as never).catch((e) => toast.error(describeError(e)))}>Download</Button>
                    {!readOnly && can('documents:upload') && <Button size="sm" variant="outline" className="h-7 text-[12px]" onClick={() => setFiling(d)}>File</Button>}
                  </li>
                ))}
                {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Nothing matched.</li>}
                {!rows && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
              </ul>
            </div>
          </div>
        </div>
      )}

      {view === 'retention' && (
        <div className="overflow-hidden rounded-[6px] border bg-card">
          <ul className="divide-y">
            {retention.map((r) => (
              <li key={r.document_id} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
                <div className="min-w-0 flex-1"><div className="truncate font-medium">{r.filename}</div><div className="truncate text-[12px] text-muted-foreground">{r.client_name ?? 'Practice'} · {r.kind} · {r.policy_name ?? 'no policy'} · added {format(new Date(r.created_at), 'd MMM yyyy')}</div></div>
                {r.retention_hold && <StatusPill tone="warn">hold</StatusPill>}
                <StatusPill tone={r.due ? 'error' : 'neutral'}>{r.due ? 'due now' : `keep to ${format(new Date(r.retain_until), 'MMM yyyy')}`}</StatusPill>
              </li>
            ))}
            {retention.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Nothing reaching its retention date in the next 6 months.</li>}
          </ul>
        </div>
      )}

      {view === 'policies' && (
        <div>
          {policies.length === 0 && !readOnly && can('documents:retain') && <Button size="sm" className="mb-3" onClick={() => void documentsModule.seedPolicies().then((p) => { setPolicies(p); toast.success('Standard policies added'); })}>Load the standard policies</Button>}
          {policies.length > 0 && !readOnly && can('documents:retain') && <Button size="sm" variant="outline" className="mb-3" onClick={() => void documentsModule.applyPolicies().then((s) => { toast.success(`${s.indexed} document(s) re-dated, ${s.held} placed on hold`); void load(); })}>Apply to all documents</Button>}
          <div className="overflow-hidden rounded-[6px] border bg-card">
            <table className="w-full text-[13px]">
              <thead className="bg-muted/60 text-left text-[11px] uppercase tracking-[0.08em] text-muted-foreground"><tr><th className="px-5 py-2 font-medium">Policy</th><th className="px-2 py-2 font-medium">Applies to</th><th className="px-2 py-2 font-medium">Keep</th><th className="px-2 py-2 font-medium">At the end</th><th className="px-2 py-2 text-right font-medium">Documents</th></tr></thead>
              <tbody className="divide-y">
                {policies.map((p) => <tr key={p.id}><td className="px-5 py-2"><div className="font-medium">{p.name}</div>{p.reference && <div className="text-[12px] text-muted-foreground">{p.reference}</div>}</td><td className="px-2 py-2 text-[12px]">{p.kinds.length ? p.kinds.join(', ') : 'everything else'}</td><td className="px-2 py-2">{p.years} years</td><td className="px-2 py-2"><StatusPill tone={p.action === 'hold' ? 'warn' : p.action === 'delete' ? 'error' : 'neutral'}>{p.action}</StatusPill></td><td className="px-2 py-2 text-right tabular-nums">{p.documents}</td></tr>)}
                {policies.length === 0 && <tr><td colSpan={5} className="px-5 py-10 text-center text-muted-foreground">No policies yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <FileDialog doc={filing} folders={folders} onClose={() => setFiling(null)} onDone={async () => { setFiling(null); await load(); }} />
    </div>
  );
}

function Stat({ icon, label, value, text, warn }: { icon: React.ReactNode; label: string; value?: number; text?: string; warn?: boolean }) {
  return <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[22px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{text ?? value ?? '—'}</div></div>;
}

function FileDialog({ doc, folders, onClose, onDone }: { doc: DocumentRow | null; folders: FolderOut[]; onClose: () => void; onDone: () => Promise<void> }) {
  const [folderId, setFolderId] = useState('');
  const [tags, setTags] = useState('');
  useEffect(() => { if (doc) { setFolderId(doc.folder_id ?? ''); setTags(doc.tags.join(', ')); } }, [doc?.id]);
  if (!doc) return null;
  const save = async () => {
    try { await documentsModule.file(doc.id, { folder_id: folderId || null, tags: tags.split(',').map((t) => t.trim()).filter(Boolean) }); toast.success('Filed'); await onDone(); }
    catch (e) { toast.error(describeError(e)); }
  };
  const available = folders.filter((f) => !doc.client_id || f.client_id === doc.client_id || f.client_id === null);
  return (
    <Dialog open={!!doc} onOpenChange={(o) => !o && onClose()}><DialogContent className="max-w-[460px]">
      <DialogHeader><DialogTitle>File {doc.filename}</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid gap-1.5"><Label>Folder</Label><Select value={folderId || 'none'} onValueChange={(v) => setFolderId(v === 'none' ? '' : v)}><SelectTrigger><SelectValue placeholder="Unfiled" /></SelectTrigger><SelectContent><SelectItem value="none">Unfiled</SelectItem>{available.map((f) => <SelectItem key={f.id} value={f.id}>{f.path}</SelectItem>)}</SelectContent></Select>{available.length === 0 && <p className="text-[12px] text-muted-foreground">This client has no folders yet — create the standard set from the library.</p>}</div>
        <div className="grid gap-1.5"><Label>Tags</Label><Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="FY26, ledger" /></div>
      </div>
      <DialogFooter><Button variant="outline" onClick={onClose}>Cancel</Button><Button onClick={() => void save()}>Save</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
