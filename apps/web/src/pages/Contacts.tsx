import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Search, Mail, Phone } from 'lucide-react';
import { Input } from '@entiq/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@entiq/ui/table';
import { crm, type ContactOut, type ClientOut } from '@/api/crm';
import { describeError } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

export function Contacts() {
  const [q, setQ] = useState('');
  const [rows, setRows] = useState<ContactOut[] | null>(null);
  const [clients, setClients] = useState<Record<string, ClientOut>>({});

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const cs = await crm.contacts.directory(q.trim() || undefined);
        setRows(cs);
        const ids = [...new Set(cs.map((c) => c.client_id))].filter((id) => !clients[id]);
        if (ids.length) {
          const page = await crm.clients.list({ size: 200 });
          setClients((m) => ({ ...m, ...Object.fromEntries(page.items.map((c) => [c.id, c])) }));
        }
      } catch (e) { toast.error('Could not load contacts', { description: describeError(e) }); }
    }, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="page">
      <PageHeader title="Contacts" description="Every person across your clients — directors, trustees, owners, bookkeepers and advisers." />
      <div className="relative mb-4 w-full max-w-[320px]">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or email" className="pl-8" />
      </div>
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <Table>
          <TableHeader><TableRow><TableHead>Person</TableHead><TableHead>Role</TableHead><TableHead>Client</TableHead><TableHead>Email</TableHead><TableHead>Phone</TableHead><TableHead></TableHead></TableRow></TableHeader>
          <TableBody>
            {rows?.map((p) => (
              <TableRow key={p.id}>
                <TableCell><div className="flex items-center gap-2 font-medium">{p.full_name}{p.is_primary && <StatusPill tone="teal">Primary</StatusPill>}</div></TableCell>
                <TableCell className="text-muted-foreground">{p.role ?? '—'}</TableCell>
                <TableCell><Link to={`/clients/${p.client_id}`} className="hover:underline">{clients[p.client_id]?.name ?? 'View client'}</Link></TableCell>
                <TableCell className="text-muted-foreground">{p.email ?? '—'}</TableCell>
                <TableCell className="text-muted-foreground">{p.phone ?? '—'}</TableCell>
                <TableCell className="text-right">{p.email && <a href={`mailto:${p.email}`} className="mr-2 inline-flex text-muted-foreground hover:text-foreground" aria-label="Email"><Mail className="size-4" /></a>}{p.phone && <a href={`tel:${p.phone}`} className="inline-flex text-muted-foreground hover:text-foreground" aria-label="Call"><Phone className="size-4" /></a>}</TableCell>
              </TableRow>
            ))}
            {rows && rows.length === 0 && <TableRow><TableCell colSpan={6} className="py-14 text-center text-muted-foreground">No contacts{q ? ' match' : ' yet — add people from a client record'}.</TableCell></TableRow>}
            {!rows && <TableRow><TableCell colSpan={6} className="py-14 text-center text-muted-foreground">Loading…</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
