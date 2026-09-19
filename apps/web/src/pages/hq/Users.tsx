import { useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { UserPlus, Check, Copy } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Checkbox } from '@entiq/ui/checkbox';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@entiq/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { catalogueModules, type ModuleKey } from '@entiq/modules';
import { api, type MemberOut } from '@/api/client';
import { useSession, describeError } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';

/** User directory + access matrix — blueprint MODULE 01 screens 5 & 6. Every tick is a server-side ModuleGrant. */
export function Users() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const owned = catalogueModules().filter((m) => m.status !== 'planned' && entitled(m.key));
  const grantable = owned.filter((m) => !['hq', 'crm', 'billing'].includes(m.key)); // base bundle needs no tick

  const [members, setMembers] = useState<MemberOut[] | null>(null);
  const [draft, setDraft] = useState<Record<string, Set<ModuleKey>>>({});
  const [saving, setSaving] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);

  const load = async () => {
    try {
      const rows = await api.users.list();
      setMembers(rows);
      setDraft(Object.fromEntries(rows.map((r) => [r.membership_id, new Set(r.modules)])));
    } catch (e) { toast.error('Could not load users', { description: describeError(e) }); }
  };
  useEffect(() => { void load(); }, []);

  const dirty = useMemo(() => {
    if (!members) return [];
    return members.filter((m) => { const a = new Set(m.modules); const b = draft[m.membership_id] ?? new Set(); return a.size !== b.size || [...a].some((k) => !b.has(k)); });
  }, [members, draft]);

  const toggle = (id: string, key: ModuleKey) => setDraft((d) => { const n = new Set(d[id]); n.has(key) ? n.delete(key) : n.add(key); return { ...d, [id]: n }; });

  const save = async () => {
    setSaving(true);
    try {
      for (const m of dirty) await api.users.setGrants(m.membership_id, [...(draft[m.membership_id] ?? [])]);
      toast.success('Access saved', { description: `${dirty.length} member${dirty.length === 1 ? '' : 's'} updated. Takes effect on their next request.` });
      await load();
    } catch (e) { toast.error('Could not save access', { description: describeError(e) }); } finally { setSaving(false); }
  };

  const canEdit = can('hq:access') && !readOnly;

  return (
    <div className="page">
      <PageHeader eyebrow="Practice HQ" title="Users & access" description="Who is in the practice, and which modules each person can open. Ticks here are enforced server-side on every request."
        actions={<Button size="sm" onClick={() => setInviteOpen(true)} disabled={!can('hq:users') || readOnly}><UserPlus className="mr-1.5 size-4" /> Invite user</Button>} />

      <Tabs defaultValue="matrix">
        <TabsList className="mb-4">
          <TabsTrigger value="matrix">Access matrix</TabsTrigger>
          <TabsTrigger value="directory">Directory</TabsTrigger>
          <TabsTrigger value="roles">Roles &amp; templates</TabsTrigger>
        </TabsList>

        <TabsContent value="matrix">
          <div className="overflow-x-auto rounded-[6px] border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="min-w-[240px]">User</TableHead>
                  <TableHead className="text-center"><div className="flex flex-col items-center gap-1"><ModuleIcon name="Users" className="size-4 text-muted-foreground" /><span className="text-[11px]">Base plan</span></div></TableHead>
                  {grantable.map((m) => (
                    <TableHead key={m.key} className="text-center">
                      <div className="flex flex-col items-center gap-1"><ModuleIcon name={m.icon} className="size-4 text-muted-foreground" /><span className="text-[11px]">{m.shortName}</span></div>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {members === null && <TableRow><TableCell colSpan={2 + grantable.length} className="py-10 text-center text-muted-foreground">Loading…</TableCell></TableRow>}
                {members?.map((u) => {
                  const privileged = u.role === 'owner' || u.role === 'admin';
                  return (
                    <TableRow key={u.membership_id}>
                      <TableCell>
                        <div className="flex items-center gap-2 font-medium">{u.full_name} <StatusPill tone={u.role === 'owner' ? 'teal' : 'neutral'} className="capitalize">{u.role}</StatusPill></div>
                        <div className="text-[12px] text-muted-foreground">{u.job_title ? `${u.job_title} · ` : ''}{u.email}</div>
                      </TableCell>
                      <TableCell className="text-center"><Checkbox checked disabled aria-label="Base plan — always" /></TableCell>
                      {grantable.map((m) => (
                        <TableCell key={m.key} className="text-center">
                          <Checkbox checked={privileged || (draft[u.membership_id]?.has(m.key) ?? false)} disabled={privileged || !canEdit} onCheckedChange={() => toggle(u.membership_id, m.key)} aria-label={`${u.full_name} · ${m.shortName}`} />
                        </TableCell>
                      ))}
                    </TableRow>
                  );
                })}
                {members?.length === 0 && <TableRow><TableCell colSpan={2 + grantable.length} className="py-10 text-center text-muted-foreground">No members yet.</TableCell></TableRow>}
              </TableBody>
            </Table>
          </div>
          <div className="mt-3 flex items-center justify-between gap-3 text-[12px] text-muted-foreground">
            <span>Owners and admins hold every module the practice has; staff hold what is ticked.</span>
            <Button size="sm" onClick={() => void save()} disabled={!dirty.length || saving || !canEdit}><Check className="mr-1.5 size-4" /> {saving ? 'Saving…' : dirty.length ? `Save ${dirty.length} change${dirty.length === 1 ? '' : 's'}` : 'Saved'}</Button>
          </div>
        </TabsContent>

        <TabsContent value="directory">
          <div className="overflow-hidden rounded-[6px] border bg-card">
            <Table>
              <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Role</TableHead><TableHead>Email</TableHead><TableHead>Status</TableHead><TableHead>Last sign-in</TableHead><TableHead className="text-right">Modules</TableHead></TableRow></TableHeader>
              <TableBody>
                {members?.map((u) => (
                  <TableRow key={u.membership_id}>
                    <TableCell className="font-medium">{u.full_name}</TableCell>
                    <TableCell className="capitalize text-muted-foreground">{u.role}</TableCell>
                    <TableCell className="text-muted-foreground">{u.email}</TableCell>
                    <TableCell><StatusPill tone={u.status === 'active' ? 'success' : u.status === 'invited' ? 'info' : 'neutral'} className="capitalize">{u.status}</StatusPill></TableCell>
                    <TableCell className="text-muted-foreground">{u.last_login_at ? new Date(u.last_login_at).toLocaleString('en-AU', { dateStyle: 'medium', timeStyle: 'short' }) : '—'}</TableCell>
                    <TableCell className="text-right tabular-nums">{u.role === 'staff' ? u.modules.length : 'all'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="roles">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {[
              { name: 'Owner', desc: 'Every module, approvals, sign-offs, billing and the card on file. At least one per practice.' },
              { name: 'Admin', desc: 'Runs the practice: users, access, integrations, settings. Cannot change the subscription.' },
              { name: 'Staff', desc: 'Base plan always; other modules only where ticked in the access matrix.' },
            ].map((r) => (
              <div key={r.name} className="rounded-[6px] border bg-card p-4"><div className="mb-1 font-medium">{r.name}</div><p className="text-[13px] text-muted-foreground">{r.desc}</p><div className="mt-2 text-[12px] text-muted-foreground">{members?.filter((m) => m.role === r.name.toLowerCase()).length ?? '—'} member{members?.filter((m) => m.role === r.name.toLowerCase()).length === 1 ? '' : 's'}</div></div>
            ))}
            <button className="rounded-[6px] border border-dashed p-4 text-left text-[13px] text-muted-foreground hover:bg-secondary" disabled>+ Custom role templates (next)</button>
          </div>
        </TabsContent>
      </Tabs>

      <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} grantable={grantable} onInvited={load} />
    </div>
  );
}

function InviteDialog({ open, onOpenChange, grantable, onInvited }: { open: boolean; onOpenChange: (o: boolean) => void; grantable: ReturnType<typeof catalogueModules>; onInvited: () => Promise<void> }) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'admin' | 'staff'>('staff');
  const [title, setTitle] = useState('');
  const [mods, setMods] = useState<Set<ModuleKey>>(new Set());
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState<string | null>(null);

  const reset = () => { setEmail(''); setRole('staff'); setTitle(''); setMods(new Set()); setLink(null); };

  const send = async () => {
    setBusy(true);
    try {
      const out = await api.users.invite({ email, role, modules: role === 'staff' ? [...mods] : [], job_title: title || undefined });
      toast.success(`Invitation created for ${out.email}`, { description: out.accept_url ? 'Email delivery lands with the notify package — copy the link below for now.' : 'An email is on its way.' });
      setLink(out.accept_url);
      await onInvited();
    } catch (e) { toast.error('Could not invite', { description: describeError(e) }); } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { onOpenChange(o); if (!o) reset(); }}>
      <DialogContent className="max-w-[520px]">
        <DialogHeader><DialogTitle>Invite a user</DialogTitle><DialogDescription>They set their own password from the link. Access can be changed any time in the matrix.</DialogDescription></DialogHeader>
        {link ? (
          <div className="space-y-3 text-[13px]">
            <div className="rounded-[5px] border bg-secondary/50 p-3 break-all font-mono text-[12px]">{link}</div>
            <Button variant="outline" size="sm" onClick={() => { void navigator.clipboard?.writeText(link); toast('Link copied'); }}><Copy className="mr-1.5 size-3.5" /> Copy link</Button>
          </div>
        ) : (
          <div className="space-y-4 text-[13px]">
            <div className="grid gap-1.5"><Label htmlFor="inv-email">Work email</Label><Input id="inv-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-1.5"><Label>Role</Label>
                <Select value={role} onValueChange={(v) => setRole(v as 'admin' | 'staff')}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="staff">Staff</SelectItem><SelectItem value="admin">Admin</SelectItem></SelectContent></Select>
              </div>
              <div className="grid gap-1.5"><Label htmlFor="inv-title">Job title</Label><Input id="inv-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Senior accountant" /></div>
            </div>
            {role === 'staff' && grantable.length > 0 && (
              <div className="grid gap-2">
                <Label>Modules they can open</Label>
                <div className="grid grid-cols-2 gap-2">
                  {grantable.map((m) => (
                    <label key={m.key} className="flex items-center gap-2 rounded-[5px] border px-2.5 py-2">
                      <Checkbox checked={mods.has(m.key)} onCheckedChange={() => setMods((s) => { const n = new Set(s); n.has(m.key) ? n.delete(m.key) : n.add(m.key); return n; })} />
                      <ModuleIcon name={m.icon} className="size-3.5 text-muted-foreground" /> {m.shortName}
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{link ? 'Done' : 'Cancel'}</Button>
          {!link && <Button onClick={() => void send()} disabled={busy || !/.+@.+\..+/.test(email)}>{busy ? 'Sending…' : 'Send invitation'}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
