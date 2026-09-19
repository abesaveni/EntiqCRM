import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Checkbox } from '@entiq/ui/checkbox';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { getModule } from '@entiq/modules';
import { crm, type TaskOut, type StaffOut, type ClientOut } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, priorityTone } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';

type View = 'open' | 'mine' | 'done';

export function Tasks() {
  const readOnly = useSession((s) => s.readOnly);
  const [view, setView] = useState<View>('open');
  const [rows, setRows] = useState<TaskOut[] | null>(null);
  const [staff, setStaff] = useState<StaffOut[]>([]);
  const [clients, setClients] = useState<ClientOut[]>([]);
  const [newOpen, setNewOpen] = useState(false);

  const load = async () => {
    try {
      const [t, s] = await Promise.all([crm.tasks.list(view === 'done' ? { status: 'done' } : view === 'mine' ? { status: 'open', mine: true } : { status: 'open' }), crm.staff()]);
      setRows(t); setStaff(s);
    } catch (e) { toast.error('Could not load tasks', { description: describeError(e) }); }
  };
  useEffect(() => { void load(); }, [view]);
  useEffect(() => { void crm.clients.list({ size: 200 }).then((p) => setClients(p.items)).catch(() => undefined); }, []);

  const complete = async (t: TaskOut) => { try { await crm.tasks.complete(t.id); await load(); } catch (e) { toast.error(describeError(e)); } };
  const overdue = rows?.filter((t) => t.overdue) ?? [];
  const rest = rows?.filter((t) => !t.overdue) ?? [];

  return (
    <div className="page">
      <PageHeader title="Tasks" description="Follow-ups and work due across the practice. Tasks raised by other modules appear here too."
        actions={<Button size="sm" onClick={() => setNewOpen(true)} disabled={readOnly}><Plus className="mr-1.5 size-4" /> New task</Button>} />
      <Tabs value={view} onValueChange={(v) => setView(v as View)} className="mb-4"><TabsList><TabsTrigger value="open">Open</TabsTrigger><TabsTrigger value="mine">Assigned to me</TabsTrigger><TabsTrigger value="done">Done</TabsTrigger></TabsList></Tabs>
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <ul className="divide-y">
          {overdue.length > 0 && <li className="bg-error-bg/60 px-6 py-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-error">Overdue · {overdue.length}</li>}
          {[...overdue, ...rest].map((t) => { const m = getModule(t.module_key); return (
            <li key={t.id} className="flex items-center gap-3 px-6 py-2.5 text-[13px]">
              {view !== 'done' ? <Checkbox aria-label={`Complete ${t.title}`} disabled={readOnly} onCheckedChange={() => void complete(t)} /> : <span className="size-4" />}
              <ModuleIcon name={m.icon} className="size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className={`truncate ${t.status === 'done' ? 'line-through text-muted-foreground' : ''}`}>{t.title}</div>
                <div className="truncate text-[12px] text-muted-foreground">{t.client_id ? <Link to={`/clients/${t.client_id}`} className="hover:underline">{t.client_name}</Link> : 'Practice'} · {t.assignee_name ?? 'Unassigned'}</div>
              </div>
              <StatusPill tone={priorityTone(t.priority)}>{t.priority}</StatusPill>
              <span className={`w-[130px] shrink-0 text-right text-[12px] ${t.overdue ? 'font-medium text-error' : 'text-muted-foreground'}`}>
                {t.status === 'done' && t.done_at ? `done ${formatDistanceToNow(new Date(t.done_at), { addSuffix: true })}` : t.due_at ? `${t.overdue ? 'overdue' : 'due'} ${formatDistanceToNow(new Date(t.due_at), { addSuffix: !t.overdue })}` : 'no due date'}
              </span>
            </li>
          ); })}
          {rows && rows.length === 0 && <li className="px-6 py-14 text-center text-[13px] text-muted-foreground">{view === 'done' ? 'Nothing completed yet.' : 'Nothing open.'}</li>}
          {!rows && <li className="px-6 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
        </ul>
      </div>

      <NewTaskDialog open={newOpen} onOpenChange={setNewOpen} staff={staff} clients={clients} onDone={load} />
    </div>
  );
}

function NewTaskDialog({ open, onOpenChange, staff, clients, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; staff: StaffOut[]; clients: ClientOut[]; onDone: () => Promise<void> }) {
  const [title, setTitle] = useState(''); const [client, setClient] = useState(''); const [due, setDue] = useState(''); const [priority, setPriority] = useState<'Low' | 'Normal' | 'High'>('Normal'); const [assignee, setAssignee] = useState('');
  const submit = async () => {
    try { await crm.tasks.create({ title: title.trim(), client_id: client || null, due_at: due ? new Date(due).toISOString() : null, priority, assignee_membership_id: assignee || null }); await onDone(); onOpenChange(false); setTitle(''); setDue(''); setClient(''); toast.success('Task added'); }
    catch (e) { toast.error(describeError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[500px]">
      <DialogHeader><DialogTitle>New task</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid gap-1.5"><Label htmlFor="nt-title">Title</Label><Input id="nt-title" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus /></div>
        <div className="grid gap-1.5"><Label>Client</Label><Select value={client || 'none'} onValueChange={(v) => setClient(v === 'none' ? '' : v)}><SelectTrigger><SelectValue placeholder="Practice (no client)" /></SelectTrigger><SelectContent><SelectItem value="none">Practice (no client)</SelectItem>{clients.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5"><Label htmlFor="nt-due">Due</Label><Input id="nt-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label>Priority</Label><Select value={priority} onValueChange={(v) => setPriority(v as typeof priority)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{['Low', 'Normal', 'High'].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent></Select></div>
        </div>
        <div className="grid gap-1.5"><Label>Assign to</Label><Select value={assignee || 'none'} onValueChange={(v) => setAssignee(v === 'none' ? '' : v)}><SelectTrigger><SelectValue placeholder="Unassigned" /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{staff.map((s) => <SelectItem key={s.membership_id} value={s.membership_id}>{s.name}</SelectItem>)}</SelectContent></Select></div>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={() => void submit()} disabled={!title.trim()}>Add task</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
