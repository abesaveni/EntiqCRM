import { useEffect, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Search, Bell, ChevronDown, LogOut, Settings, User as UserIcon, Building2, CheckCheck } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { Button } from '@entiq/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@entiq/ui/dropdown-menu';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@entiq/ui/command';
import { Dialog, DialogContent, DialogTitle } from '@entiq/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@entiq/ui/popover';
import { catalogueModules, getModule, type ModuleKey } from '@entiq/modules';
import { crm, type SearchHit } from '@/api/crm';
import { platform, type NotificationOut } from '@/api/platform';
import { useSession } from '@/state/session';
import { ModuleIcon } from '@/lib/icons';

function useCurrentModule(): ModuleKey | null {
  const { pathname } = useLocation();
  if (pathname.startsWith('/hq')) return 'hq';
  if (pathname.startsWith('/control')) return 'control';
  const m = pathname.match(/^\/m\/([a-z]+)/);
  if (m) return m[1] as ModuleKey;
  for (const mod of catalogueModules()) if (mod.nav.some((n) => n.path !== '/' && pathname.startsWith(n.path))) return mod.key;
  return 'crm';
}

export function TopBar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const user = useSession((s) => s.user);
  const entitled = useSession((s) => s.entitled);
  const entitlements = useSession((s) => s.entitlements);
  const logout = useSession((s) => s.logout);
  void entitlements;
  const currentKey = useCurrentModule();
  const current = currentKey ? getModule(currentKey) : null;
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [unread, setUnread] = useState(0);
  const [notes, setNotes] = useState<NotificationOut[] | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setOpen((o) => !o); } };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => { void crm.search(q).then(setHits).catch(() => setHits([])); }, 200);
    return () => clearTimeout(t);
  }, [q, open]);

  // Unread badge: on mount, then every minute.
  useEffect(() => {
    const tick = () => void platform.notifications.unreadCount().then((r) => setUnread(r.unread)).catch(() => undefined);
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, [pathname]);

  const entitledModules = catalogueModules().filter((m) => entitled(m.key));
  const go = (path: string) => { setOpen(false); setQ(''); navigate(path); };
  const openNote = async (n: NotificationOut) => {
    if (!n.read_at) { await platform.notifications.markRead(n.id).catch(() => undefined); setUnread((u) => Math.max(0, u - 1)); }
    if (n.link) navigate(n.link);
  };

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-4">
      <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
        {current && (<>
          <span className="mr-2 flex shrink-0 items-center gap-1.5 text-[13px] font-semibold"><ModuleIcon name={current.icon} className="size-4 text-primary" />{current.shortName}</span>
          {current.nav.map((n) => {
            const active = n.path === '/' ? pathname === '/' : pathname === n.path || pathname.startsWith(n.path + '/');
            return <Button key={n.path} asChild variant="ghost" size="sm" className={active ? 'bg-accent text-accent-foreground hover:bg-accent' : 'text-muted-foreground'}><a href={n.path} onClick={(e) => { e.preventDefault(); navigate(n.path); }}>{n.label}</a></Button>;
          })}
        </>)}
      </nav>

      <Button variant="outline" size="sm" className="hidden w-[260px] justify-start gap-2 text-muted-foreground md:flex" onClick={() => setOpen(true)}>
        <Search className="size-4" /><span className="flex-1 text-left">Search clients, contacts, modules…</span><kbd className="rounded border bg-muted px-1.5 text-[10px] font-medium">⌘K</kbd>
      </Button>
      <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setOpen(true)} aria-label="Search"><Search className="size-4" /></Button>

      <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQ(''); }}>
        <DialogContent className="overflow-hidden p-0 sm:max-w-[560px]">
          <DialogTitle className="sr-only">Search</DialogTitle>
          <Command shouldFilter={false} className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground">
            <CommandInput placeholder="Search clients, contacts, modules…" value={q} onValueChange={setQ} />
            <CommandList>
              <CommandEmpty>{q ? 'No results.' : 'Type to search.'}</CommandEmpty>
              {hits.some((h) => h.type === 'client') && <CommandGroup heading="Clients">{hits.filter((h) => h.type === 'client').map((h) => <CommandItem key={h.id} value={h.id} onSelect={() => go(`/clients/${h.client_id}`)}><Building2 className="mr-2 size-4 text-muted-foreground" /> {h.label}<span className="ml-auto text-[12px] text-muted-foreground">{h.sublabel}</span></CommandItem>)}</CommandGroup>}
              {hits.some((h) => h.type === 'contact') && <CommandGroup heading="Contacts">{hits.filter((h) => h.type === 'contact').map((h) => <CommandItem key={h.id} value={h.id} onSelect={() => go(`/clients/${h.client_id}`)}><UserIcon className="mr-2 size-4 text-muted-foreground" /> {h.label}<span className="ml-auto text-[12px] text-muted-foreground">{h.sublabel}</span></CommandItem>)}</CommandGroup>}
              <CommandGroup heading="Modules">
                {entitledModules.filter((m) => !q || m.name.toLowerCase().includes(q.toLowerCase())).map((m) => <CommandItem key={m.key} value={`mod-${m.key}`} onSelect={() => go(m.nav[0]?.path ?? `/m/${m.key}`)}><ModuleIcon name={m.icon} className="mr-2 size-4 text-muted-foreground" /> {m.name}</CommandItem>)}
              </CommandGroup>
            </CommandList>
          </Command>
        </DialogContent>
      </Dialog>

      <Popover onOpenChange={(o) => { if (o) void platform.notifications.list(false, 30).then(setNotes).catch(() => setNotes([])); }}>
        <PopoverTrigger asChild>
          <Button variant="ghost" size="icon" aria-label={unread ? `${unread} unread notifications` : 'Notifications'} className="relative">
            <Bell className="size-4" />
            {unread > 0 && <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-none text-primary-foreground">{unread > 99 ? '99+' : unread}</span>}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-[380px] p-0">
          <div className="flex items-center justify-between border-b px-4 py-2 text-[13px] font-semibold">
            Notifications
            {unread > 0 && <Button variant="ghost" size="sm" className="h-7 text-[12px] text-muted-foreground" onClick={() => void platform.notifications.readAll().then(() => { setUnread(0); setNotes((ns) => ns?.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })) ?? null); })}><CheckCheck className="mr-1 size-3.5" /> Mark all read</Button>}
          </div>
          <ul className="max-h-[380px] overflow-y-auto">
            {notes?.map((n) => { const m = getModule(n.module_key); return (
              <li key={n.id}>
                <button onClick={() => void openNote(n)} className={`flex w-full gap-3 border-b px-4 py-3 text-left last:border-0 hover:bg-secondary ${n.read_at ? '' : 'bg-accent/40'}`}>
                  <ModuleIcon name={m.icon} className={`mt-0.5 size-4 shrink-0 ${n.read_at ? 'text-muted-foreground' : 'text-primary'}`} />
                  <div className="min-w-0 flex-1">
                    <div className={`truncate text-[13px] ${n.read_at ? '' : 'font-medium'}`}>{n.title}</div>
                    {n.body && <div className="truncate text-[12px] text-muted-foreground">{n.body}</div>}
                    <div className="text-[11px] text-muted-foreground">{m.shortName} · {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}</div>
                  </div>
                </button>
              </li>
            ); })}
            {notes && notes.length === 0 && <li className="px-4 py-8 text-center text-[13px] text-muted-foreground">You're all caught up.</li>}
            {!notes && <li className="px-4 py-8 text-center text-[13px] text-muted-foreground">Loading…</li>}
          </ul>
        </PopoverContent>
      </Popover>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="gap-2 pl-1.5">
            <span className="flex size-7 items-center justify-center rounded-full bg-accent text-[12px] font-semibold text-accent-foreground">{initials(user?.name)}</span>
            <span className="hidden text-left leading-tight lg:block"><span className="block text-[13px] font-medium">{user?.name}</span><span className="block text-[11px] text-muted-foreground capitalize">{user?.role}</span></span>
            <ChevronDown className="size-3.5 text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-[220px]">
          <DropdownMenuLabel className="font-normal"><div className="text-[13px] font-medium">{user?.name}</div><div className="text-[12px] text-muted-foreground">{user?.email}</div></DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => navigate('/hq/settings')}><Settings className="mr-2 size-4" /> Practice settings</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => navigate('/hq/modules')}><Building2 className="mr-2 size-4" /> Modules &amp; subscription</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => { void logout().then(() => navigate('/login')); }}><LogOut className="mr-2 size-4" /> Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}

function initials(name?: string) { return (name ?? '?').split(/\s+/).map((s) => s[0]).slice(0, 2).join('').toUpperCase(); }
