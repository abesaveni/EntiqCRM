import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { CheckCircle2, Clock, FileSignature, Plus, XCircle } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule } from '@entiq/modules';
import { sign, KIND_LABEL, STATUS_LABEL, agreementTone, signerTone, type AgreementOut, type SignOverview } from '@/api/sign';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';
import { NewAgreementDialog } from './NewAgreementDialog';

type View = 'open' | 'completed' | 'all';

export function Agreements() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [ov, setOv] = useState<SignOverview | null>(null);
  const [rows, setRows] = useState<AgreementOut[] | null>(null);
  const [view, setView] = useState<View>('open');
  const [newOpen, setNewOpen] = useState(false);

  const load = async () => {
    try { const [o, a] = await Promise.all([sign.overview(), sign.agreements.list()]); setOv(o); setRows(a); }
    catch (e) { toast.error('Could not load agreements', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('sign')) void load(); }, []);
  if (!entitled('sign')) return <UpsellPage module={getModule('sign')} />;

  const shown = (rows ?? []).filter((a) => view === 'all' ? true : view === 'completed' ? a.status === 'completed' : ['draft', 'sent', 'partially_signed'].includes(a.status));

  return (
    <div className="page">
      <PageHeader eyebrow="Module 05" title="Sign" description="Engagement letters, declarations and resolutions sent for electronic signature, sealed on completion with a verifiable certificate."
        actions={!readOnly && can('sign:send') && <Button size="sm" onClick={() => setNewOpen(true)}><Plus className="mr-1.5 size-4" /> New agreement</Button>} />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat icon={<Clock className="size-4" />} label="Awaiting signature" value={ov?.awaiting} />
        <Stat icon={<CheckCircle2 className="size-4" />} label="Completed · 30d" value={ov?.completed_30d} />
        <Stat icon={<XCircle className="size-4" />} label="Declined" value={ov?.declined} />
        <Stat icon={<Clock className="size-4" />} label="Expiring within 7d" value={ov?.expiring_7d} warn={!!ov && ov.expiring_7d > 0} />
      </div>

      <Tabs value={view} onValueChange={(v) => setView(v as View)} className="mb-3"><TabsList><TabsTrigger value="open">Open</TabsTrigger><TabsTrigger value="completed">Completed</TabsTrigger><TabsTrigger value="all">All</TabsTrigger></TabsList></Tabs>
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <ul className="divide-y">
          {shown.map((a) => (
            <li key={a.id}>
              <Link to={`/sign/agreements/${a.id}`} className="flex items-center gap-3 px-5 py-3 text-[13px] hover:bg-muted/50">
                <FileSignature className="size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{a.title} <span className="font-normal text-muted-foreground">· {KIND_LABEL[a.kind]}</span></div>
                  <div className="truncate text-[12px] text-muted-foreground">{a.client_name ?? 'No client'} · {a.document_filename} · {a.created_by_name ?? 'System'} · {formatDistanceToNow(new Date(a.created_at), { addSuffix: true })}</div>
                </div>
                <div className="hidden items-center gap-1 md:flex">{a.signers.map((s) => <StatusPill key={s.id} tone={signerTone(s.status)} className="max-w-[140px] truncate">{s.name.split(' ')[0]} · {s.status}</StatusPill>)}</div>
                <StatusPill tone={agreementTone(a.status)}>{STATUS_LABEL[a.status]}</StatusPill>
              </Link>
            </li>
          ))}
          {rows && shown.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">{view === 'open' ? 'Nothing awaiting signature.' : 'No agreements here yet.'}</li>}
          {!rows && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
        </ul>
      </div>
      <NewAgreementDialog open={newOpen} onOpenChange={setNewOpen} onDone={load} />
    </div>
  );
}

function Stat({ icon, label, value, warn }: { icon: React.ReactNode; label: string; value: number | undefined; warn?: boolean }) {
  return (
    <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}>
      <div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div>
      <div className={`text-[24px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{value ?? '—'}</div>
    </div>
  );
}
