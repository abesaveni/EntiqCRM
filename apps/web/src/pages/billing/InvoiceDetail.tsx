import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { toast } from 'sonner';
import { ArrowLeft, BellRing, Banknote, Send, XCircle } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@entiq/ui/card';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@entiq/ui/select';
import { getModule } from '@entiq/modules';
import { practiceBilling, INVOICE_STATUS_LABEL, invoiceTone, type InvoiceDetail as Detail } from '@/api/practiceBilling';
import { fmtCents } from '@/api/platform';
import { useSession, describeError } from '@/state/session';
import { UpsellPage } from '@/components/Upsell';
import { PageHeader } from '@/components/PageHeader';
import { StatusPill } from '@/components/StatusPill';

export function InvoiceDetail() {
  const { id = '' } = useParams();
  const entitled = useSession((s) => s.entitled);
  const can = useSession((s) => s.can);
  const readOnly = useSession((s) => s.readOnly);
  const [i, setI] = useState<Detail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [pay, setPay] = useState({ amount: '', method: 'bank_transfer', reference: '', received_on: new Date().toISOString().slice(0, 10) });

  const load = async () => { try { const d = await practiceBilling.invoices.get(id); setI(d); setPay((p) => ({ ...p, amount: d.balance_cents ? String(d.balance_cents / 100) : '' })); } catch (e) { toast.error(describeError(e)); } };
  useEffect(() => { if (entitled('billing')) void load(); }, [id]);
  if (!entitled('billing')) return <UpsellPage module={getModule('billing')} />;
  if (!i) return <div className="page text-[13px] text-muted-foreground">Loading…</div>;

  const act = async (key: string, fn: () => Promise<Detail>, ok?: string) => { setBusy(key); try { const d = await fn(); setI(d); setPay((p) => ({ ...p, amount: d.balance_cents ? String(d.balance_cents / 100) : '' })); if (ok) toast.success(ok); } catch (e) { toast.error(describeError(e)); } finally { setBusy(null); } };

  return (
    <div className="page">
      <Link to="/billing" className="mb-2 inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"><ArrowLeft className="size-3.5" /> Billing</Link>
      <PageHeader eyebrow={`Invoice ${i.number}${i.period_label ? ` · ${i.period_label}` : ''}`} title={`${fmtCents(i.total_cents)} — ${i.client_name}`}
        description={`${i.contact_name ?? 'no contact'}${i.contact_email ? ` <${i.contact_email}>` : ''} · issued ${i.issued_on ? format(new Date(i.issued_on), 'd MMM yyyy') : '—'}${i.due_on ? ` · due ${format(new Date(i.due_on), 'd MMM yyyy')}` : ''}${i.days_overdue ? ` · ${i.days_overdue} days overdue` : ''}`}
        actions={<div className="flex items-center gap-2">
          <StatusPill tone={invoiceTone(i.status)} className="text-[12px]">{INVOICE_STATUS_LABEL[i.status]}</StatusPill>
          {i.status === 'draft' && !readOnly && can('billing:invoice') && <Button size="sm" disabled={busy === 'send'} onClick={() => void act('send', () => practiceBilling.invoices.send(i.id), 'Invoice sent')}><Send className="mr-1.5 size-4" /> Send</Button>}
          {['sent', 'part_paid', 'overdue'].includes(i.status) && !readOnly && can('billing:collect') && <Button size="sm" variant="outline" disabled={busy === 'remind'} onClick={() => void act('remind', () => practiceBilling.invoices.remind(i.id), 'Reminder sent')}><BellRing className="mr-1.5 size-4" /> Remind</Button>}
          {i.paid_cents === 0 && i.status !== 'void' && !readOnly && can('billing:refund') && <Button size="sm" variant="outline" className="text-error hover:text-error" onClick={() => { const r = prompt('Void this invoice — why?'); if (r) void act('void', () => practiceBilling.invoices.void(i.id, r), 'Voided'); }}><XCircle className="mr-1.5 size-4" /> Void</Button>}
        </div>} />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-[15px]">Lines</CardTitle></CardHeader>
            <CardContent className="p-0">
              <table className="w-full text-[13px]">
                <thead className="bg-muted/60 text-left text-[11px] uppercase tracking-[0.08em] text-muted-foreground"><tr><th className="px-6 py-2 font-medium">Description</th><th className="px-2 py-2 text-right font-medium">Qty</th><th className="px-2 py-2 text-right font-medium">Unit</th><th className="px-2 py-2 text-right font-medium">Amount</th></tr></thead>
                <tbody className="divide-y">
                  {i.lines.map((l) => <tr key={l.id}><td className="px-6 py-2">{l.description}{!l.gst && <span className="ml-1 text-[11px] text-muted-foreground">(no GST)</span>}</td><td className="px-2 py-2 text-right tabular-nums">{l.quantity}</td><td className="px-2 py-2 text-right tabular-nums">{fmtCents(l.unit_cents)}</td><td className="px-2 py-2 text-right tabular-nums">{fmtCents(l.amount_cents)}</td></tr>)}
                </tbody>
                <tfoot className="border-t text-[13px]">
                  <tr><td colSpan={3} className="px-6 py-1 text-right text-muted-foreground">Subtotal</td><td className="px-2 py-1 text-right tabular-nums">{fmtCents(i.subtotal_cents)}</td></tr>
                  <tr><td colSpan={3} className="px-6 py-1 text-right text-muted-foreground">GST</td><td className="px-2 py-1 text-right tabular-nums">{fmtCents(i.gst_cents)}</td></tr>
                  <tr className="font-semibold"><td colSpan={3} className="px-6 py-1 text-right">Total</td><td className="px-2 py-1 text-right tabular-nums">{fmtCents(i.total_cents)}</td></tr>
                  {i.paid_cents > 0 && <tr><td colSpan={3} className="px-6 py-1 text-right text-muted-foreground">Paid</td><td className="px-2 py-1 text-right tabular-nums text-success">−{fmtCents(i.paid_cents)}</td></tr>}
                  <tr className="font-semibold"><td colSpan={3} className="px-6 py-1 text-right">Balance</td><td className="px-2 py-1 text-right tabular-nums">{fmtCents(i.balance_cents)}</td></tr>
                </tfoot>
              </table>
            </CardContent>
          </Card>
          {i.notes && <Card className="mt-4"><CardHeader className="pb-2"><CardTitle className="text-[14px]">Notes</CardTitle></CardHeader><CardContent className="whitespace-pre-wrap text-[13px]">{i.notes}</CardContent></Card>}
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2 text-[15px]"><Banknote className="size-4 text-primary" /> Payments</CardTitle></CardHeader>
            <CardContent>
              <ul className="mb-3 divide-y text-[13px]">
                {i.payments.map((p) => <li key={p.id} className="flex items-center justify-between py-1.5"><span>{format(new Date(p.received_on), 'd MMM yyyy')} · {p.method.replace('_', ' ')}{p.reference ? ` · ${p.reference}` : ''}</span><span className="tabular-nums">{fmtCents(p.amount_cents)}</span></li>)}
                {i.payments.length === 0 && <li className="py-2 text-center text-muted-foreground">Nothing received yet.</li>}
              </ul>
              {i.balance_cents > 0 && i.status !== 'void' && !readOnly && can('billing:collect') && (
                <div className="grid gap-2 text-[13px]">
                  <div className="grid grid-cols-2 gap-2">
                    <div className="grid gap-1"><Label className="text-[11px]">Amount ($)</Label><Input type="number" value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} /></div>
                    <div className="grid gap-1"><Label className="text-[11px]">Received</Label><Input type="date" value={pay.received_on} onChange={(e) => setPay({ ...pay, received_on: e.target.value })} /></div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="grid gap-1"><Label className="text-[11px]">Method</Label><Select value={pay.method} onValueChange={(v) => setPay({ ...pay, method: v })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{['bank_transfer', 'direct_debit', 'card', 'cash', 'other'].map((m) => <SelectItem key={m} value={m}>{m.replace('_', ' ')}</SelectItem>)}</SelectContent></Select></div>
                    <div className="grid gap-1"><Label className="text-[11px]">Reference</Label><Input value={pay.reference} onChange={(e) => setPay({ ...pay, reference: e.target.value })} /></div>
                  </div>
                  <Button size="sm" disabled={!Number(pay.amount) || busy === 'pay'} onClick={() => void act('pay', () => practiceBilling.invoices.pay(i.id, { amount_cents: Math.round(Number(pay.amount) * 100), method: pay.method, reference: pay.reference || null, received_on: pay.received_on }), 'Payment recorded')}>Record payment</Button>
                </div>
              )}
            </CardContent>
          </Card>
          <Card><CardHeader className="pb-2"><CardTitle className="text-[14px]">Detail</CardTitle></CardHeader><CardContent className="grid gap-1 text-[13px]">
            <Row k="Client" v={<Link to={`/clients/${i.client_id}`} className="text-primary hover:underline">{i.client_name}</Link>} />
            <Row k="Raised by" v={i.created_by_name ?? '—'} />
            <Row k="Sent" v={i.sent_at ? format(new Date(i.sent_at), 'd MMM yyyy') : '—'} />
            <Row k="Reminders" v={i.reminders_sent} />
            <Row k="Paid" v={i.paid_at ? format(new Date(i.paid_at), 'd MMM yyyy') : '—'} />
            {i.fee_schedule_id && <Row k="Source" v="Recurring fee" />}
          </CardContent></Card>
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) { return <div className="flex justify-between border-b border-dashed py-1 last:border-0"><span className="text-muted-foreground">{k}</span><span>{v}</span></div>; }
