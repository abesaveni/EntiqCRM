import { useEffect, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Building2, ChevronRight } from 'lucide-react';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { useSession, describeError } from '@/state/session';
import { StatusPill, lifecycleTone } from '@/components/StatusPill';

export function Login() {
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const status = useSession((s) => s.status);
  const bootstrap = useSession((s) => s.bootstrap);
  const login = useSession((s) => s.login);
  const selectTenant = useSession((s) => s.selectTenant);
  const pendingTenants = useSession((s) => s.pendingTenants);
  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { void bootstrap(); }, [bootstrap]);
  if (status === 'authenticated') return <Navigate to={location.state?.from ?? '/'} replace />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const r = await login(email, pw);
      if (r === 'ok') navigate(location.state?.from ?? '/', { replace: true });
    } catch (err) { setError(describeError(err)); } finally { setBusy(false); }
  };

  const choose = async (id: string) => {
    setBusy(true); setError(null);
    try { await selectTenant(id); navigate(location.state?.from ?? '/', { replace: true }); }
    catch (err) { setError(describeError(err)); } finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-full items-center justify-center px-6 py-12">
      <div className="w-full max-w-[400px]">
        <Link to="/" className="mb-8 flex items-center gap-2.5"><img src="/favicon.svg" alt="" className="size-8" /><span className="text-[17px] font-semibold tracking-tight">EnTIQ</span></Link>

        {pendingTenants ? (
          <>
            <h1 className="mb-1">Choose a practice</h1>
            <p className="mb-6 text-muted-foreground">Your login belongs to more than one practice. You can switch later from the user menu.</p>
            <ul className="space-y-2">
              {pendingTenants.map((t) => (
                <li key={t.id}>
                  <button disabled={busy} onClick={() => void choose(t.id)} className="flex w-full items-center gap-3 rounded-[6px] border bg-card px-4 py-3 text-left transition-colors hover:bg-secondary disabled:opacity-60">
                    <Building2 className="size-4 text-primary" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] font-medium">{t.name}</span>
                      <span className="block text-[12px] text-muted-foreground capitalize">{t.role} · {t.slug}</span>
                    </span>
                    <StatusPill tone={lifecycleTone(t.status)}>{t.status.replace('_', ' ')}</StatusPill>
                    <ChevronRight className="size-4 text-muted-foreground" />
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <h1 className="mb-1">Sign in</h1>
            <p className="mb-6 text-muted-foreground">One login for every EnTIQ module.</p>
            <form className="space-y-4" onSubmit={submit}>
              <div className="grid gap-1.5"><Label htmlFor="email">Email</Label><Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus autoComplete="email" required /></div>
              <div className="grid gap-1.5">
                <div className="flex items-center justify-between"><Label htmlFor="pw">Password</Label><a className="text-[12px] text-primary hover:underline" href="#">Forgot?</a></div>
                <Input id="pw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" required />
              </div>
              <Button type="submit" className="w-full" disabled={busy}>{busy ? 'Signing in…' : 'Continue'}</Button>
            </form>
            <p className="mt-6 text-center text-[13px] text-muted-foreground">New to EnTIQ? <Link to="/signup" className="text-primary hover:underline">Start a 15-day trial</Link></p>
          </>
        )}

        {error && <div role="alert" className="mt-4 rounded-[5px] border border-error/40 bg-error-bg px-3 py-2 text-[13px] text-error">{error}</div>}
      </div>
    </div>
  );
}
