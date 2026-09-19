/**
 * Demo data for the frontend-first build. Shaped like the CRM core's eventual
 * API (party · entity · contact · relationship · activity) so screens do not
 * change when the backend lands. All records are synthetic.
 */
import type { ModuleKey } from '@entiq/modules';

export type EntityType = 'Company' | 'Trust' | 'Individual' | 'Partnership' | 'SMSF';
export type RiskLevel = 'Low' | 'Medium' | 'High';
export type Stage = 'Lead' | 'Proposal' | 'Onboarding' | 'Active' | 'Review' | 'Dormant';

export interface Client {
  id: string;
  name: string;
  type: EntityType;
  abn?: string;
  acn?: string;
  stage: Stage;
  owner: string;
  since: string; // ISO date
  risk?: RiskLevel;
  contacts: number;
  entities: number;
  openTasks: number;
  tags: string[];
}

export interface Contact {
  id: string;
  clientId: string;
  name: string;
  role: string;
  email: string;
  phone?: string;
  primary: boolean;
}

export interface Activity {
  id: string;
  clientId: string;
  at: string; // ISO
  module: ModuleKey;
  kind: string;
  summary: string;
  actor: string;
}

export interface Task {
  id: string;
  clientId?: string;
  title: string;
  due: string;
  owner: string;
  done: boolean;
  priority: 'Low' | 'Normal' | 'High';
}

const d = (daysAgo: number) => new Date(Date.now() - daysAgo * 86_400_000).toISOString();

export const CLIENTS: Client[] = [
  { id: 'c_ashfield', name: 'Ashfield Family Trust', type: 'Trust', abn: '62 114 887 302', stage: 'Active', owner: 'Priya Nair', since: '2026-03-14', risk: 'Medium', contacts: 4, entities: 3, openTasks: 2, tags: ['Discretionary trust', 'Property'] },
  { id: 'c_marlow', name: 'Marlow Constructions Pty Ltd', type: 'Company', abn: '48 902 337 115', acn: '902 337 115', stage: 'Active', owner: 'Daniel Okafor', since: '2025-11-02', risk: 'Low', contacts: 3, entities: 1, openTasks: 1, tags: ['Building', 'BAS quarterly'] },
  { id: 'c_haven', name: 'Haven Medical Group', type: 'Company', abn: '71 455 210 883', stage: 'Review', owner: 'Priya Nair', since: '2024-07-21', risk: 'Low', contacts: 6, entities: 2, openTasks: 4, tags: ['Health', 'Payroll'] },
  { id: 'c_reyes', name: 'Elena Reyes', type: 'Individual', stage: 'Active', owner: 'Sam Whitlock', since: '2026-01-09', risk: 'Low', contacts: 1, entities: 1, openTasks: 0, tags: ['Sole trader', 'Rental'] },
  { id: 'c_northcote', name: 'Northcote Super Fund', type: 'SMSF', abn: '19 663 004 972', stage: 'Active', owner: 'Daniel Okafor', since: '2025-05-30', risk: 'Medium', contacts: 2, entities: 1, openTasks: 1, tags: ['SMSF', 'Audit due'] },
  { id: 'c_tanaka', name: 'Tanaka & Bell Partnership', type: 'Partnership', abn: '33 781 445 209', stage: 'Onboarding', owner: 'Sam Whitlock', since: '2026-09-02', risk: undefined, contacts: 2, entities: 1, openTasks: 3, tags: ['Professional services'] },
  { id: 'c_greenline', name: 'Greenline Logistics Pty Ltd', type: 'Company', abn: '55 120 998 431', stage: 'Proposal', owner: 'Priya Nair', since: '2026-09-11', risk: undefined, contacts: 1, entities: 1, openTasks: 1, tags: ['Transport', 'Referral'] },
  { id: 'c_oconnor', name: "O'Connor Holdings", type: 'Company', abn: '80 345 667 120', stage: 'Lead', owner: 'Daniel Okafor', since: '2026-09-16', risk: undefined, contacts: 1, entities: 0, openTasks: 1, tags: ['Inbound'] },
  { id: 'c_bellbird', name: 'Bellbird Estate Trust', type: 'Trust', abn: '27 559 883 006', stage: 'Dormant', owner: 'Sam Whitlock', since: '2023-02-17', risk: 'Low', contacts: 2, entities: 2, openTasks: 0, tags: ['Estate'] },
];

