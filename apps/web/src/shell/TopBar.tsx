import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Search, Bell, ChevronDown, LogOut, Settings, User as UserIcon, Building2 } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@entiq/ui/dropdown-menu';
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@entiq/ui/command';
import { Popover, PopoverContent, PopoverTrigger } from '@entiq/ui/popover';
import { catalogueModules, getModule, type ModuleKey } from '@entiq/modules';
import { useSession, isEntitled } from '@/state/session';
import { CLIENTS, CONTACTS, ACTIVITY } from '@/mock/data';
import { ModuleIcon } from '@/lib/icons';
import { formatDistanceToNow } from 'date-fns';

/** Contextual workspace nav for the module the current route belongs to. */
function useCurrentModule(): ModuleKey | null {
  const { pathname } = useLocation();
  if (pathname.startsWith('/hq')) return 'hq';
  if (pathname.startsWith('/control')) return 'control';
  const m = pathname.match(/^\/m\/([a-z]+)/);
  if (m) return m[1] as ModuleKey;
  for (const mod of catalogueModules()) {
    if (mod.nav.some((n) => n.path !== '/' && pathname.startsWith(n.path))) return mod.key;
  }
  return 'crm';
}

export function TopBar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const user = useSession((s) => s.user);
  const tenant = useSession((s) => s.tenant);
  const subscriptions = useSession((s) => s.subscriptions);
  const logout = useSession((s) => s.logout);
  const currentKey = useCurrentModule();
  const current = currentKey ? getModule(currentKey) : null;
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const entitledModules = catalogueModules().filter((m) => isEntitled({ tenant, subscriptions }, m.key));
  const unread = ACTIVITY.slice(0, 4);

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-4">
      {/* contextual workspace nav */}
      <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        {current && (
          <>
            <span className="mr-2 flex shrink-0 items-center gap-1.5 text-[13px] font-semibold">
              <ModuleIcon name={current.icon} className="size-4 text-primary" />
              {current.shortName}
            </span>
            {current.nav.map((n) => {
              const active = n.path === '/' ? pathname === '/' : pathname === n.path || pathname.startsWith(n.path + '/');
              return (
                <Button key={n.path} asChild variant="ghost" size="sm" className={active ? 'bg-accent text-accent-foreground hover:bg-accent' : 'text-muted-foreground'}>
                  <a href={n.path} onClick={(e) => { e.preventDefault(); navigate(n.path); }}>{n.label}</a>
                </Button>
              );
            })}
          </>
        )}
      </nav>

      {/* global search */}
      <Button variant="outline" size="sm" className="hidden w-[260px] justify-start gap-2 text-muted-foreground md:flex" onClick={() => setOpen(true)}>
        <Search className="size-4" />
        <span className="flex-1 text-left">Search clients, contacts, modules…</span>
        <kbd className="rounded border bg-muted px-1.5 text-[10px] font-medium">⌘K</kbd>
      </Button>
      <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setOpen(true)} aria-label="Search">
        <Search className="size-4" />
      </Button>

      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Search clients, contacts, modules…" />
        <CommandList>
          <CommandEmpty>No results.</CommandEmpty>
          <CommandGroup heading="Clients">
            {CLIENTS.map((c) => (
              <CommandItem key={c.id} value={`${c.name} ${c.abn ?? ''}`} onSelect={() => { setOpen(false); navigate(`/clients/${c.id}`); }}>
                <Building2 className="mr-2 size-4 text-muted-foreground" /> {c.name}
                <span className="ml-auto text-[12px] text-muted-foreground">{c.type}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading="Contacts">
            {CONTACTS.slice(0, 6).map((p) => (
              <CommandItem key={p.id} value={`${p.name} ${p.email}`} onSelect={() => { setOpen(false); navigate(`/clients/${p.clientId}`); }}>
                <UserIcon className="mr-2 size-4 text-muted-foreground" /> {p.name}
                <span className="ml-auto text-[12px] text-muted-foreground">{p.role}</span>
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading="Modules">
            {entitledModules.map((m) => (
              <CommandItem key={m.key} value={m.name} onSelect={() => { setOpen(false); navigate(m.nav[0]?.path ?? `/m/${m.key}`); }}>
                <ModuleIcon name={m.icon} className="mr-2 size-4 text-muted-foreground" /> {m.name}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>

      {/* notifications */}
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="icon" aria-label="Notifications" className="relative">
            <Bell className="size-4" />
            <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-primary" />
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-[360px] p-0">
          <div className="border-b px-4 py-2.5 text-[13px] font-semibold">Notifications</div>
          <ul className="max-h-[360px] overflow-y-auto">
            {unread.map((a) => {
              const c = CLIENTS.find((x) => x.id === a.clientId);
              const m = getModule(a.module);
              return (
                <li key={a.id} className="flex gap-3 border-b px-4 py-3 last:border-0 hover:bg-secondary">
                  <ModuleIcon name={m.icon} className="mt-0.5 size-4 shrink-0 text-primary" />
                  <div className="min-w-0">
                    <div className="truncate text-[13px]">{a.summary}</div>
                    <div className="text-[12px] text-muted-foreground">{c?.name} · {formatDistanceToNow(new Date(a.at), { addSuffix: true })}</div>
                  </div>
                </li>
              );
            })}
          </ul>
        </PopoverContent>
      </Popover>

      {/* user menu */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="gap-2 pl-1.5">
            <span className="flex size-7 items-center justify-center rounded-full bg-accent text-[12px] font-semibold text-accent-foreground">
              {initials(user?.name)}
            </span>
            <span className="hidden text-left leading-tight lg:block">
              <span className="block text-[13px] font-medium">{user?.name}</span>
              <span className="block text-[11px] text-muted-foreground capitalize">{user?.role}</span>
            </span>
            <ChevronDown className="size-3.5 text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-[220px]">
          <DropdownMenuLabel className="font-normal">
            <div className="text-[13px] font-medium">{user?.name}</div>
            <div className="text-[12px] text-muted-foreground">{user?.email}</div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => navigate('/hq/settings')}><Settings className="mr-2 size-4" /> Practice settings</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => navigate('/hq/modules')}><Building2 className="mr-2 size-4" /> Modules & subscription</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => { logout(); navigate('/login'); }}><LogOut className="mr-2 size-4" /> Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}

function initials(name?: string) {
  return (name ?? '?').split(/\s+/).map((s) => s[0]).slice(0, 2).join('').toUpperCase();
}
