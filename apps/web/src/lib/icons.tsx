import type { LucideProps } from 'lucide-react';
import {
  Banknote, Box, Briefcase, Building2, CalendarClock, Fingerprint, FolderOpen, GraduationCap, Handshake,
  Inbox, KanbanSquare, Landmark, Megaphone, PenLine, PieChart, Receipt, Rocket, Scale, Shield, ShieldCheck,
  Smartphone, Table2, TrendingUp, Users, UsersRound,
} from 'lucide-react';

/**
 * Icons referenced by module manifests, imported by name so the bundler tree-shakes
 * the rest of the set. (A namespace import pulled all ~1,500 icons — 800 KB — into the build.)
 * Add an entry here when a manifest gains a new icon; unknown names fall back to a box.
 */
const ICONS: Record<string, React.ComponentType<LucideProps>> = {
  Banknote, Briefcase, Building2, CalendarClock, Fingerprint, FolderOpen, GraduationCap, Handshake,
  Inbox, KanbanSquare, Landmark, Megaphone, PenLine, PieChart, Receipt, Rocket, Scale, Shield, ShieldCheck,
  Smartphone, Table2, TrendingUp, Users, UsersRound,
};

export function ModuleIcon({ name, ...props }: { name: string } & LucideProps) {
  const Cmp = ICONS[name] ?? Box;
  return <Cmp {...props} />;
}
