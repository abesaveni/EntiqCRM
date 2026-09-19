import { useEffect, useRef, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { Upload, Download, Trash2, Lock, LockOpen, FileText, ShieldAlert } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { platform, fmtBytes, type DocumentOut } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { StatusPill } from './StatusPill';

/** Files on a client record — base-plan attachments with the compliance controls every module relies on. */
export function DocumentsCard({ clientId, readOnly, onChanged }: { clientId: string; readOnly: boolean; onChanged?: () => Promise<void> | void }) {
  const role = useSession((s) => s.user?.role);
  const [docs, setDocs] = useState<DocumentOut[] | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => { try { setDocs(await platform.documents.list(clientId)); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { void load(); }, [clientId]);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try { await platform.documents.upload(file, { clientId, kind: 'general' }); toast.success(`${file.name} uploaded`); await load(); await onChanged?.(); }
    catch (e) { toast.error('Upload failed', { description: describeError(e) }); } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ''; }
  };
  const remove = async (d: DocumentOut) => {
    if (!confirm(`Remove ${d.filename}? It is retained in storage; it leaves this record.`)) return;
    try { await platform.documents.remove(d.id); await load(); await onChanged?.(); } catch (e) { toast.error(describeError(e)); }
  };
  const toggleHold = async (d: DocumentOut) => {
    try { await platform.documents.setHold(d.id, !d.retention_hold, undefined, d.retention_hold ? undefined : 'Compliance record'); await load(); }
    catch (e) { toast.error(describeError(e)); }
  };

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between pb-3">
        <CardTitle className="text-[15px]">Documents{docs ? ` · ${docs.length}` : ''}</CardTitle>
        {!readOnly && (<>
          <input ref={fileRef} type="file" className="hidden" onChange={(e) => void upload(e.target.files?.[0])} />
          <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={busy}><Upload className="mr-1.5 size-4" /> {busy ? 'Uploading…' : 'Upload'}</Button>
        </>)}
      </CardHeader>
      <CardContent className="p-0">
        <ul className="divide-y">
          {docs?.map((d) => (
            <li key={d.id} className="flex items-center gap-3 px-6 py-2.5 text-[13px]">
              <FileText className="size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 truncate font-medium">{d.filename}{d.retention_hold && <StatusPill tone="warn"><Lock className="size-3" /> Hold</StatusPill>}{d.scan_status === 'unavailable' && <span title="Not scanned — anti-virus not configured in this environment"><ShieldAlert className="size-3.5 text-muted-foreground" /></span>}</div>
                <div className="text-[12px] text-muted-foreground">{d.kind} · {fmtBytes(d.size_bytes)} · {d.uploaded_by_name ?? 'Unknown'} · {formatDistanceToNow(new Date(d.created_at), { addSuffix: true })}</div>
              </div>
              <Button variant="ghost" size="icon" className="size-8" aria-label="Download" onClick={() => void platform.documents.download(d).catch((e) => toast.error(describeError(e)))}><Download className="size-4" /></Button>
              {!readOnly && (d.retention_hold ? (role === 'owner' || role === 'admin') : true) && (
                <Button variant="ghost" size="icon" className="size-8" aria-label={d.retention_hold ? 'Lift retention hold' : 'Place retention hold'} onClick={() => void toggleHold(d)}>{d.retention_hold ? <LockOpen className="size-4" /> : <Lock className="size-4" />}</Button>
              )}
              {!readOnly && !d.retention_hold && <Button variant="ghost" size="icon" className="size-8 text-muted-foreground hover:text-error" aria-label="Remove" onClick={() => void remove(d)}><Trash2 className="size-4" /></Button>}
            </li>
          ))}
          {docs && docs.length === 0 && <li className="px-6 py-6 text-center text-[13px] text-muted-foreground">No documents yet. Uploads land on the timeline; a retention hold blocks deletion.</li>}
          {!docs && <li className="px-6 py-6 text-center text-[13px] text-muted-foreground">Loading…</li>}
        </ul>
      </CardContent>
    </Card>
  );
}
