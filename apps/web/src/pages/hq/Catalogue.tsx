import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Check, Lock, ArrowLeft, Sparkles } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@entiq/ui/dialog';
import { Label } from '@entiq/ui/label';
import { Input } from '@entiq/ui/input';
import { catalogueModules, getModule, requiredClosure, enhancedBy, BASE_BUNDLE, PLATFORM_SERVICES, type ModuleKey, type ModuleManifest } from '@entiq/modules';
import { useSession, isEntitled, fmtAud, monthlyBaseExGst, GST_RATE } from '@/state/session';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';
import { ModuleIcon } from '@/lib/icons';

/** Module catalogue + subscription selection — blueprint MODULE 01 screens 2 & 3. */
export function Catalogue() {
  const { key } = useParams();
  const navigate = useNavigate();
  const tenant = useSession((s) => s.tenant);
  const subscriptions = useSession((s) => s.subscriptions);
  const subscribe = useSession((s) => s.subscribe);
  const unsubscribe = useSession((s) => s.unsubscribe);
  const [confirm, setConfirm] = useState<ModuleManifest | null>(key ? safeGet(key) : null);
  const [seats, setSeats] = useState(3);

  const owned = (k: ModuleKey) => isEntitled({ tenant, subscriptions }, k);
  const isBase = (k: ModuleKey) => BASE_BUNDLE.includes(k) || PLATFORM_SERVICES.includes(k);
  const groups: Array<{ label: string; filter: (m: ModuleManifest) => boolean }> = [
    { label: 'Base plan — included', filter: (m) => isBase(m.key) },
    { label: 'Compliance & onboarding', filter: (m) => ['start', 'verify', 'sign', 'requests', 'documents'].includes(m.key) },
    { label: 'Accounting, tax & advisory', filter: (m) => ['workpapers', 'practice', 'advisory', 'client', 'academy'].includes(m.key) },
    { label: 'Finance & transactions', filter: (m) => ['lending', 'credit', 'capital', 'settle', 'loanmanager', 'funds'].includes(m.key) },
    { label: 'Growth & administration', filter: (m) => ['marketing', 'projects', 'trust', 'associations'].includes(m.key) },
  ];
  const base = monthlyBaseExGst();

  const doSubscribe = (m: ModuleManifest) => {
    const added = subscribe(m.key, m.pricing.model === 'per_seat' ? seats : undefined);
    const extra = added.filter((k) => k !== m.key);
    toast.success(`${m.shortName} added`, {
      description: extra.length ? `Also enabled ${extra.map((k) => getModule(k).shortName).join(', ')} — required by ${m.shortName}.` : `It now appears in your switcher and on every client record.`,
    });
    setConfirm(null);
    navigate('/hq/modules', { replace: true });
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Practice HQ"
        title="Modules & subscription"
        description={`Base plan ${fmtAud(base)} + GST per month (${fmtAud(base * (1 + GST_RATE))} inc GST). Add modules individually; each one appears immediately across the platform.`}
        actions={<Button asChild variant="outline" size="sm"><Link to="/hq"><ArrowLeft className="mr-1 size-3.5" /> Overview</Link></Button>}
      />

      {groups.map((g) => {
        const mods = catalogueModules().filter(g.filter);
        if (!mods.length) return null;
        return (
          <section key={g.label} className="mb-8">
            <h2 className="mb-3 text-[13px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{g.label}</h2>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {mods.map((m) => (
                <ModuleCard key={m.key} m={m} owned={owned(m.key)} base={isBase(m.key)} onAdd={() => setConfirm(m)} onRemove={() => { unsubscribe(m.key); toast(`${m.shortName} removed`, { description: 'Your data is retained. Re-add any time.' }); }} />
              ))}
            </div>
          </section>
        );
      })}

      <Dialog open={!!confirm} onOpenChange={(o) => { if (!o) { setConfirm(null); if (key) navigate('/hq/modules', { replace: true }); } }}>
        {confirm && (
          <DialogContent className="max-w-[520px]">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2"><ModuleIcon name={confirm.icon} className="size-5 text-primary" /> Add {confirm.name}</DialogTitle>
              <DialogDescription>{confirm.outcome}</DialogDescription>
            </DialogHeader>
            <div className="space-y-4 text-[13px]">
              <div className="rounded-[5px] border bg-secondary/50 px-3 py-2.5">
                <div className="font-medium">{confirm.pricing.unit}</div>
                <div className="text-muted-foreground">{confirm.pricing.commercial}</div>
                {confirm.pricing.fromAud && <div className="mt-1 text-muted-foreground">From {fmtAud(confirm.pricing.fromAud)} + GST</div>}
              </div>
              {confirm.pricing.model === 'per_seat' && (
                <div className="flex items-center gap-3">
                  <Label htmlFor="seats" className="shrink-0">Seats</Label>
                  <Input id="seats" type="number" min={1} value={seats} onChange={(e) => setSeats(Math.max(1, Number(e.target.value)))} className="w-24" />
                </div>
              )}
              {requiredClosure(confirm.key).filter((k) => !isBase(k) && !owned(k)).length > 0 && (
                <div className="rounded-[5px] border border-info/40 bg-info-bg px-3 py-2.5 text-info">
                  Also enables <strong>{requiredClosure(confirm.key).filter((k) => !isBase(k) && !owned(k)).map((k) => getModule(k).shortName).join(', ')}</strong> — {confirm.shortName} cannot run without {requiredClosure(confirm.key).filter((k) => !isBase(k) && !owned(k)).length > 1 ? 'them' : 'it'}.
                </div>
              )}
              {enhancedBy(confirm.key).filter((m) => owned(m.key)).length > 0 && (
                <div className="flex items-start gap-2 text-muted-foreground">
                  <Sparkles className="mt-0.5 size-3.5 shrink-0 text-primary" />
                  <span>Unlocks richer features in <strong className="text-foreground">{enhancedBy(confirm.key).filter((m) => owned(m.key)).map((m) => m.shortName).join(', ')}</strong>, which you already have.</span>
                </div>
              )}
              <p className="text-muted-foreground">Charged to your card ending {tenant?.cardLast4} on your next invoice, pro-rated. Remove any time; your data is retained.</p>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setConfirm(null)}>Cancel</Button>
              <Button onClick={() => doSubscribe(confirm)}>Add {confirm.shortName}</Button>
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}

