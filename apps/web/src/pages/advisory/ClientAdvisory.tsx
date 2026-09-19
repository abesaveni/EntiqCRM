import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { ArrowLeft, CalendarPlus, Plus, TrendingUp } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Textarea } from '@entiq/ui/textarea';
import { getModule } from '@entiq/modules';
import { advisory, healthTone, severityTone, KPI_LABEL, KPI_SUFFIX, type ClientAdvisory as View, type SnapshotIn } from '@/api/advisory';
import { workpapers, type PackOut } from '@/api/workpapers';
import { fmtCents } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

export function ClientAdvisory() {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [v, setV] = useState<View | null>(null);
  const [snapOpen, setSnapOpen] = useState(false);
  const load = async () => { try { setV(await advisory.client(id)); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('advisory')) void load(); }, [id]);
  if (!entitled('advisory')) return <UpsellPage module={getModule('advisory')} />;
  if (!v) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;
  const s = v.latest;
  const canEdit = !readOnly && can('advisory:forecast');

  const scheduleMeeting = async () => {
    try { const m = await advisory.meetings.create({ client_id: id, kind: 'quarterly' }); nav(`/advisory/meetings/${m.id}`); }
    catch (e) { toast.error(describeError(e)); }
  };

  return (
    <div className="page">
      <Link to="/advisory" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Advisory</Link>
      <PageHeader eyebrow="Advisory" title={v.client_name} description={s ? `Position as at ${format(new Date(s.as_at), 'd MMM yyyy')}${s.period_label ? ` · ${s.period_label}` : ''} · from ${s.source}${s.simulated ? ' (simulated ledger)' : ''}` : 'No snapshot yet — take one to see where this client stands.'}
        actions={<div className="flex items-center gap-2">
          {s?.health_score != null && <StatusPill tone={healthTone(s.health_band)} className="text-[12px]">Health {s.health_score}/100</StatusPill>}
          <Button size="sm" variant="outline" asChild><Link to={`/clients/${id}`}>Client record</Link></Button>
          {canEdit && <Button size="sm" variant="outline" onClick={() => setSnapOpen(true)}><Plus className="mr-1.5 size-4" /> Snapshot</Button>}
          {!readOnly && can('advisory:meet') && <Button size="sm" onClick={() => void scheduleMeeting()}><CalendarPlus className="mr-1.5 size-4" /> Meeting</Button>}
        </div>} />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          {s ? (
            <>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Figure label="Revenue" cents={s.revenue_cents} /><Figure label="Net profit" cents={s.net_profit_cents} /><Figure label="Cash" cents={s.cash_cents} /><Figure label="Debtors" cents={s.receivables_cents} />
              </div>
              <Card>
                <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-[15px]"><TrendingUp className="size-4 text-primary" /> Key measures</CardTitle></CardHeader>
                <CardContent className="grid grid-cols-2 gap-x-6 gap-y-1 text-[13px] sm:grid-cols-3">
                  {Object.entries(s.kpis).map(([k, val]) => <div key={k} className="flex items-baseline justify-between border-b border-dashed py-1"><span className="text-muted-foreground">{KPI_LABEL[k] ?? k}</span><span className="font-medium tabular-nums">{val}{KPI_SUFFIX[k] ?? ''}</span></div>)}
                </CardContent>
              </Card>
              {v.history.length > 1 && (
                <Card><CardHeader className="pb-2"><CardTitle className="text-[15px]">History</CardTitle></CardHeader>
                  <CardContent className="p-0"><table className="w-full text-[13px]"><thead className="bg-muted/60 text-left text-[11px] uppercase tracking-[0.08em] text-muted-foreground"><tr><th className="px-5 py-2 font-medium">As at</th><th className="px-2 py-2 text-right font-medium">Revenue</th><th className="px-2 py-2 text-right font-medium">Net profit</th><th className="px-2 py-2 text-right font-medium">Cash</th><th className="px-2 py-2 text-right font-medium">Health</th></tr></thead>
                    <tbody className="divide-y">{v.history.map((h) => <tr key={h.id}><td className="px-5 py-1.5">{format(new Date(h.as_at), 'd MMM yyyy')}{h.simulated && <span className="ml-1 text-[11px] text-muted-foreground">sim</span>}</td><td className="px-2 py-1.5 text-right tabular-nums">{h.revenue_cents != null ? fmtCents(h.revenue_cents) : '—'}</td><td className="px-2 py-1.5 text-right tabular-nums">{h.net_profit_cents != null ? fmtCents(h.net_profit_cents) : '—'}</td><td className="px-2 py-1.5 text-right tabular-nums">{h.cash_cents != null ? fmtCents(h.cash_cents) : '—'}</td><td className="px-2 py-1.5 text-right tabular-nums">{h.health_score ?? '—'}</td></tr>)}</tbody>
                  </table></CardContent>
                </Card>
              )}
            </>
          ) : <Card><CardContent className="py-10 text-center text-[13px] text-muted-foreground">No snapshot yet.{canEdit && <> <button className="text-primary hover:underline" onClick={() => setSnapOpen(true)}>Take one</button> from a synced workpaper or by entering the figures.</>}</CardContent></Card>}

          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-[15px]">Meetings</CardTitle></CardHeader>
            <CardContent className="p-0"><ul className="divide-y">
              {v.meetings.map((m) => <li key={m.id} className="flex items-center gap-3 px-6 py-2 text-[13px]"><Link to={`/advisory/meetings/${m.id}`} className="min-w-0 flex-1 truncate hover:underline">{m.title}</Link><span className="text-[12px] text-muted-foreground">{m.scheduled_for ? format(new Date(m.scheduled_for), 'd MMM yyyy') : ''}</span><StatusPill tone={m.status === 'published' ? 'success' : m.status === 'held' ? 'teal' : 'neutral'}>{m.status}</StatusPill></li>)}
              {v.meetings.length === 0 && <li className="px-6 py-6 text-center text-[13px] text-muted-foreground">No meetings yet.</li>}
            </ul></CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className={v.alerts.some((a) => a.status === 'open' && a.severity === 'action') ? 'border-error/40' : ''}>
            <CardHeader className="pb-2"><CardTitle className="text-[15px]">Alerts</CardTitle></CardHeader>
            <CardContent className="p-0"><ul className="divide-y">
              {v.alerts.filter((a) => a.status === 'open').map((a) => (
                <li key={a.id} className="px-4 py-2.5 text-[13px]"><div className="flex items-start gap-2"><StatusPill tone={severityTone(a.severity)} className="mt-0.5">{a.severity}</StatusPill><div className="min-w-0"><div className="font-medium">{a.title}</div><div className="text-[12px] text-muted-foreground">{a.detail}</div>{a.recommendation && <div className="mt-1 text-[12px]"><span className="text-muted-foreground">Suggested: </span>{a.recommendation}</div>}</div></div></li>
              ))}
              {v.alerts.filter((a) => a.status === 'open').length === 0 && <li className="px-4 py-6 text-center text-[13px] text-muted-foreground">Nothing flagged.</li>}
            </ul></CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-[15px]">Actions</CardTitle></CardHeader>
            <CardContent className="p-0"><ul className="divide-y">
              {v.actions.filter((a) => a.status !== 'done' && a.status !== 'cancelled').map((a) => (
                <li key={a.id} className="flex items-start gap-2 px-4 py-2 text-[13px]"><div className="min-w-0 flex-1"><div className="font-medium">{a.title}</div><div className="text-[12px] text-muted-foreground">{a.owner_side === 'practice' ? a.owner_name ?? 'us' : `client${a.owner_name ? ` (${a.owner_name})` : ''}`}{a.due_on ? ` · due ${format(new Date(a.due_on), 'd MMM')}` : ''}</div></div>{!readOnly && <Button size="sm" variant="ghost" className="h-7 text-[12px]" onClick={() => void advisory.actions.patch(a.id, { status: 'done' }).then(load)}>Done</Button>}</li>
              ))}
              {v.actions.filter((a) => a.status !== 'done' && a.status !== 'cancelled').length === 0 && <li className="px-4 py-6 text-center text-[13px] text-muted-foreground">Nothing outstanding.</li>}
            </ul></CardContent>
          </Card>
        </div>
      </div>

      <SnapshotDialog open={snapOpen} onOpenChange={setSnapOpen} clientId={id} onDone={load} />
    </div>
  );
}

