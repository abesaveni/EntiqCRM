import { MANIFESTS } from './manifests';
import type { ModuleKey, ModuleManifest } from './types';

const byKey = new Map<ModuleKey, ModuleManifest>(MANIFESTS.map((m) => [m.key, m]));

/** Modules bundled into the $99/mo base plan. Every tenant is entitled to these while the tenant is in good standing. */
export const BASE_BUNDLE: ModuleKey[] = ['hq', 'crm'];

/** Platform services that ship with every tenant but are not shown as purchasable. */
/** Reserved for services the platform provisions itself. EnTIQ's own subscription billing is the
 *  spine (Practice HQ), not a module, so nothing sits here today. */
export const PLATFORM_SERVICES: ModuleKey[] = [];

export function getModule(key: ModuleKey): ModuleManifest {
  const m = byKey.get(key);
  if (!m) throw new Error(`Unknown module: ${key}`);
  return m;
}

export function allModules(): ModuleManifest[] {
  return MANIFESTS;
}

/** Customer-facing catalogue — everything a practice can see or buy. Control Centre is excluded by design. */
export function catalogueModules(): ModuleManifest[] {
  return MANIFESTS.filter((m) => m.status !== 'internal');
}

/** Modules a practice can add on top of the base plan. */
export function purchasableModules(): ModuleManifest[] {
  return MANIFESTS.filter(
    (m) => m.status !== 'internal' && !BASE_BUNDLE.includes(m.key) && !PLATFORM_SERVICES.includes(m.key),
  );
}

/** Modules that contribute a panel to the client record, in blueprint order. */
export function panelContributors(): ModuleManifest[] {
  return MANIFESTS.filter((m) => m.panels.some((p) => p.slot === 'client.360'));
}

/** Resolve the full hard-dependency closure for a module (what must also be enabled). */
export function requiredClosure(key: ModuleKey): ModuleKey[] {
  const seen = new Set<ModuleKey>();
  const walk = (k: ModuleKey) => {
    for (const dep of getModule(k).requires) {
      if (!seen.has(dep)) {
        seen.add(dep);
        walk(dep);
      }
    }
  };
  walk(key);
  return [...seen];
}

/** Which modules would be richer if `key` were added — the upsell surface of a subscription. */
export function enhancedBy(key: ModuleKey): ModuleManifest[] {
  return MANIFESTS.filter((m) => m.enhances.includes(key));
}
