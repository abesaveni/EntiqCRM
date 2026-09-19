import { Button } from '@entiq/ui/button';
import { getModule } from '@entiq/modules';
import { INTEGRATIONS } from '@/mock/data';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';

/** Integration hub — blueprint MODULE 01 screen 4. Credentials are stored as encrypted references; never shown here. */
export function Integrations() {
  return (
    <div className="page">
      <PageHeader eyebrow="Practice HQ" title="Integration hub" description="Connect once, use everywhere. Each connection is available to every module you have that needs it." />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {INTEGRATIONS.map((i) => (
          <div key={i.key} className="flex flex-col rounded-[6px] border bg-card p-4">
            <div className="mb-2 flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold">{i.name}</div>
                <div className="text-[12px] text-muted-foreground">{i.category}</div>
              </div>
              <StatusPill tone={i.status === 'connected' ? 'success' : i.status === 'attention' ? 'warn' : 'neutral'}>
                {i.status === 'connected' ? 'Connected' : i.status === 'attention' ? 'Needs attention' : 'Not connected'}
              </StatusPill>
            </div>
            <p className="mb-3 flex-1 text-[13px] text-muted-foreground">{i.detail}</p>
            <div className="flex items-center justify-between gap-3 border-t pt-3">
              <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                Used by
                {i.usedBy.map((k) => { const m = getModule(k); return <span key={k} title={m.name} className="inline-flex"><ModuleIcon name={m.icon} className="size-3.5" /></span>; })}
              </div>
              <Button variant={i.status === 'connected' ? 'outline' : 'default'} size="sm">{i.status === 'connected' ? 'Manage' : i.status === 'attention' ? 'Fix' : 'Connect'}</Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
