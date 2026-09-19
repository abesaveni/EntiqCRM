import { useState } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { useSession, describeError } from '@/state/session';

/** Landing page for an invitation link: set a name and password, join the practice. */
export function AcceptInvite() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const navigate = useNavigate();
  const acceptInvite = useSession((s) => s.acceptInvite);
  const status = useSession((s) => s.status);
  const [name, setName] = useState('');
  const [pw, setPw] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === 'authenticated') return <Navigate to="/" replace />;
  if (!token) return <Navigate to="/login" replace />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await acceptInvite(token, name, pw); navigate('/', { replace: true }); }
    catch (err) { setError(describeError(err)); } finally { setBusy(false); }
  };

  return (
    <div className="flex min-h-full items-center justify-center px-6 py-12">
      <div className="w-full max-w-[400px]">
        <Link to="/" className="mb-8 flex items-center gap-2.5"><img src="/favicon.svg" alt="" className="size-8" /><span className="text-[17px] font-semibold tracking-tight">EnTIQ</span></Link>
        <h1 className="mb-1">You have been invited</h1>
        <p className="mb-6 text-muted-foreground">Set up your login to join the practice. If you already use EnTIQ with this email, your existing password is kept.</p>
        <form className="space-y-4" onSubmit={submit}>
          <div className="grid gap-1.5"><Label htmlFor="name">Your name</Label><Input id="name" value={name} onChange={(e) => setName(e.target.value)} autoFocus required /></div>
          <div className="grid gap-1.5"><Label htmlFor="pw">Password</Label><Input id="pw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" required /><div className="text-[12px] text-muted-foreground">12+ characters with upper, lower, number and symbol.</div></div>
          <Button type="submit" className="w-full" disabled={busy}>{busy ? 'Joining…' : 'Join practice'}</Button>
        </form>
        {error && <div role="alert" className="mt-4 rounded-[5px] border border-error/40 bg-error-bg px-3 py-2 text-[13px] text-error">{error}</div>}
      </div>
    </div>
  );
}
