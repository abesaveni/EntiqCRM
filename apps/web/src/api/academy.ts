/** Typed client for EnTIQ Academy (services/api/app/modules/academy). */
import { API_BASE, ApiError, tokenStore } from './client';

export interface QuestionOut { id: string; text: string; options: string[]; points: number; correct: string[] | null }
export interface LessonOut { id: string; title: string; kind: 'reading' | 'video' | 'quiz'; order: number; minutes: number; body: string | null; video_url: string | null; questions: QuestionOut[]; completed: boolean }
export interface CourseOut { id: string; title: string; summary: string | null; category: string; level: string; minutes: number; pass_mark: number; certificate: boolean; valid_months: number | null; status: string; lesson_count: number; is_catalogue: boolean; enrolled: boolean; my_status: string | null; my_progress: number; created_at: string }
export interface EnrolmentOut { id: string; membership_id: string; member_name: string | null; course_id: string; course_title: string; category: string; status: 'not_started' | 'in_progress' | 'completed' | 'expired'; due_on: string | null; overdue: boolean; progress: number; best_score: number | null; attempts: number; started_at: string | null; completed_at: string | null; requirement_id: string | null }
export interface CourseDetail extends CourseOut { lessons: LessonOut[]; enrolment: EnrolmentOut | null }
export interface AttemptOut { score: number; passed: boolean; pass_mark: number; correct: number; total: number; enrolment: EnrolmentOut; certificate_serial: string | null; feedback: Array<{ id: string; text: string; correct: boolean; expected: string[]; picked: string[] }> }
export interface CertificateOut { id: string; serial: string; member_name: string; course_title: string; category: string; score: number; issued_on: string; expires_on: string | null; expired: boolean; revoked: boolean; sha256: string }
export interface RequirementOut { id: string; course_id: string; course_title: string; name: string; roles: string[]; frequency_months: number; grace_days: number; is_active: boolean; reference: string | null; covered: number; due_soon: number; overdue: number }
export interface ComplianceRow { membership_id: string; member_name: string; role: string; requirement_id: string; requirement_name: string; course_id: string; course_title: string; state: 'covered' | 'due_soon' | 'overdue' | 'never'; last_completed_on: string | null; expires_on: string | null; certificate_serial: string | null }
export interface AcademyOverview { courses: number; enrolments_open: number; overdue: number; completed_30d: number; certificates_valid: number; certificates_expiring_60d: number; compliance_pct: number; by_category: Record<string, number> }
export interface MyLearning { enrolments: EnrolmentOut[]; certificates: CertificateOut[]; compliance: ComplianceRow[] }

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = tokenStore.get();
  const res = await fetch(`${API_BASE}/academy${path}`, { method, headers: { Accept: 'application/json', ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(t ? { Authorization: `Bearer ${t.access_token}` } : {}) }, body: body === undefined ? undefined : JSON.stringify(body) });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown } | null)?.detail ?? data);
  return data as T;
}

export const academy = {
  overview: () => req<AcademyOverview>('GET', '/overview'),
  courses: {
    list: (category?: string) => req<CourseOut[]>('GET', `/courses${category ? `?category=${encodeURIComponent(category)}` : ''}`),
    seed: () => req<CourseOut[]>('POST', '/courses/seed'),
    get: (id: string) => req<CourseDetail>('GET', `/courses/${id}`),
    create: (b: { title: string; summary?: string | null; category: string; level?: string; pass_mark?: number; certificate?: boolean; valid_months?: number | null; lessons?: Array<{ title: string; kind: string; minutes?: number; body?: string | null; video_url?: string | null; questions?: Array<{ text: string; options: string[]; correct: string[]; points?: number }> }> }) => req<CourseDetail>('POST', '/courses', b),
    start: (id: string) => req<CourseDetail>('POST', `/courses/${id}/start`),
    completeLesson: (id: string, lessonId: string) => req<EnrolmentOut>('POST', `/courses/${id}/lessons/${lessonId}/complete`),
    attempt: (id: string, lessonId: string, answers: Record<string, string[]>) => req<AttemptOut>('POST', `/courses/${id}/lessons/${lessonId}/attempt`, { answers }),
  },
  my: () => req<MyLearning>('GET', '/my'),
  enrolments: {
    list: (f: { status?: string; membership_id?: string } = {}) => { const p = new URLSearchParams(); if (f.status) p.set('status', f.status); if (f.membership_id) p.set('membership_id', f.membership_id); const s = p.toString(); return req<EnrolmentOut[]>('GET', `/enrolments${s ? `?${s}` : ''}`); },
    assign: (b: { course_id: string; membership_ids?: string[]; all_staff?: boolean; due_in_days?: number }) => req<EnrolmentOut[]>('POST', '/enrolments', b),
  },
  certificates: (membershipId?: string) => req<CertificateOut[]>('GET', `/certificates${membershipId ? `?membership_id=${membershipId}` : ''}`),
  verify: (serial: string) => req<{ found: boolean; intact?: boolean; certificate?: CertificateOut }>('GET', `/certificates/verify/${encodeURIComponent(serial)}`),
  requirements: {
    list: () => req<RequirementOut[]>('GET', '/requirements'),
    create: (b: { course_id: string; name?: string | null; roles?: string[]; frequency_months?: number; grace_days?: number; reference?: string | null }) => req<RequirementOut>('POST', '/requirements', b),
    toggle: (id: string) => req<RequirementOut>('POST', `/requirements/${id}/toggle`),
  },
  compliance: () => req<ComplianceRow[]>('GET', '/compliance'),
  enforce: () => req<{ enrolled: number }>('POST', '/compliance/enforce'),
};

export const COMPLIANCE_LABEL: Record<ComplianceRow['state'], string> = { covered: 'Covered', due_soon: 'Due soon', overdue: 'Overdue', never: 'Never done' };
export function complianceTone(s: ComplianceRow['state']): 'neutral' | 'success' | 'warn' | 'error' | 'info' | 'teal' { return s === 'covered' ? 'success' : s === 'due_soon' ? 'warn' : 'error'; }
