import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { AlertTriangle, CalendarClock, Fingerprint, ShieldCheck, Users } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { getModule } from '@entiq/modules';
import { verify, type VerifyOverview, type VerificationOut, type ReviewDueOut } from '@/api/verify';
import { fmtDate } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, riskTone, type Tone } from '@/components/StatusPill';

type View = 'all' | 'pending' | 'verified' | 'failed';

export function verificationTone(s: VerificationOut['status']): Tone {
  return s === 'verified' ? 'success' : s === 'failed' ? 'error' : s === 'in_progress' || s === 'pending' ? 'info' : 'neutral';
}

/** Verify home: the practice-wide state of identity, screening and risk, plus every verification run. */
export function VerifyHome() {
  const entitled = useSession((s) => s.entitled);
  const [ov, setOv] = useState<VerifyOverview | null>(null);
  const [rows, setRows] = useState<VerificationOut[] | null>(null);
  const [due, setDue] = useState<ReviewDueOut[]>([]);
  const [view, setView] = useState<View>('all');

  const load = async () => {
    try {
      const [o, v, d] = await Promise.all([verify.overview(), verify.verifications.list(view === 'all' ? {} : { status: view === 'pending' ? 'in_progress' : view }), verify.reviewsDue(30)]);
      setOv(o); setRows(v); setDue(d);
    } catch (e) { toast.error('Could not load Verify', { description: describeError(e) }); }
  };
  useEffect(() => { if (entitled('verify')) void load(); }, [view]);

  if (!entitled('verify')) return <UpsellPage module={getModule('verify')} />;

  return (
    <div className="page">
      <PageHeader eyebrow="Module 04" title="Verify" description="Identity, entity, beneficial-ownership and AML/CTF checks — run from the client record, reviewed here."
        actions={ov && <ProviderBadge providers={ov.providers} />} />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat icon={<Fingerprint className="size-4" />} label="Verified identities" value={ov?.verifications_verified} />
        <Stat icon={<Users className="size-4" />} label="In progress" value={ov?.verifications_pending} />
        <Stat icon={<AlertTriangle className="size-4" />} label="Screening hits to review" value={ov?.screenings_to_review} tone={ov && ov.screenings_to_review > 0 ? 'warn' : undefined} to="/verify/screening" />
        <Stat icon={<CalendarClock className="size-4" />} label="Reviews due · 30d" value={ov?.reviews_due_30d} tone={ov && ov.reviews_due_30d > 0 ? 'warn' : undefined} />
        <Stat icon={<ShieldCheck className="size-4" />} label="Clients not yet rated" value={ov?.clients_unassessed} />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-[15px] font-semibold">Verifications</h2>
            <Tabs value={view} onValueChange={(v) => setView(v as View)}><TabsList><TabsTrigger value="all">All</TabsTrigger><TabsTrigger value="pending">In progress</TabsTrigger><TabsTrigger value="verified">Verified</TabsTrigger><TabsTrigger value="failed">Failed</TabsTrigger></TabsList></Tabs>
          </div>
          <div className="overflow-hidden rounded-[6px] border bg-card">
            <ul className="divide-y">
              {rows?.map((v) => (
                <li key={v.id} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
                  <Fingerprint className="size-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium">{v.subject_name} <span className="font-normal text-muted-foreground">· {v.subject_type}</span></div>
                    <div className="truncate text-[12px] text-muted-foreground"><Link to={`/verify/clients/${v.client_id}`} className="hover:underline">Open client checks</Link> · {v.provider}{v.simulated ? ' (simulated)' : ''} · {v.started_by_name ?? 'System'} · {formatDistanceToNow(new Date(v.created_at), { addSuffix: true })}</div>
                  </div>
                  {v.expires_at && v.status === 'verified' && <span className="hidden text-[12px] text-muted-foreground sm:inline">relied on until {fmtDate(v.expires_at)}</span>}
                  <StatusPill tone={verificationTone(v.status)}>{v.status.replace('_', ' ')}</StatusPill>
                </li>
              ))}
              {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">No verifications yet. Open a client record and start one from the Identity &amp; AML panel.</li>}
              {!rows && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
            </ul>
          </div>
        </div>

        <div>
          <h2 className="mb-2 text-[15px] font-semibold">Periodic reviews due</h2>
          <div className="overflow-hidden rounded-[6px] border bg-card">
            <ul className="divide-y">
              {due.map((d) => (
                <li key={d.client_id} className="flex items-center gap-3 px-4 py-2.5 text-[13px]">
                  <div className="min-w-0 flex-1">
                    <Link to={`/verify/clients/${d.client_id}`} className="truncate font-medium hover:underline">{d.client_name}</Link>
                    <div className={`text-[12px] ${d.overdue ? 'font-medium text-error' : 'text-muted-foreground'}`}>{d.overdue ? 'Overdue — ' : 'Due '}{fmtDate(d.next_review_at)}</div>
                  </div>
                  <StatusPill tone={riskTone(d.rating)}>{d.rating}</StatusPill>
                </li>
              ))}
              {due.length === 0 && <li className="px-4 py-10 text-center text-[13px] text-muted-foreground">Nothing due in the next 30 days.</li>}
            </ul>
          </div>
          <p className="mt-3 text-[12px] leading-5 text-muted-foreground">Review cadence follows the rating: High every 6 months, Medium every 12, Low every 24. Re-assessing a client resets the clock.</p>
        </div>
      </div>
    </div>
  );
}

export function ProviderBadge({ providers }: { providers: VerifyOverview['providers'] }) {
  const live = providers.identity.live || providers.screening.live;
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <StatusPill tone={providers.identity.live ? 'success' : 'neutral'}>ID · {providers.identity.provider}</StatusPill>
      <StatusPill tone={providers.screening.live ? 'success' : 'neutral'}>AML · {providers.screening.provider}</StatusPill>
      {!live && <span className="text-muted-foreground" title="No provider keys configured in this environment; results are clearly marked as simulated">simulation</span>}
    </div>
  );
}

function Stat({ icon, label, value, tone, to }: { icon: React.ReactNode; label: string; value: number | undefined; tone?: Tone; to?: string }) {
  const body = (
    <div className={`rounded-[6px] border bg-card p-4 ${tone === 'warn' ? 'border-warn/50' : ''}`}>
      <div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div>
      <div className={`text-[24px] font-semibold tabular-nums leading-none ${tone === 'warn' ? 'text-warn' : ''}`}>{value ?? '—'}</div>
    </div>
  );
  return to ? <Link to={to} className="block hover:opacity-90">{body}</Link> : body;
}
