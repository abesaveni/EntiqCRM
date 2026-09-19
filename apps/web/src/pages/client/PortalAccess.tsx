import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { FileText, KeyRound, MessageSquare, Users } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { getModule } from '@entiq/modules';
import { clientPortalStaff, type PortalContactOut, type StaffOverview } from '@/api/portal';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

/** Staff view of the Client portal: who has access, activity, and the door to the portal itself. */
export function PortalAccess() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [ov, setOv] = useState<StaffOverview | null>(null);
  const [rows, setRows] = useState<PortalContactOut[] | null>(null);
  const load = async () => { try { const [o, r] = await Promise.all([clientPortalStaff.overview(), clientPortalStaff.contacts()]); setOv(o); setRows(r); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('client')) void load(); }, []);
  if (!entitled('client')) return <UpsellPage module={getModule('client')} />;
  const revoke = async (c: PortalContactOut) => { if (!confirm(`Remove portal access for ${c.name}? Their sessions end immediately.`)) return; try { await clientPortalStaff.revoke(c.contact_id); await load(); } catch (e) { toast.error(describeError(e)); } };
  const reinvite = async (c: PortalContactOut) => { try { await clientPortalStaff.invite(c.contact_id); toast.success('Sign-in link sent'); await load(); } catch (e) { toast.error(describeError(e)); } };
  return (
    <div className="page">
      <PageHeader eyebrow="Module 14" title="Client portal" description="A passwordless portal for your clients: shared documents, requests, agreements, work in progress and messages. Invite contacts from their client record."
        actions={<Button size="sm" variant="outline" asChild><a href="/portal" target="_blank" rel="noreferrer">Open the portal</a></Button>} />
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat icon={<Users className="size-4" />} label="Contacts with access" value={ov?.contacts_with_access} />
        <Stat icon={<Users className="size-4" />} label="Clients with access" value={ov?.clients_with_access} />
        <Stat icon={<KeyRound className="size-4" />} label="Sign-ins · 30d" value={ov?.logins_30d} />
        <Stat icon={<MessageSquare className="size-4" />} label="Unread messages" value={ov?.unread_messages} warn={!!ov && ov.unread_messages > 0} />
        <Stat icon={<FileText className="size-4" />} label="Shared documents" value={ov?.shared_documents} />
      </div>
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <ul className="divide-y">
          {rows?.map((c) => (
            <li key={c.contact_id} className="flex items-center gap-3 px-5 py-2.5 text-[13px]">
              <div className="min-w-0 flex-1"><div className="truncate font-medium">{c.name} <span className="font-normal text-muted-foreground">· {c.role ?? 'Contact'}</span></div><div className="truncate text-[12px] text-muted-foreground"><Link to={`/clients/${c.client_id}`} className="hover:underline">{c.client_name}</Link> · {c.email} · {c.last_login_at ? `last sign-in ${formatDistanceToNow(new Date(c.last_login_at), { addSuffix: true })}` : c.invited_at ? `invited ${formatDistanceToNow(new Date(c.invited_at), { addSuffix: true })}, not signed in yet` : 'never signed in'}</div></div>
              {c.active_sessions > 0 && <StatusPill tone="success">{c.active_sessions} active</StatusPill>}
              {!readOnly && can('client:invite') && <Button size="sm" variant="ghost" onClick={() => void reinvite(c)}>Send sign-in link</Button>}
              {!readOnly && can('client:manage') && <Button size="sm" variant="ghost" className="text-error hover:text-error" onClick={() => void revoke(c)}>Revoke</Button>}
            </li>
          ))}
          {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">No contacts have portal access yet. Open a client record → contact → “Invite to portal”.</li>}
          {!rows && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
        </ul>
      </div>
    </div>
  );
}

function Stat({ icon, label, value, warn }: { icon: React.ReactNode; label: string; value: number | undefined; warn?: boolean }) {
  return <div className={`rounded-[6px] border bg-card p-4 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[24px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{value ?? '—'}</div></div>;
}
