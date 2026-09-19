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
import { VerifyHome } from './pages/verify/VerifyHome';
import { Screening } from './pages/verify/Screening';
import { ClientVerify } from './pages/verify/ClientVerify';
import { Agreements } from './pages/sign/Agreements';
import { AgreementDetail } from './pages/sign/AgreementDetail';
import { PublicSign } from './pages/sign/PublicSign';

export const router = createBrowserRouter([
  { path: '/signup', element: <SignUp /> },
  { path: '/login', element: <Login /> },
  { path: '/accept-invite', element: <AcceptInvite /> },
  { path: '/account-closed', element: <AccountClosed /> },
  { path: '/s/:token', element: <PublicSign /> },          // signer surface: emailed token, no login
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

      // Verify — module 04
      { path: 'verify', element: <VerifyHome /> },
      { path: 'verify/screening', element: <Screening /> },
      { path: 'verify/clients/:id', element: <ClientVerify /> },

      // Sign — module 05
      { path: 'sign', element: <Agreements /> },
      { path: 'sign/agreements/:id', element: <AgreementDetail /> },

      // Any other module: entitlement check → placeholder while porting
      { path: 'm/:key', element: <ModuleRoute /> },

      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
