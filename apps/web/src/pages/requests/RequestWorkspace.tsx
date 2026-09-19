import { useState } from 'react';
import { format } from 'date-fns';
import { AlertCircle, CheckCircle2, Circle, FileUp, RotateCcw, XCircle } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { ITEM_STATUS_LABEL, type ItemOut, type PublicPack } from '@/api/requests';
import { ApiError } from '@/api/client';

/** How the workspace talks to the API — the tokened /r/{token} surface and the authenticated portal both fit this. */
export interface RequestAdapter {
  answer: (key: string, answer: boolean) => Promise<PublicPack>;
  upload: (itemId: string, file: File) => Promise<PublicPack>;
  notApplicable: (itemId: string, note: string) => Promise<PublicPack>;
  submit: () => Promise<PublicPack>;
}

export function describeRequestError(e: unknown): string {
  if (e instanceof ApiError) {
    const d = e.detail as { error?: string; message?: string } | null;
    return ({ invalid_link: 'This link is not valid.', expired: 'This link has expired — ask the practice for a new one.', cancelled: 'This request was cancelled by the practice.', malware_detected: 'That file failed the virus scan and was not stored.', file_too_large: 'That file is too large.' } as Record<string, string>)[d?.error ?? ''] ?? d?.message ?? e.message ?? 'Something went wrong.';
  }
  return 'Something went wrong.';
}

