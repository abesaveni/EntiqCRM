import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { crm, type PipelineColumn, type ClientOut } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StageMenu } from '@/components/StageMenu';
import { StatusPill, riskTone } from '@/components/StatusPill';
import { NewClientDialog } from './clients/NewClientDialog';

/** Opportunity pipeline — blueprint MODULE 16 screen 4. Columns are stages; move a client from its card. */
export function Pipeline() {
  const [cols, setCols] = useState<PipelineColumn[] | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const readOnly = useSession((s) => s.readOnly);
  const load = async () => { try { setCols(await crm.pipeline()); } catch (e) { toast.error('Could not load pipeline', { description: describeError(e) }); } };
  useEffect(() => { void load(); }, []);

  const moved = (c: ClientOut) => { void load(); void c; };
  const total = cols?.reduce((n, c) => n + c.count, 0) ?? 0;

  return (
    <div className="page">
      <PageHeader title="Pipeline" description={`${total} client${total === 1 ? '' : 's'} by stage. Change a stage from the card — it lands on the client's timeline.`}
        actions={<Button size="sm" onClick={() => setNewOpen(true)} disabled={readOnly}><Plus className="mr-1.5 size-4" /> New lead</Button>} />
      <div className="-mx-6 overflow-x-auto px-6 pb-4">
        <div className="flex min-w-[1100px] gap-3">
          {cols?.map((col) => (
            <div key={col.stage} className="flex w-[260px] shrink-0 flex-col rounded-[6px] border bg-secondary/40">
              <div className="flex items-center justify-between border-b bg-card px-3 py-2 text-[13px] font-semibold">{col.stage}<span className="rounded-[4px] bg-muted px-1.5 text-[11px] font-medium tabular-nums">{col.count}</span></div>
              <div className="flex flex-col gap-2 p-2">
                {col.clients.map((c) => (
                  <div key={c.id} className="rounded-[5px] border bg-card p-3 text-[13px]">
                    <Link to={`/clients/${c.id}`} className="block truncate font-medium hover:underline">{c.name}</Link>
                    <div className="mb-2 truncate text-[12px] text-muted-foreground">{c.client_type}{c.primary_contact ? ` · ${c.primary_contact.full_name}` : ''}</div>
                    <div className="flex items-center justify-between gap-2">
                      <StageMenu client={c} onChanged={moved} disabled={readOnly} />
                      <div className="flex items-center gap-1">{c.risk_rating && <StatusPill tone={riskTone(c.risk_rating)}>{c.risk_rating}</StatusPill>}{c.open_task_count > 0 && <span className="text-[11px] text-muted-foreground">{c.open_task_count} task{c.open_task_count === 1 ? '' : 's'}</span>}</div>
                    </div>
                  </div>
                ))}
                {col.clients.length === 0 && <div className="py-6 text-center text-[12px] text-muted-foreground">Empty</div>}
                {col.count > col.clients.length && <Link to={`/clients?stage=${col.stage}`} className="py-1 text-center text-[12px] text-primary hover:underline">+{col.count - col.clients.length} more</Link>}
              </div>
            </div>
          ))}
          {!cols && <div className="py-10 text-[13px] text-muted-foreground">Loading…</div>}
        </div>
      </div>
      <NewClientDialog open={newOpen} onOpenChange={setNewOpen} onCreated={() => void load()} defaultStage="Lead" />
    </div>
  );
}
