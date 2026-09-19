import { useEffect, useState } from 'react';
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { Briefcase, CheckCircle2, FileSignature, FileText, FileUp, Inbox, LogOut, MessageSquare, Send, ShieldAlert } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { Textarea } from '@entiq/ui/textarea';
import { portal, portalSession, type PortalDocument, type PortalHome, type ThreadMessage } from '@/api/portal';
import { fmtBytes } from '@/api/platform';
import { PACK_STATUS_LABEL, PURPOSE_LABEL, type PublicPack } from '@/api/requests';
import { ApiError } from '@/api/client';
import { RequestWorkspace, describeRequestError } from '@/pages/requests/RequestWorkspace';

function describe(e: unknown): string {
  if (e instanceof ApiError) { const d = e.detail as { error?: string; message?: string } | null; return ({ invalid_link: 'This sign-in link is not valid or has expired — request a new one below.', access_revoked: 'Your portal access has been removed by the practice.', portal_unavailable: 'The practice’s client portal is not active right now.' } as Record<string, string>)[d?.error ?? ''] ?? d?.message ?? 'Something went wrong.'; }
  return 'Something went wrong.';
}

function Shell({ title, right, children }: { title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="border-b bg-card"><div className="mx-auto flex h-14 max-w-[960px] items-center gap-3 px-4"><img src="/favicon.svg" alt="" className="size-6" /><span className="truncate text-[14px] font-semibold">{title}</span><span className="ml-auto flex items-center gap-2 text-[12px] text-muted-foreground">{right}</span></div></header>
      <main className="mx-auto max-w-[960px] px-4 py-6">{children}</main>
    </div>
  );
}

/** /portal — email me a sign-in link. */
export function PortalLogin() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  if (portalSession.get()) return <Navigate to="/portal/home" replace />;
  return (
    <Shell title="Client portal">
      <div className="mx-auto max-w-[420px] rounded-[6px] border bg-card p-6">
        <h1 className="text-[18px] font-semibold">Sign in</h1>
        <p className="mb-4 text-[13px] text-muted-foreground">No password. Enter the email your accountant has for you and we'll send a one-time link.</p>
        {sent ? <p className="rounded-[4px] bg-muted px-3 py-2 text-[13px]"><CheckCircle2 className="mr-1.5 inline size-4 text-success" /> If that email has portal access, a sign-in link is on its way (valid 30 minutes).</p> : (
          <form onSubmit={(e) => { e.preventDefault(); setBusy(true); void portal.requestLink(email.trim()).finally(() => { setBusy(false); setSent(true); }); }} className="grid gap-3">
            <Input type="email" required placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
            <Button type="submit" disabled={busy || !email.trim()}>{busy ? 'Sending…' : 'Email me a link'}</Button>
          </form>
        )}
      </div>
    </Shell>
  );
}

/** /portal/login/:token — exchange the emailed token for a session. */
export function PortalExchange() {
  const { token = '' } = useParams();
  const nav = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { portal.exchange(token).then(() => nav('/portal/home', { replace: true })).catch((e: unknown) => setErr(describe(e))); }, [token]);
  return <Shell title="Client portal">{err ? <div className="mx-auto max-w-[420px] rounded-[6px] border bg-card p-6 text-center"><ShieldAlert className="mx-auto mb-2 size-7 text-muted-foreground" /><p className="text-[13px]">{err}</p><Button variant="outline" className="mt-4" asChild><Link to="/portal">Request a new link</Link></Button></div> : <p className="text-center text-[13px] text-muted-foreground">Signing you in…</p>}</Shell>;
}