function Figure({ label, cents }: { label: string; cents: number | null }) {
  return <div className="rounded-[6px] border bg-card p-4"><div className="mb-1 text-[12px] text-muted-foreground">{label}</div><div className="text-[20px] font-semibold tabular-nums leading-none">{cents != null ? fmtCents(cents) : '—'}</div></div>;
}

const FIELDS: Array<[keyof SnapshotIn, string]> = [
  ['revenue_cents', 'Revenue'], ['gross_profit_cents', 'Gross profit'], ['expenses_cents', 'Total expenses'], ['net_profit_cents', 'Net profit'],
  ['cash_cents', 'Cash at bank'], ['receivables_cents', 'Debtors'], ['payables_cents', 'Creditors'], ['inventory_cents', 'Inventory'],
  ['debt_cents', 'Borrowings'], ['equity_cents', 'Equity'], ['tax_provision_cents', 'Tax provision'],
];

function SnapshotDialog({ open, onOpenChange, clientId, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; clientId: string; onDone: () => Promise<void> }) {
  const entitled = useSession((s) => s.entitled);
  const [packs, setPacks] = useState<PackOut[]>([]);
  const [packId, setPackId] = useState('');
  const [asAt, setAsAt] = useState(new Date().toISOString().slice(0, 10));
  const [period, setPeriod] = useState('');
  const [vals, setVals] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open && entitled('workpapers')) void workpapers.packs.list({ client_id: clientId }).then(setPacks).catch(() => undefined); }, [open, clientId]);
  const submit = async () => {
    setBusy(true);
    try {
      const figures = Object.fromEntries(Object.entries(vals).filter(([, v]) => v !== '').map(([k, v]) => [k, Math.round(Number(v) * 100)]));
      await advisory.snapshots.create({ client_id: clientId, as_at: asAt, period_label: period || null, workpaper_id: packId || null, ...figures });
      toast.success('Snapshot taken'); await onDone(); onOpenChange(false); setVals({});
    } catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[640px]">
      <DialogHeader><DialogTitle>Take a snapshot</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid grid-cols-3 gap-3">
          <div className="grid gap-1.5"><Label>As at</Label><Input type="date" value={asAt} onChange={(e) => setAsAt(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label>Period</Label><Input placeholder="FY26" value={period} onChange={(e) => setPeriod(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label>From workpaper</Label><Select value={packId || 'none'} onValueChange={(v) => setPackId(v === 'none' ? '' : v)} disabled={!entitled('workpapers')}><SelectTrigger><SelectValue placeholder="Manual" /></SelectTrigger><SelectContent><SelectItem value="none">Manual entry</SelectItem>{packs.map((p) => <SelectItem key={p.id} value={p.id}>{p.title}</SelectItem>)}</SelectContent></Select></div>
        </div>
        {packId && <p className="rounded-[4px] bg-muted px-3 py-2 text-[12px]">Figures are read from the pack's trial balance. Anything you type below overrides what it found.</p>}
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          {FIELDS.map(([k, label]) => <div key={k as string} className="grid gap-1"><Label className="text-[11px]">{label} ($)</Label><Input type="number" value={vals[k as string] ?? ''} onChange={(e) => setVals({ ...vals, [k as string]: e.target.value })} /></div>)}
        </div>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button><Button disabled={busy || (!packId && Object.values(vals).every((v) => v === ''))} onClick={() => void submit()}>Take snapshot</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
