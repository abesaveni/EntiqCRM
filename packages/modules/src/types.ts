/**
 * Module manifest — the single declaration each EnTIQ module makes about itself.
 *
 * Everything the platform needs to know about a module lives here: what it is
 * called, what it sells for, what it needs, what it offers others, and what it
 * contributes to the shared client record. The catalogue, the navigation, the
 * permission list and the entitlement gate are all GENERATED from these — a new
 * module is a new manifest, not a change to the platform.
 *
 * Source of truth: EnTIQ Commercial Module Blueprint v1.1 (1 Aug 2026), §3 + MODULE 01–24.
 */

export type ModuleKey =
  | 'hq'          // 01 Practice HQ
  | 'control'     // 02 Control Centre (internal)
  | 'start'       // 03 Start
  | 'verify'      // 04 Verify
  | 'sign'        // 05 Sign
  | 'requests'    // 06 Requests
  | 'documents'   // 07 Documents
  | 'workpapers'  // 08 Workpapers
  | 'practice'    // 09 Practice
  | 'advisory'    // 10 Advisory
  | 'capital'     // 11 Capital
  | 'credit'      // 12 Credit
  | 'settle'      // 13 Settle
  | 'client'      // 14 Client
  | 'academy'     // 15 Academy
  | 'crm'         // 16 CRM
  | 'marketing'   // 17 Marketing
  | 'projects'    // 18 Projects
  | 'billing'     // 19 Billing
  | 'lending'     // 20 Lending
  | 'loanmanager' // 21 Loan Manager
  | 'funds'       // 22 Funds
  | 'trust'       // 23 Trust
  | 'associations'; // 24 Associations

/** How the module is charged. `included` = part of the $99 base; `internal` = never sold. */
export type PricingModel =
  | 'included'
  | 'internal'
  | 'per_seat'
  | 'per_client'
  | 'metered'
  | 'tiered';

export interface ModulePricing {
  model: PricingModel;
  /** Short unit label for the catalogue card, e.g. "per verification". */
  unit: string;
  /** The blueprint's commercial-model sentence, verbatim. */
  commercial: string;
  /** Indicative monthly price in AUD ex-GST where one has been set. Undefined = "to be set". */
  fromAud?: number;
}

/**
 * Release status of the module in THIS codebase.
 *  - built:       code exists and is wired
 *  - porting:     a source repo exists and is being brought across
 *  - planned:     blueprint only, no source code yet
 *  - internal:    operator-only, never in the customer catalogue
 */
export type ModuleStatus = 'built' | 'porting' | 'planned' | 'internal';

export interface NavEntry {
  label: string;
  path: string;
}

/** A card the module contributes to a shared composition surface (today: the client record). */
export interface PanelContribution {
  slot: 'client.360';
  title: string;
  /** Shown in the same slot when the tenant has not subscribed. */
  upsell: string;
}

export interface ModuleManifest {
  key: ModuleKey;
  /** Blueprint module number, 1–24. */
  number: number;
  name: string;
  /** Name without the "EnTIQ" prefix, for the switcher. */
  shortName: string;
  /** One line: the outcome the module delivers (blueprint §3 "Primary outcome"). */
  outcome: string;
  /** Lucide icon name used by the module switcher and catalogue. */
  icon: string;
  status: ModuleStatus;
  pricing: ModulePricing;
  /** Hard dependencies — the module cannot run without these. */
  requires: ModuleKey[];
  /** Soft dependencies — richer when present, upsell when absent. */
  enhances: ModuleKey[];
  /** Capabilities other modules may consume. */
  provides: string[];
  permissions: string[];
  nav: NavEntry[];
  panels: PanelContribution[];
  /** Repos this module is ported from (blueprint "Source assets", mapped to the nine repos read). */
  sourceRepos: string[];
}
