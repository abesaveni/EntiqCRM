import { cn } from '@entiq/ui/utils';

type Tone = 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal';

const tones: Record<Tone, string> = {
  neutral: 'bg-muted text-foreground',
  success: 'bg-success-bg text-success',
  warn: 'bg-warn-bg text-warn',
  error: 'bg-error-bg text-error',
  info: 'bg-info-bg text-info',
  teal: 'bg-accent text-accent-foreground',
};

export function StatusPill({ tone = 'neutral', children, className }: { tone?: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-[4px] px-2 py-[2px] text-[12px] font-medium leading-[18px] whitespace-nowrap', tones[tone], className)}>
      {children}
    </span>
  );
}

export function riskTone(risk?: string): Tone {
  if (risk === 'High') return 'error';
  if (risk === 'Medium') return 'warn';
  if (risk === 'Low') return 'success';
  return 'neutral';
}

export function stageTone(stage: string): Tone {
  switch (stage) {
    case 'Active': return 'success';
    case 'Onboarding': return 'teal';
    case 'Proposal': return 'info';
    case 'Lead': return 'neutral';
    case 'Review': return 'warn';
    case 'Dormant': return 'neutral';
    default: return 'neutral';
  }
}

export function lifecycleTone(status: string): Tone {
  switch (status) {
    case 'active': return 'success';
    case 'trialing': return 'teal';
    case 'past_due': return 'warn';
    case 'suspended': return 'warn';
    case 'cancelled': return 'error';
    case 'retained': return 'neutral';
    default: return 'neutral';
  }
}
