import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getModule, type ModuleKey } from '@entiq/modules';
import { useSession } from '@/state/session';
import { ModuleIcon } from '@/lib/icons';

import { verify } from '@/api/verify';
import { sign } from '@/api/sign';
import { start } from '@/api/start';
import { practice } from '@/api/practice';
import { requests } from '@/api/requests';
import { workpapers } from '@/api/workpapers';
import { advisory } from '@/api/advisory';
import { academy } from '@/api/academy';
import { lending } from '@/api/lending';
import { practiceBilling } from '@/api/practiceBilling';
import { clientPortalStaff } from '@/api/portal';
import { support } from '@/api/support';

type Item = { module: ModuleKey; label: string; count: number; to: string; urgent?: boolean };

/**
 * One line per module the practice holds, answering the only question a home page should:
 * what is waiting on us right now. Each module reports its own number from its own overview.
 */
export function AcrossModules() {
  const entitled = useSession((s) => s.entitled);
  const [items, setItems] = useState<Item[] | null>(null);

  useEffect(() => {
    const jobs: Array<Promise<Item[]>> = [];
    const has = (k: ModuleKey) => entitled(k);
    const wrap = async (fn: () => Promise<Item[]>): Promise<Item[]> => { try { return await fn(); } catch { return []; } };

    if (has('start')) jobs.push(wrap(async () => { const o = await start.overview(); return [{ module: 'start', label: 'onboardings waiting on us', count: o.awaiting_practice, to: '/start', urgent: o.awaiting_practice > 0 }]; }));
    if (has('verify')) jobs.push(wrap(async () => { const o = await verify.overview(); return [
      { module: 'verify', label: 'screening hits to review', count: o.screenings_to_review, to: '/verify/screening', urgent: o.screenings_to_review > 0 },
      { module: 'verify', label: 'risk reviews due', count: o.reviews_due_30d, to: '/verify' }]; }));
    if (has('sign')) jobs.push(wrap(async () => { const o = await sign.overview(); return [{ module: 'sign', label: 'awaiting signature', count: o.awaiting, to: '/sign' }]; }));
    if (has('requests')) jobs.push(wrap(async () => { const o = await requests.overview(); return [
      { module: 'requests', label: 'submissions to review', count: o.awaiting_review, to: '/requests', urgent: o.awaiting_review > 0 },
      { module: 'requests', label: 'flagged uploads', count: o.exceptions, to: '/requests', urgent: o.exceptions > 0 }]; }));
    if (has('practice')) jobs.push(wrap(async () => { const o = await practice.overview(); return [
      { module: 'practice', label: 'jobs overdue', count: o.overdue, to: '/practice', urgent: o.overdue > 0 },
      { module: 'practice', label: 'jobs unassigned', count: o.unassigned, to: '/practice' }]; }));
    if (has('workpapers')) jobs.push(wrap(async () => { const o = await workpapers.overview(); return [
      { module: 'workpapers', label: 'packs in review', count: o.in_review, to: '/workpapers' },
      { module: 'workpapers', label: 'blocking issues', count: o.blocking_issues, to: '/workpapers', urgent: o.blocking_issues > 0 }]; }));
    if (has('advisory')) jobs.push(wrap(async () => { const o = await advisory.overview(); return [
      { module: 'advisory', label: 'clients needing action', count: o.action_alerts, to: '/advisory', urgent: o.action_alerts > 0 },
      { module: 'advisory', label: 'actions overdue', count: o.overdue_actions, to: '/advisory', urgent: o.overdue_actions > 0 }]; }));
    if (has('lending')) jobs.push(wrap(async () => { const o = await lending.overview(); return [
      { module: 'lending', label: 'applications with the client', count: o.awaiting_client, to: '/lending' },
      { module: 'lending', label: 'conditions open', count: o.conditions_open, to: '/lending' }]; }));
    if (has('academy')) jobs.push(wrap(async () => { const o = await academy.overview(); return [{ module: 'academy', label: 'training overdue', count: o.overdue, to: '/academy', urgent: o.overdue > 0 }]; }));
    if (has('billing')) jobs.push(wrap(async () => { const o = await practiceBilling.overview(); return [{ module: 'billing', label: 'invoices overdue', count: o.overdue_count, to: '/billing', urgent: o.overdue_count > 0 }]; }));
    if (has('client')) jobs.push(wrap(async () => { const o = await clientPortalStaff.overview(); return [{ module: 'client', label: 'unread client messages', count: o.unread_messages, to: '/client', urgent: o.unread_messages > 0 }]; }));
    jobs.push(wrap(async () => { const rows = await support.mine('pending'); return [{ module: 'hq' as ModuleKey, label: 'support tickets waiting on you', count: rows.length, to: '/hq/support' }]; }));

    void Promise.all(jobs).then((r) => setItems(r.flat().filter((i) => i.count > 0)));
  }, []);

  if (!items || items.length === 0) return null;
  const urgent = items.filter((i) => i.urgent);
  const rest = items.filter((i) => !i.urgent);

  return (
    <div className="mb-6">
      <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Across your modules</div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-4">
        {[...urgent, ...rest].map((i, n) => {
          const m = getModule(i.module);
          return (
            <Link key={n} to={i.to} className={`flex items-center gap-2.5 rounded-[6px] border bg-card px-3 py-2 text-[13px] hover:bg-muted/40 ${i.urgent ? 'border-warn/50' : ''}`}>
              <ModuleIcon name={m.icon} className={`size-4 shrink-0 ${i.urgent ? 'text-warn' : 'text-muted-foreground'}`} />
              <span className={`text-[18px] font-semibold tabular-nums leading-none ${i.urgent ? 'text-warn' : ''}`}>{i.count}</span>
              <span className="min-w-0 flex-1 truncate text-muted-foreground">{i.label}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
