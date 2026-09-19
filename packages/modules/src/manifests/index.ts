import type { ModuleManifest } from '../types';
import data from '../../manifests.json';

/**
 * All 24 modules from the Commercial Module Blueprint v1.1, in blueprint order.
 *
 * The DATA lives in `packages/modules/manifests.json` — one file read by both this
 * TypeScript package (frontend) and `services/api/app/modules/registry.py` (backend).
 * Edit the JSON; never fork the list. The type below is the contract both sides honour.
 *
 * Pricing decisions taken 19 Sep 2026:
 *   - Practice HQ + CRM are BUNDLED as the $99/mo + GST base plan (15-day trial, card at signup).
 *   - Every other customer module is sold on top, per its blueprint commercial model.
 *   - Control Centre is internal and never appears in the customer catalogue.
 */
export const MANIFESTS: ModuleManifest[] = data as ModuleManifest[];