export const CONTACTS: Contact[] = [
  { id: 'p1', clientId: 'c_ashfield', name: 'Margaret Ashfield', role: 'Trustee', email: 'margaret@ashfield.example', phone: '0412 338 902', primary: true },
  { id: 'p2', clientId: 'c_ashfield', name: 'Tom Ashfield', role: 'Beneficiary', email: 'tom@ashfield.example', primary: false },
  { id: 'p3', clientId: 'c_ashfield', name: 'Ashfield Nominees Pty Ltd', role: 'Corporate trustee', email: 'admin@ashfieldnominees.example', primary: false },
  { id: 'p4', clientId: 'c_ashfield', name: 'Ruth Delgado', role: 'Bookkeeper', email: 'ruth@delgadobooks.example', phone: '0433 118 774', primary: false },
  { id: 'p5', clientId: 'c_marlow', name: 'Gavin Marlow', role: 'Director', email: 'gavin@marlowcon.example', phone: '0401 220 556', primary: true },
  { id: 'p6', clientId: 'c_marlow', name: 'Sonia Marlow', role: 'Director · Secretary', email: 'sonia@marlowcon.example', primary: false },
  { id: 'p7', clientId: 'c_haven', name: 'Dr Anika Rao', role: 'Practice principal', email: 'anika@havenmedical.example', primary: true },
  { id: 'p8', clientId: 'c_reyes', name: 'Elena Reyes', role: 'Owner', email: 'elena.reyes@example.com', phone: '0422 909 313', primary: true },
  { id: 'p9', clientId: 'c_tanaka', name: 'Kenji Tanaka', role: 'Partner', email: 'kenji@tanakabell.example', primary: true },
  { id: 'p10', clientId: 'c_greenline', name: 'Marcus Field', role: 'CFO', email: 'marcus@greenline.example', primary: true },
];

export const ACTIVITY: Activity[] = [
  { id: 'a1', clientId: 'c_ashfield', at: d(0.2), module: 'crm', kind: 'note', summary: 'Called Margaret re: distribution minute — will sign this week.', actor: 'Priya Nair' },
  { id: 'a2', clientId: 'c_ashfield', at: d(1), module: 'workpapers', kind: 'xero.sync', summary: 'Xero ledger synced · 214 transactions · 3 uncoded', actor: 'System' },
  { id: 'a3', clientId: 'c_ashfield', at: d(3), module: 'sign', kind: 'agreement.completed', summary: 'FY26 engagement letter signed by Margaret Ashfield', actor: 'EnTIQ Sign' },
  { id: 'a4', clientId: 'c_ashfield', at: d(9), module: 'verify', kind: 'screening.cleared', summary: 'Annual PEP/sanctions re-screen · 2 beneficial owners · no matches', actor: 'EnTIQ Verify' },
  { id: 'a5', clientId: 'c_ashfield', at: d(12), module: 'crm', kind: 'task.completed', summary: 'Collected trust deed variation', actor: 'Daniel Okafor' },
  { id: 'a6', clientId: 'c_ashfield', at: d(40), module: 'verify', kind: 'verification.approved', summary: 'KYC verified · risk rating Medium (property concentration)', actor: 'Priya Nair' },
  { id: 'a7', clientId: 'c_marlow', at: d(0.5), module: 'workpapers', kind: 'bas.due', summary: 'BAS Q1 FY27 due 28 Oct — workpaper 60% complete', actor: 'System' },
  { id: 'a8', clientId: 'c_tanaka', at: d(1.5), module: 'start', kind: 'stage.completed', summary: 'Onboarding stage 6 complete — service package confirmed', actor: 'Kenji Tanaka' },
  { id: 'a9', clientId: 'c_greenline', at: d(2), module: 'crm', kind: 'proposal.sent', summary: 'Proposal sent · $18,400 pa · awaiting response', actor: 'Priya Nair' },
  { id: 'a10', clientId: 'c_oconnor', at: d(3), module: 'crm', kind: 'lead.created', summary: 'Inbound enquiry via website — restructure advice', actor: 'System' },
  { id: 'a11', clientId: 'c_haven', at: d(4), module: 'practice', kind: 'job.overdue', summary: 'Payroll reconciliation job 6 days overdue', actor: 'System' },
];

