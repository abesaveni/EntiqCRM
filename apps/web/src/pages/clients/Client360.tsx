import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { Mail, Phone, Plus, MoreHorizontal, Archive, Pin, Trash2, Link2 } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Checkbox } from '@entiq/ui/checkbox';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { Textarea } from '@entiq/ui/textarea';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from '@entiq/ui/dropdown-menu';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { getModule, panelContributors, type ModuleManifest } from '@entiq/modules';
import { crm, fmtDate, RELATIONSHIP_KINDS, type ClientOut, type ContactOut, type NoteOut, type RelationshipOut, type StaffOut, type TaskOut, type TimelineOut } from '@/api/crm';
import { useSession, describeError } from '@/state/session';
import { StatusPill, riskTone, priorityTone } from '@/components/StatusPill';
import { StageMenu } from '@/components/StageMenu';
import { UpsellPanel } from '@/components/Upsell';
import { ModuleIcon } from '@/lib/icons';
import { ModulePanel } from './panels';

/**
 * The client record as a COMPOSITION SURFACE. Left: what the base plan always provides.
 * Right: one slot per contributing module — live panel when subscribed, upsell tile when not.
 */
export function Client360() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const entitledKey = useSession((s) => s.entitled);
  const entitlements = useSession((s) => s.entitlements);
  const readOnly = useSession((s) => s.readOnly);
  void entitlements;

  const [client, setClient] = useState<ClientOut | null>(null);
  const [contacts, setContacts] = useState<ContactOut[]>([]);
  const [timeline, setTimeline] = useState<TimelineOut[]>([]);
  const [tasks, setTasks] = useState<TaskOut[]>([]);
  const [notes, setNotes] = useState<NoteOut[]>([]);
  const [rels, setRels] = useState<RelationshipOut[]>([]);
  const [staff, setStaff] = useState<StaffOut[]>([]);
  const [missing, setMissing] = useState(false);
  const [noteBody, setNoteBody] = useState('');
  const [taskOpen, setTaskOpen] = useState(false);
  const [contactOpen, setContactOpen] = useState(false);
  const [relOpen, setRelOpen] = useState(false);

  const loadAll = async () => {
    try {
      const [c, ct, tl, ts, ns, rl, st] = await Promise.all([crm.clients.get(id), crm.clients.contacts(id), crm.clients.timeline(id), crm.tasks.list({ client_id: id, status: 'open' }), crm.clients.notes(id), crm.clients.relationships(id), crm.staff()]);
      setClient(c); setContacts(ct); setTimeline(tl); setTasks(ts); setNotes(ns); setRels(rl); setStaff(st);
    } catch (e) { setMissing(true); toast.error('Could not load client', { description: describeError(e) }); }
  };
  useEffect(() => { void loadAll(); }, [id]);

  if (missing) return <div className="page"><p className="text-muted-foreground">Client not found. <Link to="/clients" className="text-primary hover:underline">Back to clients</Link></p></div>;
  if (!client) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;

  const contributors = panelContributors();
  const entitled = (m: ModuleManifest) => entitledKey(m.key);

  const addNote = async () => {
    if (!noteBody.trim()) return;
    try { await crm.clients.addNote(client.id, noteBody.trim()); setNoteBody(''); await loadAll(); toast.success('Note added'); } catch (e) { toast.error(describeError(e)); }
  };
  const completeTask = async (t: TaskOut) => { try { await crm.tasks.complete(t.id); await loadAll(); } catch (e) { toast.error(describeError(e)); } };
  const archive = async () => {
    if (!confirm(`Archive ${client.name}? The record and its history are kept; it leaves lists and search.`)) return;
    try { await crm.clients.archive(client.id); toast.success('Archived'); navigate('/clients'); } catch (e) { toast.error(describeError(e)); }
  };

  return (
    <div className="page">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-1 text-[12px] text-muted-foreground"><Link to="/clients" className="hover:underline">Clients</Link> / {client.client_type}</div>
          <h1 className="truncate">{client.name}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[13px] text-muted-foreground">
            {client.abn_formatted && <span>ABN {client.abn_formatted}</span>}
            {client.acn && <span>· ACN {client.acn}</span>}
            {client.since && <span>· client since {fmtDate(client.since, { month: 'short', year: 'numeric' })}</span>}
            <span>· owner {client.owner_name ?? 'unassigned'}</span>
            {client.source && <span>· via {client.source.replace('import:', '').toUpperCase()}</span>}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <StageMenu client={client} onChanged={(c) => { setClient(c); void crm.clients.timeline(id).then(setTimeline); }} disabled={readOnly} />
            {client.risk_rating && entitledKey('verify') && <StatusPill tone={riskTone(client.risk_rating)}>Risk · {client.risk_rating}</StatusPill>}
            {client.tags.map((t) => <StatusPill key={t}>{t}</StatusPill>)}
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" size="sm" onClick={() => setTaskOpen(true)} disabled={readOnly}><Plus className="mr-1.5 size-4" /> Task</Button>
          <Button variant="outline" size="sm" onClick={() => setContactOpen(true)} disabled={readOnly}><Plus className="mr-1.5 size-4" /> Contact</Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild><Button variant="outline" size="icon" className="size-8" aria-label="More"><MoreHorizontal className="size-4" /></Button></DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => setRelOpen(true)} disabled={readOnly}><Link2 className="mr-2 size-4" /> Add relationship</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => void archive()} disabled={readOnly} className="text-error"><Archive className="mr-2 size-4" /> Archive client</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        {/* LEFT — base plan */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="flex-row items-center justify-between pb-3">
              <CardTitle className="text-[15px]">Contacts &amp; relationships</CardTitle>
              <span className="text-[12px] text-muted-foreground">{contacts.length} people · {rels.length} relationships</span>
            </CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y">
                {contacts.map((p) => (
                  <li key={p.id} className="flex items-center gap-3 px-6 py-2.5">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-[12px] font-semibold">{p.full_name.split(' ').map((s) => s[0]).slice(0, 2).join('')}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 text-[13px] font-medium">{p.full_name}{p.is_primary && <StatusPill tone="teal">Primary</StatusPill>}{p.has_portal_access && <StatusPill tone="info">Portal</StatusPill>}</div>
                      <div className="text-[12px] text-muted-foreground">{p.role ?? 'Contact'}{p.email ? ` · ${p.email}` : ''}</div>
                    </div>
                    <div className="flex shrink-0 gap-1">
                      {p.email && <Button variant="ghost" size="icon" className="size-8" asChild><a href={`mailto:${p.email}`} aria-label="Email"><Mail className="size-4" /></a></Button>}
                      {p.phone && <Button variant="ghost" size="icon" className="size-8" asChild><a href={`tel:${p.phone}`} aria-label="Call"><Phone className="size-4" /></a></Button>}
                    </div>
                  </li>
                ))}
                {contacts.length === 0 && <li className="px-6 py-6 text-center text-[13px] text-muted-foreground">No contacts yet.</li>}
                {rels.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 bg-secondary/40 px-6 py-2 text-[12.5px]">
                    <Link2 className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="min-w-0 flex-1 truncate"><strong>{r.from_label}</strong> is {r.kind.replace(/_/g, ' ')} <strong>{r.to_label}</strong>{r.percentage != null ? ` · ${r.percentage}%` : ''}</span>
                    {!readOnly && <button className="text-muted-foreground hover:text-error" aria-label="End relationship" onClick={() => void crm.relationships.end(r.id).then(loadAll)}><Trash2 className="size-3.5" /></button>}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-0">
              <Tabs defaultValue="timeline">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-[15px]">Activity</CardTitle>
                  <TabsList className="h-8">
                    <TabsTrigger value="timeline" className="text-[12px]">Timeline</TabsTrigger>
                    <TabsTrigger value="tasks" className="text-[12px]">Tasks · {tasks.length}</TabsTrigger>
                    <TabsTrigger value="notes" className="text-[12px]">Notes · {notes.length}</TabsTrigger>
                  </TabsList>
                </div>
                <TabsContent value="timeline" className="-mx-6 mt-3 border-t">
                  <ul className="divide-y">
                    {timeline.map((a) => { const m = getModule(a.module_key); return (
                      <li key={a.id} className="flex items-start gap-3 px-6 py-3">
                        <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-[4px] bg-muted"><ModuleIcon name={m.icon} className="size-3.5 text-muted-foreground" /></span>
                        <div className="min-w-0 flex-1"><div className="text-[13px]">{a.summary}</div><div className="text-[12px] text-muted-foreground">{m.shortName} · {a.actor_label} · {formatDistanceToNow(new Date(a.occurred_at), { addSuffix: true })}</div></div>
                      </li>
                    ); })}
                    {timeline.length === 0 && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">No activity yet.</li>}
                  </ul>
                </TabsContent>
                <TabsContent value="tasks" className="-mx-6 mt-3 border-t">
                  <ul className="divide-y">
                    {tasks.map((t) => (
                      <li key={t.id} className="flex items-center gap-3 px-6 py-2.5 text-[13px]">
                        <Checkbox aria-label={`Complete ${t.title}`} disabled={readOnly} onCheckedChange={() => void completeTask(t)} />
                        <span className="flex-1">{t.title}</span>
                        <StatusPill tone={priorityTone(t.priority)}>{t.priority}</StatusPill>
                        <span className={`text-[12px] ${t.overdue ? 'font-medium text-error' : 'text-muted-foreground'}`}>{t.assignee_name ?? 'Unassigned'}{t.due_at ? ` · ${t.overdue ? 'overdue' : 'due'} ${formatDistanceToNow(new Date(t.due_at), { addSuffix: !t.overdue })}` : ''}</span>
                      </li>
                    ))}
                    {tasks.length === 0 && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">Nothing open.</li>}
                  </ul>
                </TabsContent>
                <TabsContent value="notes" className="-mx-6 mt-3 border-t">
                  {!readOnly && (
                    <div className="border-b px-6 py-3">
                      <Textarea value={noteBody} onChange={(e) => setNoteBody(e.target.value)} placeholder="Add a note — it lands on the timeline." rows={2} />
                      <div className="mt-2 flex justify-end"><Button size="sm" onClick={() => void addNote()} disabled={!noteBody.trim()}>Add note</Button></div>
                    </div>
                  )}
                  <ul className="divide-y">
                    {notes.map((n) => (
                      <li key={n.id} className="px-6 py-3 text-[13px]">
                        <div className="mb-1 flex items-center gap-2 text-[12px] text-muted-foreground">{n.pinned && <Pin className="size-3 text-primary" />}{n.author_name ?? 'Unknown'} · {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
                          {!readOnly && <button className="ml-auto hover:text-error" aria-label="Delete note" onClick={() => void crm.notes.remove(n.id).then(loadAll)}><Trash2 className="size-3.5" /></button>}
                        </div>
                        <div className="whitespace-pre-wrap">{n.body}</div>
                      </li>
                    ))}
                    {notes.length === 0 && <li className="px-6 py-8 text-center text-[13px] text-muted-foreground">No notes yet.</li>}
                  </ul>
                </TabsContent>
              </Tabs>
            </CardHeader>
            <CardContent className="hidden" />
          </Card>
        </div>

        {/* RIGHT — module contributions */}
        <div>
          <div className="mb-2 flex items-center justify-between px-0.5">
            <span className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">From your modules</span>
            <Link to="/hq/modules" className="text-[12px] text-muted-foreground hover:underline">Manage</Link>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
            {contributors.map((m) => (
              <div key={m.key} className="min-h-[150px]">{entitled(m) ? <ModulePanel module={m} client={client} /> : <UpsellPanel module={m} message={m.panels[0]?.upsell} />}</div>
            ))}
          </div>
        </div>
      </div>

      <TaskDialog open={taskOpen} onOpenChange={setTaskOpen} clientId={client.id} staff={staff} onDone={loadAll} />
      <ContactDialog open={contactOpen} onOpenChange={setContactOpen} clientId={client.id} onDone={loadAll} />
      <RelationshipDialog open={relOpen} onOpenChange={setRelOpen} client={client} contacts={contacts} onDone={loadAll} />
    </div>
  );
}

// ---------------------------------------------------------------- dialogs
function TaskDialog({ open, onOpenChange, clientId, staff, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; clientId: string; staff: StaffOut[]; onDone: () => Promise<void> }) {
  const [title, setTitle] = useState(''); const [due, setDue] = useState(''); const [priority, setPriority] = useState<'Low' | 'Normal' | 'High'>('Normal'); const [assignee, setAssignee] = useState<string>('');
  const submit = async () => {
    try { await crm.tasks.create({ title: title.trim(), client_id: clientId, due_at: due ? new Date(due).toISOString() : null, priority, assignee_membership_id: assignee || null }); await onDone(); onOpenChange(false); setTitle(''); setDue(''); toast.success('Task added'); }
    catch (e) { toast.error(describeError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[480px]">
      <DialogHeader><DialogTitle>New task</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid gap-1.5"><Label htmlFor="t-title">Title</Label><Input id="t-title" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus /></div>
        <div className="grid grid-cols-2 gap-3">
          <div className="grid gap-1.5"><Label htmlFor="t-due">Due</Label><Input id="t-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></div>
          <div className="grid gap-1.5"><Label>Priority</Label><Select value={priority} onValueChange={(v) => setPriority(v as typeof priority)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{['Low', 'Normal', 'High'].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent></Select></div>
        </div>
        <div className="grid gap-1.5"><Label>Assign to</Label><Select value={assignee || 'none'} onValueChange={(v) => setAssignee(v === 'none' ? '' : v)}><SelectTrigger><SelectValue placeholder="Unassigned" /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{staff.map((s) => <SelectItem key={s.membership_id} value={s.membership_id}>{s.name}</SelectItem>)}</SelectContent></Select></div>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={() => void submit()} disabled={!title.trim()}>Add task</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function ContactDialog({ open, onOpenChange, clientId, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; clientId: string; onDone: () => Promise<void> }) {
  const [f, setF] = useState({ first_name: '', last_name: '', email: '', phone: '', role: '', is_primary: false });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const submit = async () => {
    try { await crm.clients.addContact(clientId, { ...f, last_name: f.last_name || null, email: f.email || null, phone: f.phone || null, role: f.role || null }); await onDone(); onOpenChange(false); setF({ first_name: '', last_name: '', email: '', phone: '', role: '', is_primary: false }); toast.success('Contact added'); }
    catch (e) { toast.error(describeError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[480px]">
      <DialogHeader><DialogTitle>Add contact</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid grid-cols-2 gap-3"><div className="grid gap-1.5"><Label htmlFor="c-fn">First name</Label><Input id="c-fn" value={f.first_name} onChange={set('first_name')} autoFocus /></div><div className="grid gap-1.5"><Label htmlFor="c-ln">Last name</Label><Input id="c-ln" value={f.last_name} onChange={set('last_name')} /></div></div>
        <div className="grid gap-1.5"><Label htmlFor="c-role">Role</Label><Input id="c-role" value={f.role} onChange={set('role')} placeholder="Director · Trustee · Bookkeeper" /></div>
        <div className="grid grid-cols-2 gap-3"><div className="grid gap-1.5"><Label htmlFor="c-email">Email</Label><Input id="c-email" type="email" value={f.email} onChange={set('email')} /></div><div className="grid gap-1.5"><Label htmlFor="c-phone">Phone</Label><Input id="c-phone" value={f.phone} onChange={set('phone')} /></div></div>
        <label className="flex items-center gap-2"><Checkbox checked={f.is_primary} onCheckedChange={(v) => setF({ ...f, is_primary: !!v })} /> Primary contact</label>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={() => void submit()} disabled={!f.first_name.trim()}>Add contact</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}

function RelationshipDialog({ open, onOpenChange, client, contacts, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; client: ClientOut; contacts: ContactOut[]; onDone: () => Promise<void> }) {
  const [from, setFrom] = useState(''); const [kind, setKind] = useState<string>('director_of'); const [pct, setPct] = useState('');
  const submit = async () => {
    try { await crm.relationships.add({ from_type: 'contact', from_id: from, to_type: 'client', to_id: client.id, kind, percentage: pct ? Number(pct) : null }); await onDone(); onOpenChange(false); toast.success('Relationship added'); }
    catch (e) { toast.error(describeError(e)); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-[480px]">
      <DialogHeader><DialogTitle>Add relationship</DialogTitle></DialogHeader>
      <div className="grid gap-3 text-[13px]">
        <div className="grid gap-1.5"><Label>Person</Label><Select value={from} onValueChange={setFrom}><SelectTrigger><SelectValue placeholder="Choose a contact" /></SelectTrigger><SelectContent>{contacts.map((c) => <SelectItem key={c.id} value={c.id}>{c.full_name}</SelectItem>)}</SelectContent></Select></div>
        <div className="grid gap-1.5"><Label>is</Label><Select value={kind} onValueChange={setKind}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{RELATIONSHIP_KINDS.map((k) => <SelectItem key={k} value={k}>{k.replace(/_/g, ' ')}</SelectItem>)}</SelectContent></Select></div>
        <div className="text-muted-foreground">→ <strong className="text-foreground">{client.name}</strong></div>
        {(kind === 'shareholder_of' || kind === 'owner_of' || kind === 'beneficiary_of') && <div className="grid gap-1.5"><Label htmlFor="r-pct">Percentage</Label><Input id="r-pct" type="number" min={0} max={100} value={pct} onChange={(e) => setPct(e.target.value)} className="w-28" /></div>}
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={() => void submit()} disabled={!from}>Add</Button></DialogFooter>
    </DialogContent></Dialog>
  );
}
