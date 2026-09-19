import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button } from '@entiq/ui/button';
import { Input } from '@entiq/ui/input';
import { Label } from '@entiq/ui/label';
import { useSession } from '@/state/session';

export function Login() {
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const login = useSession((s) => s.login);
  const [email, setEmail] = useState('priya@ashfieldpartners.example');
  const [pw, setPw] = useState('');

  return (
    <div className="flex min-h-full items-center justify-center px-6 py-12">
      <div className="w-full max-w-[400px]">
        <Link to="/" className="mb-8 flex items-center gap-2.5"><img src="/favicon.svg" alt="" className="size-8" /><span className="text-[17px] font-semibold tracking-tight">EnTIQ</span></Link>
        <h1 className="mb-1">Sign in</h1>
        <p className="mb-6 text-muted-foreground">One login for every EnTIQ module.</p>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); login(email); navigate(location.state?.from ?? '/', { replace: true }); }}>
          <div className="grid gap-1.5"><Label htmlFor="email">Email</Label><Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus /></div>
          <div className="grid gap-1.5">
            <div className="flex items-center justify-between"><Label htmlFor="pw">Password</Label><a className="text-[12px] text-primary hover:underline" href="#">Forgot?</a></div>
            <Input id="pw" type="password" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="Any value in the demo" />
          </div>
          <Button type="submit" className="w-full">Continue</Button>
        </form>
        <p className="mt-6 text-center text-[13px] text-muted-foreground">New to EnTIQ? <Link to="/signup" className="text-primary hover:underline">Start a 15-day trial</Link></p>
      </div>
    </div>
  );
}