export const TASKS: Task[] = [
  { id: 't1', clientId: 'c_ashfield', title: 'Obtain signed distribution minute', due: d(-2), owner: 'Priya Nair', done: false, priority: 'High' },
  { id: 't2', clientId: 'c_ashfield', title: 'Confirm new beneficiary TFN', due: d(-6), owner: 'Daniel Okafor', done: false, priority: 'Normal' },
  { id: 't3', clientId: 'c_marlow', title: 'Code 3 uncoded Xero transactions', due: d(-1), owner: 'Daniel Okafor', done: false, priority: 'Normal' },
  { id: 't4', clientId: 'c_haven', title: 'Payroll reconciliation — Q1', due: d(6), owner: 'Priya Nair', done: false, priority: 'High' },
  { id: 't5', clientId: 'c_tanaka', title: 'Review partnership agreement upload', due: d(-1), owner: 'Sam Whitlock', done: false, priority: 'Normal' },
  { id: 't6', clientId: 'c_greenline', title: 'Follow up proposal', due: d(-3), owner: 'Priya Nair', done: false, priority: 'Normal' },
  { id: 't7', clientId: 'c_oconnor', title: 'Qualify lead — book discovery call', due: d(-1), owner: 'Daniel Okafor', done: false, priority: 'High' },
  { id: 't8', title: 'Quarterly access review (Practice HQ)', due: d(-10), owner: 'You', done: false, priority: 'Low' },
];

export const STAFF = [
  { id: 'u1', name: 'Priya Nair', email: 'priya@ashfieldpartners.example', role: 'Partner', status: 'Active', modules: ['crm', 'workpapers', 'verify', 'sign', 'advisory'] as ModuleKey[] },
  { id: 'u2', name: 'Daniel Okafor', email: 'daniel@ashfieldpartners.example', role: 'Senior accountant', status: 'Active', modules: ['crm', 'workpapers', 'verify'] as ModuleKey[] },
  { id: 'u3', name: 'Sam Whitlock', email: 'sam@ashfieldpartners.example', role: 'Client coordinator', status: 'Active', modules: ['crm', 'start', 'sign'] as ModuleKey[] },
  { id: 'u4', name: 'Ruth Delgado', email: 'ruth@delgadobooks.example', role: 'External bookkeeper', status: 'Invited', modules: ['workpapers'] as ModuleKey[] },
];

export const INTEGRATIONS = [
  { key: 'xero', name: 'Xero', category: 'Accounting ledger', status: 'connected' as const, detail: 'Ashfield Partners · 9 organisations · synced 2h ago', usedBy: ['workpapers', 'advisory'] as ModuleKey[] },
  { key: 'm365', name: 'Microsoft 365', category: 'Email & calendar', status: 'not_connected' as const, detail: 'Sync email and meetings onto the client timeline', usedBy: ['crm', 'advisory'] as ModuleKey[] },
  { key: 'didit', name: 'Didit', category: 'Identity verification', status: 'connected' as const, detail: 'Live · individual + KYB workflows', usedBy: ['verify', 'start'] as ModuleKey[] },
  { key: 'equifax', name: 'Equifax', category: 'Entity & credit data', status: 'attention' as const, detail: 'Company enquiry live · identity module awaiting tech pack', usedBy: ['verify'] as ModuleKey[] },
  { key: 'opensanctions', name: 'OpenSanctions', category: 'PEP & sanctions', status: 'connected' as const, detail: 'Default dataset · threshold 0.7', usedBy: ['verify'] as ModuleKey[] },
  { key: 'stripe', name: 'Stripe', category: 'Payments', status: 'connected' as const, detail: 'Platform billing · card ending 4242', usedBy: ['billing', 'hq'] as ModuleKey[] },
  { key: 'smtp', name: 'Email (SMTP)', category: 'Communications', status: 'connected' as const, detail: 'no-reply@entiq.com.au', usedBy: ['crm', 'sign', 'start', 'hq'] as ModuleKey[] },
];
