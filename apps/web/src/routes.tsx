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
import { StartHome } from './pages/start/StartHome';
import { OnboardingDetail } from './pages/start/OnboardingDetail';
import { OnboardPublic } from './pages/start/OnboardPublic';
import { ServiceCatalogue } from './pages/start/ServiceCatalogue';
import { PracticeHome } from './pages/practice/PracticeHome';
import { JobDetail } from './pages/practice/JobDetail';
import { Deadlines, Team } from './pages/practice/DeadlinesTeam';
import { RequestsHome } from './pages/requests/RequestsHome';
import { RequestDetail } from './pages/requests/RequestDetail';
import { RequestPublic } from './pages/requests/RequestPublic';
import { PortalAccess } from './pages/client/PortalAccess';
import { PortalLogin, PortalExchange, PortalHomePage, PortalRequestPage } from './pages/portal/PortalApp';
import { SupportPage, SupportTicketPage } from './pages/hq/Support';
import { SupportQueue, SupportTicketOps } from './pages/control/SupportQueue';
import { WorkpapersHome } from './pages/workpapers/WorkpapersHome';
import { PackDetail } from './pages/workpapers/PackDetail';
import { AdvisoryHome } from './pages/advisory/AdvisoryHome';
import { ClientAdvisory } from './pages/advisory/ClientAdvisory';
import { MeetingDetail } from './pages/advisory/MeetingDetail';
import { AcademyHome } from './pages/academy/AcademyHome';
import { CoursePlayer, MyLearningPage } from './pages/academy/CoursePlayer';
import { LendingHome } from './pages/lending/LendingHome';
import { ApplicationDetail } from './pages/lending/ApplicationDetail';
import { DocumentsHome } from './pages/documents/DocumentsHome';
import { PracticeBillingHome } from './pages/billing/PracticeBillingHome';
import { InvoiceDetail } from './pages/billing/InvoiceDetail';

export const router = createBrowserRouter([
  { path: '/signup', element: <SignUp /> },
  { path: '/login', element: <Login /> },
  { path: '/accept-invite', element: <AcceptInvite /> },
  { path: '/account-closed', element: <AccountClosed /> },
  { path: '/s/:token', element: <PublicSign /> },          // signer surface: emailed token, no login
  { path: '/onboard/:token', element: <OnboardPublic /> },  // prospect surface: magic link, no login
  { path: '/r/:token', element: <RequestPublic /> },        // request surface: emailed token, no login
  { path: '/portal', element: <PortalLogin /> },            // client portal: passwordless
  { path: '/portal/login/:token', element: <PortalExchange /> },
  { path: '/portal/home', element: <PortalHomePage /> },
  { path: '/portal/requests/:id', element: <PortalRequestPage /> },
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
      { path: 'hq/support', element: <SupportPage /> },
      { path: 'hq/support/:id', element: <SupportTicketPage /> },

      // Control Centre — operators
      { path: 'control', element: <SupportQueue /> },
      { path: 'control/support', element: <SupportQueue /> },
      { path: 'control/support/:id', element: <SupportTicketOps /> },

      // Verify — module 04
      { path: 'verify', element: <VerifyHome /> },
      { path: 'verify/screening', element: <Screening /> },
      { path: 'verify/clients/:id', element: <ClientVerify /> },

      // Sign — module 05
      { path: 'sign', element: <Agreements /> },
      { path: 'sign/agreements/:id', element: <AgreementDetail /> },

      // Start — module 03
      { path: 'start', element: <StartHome /> },
      { path: 'start/services', element: <ServiceCatalogue /> },
      { path: 'start/onboardings/:id', element: <OnboardingDetail /> },

      // Practice — module 09
      { path: 'practice', element: <PracticeHome /> },
      { path: 'practice/jobs/:id', element: <JobDetail /> },
      { path: 'practice/deadlines', element: <Deadlines /> },
      { path: 'practice/team', element: <Team /> },

      // Requests — module 06
      { path: 'requests', element: <RequestsHome /> },
      { path: 'requests/:id', element: <RequestDetail /> },

      // Client portal — module 14 (staff side)
      { path: 'client', element: <PortalAccess /> },

      // Workpapers — module 08
      { path: 'workpapers', element: <WorkpapersHome /> },
      { path: 'workpapers/:id', element: <PackDetail /> },

      // Advisory — module 10
      { path: 'advisory', element: <AdvisoryHome /> },
      { path: 'advisory/clients/:id', element: <ClientAdvisory /> },
      { path: 'advisory/meetings/:id', element: <MeetingDetail /> },

      // Academy — module 15
      { path: 'academy', element: <AcademyHome /> },
      { path: 'academy/my', element: <MyLearningPage /> },
      { path: 'academy/courses/:id', element: <CoursePlayer /> },

      // Lending — module 20
      { path: 'lending', element: <LendingHome /> },
      { path: 'lending/:id', element: <ApplicationDetail /> },

      // Documents — module 07
      { path: 'documents', element: <DocumentsHome /> },

      // Billing — module 19 (the practice invoicing its clients)
      { path: 'billing', element: <PracticeBillingHome /> },
      { path: 'billing/invoices/:id', element: <InvoiceDetail /> },

      // Any other module: entitlement check → placeholder while porting
      { path: 'm/:key', element: <ModuleRoute /> },

      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