/** /portal/home — everything the practice has for this client, phone-first. */
export function PortalHomePage() {
  const nav = useNavigate();
  const [home, setHome] = useState<PortalHome | null>(null);
  const [docs, setDocs] = useState<PortalDocument[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState('');
  const [tab, setTab] = useState('overview');
  const load = async () => { try { setHome(await portal.home()); } catch (e) { if (e instanceof ApiError && e.status === 401) nav('/portal', { replace: true }); else setErr(describe(e)); } };
  useEffect(() => { if (!portalSession.get()) nav('/portal', { replace: true }); else void load(); }, []);
  useEffect(() => { if (tab === 'documents' && !docs) void portal.documents().then(setDocs).catch(() => setDocs([])); }, [tab]);
  if (err) return <Shell title="Client portal"><p className="text-[13px] text-error">{err}</p></Shell>;
  if (!home) return <Shell title="Client portal"><p className="text-[13px] text-muted-foreground">Loading…</p></Shell>;
  const { me } = home;
  const send = async () => { const r = await portal.post(msg.trim()); setHome({ ...home, messages: r }); setMsg(''); };
  const upload = async (f: File | undefined) => { if (!f) return; try { const d = await portal.upload(f); setDocs((x) => [d, ...(x ?? [])]); } catch (e) { setErr(describeRequestError(e)); } };
  return (
    <Shell title={me.client_name} right={<><span className="hidden sm:inline">{me.name} · {me.practice_name}</span><button className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => void portal.logout().then(() => nav('/portal', { replace: true }))}><LogOut className="size-3.5" /> Sign out</button></>}>
      <div className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Tile icon={<Inbox className="size-4" />} label="Open requests" value={me.counts.open_requests} onClick={() => setTab('requests')} warn={me.counts.open_requests > 0} />
        <Tile icon={<FileSignature className="size-4" />} label="To sign" value={me.counts.awaiting_signature} onClick={() => setTab('agreements')} warn={me.counts.awaiting_signature > 0} />
        <Tile icon={<MessageSquare className="size-4" />} label="Unread messages" value={me.counts.unread_messages} onClick={() => setTab('messages')} warn={me.counts.unread_messages > 0} />
        <Tile icon={<FileText className="size-4" />} label="Documents" value={me.counts.shared_documents} onClick={() => setTab('documents')} />
      </div>
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="mb-3 flex w-full overflow-x-auto"><TabsTrigger value="overview">Overview</TabsTrigger>{me.features.requests && <TabsTrigger value="requests">Requests</TabsTrigger>}{me.features.agreements && <TabsTrigger value="agreements">Agreements</TabsTrigger>}<TabsTrigger value="documents">Documents</TabsTrigger>{me.features.jobs && <TabsTrigger value="work">Work</TabsTrigger>}<TabsTrigger value="messages">Messages</TabsTrigger></TabsList>
        <TabsContent value="overview">
          <div className="rounded-[6px] border bg-card p-4 text-[13px]">
            <div className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">Recent activity</div>
            <ul className="divide-y">{home.recent.map((e, i) => <li key={i} className="flex justify-between gap-3 py-1.5"><span>{e.summary}</span><span className="shrink-0 text-[12px] text-muted-foreground">{formatDistanceToNow(new Date(e.occurred_at), { addSuffix: true })}</span></li>)}{home.recent.length === 0 && <li className="py-4 text-center text-muted-foreground">Nothing yet.</li>}</ul>
          </div>
        </TabsContent>
        <TabsContent value="requests">
          <ul className="divide-y rounded-[6px] border bg-card text-[13px]">
            {home.requests.map((r) => <li key={r.id}><Link to={`/portal/requests/${r.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-muted/50"><div className="min-w-0 flex-1"><div className="font-medium">{r.title}</div><div className="text-[12px] text-muted-foreground">{r.items_done}/{r.items_total} done{r.outstanding ? ` · ${r.outstanding} still needed` : ''}{r.due_on ? ` · ${r.overdue ? 'overdue' : 'due'} ${format(new Date(r.due_on), 'd MMM')}` : ''}</div></div><span className={`rounded-[4px] px-2 py-0.5 text-[11px] ${r.status === 'complete' ? 'bg-success-bg text-success' : r.outstanding ? 'bg-warn-bg text-warn' : 'bg-muted'}`}>{PACK_STATUS_LABEL[r.status as keyof typeof PACK_STATUS_LABEL] ?? r.status}</span></Link></li>)}
            {home.requests.length === 0 && <li className="px-4 py-8 text-center text-muted-foreground">No requests from {me.practice_name}.</li>}
          </ul>
        </TabsContent>
        <TabsContent value="agreements">
          <ul className="divide-y rounded-[6px] border bg-card text-[13px]">
            {home.agreements.map((a) => <li key={a.id} className="flex items-center gap-3 px-4 py-3"><FileSignature className="size-4 text-muted-foreground" /><div className="min-w-0 flex-1"><div className="font-medium">{a.title}</div><div className="text-[12px] text-muted-foreground">{a.kind.replace('_', ' ')} · {a.status.replace('_', ' ')}{a.completed_at ? ` · signed ${format(new Date(a.completed_at), 'd MMM yyyy')}` : ''}</div></div>{(a.my_status === 'sent' || a.my_status === 'viewed') && <Button size="sm" variant="outline" onClick={() => void portal.resendAgreement(a.id)}>Email me the signing link</Button>}{a.my_status === 'signed' && <CheckCircle2 className="size-4 text-success" />}</li>)}
            {home.agreements.length === 0 && <li className="px-4 py-8 text-center text-muted-foreground">No agreements.</li>}
          </ul>
        </TabsContent>
        <TabsContent value="documents">
          <div className="mb-2 flex justify-end"><label className="inline-flex cursor-pointer items-center gap-1.5 rounded-[5px] border px-3 py-1.5 text-[13px] hover:bg-muted"><FileUp className="size-4" /> Send a file to {me.practice_name}<input type="file" className="hidden" onChange={(e) => void upload(e.target.files?.[0])} /></label></div>
          <ul className="divide-y rounded-[6px] border bg-card text-[13px]">
            {docs?.map((d) => <li key={d.id} className="flex items-center gap-3 px-4 py-2.5"><FileText className="size-4 text-muted-foreground" /><div className="min-w-0 flex-1"><div className="truncate font-medium">{d.filename}</div><div className="text-[12px] text-muted-foreground">{d.uploaded_by} · {fmtBytes(d.size_bytes)} · {format(new Date(d.created_at), 'd MMM yyyy')}</div></div><Button size="sm" variant="ghost" onClick={() => void portal.download(d)}>Download</Button></li>)}
            {docs && docs.length === 0 && <li className="px-4 py-8 text-center text-muted-foreground">Nothing shared yet.</li>}
            {!docs && <li className="px-4 py-8 text-center text-muted-foreground">Loading…</li>}
          </ul>
        </TabsContent>
        <TabsContent value="work">
          <ul className="divide-y rounded-[6px] border bg-card text-[13px]">
            {home.jobs.map((j) => <li key={j.id} className="flex items-center gap-3 px-4 py-2.5"><Briefcase className="size-4 text-muted-foreground" /><div className="min-w-0 flex-1"><div className="font-medium">{j.title}</div><div className="text-[12px] text-muted-foreground">{j.job_type}{j.period_label ? ` · ${j.period_label}` : ''}{j.due_on ? ` · due ${format(new Date(j.due_on), 'd MMM')}` : ''}</div></div><span className="rounded-[4px] bg-muted px-2 py-0.5 text-[11px]">{j.status.replace('_', ' ')}</span></li>)}
            {home.jobs.length === 0 && <li className="px-4 py-8 text-center text-muted-foreground">No work in progress.</li>}
          </ul>
        </TabsContent>
        <TabsContent value="messages">
          <div className="rounded-[6px] border bg-card p-4">
            <ul className="mb-3 max-h-[380px] space-y-2 overflow-y-auto text-[13px]">
              {home.messages.map((m: ThreadMessage) => <li key={m.id} className={`max-w-[85%] rounded-[6px] px-3 py-2 ${m.from_client ? 'ml-auto bg-primary/10' : 'bg-muted'}`}><div className="mb-0.5 text-[11px] text-muted-foreground">{m.from_client ? 'You' : m.author} · {formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}</div><div className="whitespace-pre-wrap">{m.body}</div></li>)}
              {home.messages.length === 0 && <li className="py-4 text-center text-muted-foreground">Ask {me.practice_name} anything — replies come here and to your email.</li>}
            </ul>
            <div className="flex gap-2"><Textarea rows={2} value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="Write a message…" /><Button className="self-end" disabled={!msg.trim()} onClick={() => void send()}><Send className="size-4" /></Button></div>
          </div>
        </TabsContent>
      </Tabs>
    </Shell>
  );
}

function Tile({ icon, label, value, onClick, warn }: { icon: React.ReactNode; label: string; value: number; onClick: () => void; warn?: boolean }) {
  return <button onClick={onClick} className={`rounded-[6px] border bg-card p-3 text-left hover:bg-muted/40 ${warn ? 'border-warn/50' : ''}`}><div className="mb-1 flex items-center gap-1.5 text-[12px] text-muted-foreground">{icon}{label}</div><div className={`text-[22px] font-semibold tabular-nums leading-none ${warn ? 'text-warn' : ''}`}>{value}</div></button>;
}

/** /portal/requests/:id — work a request from inside the portal (same workspace as the emailed link). */
export function PortalRequestPage() {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const [pack, setPack] = useState<PublicPack | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (!portalSession.get()) { nav('/portal', { replace: true }); return; } portal.request(id).then(setPack).catch((e: unknown) => setErr(describeRequestError(e))); }, [id]);
  return (
    <Shell title={pack?.client_name ?? 'Client portal'} right={<Link to="/portal/home" className="hover:text-foreground">← Back</Link>}>
      {err && <p className="text-[13px] text-error">{err}</p>}
      {pack && (<><div className="mb-4"><div className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{PURPOSE_LABEL[pack.purpose]}</div><h1 className="text-[20px] font-semibold leading-tight">{pack.title}</h1></div>
        <RequestWorkspace pack={pack} onChange={setPack} adapter={{ answer: (k, a) => portal.answer(id, k, a), upload: (iid, f) => portal.uploadItem(id, iid, f), notApplicable: (iid, n) => portal.notApplicable(id, iid, n), submit: () => portal.submit(id) }} /></>)}
    </Shell>
  );
}
