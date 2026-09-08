const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export type IntegrationStatus = "pending" | "connecting" | "connected" | "error";

export interface Integration {
  id: number;
  type: string;
  base_url: string | null;
  status: IntegrationStatus;
  last_error: string | null;
  last_synced_at: string | null;
}

export interface Course {
  id: number;
  source: string;
  external_id: string;
  name: string;
  term: string | null;
  code: string | null;
  archived: boolean;
  // What to actually render - the backend already folds the same real class
  // synced from more than one platform (e.g. Gradescope + PrairieLearn) into
  // one course, so this is never duplicated. `sources` lists every platform
  // behind it (more than one only for a merged class).
  display_name: string;
  sources: string[];
}

export type TaskStatus = "pending" | "done" | "dismissed";

export interface Task {
  id: number;
  source: string;
  course_id: number | null;
  title: string;
  type: string;
  due_at: string | null;
  late_due_at: string | null;
  url: string | null;
  status: TaskStatus;
  points_possible: number | null;
  score: number | null;
  graded_at: string | null;
  started_at: string | null;
}

export interface SyncResult {
  integrations_synced: number;
  courses_upserted: number;
  tasks_upserted: number;
  tasks_auto_dismissed: number;
  courses_archive_changed: number;
  courses_merged: number;
  errors: string[];
}

export type ReminderStatus = "pending" | "dismissed";

export interface Reminder {
  id: number;
  task_id: number;
  lead_minutes: number;
  remind_at: string;
  status: ReminderStatus;
  task_title: string;
  task_url: string | null;
  task_due_at: string | null;
  task_source: string;
}

export interface Settings {
  reminder_lead_minutes: number[];
}

// --- Study Time Tracker ---

export interface StudySession {
  id: number;
  course_id: number;
  course_name: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number | null;
}

// --- Analytics Dashboard ---

export interface CourseOverview {
  course_id: number;
  course_name: string;
  avg_grade_pct: number | null;
  graded_task_count: number;
  study_hours_this_week: number;
  study_hours_total: number;
  tasks_pending: number;
  tasks_completed: number;
}

export interface GradeTrendPoint {
  task_id: number;
  task_title: string;
  graded_at: string;
  grade_pct: number;
}

export interface StudyVsGradePoint {
  course_id: number;
  course_name: string;
  avg_weekly_study_hours: number;
  avg_grade_pct: number | null;
}

export interface EarlyStartVsGradePoint {
  task_id: number;
  task_title: string;
  course_id: number | null;
  course_name: string | null;
  days_before_due: number;
  grade_pct: number;
}

export interface WeeklyProductivityPoint {
  week_start: string;
  study_hours: number;
  tasks_completed: number;
}

// --- AI Recommendation System ---

export interface RecommendationItem {
  course_id: number | null;
  course_name: string | null;
  kind: "study_time" | "grade" | "assignment_start" | "productivity" | "general" | string;
  message: string;
  priority: 1 | 2 | 3;
}

export interface RecommendationRead {
  id: number | null;
  generated_at: string | null;
  period_start: string | null;
  period_end: string | null;
  items: RecommendationItem[];
  eligible: boolean;
  days_until_eligible: number | null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail ?? `Request failed: ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  getHealth: () => request<{ status: string; demo_mode: boolean }>("/health"),

  listIntegrations: () => request<Integration[]>("/integrations"),
  connectCanvas: (base_url: string, token: string) =>
    request<Integration>("/integrations/canvas", {
      method: "POST",
      body: JSON.stringify({ base_url, token }),
    }),
  disconnectIntegration: (id: number) =>
    request<void>(`/integrations/${id}`, { method: "DELETE" }),
  startGradescopeLogin: () =>
    request<Integration>("/integrations/gradescope/start-login", { method: "POST" }),
  startPrairieLearnLogin: () =>
    request<Integration>("/integrations/prairielearn/start-login", { method: "POST" }),

  listCourses: (includeArchived = false) =>
    request<Course[]>(`/courses?include_archived=${includeArchived}`),
  createCourse: (name: string, term?: string) =>
    request<Course>("/courses", { method: "POST", body: JSON.stringify({ name, term }) }),
  updateCourse: (id: number, body: { name?: string; term?: string; archived?: boolean }) =>
    request<Course>(`/courses/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteCourse: (id: number) => request<void>(`/courses/${id}`, { method: "DELETE" }),

  listTasks: (params?: { course_id?: number; status?: TaskStatus }) => {
    const qs = new URLSearchParams();
    if (params?.course_id != null) qs.set("course_id", String(params.course_id));
    if (params?.status) qs.set("status", params.status);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<Task[]>(`/tasks${suffix}`);
  },
  updateTaskStatus: (id: number, status: TaskStatus) =>
    request<Task>(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  startTask: (id: number) => request<Task>(`/tasks/${id}/start`, { method: "POST" }),

  syncNow: () => request<SyncResult>("/sync/run", { method: "POST" }),

  listReminders: (activeOnly = true) =>
    request<Reminder[]>(`/reminders?active_only=${activeOnly}`),
  updateReminderStatus: (id: number, status: ReminderStatus) =>
    request<Reminder>(`/reminders/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  dismissActiveReminders: () => request<number[]>("/reminders/dismiss-active", { method: "POST" }),

  getSettings: () => request<Settings>("/settings"),
  updateSettings: (reminder_lead_minutes: number[]) =>
    request<Settings>("/settings", { method: "PUT", body: JSON.stringify({ reminder_lead_minutes }) }),

  // Study Time Tracker
  startStudySession: (course_id: number) =>
    request<StudySession>("/study-sessions/start", { method: "POST", body: JSON.stringify({ course_id }) }),
  stopStudySession: (id: number) =>
    request<StudySession>(`/study-sessions/${id}/stop`, { method: "POST" }),
  activeStudySession: () => request<StudySession | null>("/study-sessions/active"),
  listStudySessions: (params?: { course_id?: number; since?: string }) => {
    const qs = new URLSearchParams();
    if (params?.course_id != null) qs.set("course_id", String(params.course_id));
    if (params?.since) qs.set("since", params.since);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return request<StudySession[]>(`/study-sessions${suffix}`);
  },

  // Analytics Dashboard
  courseOverview: () => request<CourseOverview[]>("/analytics/overview"),
  gradeTrends: (course_id?: number) =>
    request<GradeTrendPoint[]>(`/analytics/grade-trends${course_id != null ? `?course_id=${course_id}` : ""}`),
  studyVsGrade: () => request<StudyVsGradePoint[]>("/analytics/study-vs-grade"),
  earlyStartVsGrade: () => request<EarlyStartVsGradePoint[]>("/analytics/early-start-vs-grade"),
  weeklyProductivity: (weeks = 8) =>
    request<WeeklyProductivityPoint[]>(`/analytics/weekly-productivity?weeks=${weeks}`),

  // AI Recommendation System
  getRecommendations: () => request<RecommendationRead>("/recommendations"),
  generateRecommendations: () => request<RecommendationRead>("/recommendations/generate", { method: "POST" }),
};
