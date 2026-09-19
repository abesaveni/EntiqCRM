import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus, Upload, Search, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@entiq/ui/table';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { crm, fmtDate, CLIENT_TYPES, STAGES, type ClientPage, type ClientOut, type Stage, type ClientType } from '@/api/crm';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, riskTone } from '@/components/StatusPill';
import { StageMenu } from '@/components/StageMenu';
import { useEntitled, useSession, describeError } from '@/state/session';
import { NewClientDialog } from './NewClientDialog';

const SIZE = 50;

export function ClientsList() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const hasVerify = useEntitled('verify');
  const readOnly = useSession((s) => s.readOnly);
  const [q, setQ] = useState(params.get('q') ?? '');
  const [page, setPage] = useState<ClientPage | null>(null);
  const [pageNo, setPageNo] = useState(1);
  const [newOpen, setNewOpen] = useState(false);
  const stage = (params.get('stage') ?? '') as Stage | '';
  const type = (params.get('type') ?? '') as ClientType | '';
  const risk = params.get('risk') ?? '';

  const load = async () => {
    try { setPage(await crm.clients.list({ q: q.trim() || undefined, stage: stage || undefined, client_type: type || undefined, risk: (risk as 'elevated') || undefined, page: pageNo, size: SIZE, sort: 'name' })); }
    catch (e) { toast.error('Could not load clients', { description: describeError(e) }); }
  };
  useEffect(() => { const t = setTimeout(() => void load(), q ? 250 : 0); return () => clearTimeout(t); }, [q, stage, type, risk, pageNo]);
  useEffect(() => { setPageNo(1); }, [q, stage, type, risk]);

  const setParam = (k: string, v: string) => { const n = new URLSearchParams(params); v ? n.set(k, v) : n.delete(k); setParams(n, { replace: true }); };
  const replaceRow = (c: ClientOut) => setPage((p) => p && { ...p, items: p.items.map((x) => (x.id === c.id ? c : x)) });
  const pages = page ? Math.max(1, Math.ceil(page.total / SIZE)) : 1;

  return (
    <div className="page">
      <PageHeader
        title="Clients"
        description={page ? `${page.total} client record${page.total === 1 ? '' : 's'} · one per party, shared by every module.` : 'Loading…'}
        actions={<>
          <Button asChild variant="outline" size="sm"><Link to="/clients/import"><Upload className="mr-1.5 size-4" /> Import from Xero / MYOB</Link></Button>
          <Button size="sm" onClick={() => setNewOpen(true)} disabled={readOnly}><Plus className="mr-1.5 size-4" /> New client</Button>
        </>}
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-[320px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => { setQ(e.target.value); setParam('q', e.target.value); }} placeholder="Search name, ABN, email" className="pl-8" />
        </div>
        <Tabs value={stage || 'All'} onValueChange={(v) => setParam('stage', v === 'All' ? '' : v)}>
          <TabsList>{['All', ...STAGES.filter((s) => s !== 'Lost')].map((s) => <TabsTrigger key={s} value={s}>{s}</TabsTrigger>)}</TabsList>
        </Tabs>
        <Select value={type || 'any'} onValueChange={(v) => setParam('type', v === 'any' ? '' : v)}>
          <SelectTrigger className="w-[150px]"><SelectValue placeholder="Any type" /></SelectTrigger>
          <SelectContent><SelectItem value="any">Any type</SelectItem>{CLIENT_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
        </Select>
        {risk && <Button variant="ghost" size="sm" onClick={() => setParam('risk', '')}>Elevated risk × </Button>}
      </div>

      <div className="overflow-hidden rounded-[6px] border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Client</TableHead><TableHead>Type</TableHead><TableHead>Stage</TableHead>
              <TableHead>{hasVerify ? 'Risk' : <span className="text-warn">Risk · Verify</span>}</TableHead>
              <TableHead>Primary contact</TableHead><TableHead className="text-right">Open tasks</TableHead><TableHead>Owner</TableHead><TableHead>Since</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {page?.items.map((c) => (
              <TableRow key={c.id} className="cursor-pointer" onClick={() => navigate(`/clients/${c.id}`)}>
                <TableCell>
                  <div className="font-medium">{c.name}</div>
                  <div className="text-[12px] text-muted-foreground">{c.abn_formatted ? `ABN ${c.abn_formatted}` : c.email ?? '—'}</div>
                </TableCell>
                <TableCell className="text-muted-foreground">{c.client_type}</TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}><StageMenu client={c} onChanged={replaceRow} disabled={readOnly} /></TableCell>
                <TableCell onClick={(e) => e.stopPropagation()}>
                  {hasVerify ? (c.risk_rating ? <StatusPill tone={riskTone(c.risk_rating)}>{c.risk_rating}</StatusPill> : <span className="text-[12px] text-muted-foreground">Not assessed</span>)
                    : <Link to="/hq/modules/verify" className="text-[12px] text-warn hover:underline">Add Verify</Link>}
                </TableCell>
                <TableCell className="text-muted-foreground">{c.primary_contact ? c.primary_contact.full_name : c.contact_count ? `${c.contact_count} contacts` : '—'}</TableCell>
                <TableCell className="text-right tabular-nums">{c.open_task_count || <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell className="text-muted-foreground">{c.owner_name ?? '—'}</TableCell>
                <TableCell className="text-muted-foreground">{fmtDate(c.since, { month: 'short', year: 'numeric' })}</TableCell>
              </TableRow>
            ))}
            {page && page.items.length === 0 && (
              <TableRow><TableCell colSpan={8} className="py-14 text-center text-muted-foreground">
                {page.total === 0 && !q && !stage && !type ? <>No clients yet. <Link to="/clients/import" className="text-primary hover:underline">Import from Xero or MYOB</Link>, or add one.</> : 'No clients match.'}
              </TableCell></TableRow>
            )}
            {!page && <TableRow><TableCell colSpan={8} className="py-14 text-center text-muted-foreground">Loading…</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      {pages > 1 && (
        <div className="mt-3 flex items-center justify-end gap-2 text-[13px] text-muted-foreground">
          Page {pageNo} of {pages}
          <Button variant="outline" size="icon" className="size-8" disabled={pageNo <= 1} onClick={() => setPageNo((p) => p - 1)}><ChevronLeft className="size-4" /></Button>
          <Button variant="outline" size="icon" className="size-8" disabled={pageNo >= pages} onClick={() => setPageNo((p) => p + 1)}><ChevronRight className="size-4" /></Button>
        </div>
      )}

      <NewClientDialog open={newOpen} onOpenChange={setNewOpen} onCreated={(c) => navigate(`/clients/${c.id}`)} defaultStage={stage || 'Lead'} />
    </div>
  );
}
