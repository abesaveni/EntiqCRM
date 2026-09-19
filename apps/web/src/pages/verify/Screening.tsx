import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { AlertTriangle, ShieldCheck } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Label } from '@entiq/ui/label';
import { Tabs, TabsList, TabsTrigger } from '@entiq/ui/tabs';
import { Textarea } from '@entiq/ui/textarea';
import { getModule } from '@entiq/modules';
import { verify, SCREENING_LABEL, type ScreeningOut } from '@/api/verify';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill, type Tone } from '@/components/StatusPill';

export function screeningTone(s: ScreeningOut['status'] | 'none'): Tone {
  return s === 'clear' || s === 'false_positive' ? 'success' : s === 'potential_match' ? 'warn' : s === 'confirmed_match' || s === 'error' ? 'error' : 'neutral';
}

/** Sanctions / PEP screening: the review queue first, then every screening run. */
export function Screening() {
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [view, setView] = useState<'queue' | 'all'>('queue');
  const [rows, setRows] = useState<ScreeningOut[] | null>(null);
  const [reviewing, setReviewing] = useState<ScreeningOut | null>(null);

  const load = async () => { try { setRows(await verify.screenings.list(view === 'queue' ? { review_queue: true } : { limit: 200 })); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('verify')) void load(); }, [view]);
  if (!entitled('verify')) return <UpsellPage module={getModule('verify')} />;

  return (
    <div className="page">
      <PageHeader eyebrow="Verify" title="Screening" description="Sanctions, PEP and adverse-media matches. Every potential match needs a human decision; a confirmed match re-rates the client immediately." />
      <Tabs value={view} onValueChange={(v) => setView(v as typeof view)} className="mb-4"><TabsList><TabsTrigger value="queue">Review queue</TabsTrigger><TabsTrigger value="all">All screenings</TabsTrigger></TabsList></Tabs>
      <div className="overflow-hidden rounded-[6px] border bg-card">
        <ul className="divide-y">
          {rows?.map((s) => (
            <li key={s.id} className="flex items-start gap-3 px-5 py-3 text-[13px]">
              {s.status === 'potential_match' || s.status === 'confirmed_match' ? <AlertTriangle className={`mt-0.5 size-4 shrink-0 ${s.status === 'confirmed_match' ? 'text-error' : 'text-warn'}`} /> : <ShieldCheck className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 font-medium">{s.subject_name}<span className="font-normal text-muted-foreground">· {s.subject_type}</span><StatusPill tone={screeningTone(s.status)}>{SCREENING_LABEL[s.status]}</StatusPill>{s.simulated && <StatusPill>simulated</StatusPill>}</div>
                <div className="text-[12px] text-muted-foreground">{s.client_name && <><Link to={`/verify/clients/${s.client_id}`} className="hover:underline">{s.client_name}</Link> · </>}{s.provider} · threshold {s.threshold}% · {formatDistanceToNow(new Date(s.screened_at), { addSuffix: true })}{s.reviewed_by_name && <> · reviewed by {s.reviewed_by_name}{s.review_notes ? ` — “${s.review_notes}”` : ''}</>}</div>
                {s.matches.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {s.matches.slice(0, 3).map((m, i) => (
                      <li key={m.id ?? i} className="flex flex-wrap items-center gap-2 rounded-[4px] bg-muted px-2.5 py-1.5 text-[12px]">
                        <span className="font-medium">{m.name ?? 'Unnamed match'}</span>{typeof m.score === 'number' && <span className="tabular-nums text-muted-foreground">{Math.round(m.score * 100)}%</span>}
                        {(m.topics ?? []).map((t) => <span key={t} className="rounded-[3px] border px-1.5 py-0.5">{t}</span>)}{(m.countries ?? []).slice(0, 3).map((c) => <span key={c} className="text-muted-foreground">{c.toUpperCase()}</span>)}
                      </li>
                    ))}
                    {s.matches.length > 3 && <li className="text-[12px] text-muted-foreground">+{s.matches.length - 3} more</li>}
                  </ul>
                )}
              </div>
              {s.status === 'potential_match' && !readOnly && can('verify:review') && <Button size="sm" variant="outline" onClick={() => setReviewing(s)}>Review</Button>}
            </li>
          ))}
          {rows && rows.length === 0 && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">{view === 'queue' ? 'No screening hits awaiting review.' : 'No screenings yet.'}</li>}
          {!rows && <li className="px-5 py-14 text-center text-[13px] text-muted-foreground">Loading…</li>}
        </ul>
      </div>
      <ReviewDialog s={reviewing} onClose={() => setReviewing(null)} onDone={load} />
    </div>
  );
}

export function ReviewDialog({ s, onClose, onDone }: { s: ScreeningOut | null; onClose: () => void; onDone: () => Promise<void> }) {
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const decide = async (decision: 'true_match' | 'false_positive') => {
    if (!s) return;
    setBusy(true);
    try { await verify.screenings.review(s.id, { decision, notes: notes.trim() || null }); toast.success(decision === 'true_match' ? 'Recorded as a true match — client risk re-assessed' : 'Recorded as a false positive'); await onDone(); onClose(); setNotes(''); }
    catch (e) { toast.error(describeError(e)); } finally { setBusy(false); }
  };
  return (
    <Dialog open={!!s} onOpenChange={(o) => !o && onClose()}><DialogContent className="max-w-[560px]">
      <DialogHeader><DialogTitle>Review screening match</DialogTitle></DialogHeader>
      {s && (
        <div className="grid gap-3 text-[13px]">
          <p><span className="font-medium">{s.subject_name}</span> returned {s.match_count} potential match{s.match_count === 1 ? '' : 'es'} at or above {s.threshold}%. Decide whether the subject <em>is</em> the listed person or entity.</p>
          <ul className="space-y-1">{s.matches.map((m, i) => <li key={m.id ?? i} className="rounded-[4px] bg-muted px-2.5 py-1.5 text-[12px]"><span className="font-medium">{m.name}</span> · {typeof m.score === 'number' ? `${Math.round(m.score * 100)}%` : ''} · {(m.topics ?? []).join(', ') || 'no topics'} · {(m.datasets ?? []).slice(0, 2).join(', ')}</li>)}</ul>
          <div className="grid gap-1.5"><Label htmlFor="rv-notes">Reviewer notes</Label><Textarea id="rv-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What you compared (DOB, nationality, photo, role) and why you decided this way." /></div>
          <p className="text-[12px] text-muted-foreground">Your decision, name and time are written to the screening record and the client timeline. A true match re-rates the client High and shortens its review cycle.</p>
        </div>
      )}
      <DialogFooter>
        <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
        <Button variant="outline" onClick={() => void decide('false_positive')} disabled={busy}>False positive</Button>
        <Button variant="destructive" onClick={() => void decide('true_match')} disabled={busy}>Confirm true match</Button>
      </DialogFooter>
    </DialogContent></Dialog>
  );
}