/** The client's view of a request: answer the adaptive questions, upload or mark N/A per item, submit when nothing required is outstanding. */
export function RequestWorkspace({ pack, adapter, onChange }: { pack: PublicPack; adapter: RequestAdapter; onChange: (p: PublicPack) => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [naFor, setNaFor] = useState<string | null>(null);
  const [naNote, setNaNote] = useState('');
  const run = async (key: string, fn: () => Promise<PublicPack>) => { setBusy(key); setErr(null); try { onChange(await fn()); } catch (e) { setErr(describeRequestError(e)); } finally { setBusy(null); } };
  const closed = pack.status === 'complete' || pack.status === 'cancelled';
  const submitted = pack.status === 'submitted' || pack.status === 'reviewing';
  const groups = pack.items.reduce<Record<string, ItemOut[]>>((a, i) => { (a[i.category] ||= []).push(i); return a; }, {});
  const done = pack.items.filter((i) => i.status === 'accepted' || i.status === 'not_applicable' || i.status === 'uploaded').length;

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-all" style={{ width: `${pack.items.length ? (done / pack.items.length) * 100 : 0}%` }} /></div>
        <span className="text-[12px] tabular-nums text-muted-foreground">{done} of {pack.items.length}</span>
      </div>
      {err && <p className="mb-3 rounded-[4px] border border-error/40 bg-error-bg/40 px-3 py-2 text-[12px] text-error">{err}</p>}
      {pack.message && <p className="mb-4 rounded-[5px] border-l-2 border-primary bg-muted/60 px-3 py-2 text-[13px]">{pack.message}</p>}

      {pack.questions.length > 0 && !closed && (
        <div className="mb-5 rounded-[6px] border bg-card p-4">
          <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">A few quick questions</div>
          <ul className="space-y-2">
            {pack.questions.map((q) => (
              <li key={q.key} className="flex flex-wrap items-center justify-between gap-2 text-[13px]"><span>{q.label}</span>
                <div className="flex gap-1.5">{[true, false].map((b) => <Button key={String(b)} size="sm" variant={q.answer === b ? 'default' : 'outline'} disabled={busy !== null || submitted} onClick={() => void run(`q${q.key}`, () => adapter.answer(q.key, b))}>{b ? 'Yes' : 'No'}</Button>)}</div>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[12px] text-muted-foreground">Answering “yes” adds the related items below; “no” removes them.</p>
        </div>
      )}

      {Object.entries(groups).map(([cat, items]) => (
        <div key={cat} className="mb-4">
          <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{cat}</div>
          <ul className="divide-y rounded-[6px] border bg-card">
            {items.map((i) => (
              <li key={i.id} className="px-4 py-3 text-[13px]">
                <div className="flex items-start gap-3">
                  <span className="mt-0.5">{i.status === 'accepted' ? <CheckCircle2 className="size-4 text-success" /> : i.status === 'uploaded' ? <CheckCircle2 className="size-4 text-primary" /> : i.status === 'rejected' ? <AlertCircle className="size-4 text-error" /> : i.status === 'not_applicable' ? <XCircle className="size-4 text-muted-foreground" /> : <Circle className="size-4 text-muted-foreground/50" />}</span>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{i.label}{!i.required && <span className="font-normal text-muted-foreground"> · optional</span>}</div>
                    {i.description && <div className="text-[12px] text-muted-foreground">{i.description}</div>}
                    <div className="mt-0.5 text-[12px] text-muted-foreground">
                      {i.status === 'rejected' && <span className="text-error">Needs another look: {i.rejection_reason}</span>}
                      {i.status === 'uploaded' && <>{i.document_filename} · uploaded {i.uploaded_at ? format(new Date(i.uploaded_at), 'd MMM HH:mm') : ''} · awaiting review</>}
                      {i.status === 'accepted' && <>{i.document_filename ?? 'Accepted'} · accepted</>}
                      {i.status === 'not_applicable' && <>Not applicable — {i.client_note}</>}
                      {i.status === 'pending' && ITEM_STATUS_LABEL.pending}
                    </div>
                  </div>
                  {!closed && !submitted && i.status !== 'accepted' && (
                    <div className="flex shrink-0 gap-1.5">
                      <label className={`inline-flex cursor-pointer items-center gap-1.5 rounded-[5px] border px-2.5 py-1 text-[12px] hover:bg-muted ${busy ? 'opacity-50' : ''}`}><FileUp className="size-3.5" />{i.document_id ? 'Replace' : 'Upload'}<input type="file" className="hidden" disabled={busy !== null} onChange={(e) => { const f = e.target.files?.[0]; if (f) void run(i.id, () => adapter.upload(i.id, f)); }} /></label>
                      {i.status !== 'not_applicable' && !i.document_id && <Button size="sm" variant="ghost" className="h-7 text-[12px]" onClick={() => { setNaFor(i.id); setNaNote(''); }}>N/A</Button>}
                      {i.status === 'not_applicable' && <Button size="sm" variant="ghost" className="h-7 text-[12px]" title="Upload instead" onClick={() => setNaFor(i.id)}><RotateCcw className="size-3.5" /></Button>}
                    </div>
                  )}
                </div>
                {naFor === i.id && (
                  <div className="mt-2 flex gap-2 pl-7"><Input className="h-8" placeholder="Why doesn't this apply? (e.g. no employees this year)" value={naNote} onChange={(e) => setNaNote(e.target.value)} /><Button size="sm" disabled={naNote.trim().length < 2 || busy !== null} onClick={() => { void run(i.id, () => adapter.notApplicable(i.id, naNote.trim())); setNaFor(null); }}>Mark N/A</Button><Button size="sm" variant="ghost" onClick={() => setNaFor(null)}>Cancel</Button></div>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}

      {closed ? <p className="rounded-[5px] bg-muted px-3 py-2 text-[13px]">{pack.status === 'complete' ? 'Everything has been received and accepted. Thank you.' : 'This request has been cancelled.'}</p>
        : submitted ? <p className="rounded-[5px] bg-muted px-3 py-2 text-[13px]">Submitted — {pack.practice_name} is reviewing. If anything needs another look you will get an email.</p>
        : (
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={!pack.can_submit || busy !== null} onClick={() => void run('submit', () => adapter.submit())}>Submit to {pack.practice_name}</Button>
            {!pack.can_submit && <span className="text-[12px] text-muted-foreground">{pack.outstanding.length} required item{pack.outstanding.length === 1 ? '' : 's'} outstanding{pack.due_on ? ` · due ${format(new Date(pack.due_on), 'd MMM yyyy')}` : ''}</span>}
          </div>
        )}
    </div>
  );
}
