import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus, Trash2, Users } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { crm, CLIENT_TYPES, STAGES, type SegmentOut, type ClientFilters, type DuplicateGroup } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, stageTone } from '@/components/StatusPill';

/** Segments & lists — blueprint MODULE 16 screen 9 — plus duplicate detection, the CRM's data-hygiene surface. */
export function Segments() {
  const readOnly = useSession((s) => s.readOnly);
  const [segs, setSegs] = useState<SegmentOut[] | null>(null);
  const [dups, setDups] = useState<DuplicateGroup[]>([]);
  const [open, setOpen] = useState(false);
  const load = async () => { try { const [s, d] = await Promise.all([crm.segments.list(), crm.duplicates()]); setSegs(s); setDups(d); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { void load(); }, []);

  const describe = (f: ClientFilters) => [f.stage && `stage ${f.stage}`, f.client_type && f.client_type, f.risk && `${f.risk} risk`, f.tag && `tag "${f.tag}"`, f.q && `"${f.q}"`].filter(Boolean).join(' · ') || 'all clients';
  const link = (f: ClientFilters) => `/clients?${new URLSearchParams(Object.fromEntries(Object.entries({ q: f.q, stage: f.stage, type: f.client_type, risk: f.risk }).filter(([, v]) => v)) as Record<string, string>).toString()}`;

  return (
    <div className="page">
      <PageHeader title="Segments & lists" description="Saved client filters for outreach, review cycles and reporting. Membership is computed live, so a list is never stale."
        actions={<Button size="sm" onClick={() => setOpen(true)} disabled={readOnly}><Plus className="mr-1.5 size-4" /> New segment</Button>} />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {segs?.map((s) => (
          <div key={s.id} className="flex flex-col rounded-[6px] border bg-card p-4">
            <div className="mb-1 flex items-start justify-between gap-2"><div className="font-semibold">{s.name}</div><span className="inline-flex items-center gap-1 text-[12px] text-muted-foreground"><Users className="size-3.5" /> {s.member_count}</span></div>
            <div className="mb-3 flex-1 text-[13px] text-muted-foreground">{s.description || describe(s.filters)}</div>
            <div className="flex items-center justify-between border-t pt-3"><Button asChild variant="outline" size="sm"><Link to={link(s.filters)}>Open list</Link></Button>{!readOnly && <button className="text-muted-foreground hover:text-error" aria-label="Delete segment" onClick={() => void crm.segments.remove(s.id).then(load)}><Trash2 className="size-4" /></button>}</div>
          </div>
        ))}
        {segs && segs.length === 0 && <div className="col-span-full rounded-[6px] border border-dashed bg-card px-6 py-12 text-center text-[13px] text-muted-foreground">No segments yet. Save a filter to reuse it.</div>}
      </div>

      <h2 className="mb-3 mt-10 text-[15px]">Possible duplicates <span className="text-muted-foreground">· {dups.length}</span></h2>
      {dups.length === 0 ? <div className="rounded-[6px] border bg-card px-6 py-8 text-center text-[13px] text-muted-foreground">No duplicate clients found — same ABN or same normalised name.</div> : (
        <div className="space-y-3">
          {dups.map((g, i) => (
            <div key={i} className="rounded-[6px] border bg-card p-4 text-[13px]">
              <div className="mb-2 text-[12px] text-muted-foreground">Same {g.reason === 'abn' ? `ABN ${g.key}` : `name "${g.key}"`}</div>
              <ul className="divide-y">{g.clients.map((c) => <li key={c.id} className="flex items-center justify-between py-2"><Link to={`/clients/${c.id}`} className="font-medium hover:underline">{c.name}</Link><div className="flex items-center gap-2"><StatusPill tone={stageTone(c.stage)}>{c.stage}</StatusPill><span className="text-muted-foreground">{c.client_type}</span></div></li>)}</ul>
              <div className="mt-2 text-[12px] text-muted-foreground">Open one, move its contacts across, then archive the other. Merge tooling comes with the data-hygiene release.</div>
            </div>
          ))}
        </div>
      )}

      <NewSegmentDialog open={open} onOpenChange={setOpen} onDone={load} />
    </div>
  );
}

function NewSegmentDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: () => Promise<void> }) {
  const [name, setName] = useState(''); const [f, setF] = useState<ClientFilters>({});
  const submit = async () => {
    try { await crm.segments.create({ name: name.trim(), filters: Object.fromEntries(Object.entries(f).filter(([, v]) => v)) }); await onDone(); onOpenChange(false); setName(''); setF({}); toast.success('Segment saved'); }
    catch (e) { toast.error(describeError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[480px]">
      <DialogHeader><DialogTitle>New segment</DialogTitle><DialogDescription>Clients matching every chosen filter.</DialogDescription></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid gap-1.5"><Label htmlFor="sg-name">Name</Label><Input id="sg-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Active companies · BAS quarterly" autoFocus /></div>
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5"><Label>Stage</Label><Select value={f.stage || 'any'} onValueChange={(v) => setF({ ...f, stage: v === 'any' ? '' : (v as ClientFilters['stage']) })}><SelectTrigger><SelectValue placeholder="Any" /></SelectTrigger><SelectContent><SelectItem value="any">Any</SelectItem>{STAGES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent></Select></div>
          <div className="grid gap-1.5"><Label>Type</Label><Select value={f.client_type || 'any'} onValueChange={(v) => setF({ ...f, client_type: v === 'any' ? '' : (v as ClientFilters['client_type']) })}><SelectTrigger><SelectValue placeholder="Any" /></SelectTrigger><SelectContent><SelectItem value="any">Any</SelectItem>{CLIENT_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select></div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5"><Label>Risk</Label><Select value={f.risk || 'any'} onValueChange={(v) => setF({ ...f, risk: v === 'any' ? '' : (v as ClientFilters['risk']) })}><SelectTrigger><SelectValue placeholder="Any" /></SelectTrigger><SelectContent><SelectItem value="any">Any</SelectItem><SelectItem value="elevated">Elevated (Medium + High)</SelectItem><SelectItem value="High">High</SelectItem><SelectItem value="Medium">Medium</SelectItem><SelectItem value="Low">Low</SelectItem></SelectContent></Select></div>
          <div className="grid gap-1.5"><Label htmlFor="sg-tag">Tag contains</Label><Input id="sg-tag" value={f.tag ?? ''} onChange={(e) => setF({ ...f, tag: e.target.value })} /></div>
        </div>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={() => void submit()} disabled={!name.trim()}>Save segment</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
