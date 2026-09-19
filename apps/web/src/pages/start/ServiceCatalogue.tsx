import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Switch } from '@entiq/ui/switch';
import { getModule } from '@entiq/modules';
import { start, BASIS_LABEL, type ServiceOut, type EntityType } from '@/api/start';
import { CLIENT_TYPES } from '@/api/crm';
import { fmtCents } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';

const CATEGORIES = ['tax', 'bas', 'ias', 'financials', 'bookkeeping', 'payroll', 'asic', 'fbt', 'advisory', 'smsf', 'other'];
const EMPTY: Omit<ServiceOut, 'id'> = { name: '', category: 'tax', description: null, basis: 'annual', amount_cents: 0, gst: true, entity_types: [], is_active: true, sort: 0 };

/** The practice's service catalogue — what prospects pick from in stage 6 and proposals price from in stage 7. Activated services become Practice recurring work. */
export function ServiceCatalogue() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [rows, setRows] = useState<ServiceOut[] | null>(null);
  const [editing, setEditing] = useState<ServiceOut | Omit<ServiceOut, 'id'> | null>(null);
  const load = () => start.services.list(true).then(setRows).catch((e) => toast.error(describeError(e)));
  useEffect(() => { if (entitled('start')) void load(); }, []);
  if (!entitled('start')) return <UpsellPage module={getModule('start')} />;
  const edit = !readOnly && can('start:review');
  const save = async (s: ServiceOut | Omit<ServiceOut, 'id'>) => {
    try { if ('id' in s) await start.services.update(s.id, s); else await start.services.create(s); toast.success('Saved'); setEditing(null); await load(); } catch (e) { toast.error(describeError(e)); }
  };
  const groups = (rows ?? []).reduce<Record<string, ServiceOut[]>>((a, s) => { (a[s.category] ||= []).push(s); return a; }, {});
  return (
    <div className="page">
      <PageHeader eyebrow="Start" title="Service catalogue" description="What you offer and what it costs. Prospects choose from active services matching their entity type; proposals start from these prices."
        actions={edit && <div className="flex gap-2">{rows && rows.length === 0 && <Button size="sm" variant="outline" onClick={() => void start.services.seedDefaults().then(load)}>Load standard catalogue</Button>}<Button size="sm" onClick={() => setEditing({ ...EMPTY })}><Plus className="mr-1.5 size-4" /> Add service</Button></div>} />
      <div className="space-y-5">
        {Object.entries(groups).map(([cat, items]) => (
          <div key={cat}>
            <div className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{cat}</div>
            <ul className="divide-y rounded-[6px] border bg-card">
              {items.map((s) => (
                <li key={s.id} className={`flex items-center gap-3 px-5 py-2.5 text-[13px] ${s.is_active ? '' : 'opacity-60'}`}>
                  <div className="min-w-0 flex-1"><div className="font-medium">{s.name}</div><div className="text-[12px] text-muted-foreground">{s.entity_types.length ? s.entity_types.join(', ') : 'All entity types'}{s.description ? ` · ${s.description}` : ''}</div></div>
                  <span className="tabular-nums">{fmtCents(s.amount_cents)} <span className="text-[11px] text-muted-foreground">{BASIS_LABEL[s.basis]}{s.gst ? ' + GST' : ''}</span></span>
                  {edit && <Button size="sm" variant="ghost" onClick={() => setEditing(s)}>Edit</Button>}
                </li>
              ))}
            </ul>
          </div>
        ))}
        {rows && rows.length === 0 && <p className="py-14 text-center text-[13px] text-muted-foreground">No services yet. Load the standard catalogue or add your own.</p>}
      </div>
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}><DialogContent className="max-w-[520px]">
        <DialogHeader><DialogTitle>{editing && 'id' in editing ? 'Edit service' : 'New service'}</DialogTitle></DialogHeader>
        {editing && (
          <div className="grid gap-3 text-[13px]">
            <div className="grid gap-1.5"><Label>Name</Label><Input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} /></div>
            <div className="grid grid-cols-3 gap-3">
              <div className="grid gap-1.5"><Label>Category</Label><Select value={editing.category} onValueChange={(v) => setEditing({ ...editing, category: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></div>
              <div className="grid gap-1.5"><Label>Basis</Label><Select value={editing.basis} onValueChange={(v) => setEditing({ ...editing, basis: v as ServiceOut['basis'] })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(Object.keys(BASIS_LABEL) as ServiceOut['basis'][]).map((b) => <SelectItem key={b} value={b}>{BASIS_LABEL[b]}</SelectItem>)}</SelectContent></Select></div>
              <div className="grid gap-1.5"><Label>Amount ($ ex GST)</Label><Input type="number" min={0} value={editing.amount_cents / 100} onChange={(e) => setEditing({ ...editing, amount_cents: Math.round(Number(e.target.value || 0) * 100) })} /></div>
            </div>
            <div className="grid gap-1.5"><Label>Description</Label><Input value={editing.description ?? ''} onChange={(e) => setEditing({ ...editing, description: e.target.value || null })} /></div>
            <div className="grid gap-1.5"><Label>Entity types (none = all)</Label><div className="flex flex-wrap gap-1.5">{CLIENT_TYPES.map((t) => { const on = editing.entity_types.includes(t as EntityType); return <button key={t} type="button" className={`rounded-[4px] border px-2 py-0.5 text-[12px] ${on ? 'border-primary bg-primary/10' : ''}`} onClick={() => setEditing({ ...editing, entity_types: on ? editing.entity_types.filter((x) => x !== t) : [...editing.entity_types, t as EntityType] })}>{t}</button>; })}</div></div>
            <div className="flex items-center gap-6"><label className="flex items-center gap-2"><Switch checked={editing.gst} onCheckedChange={(v) => setEditing({ ...editing, gst: v })} /> GST applies</label><label className="flex items-center gap-2"><Switch checked={editing.is_active} onCheckedChange={(v) => setEditing({ ...editing, is_active: v })} /> Active</label></div>
          </div>
        )}
        <DialogFooter><Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button><Button disabled={!editing?.name.trim()} onClick={() => editing && void save(editing)}>Save</Button></DialogFooter>
      </DialogContent></Dialog>
    </div>
  );
}
