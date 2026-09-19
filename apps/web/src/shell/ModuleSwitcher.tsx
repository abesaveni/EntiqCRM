import { NavLink, Link } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { cn } from '@entiq/ui/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@entiq/ui/tooltip';
import { catalogueModules, getModule, type ModuleKey, type ModuleManifest } from '@entiq/modules';
import { useSession, isEntitled } from '@/state/session';
import { ModuleIcon } from '@/lib/icons';

/**
 * The left module switcher — blueprint §2 "a consistent left module switcher".
 * The only dark surface in the product. Lists every catalogue module: owned ones
 * are live links; unowned ones are shown locked and route to the catalogue, so
 * the switcher itself is the first upsell surface.
 */
export function ModuleSwitcher() {
  const tenant = useSession((s) => s.tenant);
  const subscriptions = useSession((s) => s.subscriptions);
  const user = useSession((s) => s.user);

  const owned: ModuleManifest[] = [];
  const locked: ModuleManifest[] = [];
  for (const m of catalogueModules()) {
    if (m.status === 'planned') continue; // blueprint-only modules live in the catalogue, not the rail
    (isEntitled({ tenant, subscriptions }, m.key) ? owned : locked).push(m);
  }

  return (
    <TooltipProvider delayDuration={200}>
      <aside className="flex h-full w-[220px] shrink-0 flex-col bg-sidebar text-sidebar-foreground">
        <Link to="/" className="flex h-14 items-center gap-2.5 border-b border-sidebar-border px-4">
          <img src="/favicon.svg" alt="" className="size-7" />
          <span className="text-[15px] font-semibold tracking-tight text-white">EnTIQ</span>
        </Link>

        <nav className="flex-1 overflow-y-auto px-2 py-3">
          <Section label="Your modules">
            {owned.map((m) => (
              <RailLink key={m.key} module={m} />
            ))}
          </Section>

          {locked.length > 0 && (
            <Section label="Available to add">
              {locked.map((m) => (
                <RailLink key={m.key} module={m} locked />
              ))}
            </Section>
          )}

          {user?.isOperator && (
            <Section label="EnTIQ operators">
              <RailLink module={getModule('control')} />
            </Section>
          )}
        </nav>

        <div className="border-t border-sidebar-border px-4 py-3 text-[11px] leading-4 text-sidebar-foreground/60">
          <div className="truncate font-medium text-sidebar-foreground/90">{tenant?.name ?? '—'}</div>
          <div className="truncate">{tenant?.slug}.entiq.com.au</div>
        </div>
      </aside>
    </TooltipProvider>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-1 px-2 text-[10.5px] font-medium uppercase tracking-[0.1em] text-sidebar-foreground/45">{label}</div>
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  );
}

function RailLink({ module, locked }: { module: ModuleManifest; locked?: boolean }) {
  const to = locked ? `/hq/modules/${module.key}` : routeFor(module.key, module);
  const link = (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        cn(
          'group flex items-center gap-2.5 rounded-[5px] px-2 py-[7px] text-[13px] leading-[18px] transition-colors',
          locked
            ? 'text-sidebar-foreground/55 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground/80'
            : isActive && !locked
              ? 'bg-sidebar-accent text-white'
              : 'text-sidebar-foreground/85 hover:bg-sidebar-accent/70 hover:text-white',
        )
      }
    >
      {({ isActive }) => (
        <>
          <span className={cn('flex size-5 items-center justify-center', isActive && !locked && 'text-sidebar-primary')}>
            <ModuleIcon name={module.icon} className="size-[17px]" />
          </span>
          <span className="flex-1 truncate">{module.shortName}</span>
          {locked && <Lock className="size-3 opacity-60" />}
        </>
      )}
    </NavLink>
  );

  if (!locked) return link;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right" className="max-w-[240px]">
        <div className="font-medium">{module.name}</div>
        <div className="text-[12px] opacity-80">{module.pricing.unit} · click to add</div>
      </TooltipContent>
    </Tooltip>
  );
}

/** First nav entry of a module, or a placeholder route while the module is still being ported. */
function routeFor(key: ModuleKey, m: ModuleManifest): string {
  if (m.status === 'built' || m.status === 'internal') return m.nav[0]?.path ?? `/m/${key}`;
  return `/m/${key}`;
}
