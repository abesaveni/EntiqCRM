import { Link } from 'react-router-dom';
import { Archive, Download } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { useSession } from '@/state/session';

/** Cancelled / retained tenants land here. Access is gone; records are not. */
export function AccountClosed() {
  const tenant = useSession((s) => s.tenant);
  const simulate = useSession((s) => s.simulateTenantStatus);
  const logout = useSession((s) => s.logout);
  return (
    <div className="flex min-h-full items-center justify-center px-6 py-12">
      <div className="w-full max-w-[520px] rounded-[6px] border bg-card p-8 text-center">
        <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-[8px] bg-muted"><Archive className="size-6 text-muted-foreground" /></div>
        <h1 className="mb-2">This practice is {tenant?.status === 'retained' ? 'archived' : 'cancelled'}</h1>
        <p className="mb-6 text-muted-foreground">
          {tenant?.status === 'cancelled'
            ? 'You have a 30-day window to export everything. After that the records are retained under our compliance obligations but are no longer accessible in the app.'
            : 'Your records are retained to meet AML/CTF and record-keeping obligations. Contact support to reinstate access.'}
        </p>
        <div className="flex justify-center gap-2">
          {tenant?.status === 'cancelled' && <Button><Download className="mr-1.5 size-4" /> Export all data</Button>}
          <Button variant="outline" onClick={() => simulate('active')}>Reinstate (demo)</Button>
          <Button variant="ghost" onClick={logout} asChild><Link to="/login">Sign out</Link></Button>
        </div>
      </div>
    </div>
  );
}
