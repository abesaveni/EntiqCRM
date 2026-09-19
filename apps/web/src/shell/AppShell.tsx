import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useSession, tenantHasAccess, tenantIsReadOnly } from '@/state/session';
import { ModuleSwitcher } from './ModuleSwitcher';
import { TopBar } from './TopBar';
import { TrialBanner } from './TrialBanner';

/**
 * The application frame — blueprint §2. Left module switcher (dark), top bar with
 * contextual nav / global search / notifications / user menu, lifecycle banner, content.
 * Unauthenticated → /login. Cancelled/retained tenants → the exit page.
 */
export function AppShell() {
  const authenticated = useSession((s) => s.authenticated);
  const tenant = useSession((s) => s.tenant);
  const location = useLocation();

  if (!authenticated) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
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
