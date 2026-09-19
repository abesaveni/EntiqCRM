import { PageHeader } from '@/components/PageHeader';

/** Named CRM screens from the blueprint not yet built out — kept as real routes so navigation is complete. */
export function Placeholder({ title, description }: { title: string; description: string }) {
  return (
    <div className="page">
      <PageHeader eyebrow="CRM" title={title} description={description} />
      <div className="rounded-[6px] border border-dashed bg-card px-6 py-16 text-center text-[13px] text-muted-foreground">Next in the CRM build.</div>
    </div>
  );
}
