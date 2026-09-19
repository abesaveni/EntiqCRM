import { useState } from 'react';
import { toast } from 'sonner';
import { UserPlus, Check } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Checkbox } from '@entiq/ui/checkbox';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@entiq/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { catalogueModules, type ModuleKey } from '@entiq/modules';
import { useSession, isEntitled } from '@/state/session';
import { STAFF } from '@/mock/data';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';

/** User directory + access matrix — blueprint MODULE 01 screens 5 & 6: "module tick boxes and permission levels". */
export function Users() {
  const tenant = useSession((s) => s.tenant);
  const subscriptions = useSession((s) => s.subscriptions);
  const owned = catalogueModules().filter((m) => m.status !== 'planned' && isEntitled({ tenant, subscriptions }, m.key));
  const [grants, setGrants] = useState<Record<string, Set<ModuleKey>>>(() => Object.fromEntries(STAFF.map((s) => [s.id, new Set(s.modules)])));

  const toggle = (uid: string, mk: ModuleKey) => {
    setGrants((g) => {
      const next = new Set(g[uid]);
      next.has(mk) ? next.delete(mk) : next.add(mk);
      return { ...g, [uid]: next };
    });
  };

  return (
    <div className="page">
      <PageHeader eyebrow="Practice HQ" title="Users & access" description="Who is in the practice, and which modules each person can open. Ticks here are enforced server-side on every request." actions={<Button size="sm"><UserPlus className="mr-1.5 size-4" /> Invite user</Button>} />

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
                  <TableHead className="min-w-[220px]">User</TableHead>
                  {owned.map((m) => (
                    <TableHead key={m.key} className="text-center">
                      <div className="flex flex-col items-center gap-1"><ModuleIcon name={m.icon} className="size-4 text-muted-foreground" /><span className="text-[11px]">{m.shortName}</span></div>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {STAFF.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <div className="font-medium">{u.name}</div>
                      <div className="text-[12px] text-muted-foreground">{u.role} · {u.email}</div>
                    </TableCell>
                    {owned.map((m) => (
                      <TableCell key={m.key} className="text-center">
                        <Checkbox checked={grants[u.id]?.has(m.key) ?? false} onCheckedChange={() => toggle(u.id, m.key)} aria-label={`${u.name} · ${m.shortName}`} disabled={m.key === 'hq' && u.role === 'Partner'} />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-3 flex justify-end">
            <Button size="sm" onClick={() => toast.success('Access saved', { description: 'Changes take effect on each user\'s next request.' })}><Check className="mr-1.5 size-4" /> Save access</Button>
          </div>
        </TabsContent>

        <TabsContent value="directory">
          <div className="overflow-hidden rounded-[6px] border bg-card">
            <Table>
              <TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Role</TableHead><TableHead>Email</TableHead><TableHead>Status</TableHead><TableHead className="text-right">Modules</TableHead></TableRow></TableHeader>
              <TableBody>
                {STAFF.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-medium">{u.name}</TableCell>
                    <TableCell className="text-muted-foreground">{u.role}</TableCell>
                    <TableCell className="text-muted-foreground">{u.email}</TableCell>
                    <TableCell><StatusPill tone={u.status === 'Active' ? 'success' : 'info'}>{u.status}</StatusPill></TableCell>
                    <TableCell className="text-right tabular-nums">{grants[u.id]?.size ?? 0}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="roles">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {[
              { name: 'Partner', desc: 'Every module, approvals, sign-offs, billing.', n: 1 },
              { name: 'Senior accountant', desc: 'Workpapers, Verify, CRM. No billing.', n: 1 },
              { name: 'Client coordinator', desc: 'CRM, Start, Sign. Read-only Workpapers.', n: 1 },
              { name: 'External bookkeeper', desc: 'Workpapers only, scoped to assigned clients.', n: 1 },
            ].map((r) => (
              <div key={r.name} className="rounded-[6px] border bg-card p-4"><div className="mb-1 font-medium">{r.name}</div><p className="text-[13px] text-muted-foreground">{r.desc}</p><div className="mt-2 text-[12px] text-muted-foreground">{r.n} user</div></div>
            ))}
            <button className="rounded-[6px] border border-dashed p-4 text-left text-[13px] text-muted-foreground hover:bg-secondary">+ New role template</button>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
