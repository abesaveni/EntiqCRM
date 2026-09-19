import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Plus, Upload, Search } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@entiq/ui/table';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { CLIENTS, type Stage } from '@/mock/data';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, riskTone, stageTone } from '@/components/StatusPill';
import { useEntitled } from '@/state/session';

const STAGES: Array<Stage | 'All'> = ['All', 'Lead', 'Proposal', 'Onboarding', 'Active', 'Review', 'Dormant'];

export function ClientsList() {
  const [params] = useSearchParams();
  const [q, setQ] = useState('');
  const [stage, setStage] = useState<Stage | 'All'>('All');
  const hasVerify = useEntitled('verify');

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return CLIENTS.filter((c) => {
      if (stage !== 'All' && c.stage !== stage) return false;
      if (params.get('risk') === 'elevated' && !(c.risk === 'Medium' || c.risk === 'High')) return false;
      if (needle && !`${c.name} ${c.abn ?? ''} ${c.tags.join(' ')}`.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [q, stage, params]);

  return (
    <div className="page">
      <PageHeader
        title="Clients"
        description={`${CLIENTS.length} client records · one per party, shared by every module.`}
        actions={
          <>
            <Button variant="outline" size="sm"><Upload className="mr-1.5 size-4" /> Import from Xero / MYOB</Button>
            <Button size="sm"><Plus className="mr-1.5 size-4" /> New client</Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-[320px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, ABN, tag" className="pl-8" />
        </div>
        <Tabs value={stage} onValueChange={(v) => setStage(v as Stage | 'All')}>
          <TabsList>
            {STAGES.map((s) => (
              <TabsTrigger key={s} value={s}>{s}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <div className="overflow-hidden rounded-[6px] border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Client</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Stage</TableHead>
              <TableHead>{hasVerify ? 'Risk' : <span className="text-warn">Risk · Verify</span>}</TableHead>
              <TableHead className="text-right">Contacts</TableHead>
              <TableHead className="text-right">Open tasks</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead>Since</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((c) => (
              <TableRow key={c.id} className="cursor-pointer">
                <TableCell>
                  <Link to={`/clients/${c.id}`} className="font-medium hover:underline">{c.name}</Link>
                  <div className="text-[12px] text-muted-foreground">{c.abn ? `ABN ${c.abn}` : '—'}</div>
                </TableCell>
                <TableCell className="text-muted-foreground">{c.type}</TableCell>
                <TableCell><StatusPill tone={stageTone(c.stage)}>{c.stage}</StatusPill></TableCell>
                <TableCell>
                  {hasVerify ? (
                    c.risk ? <StatusPill tone={riskTone(c.risk)}>{c.risk}</StatusPill> : <span className="text-[12px] text-muted-foreground">Not assessed</span>
                  ) : (
                    <Link to="/hq/modules/verify" className="text-[12px] text-warn hover:underline">Add Verify</Link>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">{c.contacts}</TableCell>
                <TableCell className="text-right tabular-nums">{c.openTasks || <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell className="text-muted-foreground">{c.owner}</TableCell>
                <TableCell className="text-muted-foreground">{new Date(c.since).toLocaleDateString('en-AU', { month: 'short', year: 'numeric' })}</TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow><TableCell colSpan={8} className="py-12 text-center text-muted-foreground">No clients match.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
