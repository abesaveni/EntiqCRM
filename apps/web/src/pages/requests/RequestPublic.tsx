import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { requests, PURPOSE_LABEL, type PublicPack } from '@/api/requests';
import { RequestWorkspace, describeRequestError } from './RequestWorkspace';

/** The client's request page — reached from the emailed link (/r/{token}), no login. */
export function RequestPublic() {
  const { token = '' } = useParams();
  const [pack, setPack] = useState<PublicPack | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { requests.public.view(token).then(setPack).catch((e: unknown) => setErr(describeRequestError(e))); }, [token]);
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <header className="border-b bg-card"><div className="mx-auto flex h-14 max-w-[880px] items-center gap-3 px-4"><img src="/favicon.svg" alt="" className="size-6" /><span className="text-[14px] font-semibold">{pack?.practice_name ?? 'EnTIQ'}</span><span className="ml-auto text-[12px] text-muted-foreground">Secure request</span></div></header>
      <main className="mx-auto max-w-[880px] px-4 py-6">
        {err && <div className="rounded-[6px] border bg-card p-8 text-center"><ShieldAlert className="mx-auto mb-3 size-8 text-muted-foreground" /><h1 className="text-[18px] font-semibold">{err}</h1></div>}
        {!pack && !err && <p className="text-[13px] text-muted-foreground">Loading…</p>}
        {pack && (<>
          <div className="mb-4"><div className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground">{PURPOSE_LABEL[pack.purpose]} · {pack.client_name}</div><h1 className="text-[22px] font-semibold leading-tight">{pack.title}</h1>{pack.contact_name && <p className="text-[13px] text-muted-foreground">Hi {pack.contact_name.split(' ')[0]} — upload what you have; you can come back to this link any time.</p>}</div>
          <RequestWorkspace pack={pack} onChange={setPack} adapter={{ answer: (k, a) => requests.public.answer(token, k, a), upload: (id, f) => requests.public.upload(token, id, f), notApplicable: (id, n) => requests.public.notApplicable(token, id, n), submit: () => requests.public.submit(token) }} />
          <p className="mt-6 text-[11px] text-muted-foreground">Files are virus-scanned and stored encrypted for {pack.practice_name}. This page is provided by EnTIQ.</p>
        </>)}
      </main>
    </div>
  );
}
