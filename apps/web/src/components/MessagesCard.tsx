import { useEffect, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { MessageSquare, Send } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Textarea } from '@entiq/ui/textarea';
import { clientPortalStaff, type ThreadMessage } from '@/api/portal';
import { describeError } from '@/state/session';

/** The client ↔ practice thread (Client portal module) as seen by staff on the client record. */
export function MessagesCard({ clientId, readOnly }: { clientId: string; readOnly: boolean }) {
  const [rows, setRows] = useState<ThreadMessage[] | null>(null);
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { void clientPortalStaff.thread(clientId).then(setRows).catch(() => setRows([])); }, [clientId]);
  const send = async () => { setBusy(true); try { setRows(await clientPortalStaff.post(clientId, body.trim())); setBody(''); } catch (e) { toast.error(describeError(e)); } finally { setBusy(false); } };
  return (
    <Card>
      <CardHeader className="pb-3"><CardTitle className="flex items-center gap-2 text-[15px]"><MessageSquare className="size-4 text-primary" /> Messages{rows ? ` · ${rows.length}` : ''}</CardTitle></CardHeader>
      <CardContent>
        <ul className="mb-3 max-h-[320px] space-y-2 overflow-y-auto text-[13px]">
          {rows?.map((m) => <li key={m.id} className={`max-w-[85%] rounded-[6px] px-3 py-2 ${m.from_client ? 'bg-muted' : 'ml-auto bg-primary/10'}`}><div className="mb-0.5 text-[11px] text-muted-foreground">{m.author} · {formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}{!m.from_client && (m.read ? ' · read' : '')}</div><div className="whitespace-pre-wrap">{m.body}</div></li>)}
          {rows && rows.length === 0 && <li className="py-4 text-center text-muted-foreground">No messages yet. Anything you send is emailed to portal contacts.</li>}
        </ul>
        {!readOnly && <div className="flex gap-2"><Textarea rows={2} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Message the client…" /><Button size="sm" className="self-end" disabled={!body.trim() || busy} onClick={() => void send()}><Send className="size-4" /></Button></div>}
      </CardContent>
    </Card>
  );
}
