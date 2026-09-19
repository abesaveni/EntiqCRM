import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from './shell/AppShell';
import { Home } from './pages/Home';
import { ClientsList } from './pages/clients/ClientsList';
import { Client360 } from './pages/clients/Client360';
import { ImportWizard } from './pages/clients/ImportWizard';
import { Contacts } from './pages/Contacts';
import { Pipeline } from './pages/Pipeline';
import { Tasks } from './pages/Tasks';
import { Segments } from './pages/Segments';
import { HqOverview } from './pages/hq/HqOverview';
import { Catalogue } from './pages/hq/Catalogue';
import { Users } from './pages/hq/Users';
import { Integrations } from './pages/hq/Integrations';
import { Settings } from './pages/hq/Settings';
import { ModuleRoute } from './pages/ModuleRoute';
import { SignUp } from './pages/auth/SignUp';
import { Login } from './pages/auth/Login';
import { AcceptInvite } from './pages/auth/AcceptInvite';
import { AccountClosed } from './pages/AccountClosed';

export const router = createBrowserRouter([
  { path: '/signup', element: <SignUp /> },
  { path: '/login', element: <Login /> },
  { path: '/accept-invite', element: <AcceptInvite /> },
  { path: '/account-closed', element: <AccountClosed /> },
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Home /> },

      // CRM — base plan
      { path: 'clients', element: <ClientsList /> },
      { path: 'clients/import', element: <ImportWizard /> },
      { path: 'clients/:id', element: <Client360 /> },
      { path: 'contacts', element: <Contacts /> },
      { path: 'pipeline', element: <Pipeline /> },
      { path: 'tasks', element: <Tasks /> },
      { path: 'segments', element: <Segments /> },

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
