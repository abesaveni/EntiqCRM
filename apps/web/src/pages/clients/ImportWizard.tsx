import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Upload, FileSpreadsheet, Check, AlertTriangle, ArrowLeft } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Checkbox } from '@entiq/ui/checkbox';
import { Label } from '@entiq/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@entiq/ui/table';
import { crm, IMPORT_FIELDS, STAGES, type ImportPreview, type ImportResult, type Stage } from '@/api/crm';
import { describeError } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

/**
 * Import wizard — the activation moment of the 15-day trial.
 * Upload → detect (Xero / MYOB / CSV) → check mapping → commit → summary. Bad rows are reported, never fatal.
 */
export function ImportWizard() {
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [stage, setStage] = useState<Stage>('Active');
  const [updateExisting, setUpdateExisting] = useState(true);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [dragging, setDragging] = useState(false);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try { const p = await crm.import.preview(file); setPreview(p); setMapping(p.proposed_mapping); }
    catch (e) { toast.error('Could not read file', { description: describeError(e) }); } finally { setBusy(false); }
  };

  const commit = async () => {
    if (!preview) return;
    setBusy(true);
    try { setResult(await crm.import.commit(preview.job_id, { mapping, default_stage: stage, update_existing: updateExisting })); }
    catch (e) { toast.error('Import failed', { description: describeError(e) }); } finally { setBusy(false); }
  };

  const sourceLabel = { xero: 'Xero contacts export', myob: 'MYOB card file', csv: 'CSV' } as const;

  return (
    <div className="page">
      <PageHeader eyebrow="Clients" title="Import your client list" description="Xero: Contacts → Export. MYOB: Cards List → Export. Or any CSV with a header row. Existing clients are matched by ABN, then by name — nothing is duplicated."
        actions={<Button asChild variant="outline" size="sm"><Link to="/clients"><ArrowLeft className="mr-1 size-3.5" /> Clients</Link></Button>} />

      {result ? (
        <div className="mx-auto max-w-[640px] rounded-[6px] border bg-card p-8 text-center">
          <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-[8px] bg-success-bg text-success"><Check className="size-6" /></div>
          <h2 className="mb-1">Import complete</h2>
          <p className="mb-6 text-muted-foreground">{result.row_count} rows processed.</p>
          <div className="mb-6 grid grid-cols-3 gap-3">
            <Num label="Created" n={result.created_count} tone="text-success" /><Num label="Updated" n={result.updated_count} /><Num label="Skipped" n={result.skipped_count} tone={result.skipped_count ? 'text-warn' : undefined} />
          </div>
          {result.errors.length > 0 && (
            <details className="mb-6 text-left text-[13px]"><summary className="cursor-pointer text-warn"><AlertTriangle className="mr-1 inline size-3.5" /> {result.errors.length} note{result.errors.length === 1 ? '' : 's'}</summary>
              <ul className="mt-2 max-h-[220px] overflow-y-auto rounded-[5px] border bg-secondary/50 p-3 font-mono text-[12px]">{result.errors.map((e, i) => <li key={i}>{e}</li>)}</ul></details>
          )}
          <div className="flex justify-center gap-2"><Button onClick={() => navigate('/clients')}>Go to clients</Button><Button variant="outline" onClick={() => { setResult(null); setPreview(null); }}>Import another file</Button></div>
        </div>
      ) : !preview ? (
        <div
          className={`mx-auto flex max-w-[640px] flex-col items-center justify-center rounded-[6px] border-2 border-dashed bg-card px-8 py-16 text-center transition-colors ${dragging ? 'border-primary bg-accent' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); void pick(e.dataTransfer.files[0]); }}
        >
          <FileSpreadsheet className="mb-3 size-10 text-muted-foreground" />
          <div className="mb-1 text-[15px] font-semibold">Drop your export here</div>
          <div className="mb-5 text-[13px] text-muted-foreground">.csv or .txt · up to 10 MB · we detect Xero and MYOB formats automatically</div>
          <input ref={fileRef} type="file" accept=".csv,.txt,text/csv" className="hidden" onChange={(e) => void pick(e.target.files?.[0])} />
          <Button onClick={() => fileRef.current?.click()} disabled={busy}><Upload className="mr-1.5 size-4" /> {busy ? 'Reading…' : 'Choose file'}</Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 rounded-[6px] border bg-card px-4 py-3 text-[13px]">
              <FileSpreadsheet className="size-4 text-primary" /><span className="font-medium">{preview.filename}</span>
              <StatusPill tone="teal">{sourceLabel[preview.source]}</StatusPill>
              <span className="text-muted-foreground">{preview.row_count} rows · {preview.columns.length} columns</span>
              <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setPreview(null)}>Choose another file</Button>
            </div>
            {preview.warnings.map((w, i) => <div key={i} className="rounded-[5px] border border-warn/40 bg-warn-bg px-3 py-2 text-[13px] text-warn"><AlertTriangle className="mr-1 inline size-3.5" /> {w}</div>)}

            <div className="rounded-[6px] border bg-card">
              <div className="border-b px-4 py-2.5 text-[13px] font-semibold">Column mapping</div>
              <div className="grid grid-cols-1 gap-x-6 gap-y-2 p-4 md:grid-cols-2">
                {IMPORT_FIELDS.map((f) => (
                  <div key={f.key} className="flex items-center justify-between gap-3 text-[13px]">
                    <Label className="shrink-0">{f.label}{f.required && <span className="text-error"> *</span>}</Label>
                    <Select value={mapping[f.key] ?? '__none__'} onValueChange={(v) => setMapping({ ...mapping, [f.key]: v === '__none__' ? null : v })}>
                      <SelectTrigger className="h-8 w-[200px] text-[12px]"><SelectValue placeholder="—" /></SelectTrigger>
                      <SelectContent><SelectItem value="__none__">— not imported —</SelectItem>{preview.columns.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                ))}
              </div>
            </div>

            <div className="overflow-x-auto rounded-[6px] border bg-card">
              <div className="border-b px-4 py-2.5 text-[13px] font-semibold">First rows</div>
              <Table><TableHeader><TableRow>{preview.columns.slice(0, 8).map((c) => <TableHead key={c} className="whitespace-nowrap text-[11px]">{c}</TableHead>)}</TableRow></TableHeader>
                <TableBody>{preview.sample.slice(0, 6).map((r, i) => <TableRow key={i}>{preview.columns.slice(0, 8).map((c) => <TableCell key={c} className="max-w-[180px] truncate text-[12px]">{r[c] || <span className="text-muted-foreground">—</span>}</TableCell>)}</TableRow>)}</TableBody></Table>
            </div>
          </div>

          <aside className="space-y-4">
            <div className="rounded-[6px] border bg-card p-4 text-[13px]">
              <div className="mb-3 font-semibold">Options</div>
              <div className="grid gap-1.5"><Label>Stage for new clients</Label>
                <Select value={stage} onValueChange={(v) => setStage(v as Stage)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{STAGES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent></Select>
                <div className="text-[12px] text-muted-foreground">Existing customers → Active. A prospect list → Lead.</div>
              </div>
              <label className="mt-4 flex items-start gap-2"><Checkbox checked={updateExisting} onCheckedChange={(v) => setUpdateExisting(!!v)} className="mt-0.5" /><span>Fill in blanks on clients that already exist<br /><span className="text-[12px] text-muted-foreground">Never overwrites a value you already have.</span></span></label>
            </div>
            <Button className="w-full" onClick={() => void commit()} disabled={busy || !mapping.name}>{busy ? 'Importing…' : `Import ${preview.row_count} rows`}</Button>
            {!mapping.name && <div className="text-center text-[12px] text-error">Map the client name column to continue.</div>}
          </aside>
        </div>
      )}
    </div>
  );
}

function Num({ label, n, tone }: { label: string; n: number; tone?: string }) {
  return <div className="rounded-[5px] border bg-secondary/40 px-3 py-3"><div className={`text-[24px] font-semibold tabular-nums ${tone ?? ''}`}>{n}</div><div className="text-[12px] text-muted-foreground">{label}</div></div>;
}
