import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { crm, CLIENT_TYPES, STAGES, type ClientOut, type ClientType, type Stage } from '@/api/crm';
import { describeError } from '@/state/session';

export function NewClientDialog({ open, onOpenChange, onCreated, defaultStage = 'Lead' }: { open: boolean; onOpenChange: (o: boolean) => void; onCreated: (c: ClientOut) => void; defaultStage?: Stage }) {
  const [f, setF] = useState({ name: '', client_type: 'Company' as ClientType, abn: '', stage: defaultStage as Stage, email: '', phone: '', first_name: '', last_name: '' });
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });

  const submit = async () => {
    setBusy(true);
    try {
      const c = await crm.clients.create({ name: f.name.trim(), client_type: f.client_type, abn: f.abn.trim() || null, stage: f.stage, email: f.email.trim() || null, phone: f.phone.trim() || null, source: 'manual' });
      if (f.first_name.trim()) await crm.clients.addContact(c.id, { first_name: f.first_name.trim(), last_name: f.last_name.trim() || null, email: f.email.trim() || null, phone: f.phone.trim() || null, is_primary: true, role: f.client_type === 'Individual' ? 'Owner' : 'Primary contact' });
      toast.success(`${c.name} added`);
      onCreated(await crm.clients.get(c.id));
      onOpenChange(false);
      setF({ name: '', client_type: 'Company', abn: '', stage: defaultStage, email: '', phone: '', first_name: '', last_name: '' });
    } catch (e) { toast.error('Could not add client', { description: describeError(e) }); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[560px]">
        <DialogHeader><DialogTitle>New client</DialogTitle><DialogDescription>One record per legal party. Contacts, entities and modules attach to it.</DialogDescription></DialogHeader>
        <div className="grid gap-4 text-[13px]">
          <div className="grid gap-1.5"><Label htmlFor="nc-name">Name</Label><Input id="nc-name" value={f.name} onChange={set('name')} placeholder="Ashfield Family Trust" autoFocus /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5"><Label>Type</Label>
              <Select value={f.client_type} onValueChange={(v) => setF({ ...f, client_type: v as ClientType })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{CLIENT_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select>
            </div>
            <div className="grid gap-1.5"><Label>Stage</Label>
              <Select value={f.stage} onValueChange={(v) => setF({ ...f, stage: v as Stage })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{STAGES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent></Select>
            </div>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="nc-abn">ABN <span className="text-muted-foreground">(optional)</span></Label><Input id="nc-abn" value={f.abn} onChange={set('abn')} placeholder="62 114 887 302" inputMode="numeric" /></div>
          <div className="mt-1 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Primary contact (optional)</div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5"><Label htmlFor="nc-fn">First name</Label><Input id="nc-fn" value={f.first_name} onChange={set('first_name')} /></div>
            <div className="grid gap-1.5"><Label htmlFor="nc-ln">Last name</Label><Input id="nc-ln" value={f.last_name} onChange={set('last_name')} /></div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5"><Label htmlFor="nc-email">Email</Label><Input id="nc-email" type="email" value={f.email} onChange={set('email')} /></div>
            <div className="grid gap-1.5"><Label htmlFor="nc-phone">Phone</Label><Input id="nc-phone" value={f.phone} onChange={set('phone')} /></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => void submit()} disabled={busy || f.name.trim().length < 1}>{busy ? 'Adding…' : 'Add client'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