function ModuleCard({ m, owned, base, onAdd, onRemove }: { m: ModuleManifest; owned: boolean; base: boolean; onAdd: () => void; onRemove: () => void }) {
  const planned = m.status === 'planned';
  return (
    <div className={`flex flex-col rounded-[6px] border bg-card p-4 ${owned ? 'border-primary/40' : ''}`}>
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className={`flex size-9 items-center justify-center rounded-[6px] ${owned ? 'bg-accent text-primary' : 'bg-muted text-muted-foreground'}`}><ModuleIcon name={m.icon} className="size-[18px]" /></span>
          <div>
            <div className="text-[14px] font-semibold leading-tight">{m.shortName}</div>
            <div className="text-[11px] text-muted-foreground">Module {String(m.number).padStart(2, '0')}</div>
          </div>
        </div>
        {owned ? <StatusPill tone="success"><Check className="size-3" /> {base ? 'Included' : 'Active'}</StatusPill> : planned ? <StatusPill>Coming soon</StatusPill> : <StatusPill tone="warn"><Lock className="size-3" /> Add-on</StatusPill>}
      </div>
      <p className="mb-3 flex-1 text-[13px] leading-[19px] text-muted-foreground">{m.outcome}</p>
      <div className="flex items-center justify-between gap-3 border-t pt-3">
        <span className="text-[12px] text-muted-foreground">{m.pricing.unit}</span>
        {base ? null : owned ? (
          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={onRemove}>Remove</Button>
        ) : planned ? (
          <Button variant="outline" size="sm" disabled>Notify me</Button>
        ) : (
          <Button size="sm" onClick={onAdd}>Add</Button>
        )}
      </div>
    </div>
  );
}

function safeGet(k: string): ModuleManifest | null {
  try { return getModule(k as ModuleKey); } catch { return null; }
}
