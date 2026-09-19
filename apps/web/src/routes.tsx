import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from './shell/AppShell';
import { Home } from './pages/Home';
import { ClientsList } from './pages/clients/ClientsList';
import { Client360 } from './pages/clients/Client360';
import { HqOverview } from './pages/hq/HqOverview';
import { Catalogue } from './pages/hq/Catalogue';
import { Users } from './pages/hq/Users';
import { Integrations } from './pages/hq/Integrations';
import { Settings } from './pages/hq/Settings';
import { ModuleRoute } from './pages/ModuleRoute';
import { SignUp } from './pages/auth/SignUp';
import { Login } from './pages/auth/Login';
import { AccountClosed } from './pages/AccountClosed';
import { Placeholder } from './pages/Placeholder';

export const router = createBrowserRouter([
  { path: '/signup', element: <SignUp /> },
  { path: '/login', element: <Login /> },
  { path: '/account-closed', element: <AccountClosed /> },
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Home /> },

      // CRM — base plan
      { path: 'clients', element: <ClientsList /> },
      { path: 'clients/:id', element: <Client360 /> },
      { path: 'contacts', element: <Placeholder title="Contacts" description="Every person and organisation across prospects, clients, investors, lenders and partners." /> },
      { path: 'pipeline', element: <Placeholder title="Pipeline" description="Leads and opportunities by stage, owner and value." /> },
      { path: 'tasks', element: <Placeholder title="Tasks" description="Follow-ups and work due across the practice." /> },
      { path: 'segments', element: <Placeholder title="Segments & lists" description="Saved client and contact lists for outreach and review." /> },

      // Practice HQ — base plan
      { path: 'hq', element: <HqOverview /> },
      { path: 'hq/modules', element: <Catalogue /> },
      { path: 'hq/modules/:key', element: <Catalogue /> },
      { path: 'hq/users', element: <Users /> },
      { path: 'hq/integrations', element: <Integrations /> },
      { path: 'hq/settings', element: <Settings /> },

      // Any other module: entitlement check → placeholder while porting
      { path: 'm/:key', element: <ModuleRoute /> },

      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
