import { useEffect } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useSession, tenantHasAccess, tenantIsReadOnly } from '@/state/session';
import { ModuleSwitcher } from './ModuleSwitcher';
import { TopBar } from './TopBar';
import { TrialBanner } from './TrialBanner';

/**
 * The application frame — blueprint §2. Left module switcher (dark), top bar with
 * contextual nav / global search / notifications / user menu, lifecycle banner, content.
 * Bootstraps the session from stored tokens; anonymous → /login; cancelled/retained → exit page.
 */
export function AppShell() {
  const status = useSession((s) => s.status);
  const tenant = useSession((s) => s.tenant);
  const bootstrap = useSession((s) => s.bootstrap);
  const location = useLocation();

  useEffect(() => { void bootstrap(); }, [bootstrap]);

  if (status === 'idle' || status === 'loading') {
    return (
      <div className="flex h-full items-center justify-center text-[13px] text-muted-foreground" role="status" aria-live="polite">
        <img src="/favicon.svg" alt="" className="mr-2 size-5 animate-pulse" /> Loading EnTIQ…
      </div>
    );
  }
  if (status === 'anonymous') return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (tenant && !tenantHasAccess(tenant) && !tenantIsReadOnly(tenant)) return <Navigate to="/account-closed" replace />;

  return (
    <div className="flex h-full min-h-0">
      <ModuleSwitcher />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <TrialBanner />
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
