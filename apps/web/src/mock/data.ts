/**
 * Remaining demo data. Client, contact, task and timeline data now come from the CRM API;
 * integration status stays mocked until the Integration Hub is wired (M6).
 */
import type { ModuleKey } from '@entiq/modules';

export const INTEGRATIONS = [
  { key: 'xero', name: 'Xero', category: 'Accounting ledger', status: 'not_connected' as const, detail: 'Connect to sync ledgers into Workpapers and Advisory', usedBy: ['workpapers', 'advisory'] as ModuleKey[] },
  { key: 'm365', name: 'Microsoft 365', category: 'Email & calendar', status: 'not_connected' as const, detail: 'Sync email and meetings onto the client timeline', usedBy: ['crm', 'advisory'] as ModuleKey[] },
  { key: 'didit', name: 'Didit', category: 'Identity verification', status: 'connected' as const, detail: 'Live · individual + KYB workflows', usedBy: ['verify', 'start'] as ModuleKey[] },
  { key: 'equifax', name: 'Equifax', category: 'Entity & credit data', status: 'attention' as const, detail: 'Company enquiry live · identity module awaiting tech pack', usedBy: ['verify'] as ModuleKey[] },
  { key: 'opensanctions', name: 'OpenSanctions', category: 'PEP & sanctions', status: 'connected' as const, detail: 'Default dataset · threshold 0.7', usedBy: ['verify'] as ModuleKey[] },
  { key: 'stripe', name: 'Stripe', category: 'Payments', status: 'not_connected' as const, detail: 'Platform billing — awaiting keys', usedBy: ['billing', 'hq'] as ModuleKey[] },
  { key: 'smtp', name: 'Email (SMTP)', category: 'Communications', status: 'connected' as const, detail: 'no-reply@entiq.com.au', usedBy: ['crm', 'sign', 'start', 'hq'] as ModuleKey[] },
];
