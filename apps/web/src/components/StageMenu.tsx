import { ChevronDown } from 'lucide-react';
import { toast } from 'sonner';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@entiq/ui/dropdown-menu';
import { crm, STAGES, type ClientOut, type Stage } from '@/api/crm';
import { describeError } from '@/state/session';
import { StatusPill, stageTone } from './StatusPill';

/** Stage pill that opens a menu to move the client. One place; used on the list, the record and the pipeline. */
export function StageMenu({ client, onChanged, disabled }: { client: ClientOut; onChanged: (c: ClientOut) => void; disabled?: boolean }) {
  const move = async (stage: Stage) => {
    if (stage === client.stage) return;
    try {
      const updated = await crm.clients.setStage(client.id, stage);
      onChanged(updated);
      toast.success(`${client.name} → ${stage}`);
    } catch (e) { toast.error('Could not change stage', { description: describeError(e) }); }
  };
  if (disabled) return <StatusPill tone={stageTone(client.stage)}>{client.stage}</StatusPill>;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="inline-flex items-center gap-0.5 rounded-[4px] focus-visible:outline-2 focus-visible:outline-ring" aria-label={`Stage: ${client.stage}. Change`}>
          <StatusPill tone={stageTone(client.stage)}>{client.stage} <ChevronDown className="size-3 opacity-70" /></StatusPill>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {STAGES.map((s) => (
          <DropdownMenuItem key={s} onSelect={() => void move(s)} className={s === client.stage ? 'font-semibold' : ''}>
            <StatusPill tone={stageTone(s)} className="mr-2">{s}</StatusPill>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
