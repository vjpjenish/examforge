export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "examforge.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private mode) */
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`${API_URL}${path}`, { ...init, headers, body });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    } catch {
      /* non-JSON error */
    }
    if (res.status === 401 && typeof window !== "undefined") {
      setToken(null);
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const fileUrl = (path?: string | null) => (path ? `${API_URL}/files/${path}` : "");

// ---- types -------------------------------------------------------------------------------
export type Role = "student" | "admin";
export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
}
export interface Exam {
  id: number;
  name: string;
  description: string;
}
export type QuestionType = "mcq_single" | "mcq_multi" | "numerical" | "subjective";
export interface Option {
  label: string;
  text: string;
  image?: string | null;
}
export interface Figure {
  path: string;
  caption?: string | null;
}
export type NumericAnswer = { value?: number; tolerance?: number; raw?: string };
export type Answer = string[] | NumericAnswer | null;

export interface Job {
  id: number;
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  progress: number;
  error: string | null;
  stats: Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}
export type DocumentKind = "test_series" | "pyq" | "solutions";
export interface DocumentInfo {
  id: number;
  title: string;
  kind: DocumentKind;
  exam: Exam | null;
  institution: { id: number; name: string } | null;
  year: number | null;
  page_count: number;
  profile: Record<string, unknown> | null;
  /** Marking scheme chosen at upload; test series only. */
  duration_minutes: number | null;
  marks_correct: number | null;
  marks_incorrect: number | null;
  created_at: string;
  latest_job: Job | null;
  question_counts: Record<string, number>;
  solutions_for_id: number | null;
  solutions: { id: number; title: string; status: Job["status"] | null }[];
  test_id: number | null;
  answer_key_entries: number | null;
}
export interface Question {
  id: number;
  document_id: number | null;
  order_index: number;
  number: string;
  section: string;
  subject: string | null;
  topic: string | null;
  difficulty: string | null;
  year: number | null;
  type: QuestionType;
  text: string;
  options: Option[];
  answer: Answer;
  explanation: string | null;
  images: Figure[];
  source_pages: number[];
  confidence: number;
  issues: string[];
  review_status: "needs_review" | "approved" | "rejected";
  answer_source: string | null;
  edit_count: number;
}
export interface TestInfo {
  id: number;
  title: string;
  description: string;
  exam: Exam | null;
  duration_minutes: number;
  marks_correct: number;
  marks_incorrect: number;
  marks_unattempted: number;
  is_published: boolean;
  created_at: string;
  question_count: number;
  sections: string[];
  my_attempts: number;
  in_progress_attempt_id: number | null;
}
export interface AttemptQuestion {
  question_id: number;
  order: number;
  section: string;
  number: string;
  type: QuestionType;
  text: string;
  options: Option[];
  images: Figure[];
  response: string[] | string | null;
  marked_for_review: boolean;
  time_spent_seconds: number;
  visited: boolean;
}
export interface AttemptState {
  id: number;
  status: "in_progress" | "submitted";
  test: {
    id: number;
    title: string;
    duration_minutes: number;
    marks_correct: number;
    marks_incorrect: number;
    sections: string[];
  };
  server_now: string;
  deadline_at: string;
  questions: AttemptQuestion[];
}
export interface SectionStat {
  name: string;
  score: number;
  max_score: number;
  correct: number;
  incorrect: number;
  unattempted: number;
  negative_marks: number;
  time_seconds: number;
  total: number;
  accuracy: number;
}
export interface ReportQuestion {
  question_id: number;
  order: number;
  number: string;
  section: string;
  topic: string | null;
  type: QuestionType;
  text: string;
  options: Option[];
  images: Figure[];
  response: string[] | string | null;
  answer: Answer;
  explanation: string | null;
  status: "correct" | "incorrect" | "unattempted" | "ungraded";
  marks: number;
  time_seconds: number;
  visits: number;
  marked_for_review: boolean;
}
export interface Report {
  attempt_id: number;
  test_id: number;
  test_title: string;
  score: number;
  max_score: number;
  total_questions: number;
  attempted: number;
  correct: number;
  incorrect: number;
  unattempted: number;
  negative_marks: number;
  accuracy: number;
  time_seconds: number;
  duration_seconds: number;
  started_at: string;
  submitted_at: string | null;
  sections: SectionStat[];
  topics: { name: string; correct: number; attempted: number; total: number; accuracy: number }[];
  questions: ReportQuestion[];
  rank: number;
  total_attempts: number;
  percentile: number;
}
export interface PyqItem {
  id: number;
  exam_id: number | null;
  year: number | null;
  number: string;
  section: string;
  subject: string | null;
  topic: string | null;
  difficulty: string | null;
  type: QuestionType;
  text: string;
  options: Option[];
  images: Figure[];
  answer: Answer;
  explanation: string | null;
  progress: {
    solved: boolean;
    is_correct: boolean | null;
    attempts: number;
    bookmarked: boolean;
    last_response: string[] | string | null;
  } | null;
}
export interface PyqStats {
  total: number;
  solved: number;
  correct: number;
  accuracy: number;
  by_subject: { subject: string; total: number; solved: number; correct: number }[];
}
export interface ContinueTest {
  attempt_id: number;
  test_id: number;
  test_title: string;
  sections: string[];
  question_count: number;
  answered: number;
  seconds_left: number;
  expired: boolean;
  started_at: string;
}
export interface Dashboard {
  user: { name: string };
  totals: {
    tests_taken: number;
    avg_percent: number;
    best_percent: number;
    accuracy: number;
    hours_practiced: number;
    tests_this_week: number;
    hours_this_week: number;
    avg_delta_30d: number | null;
  };
  streak: { current: number; best: number };
  activity: { start: string; days: { date: string; tests: number; minutes: number }[] };
  continue_test: ContinueTest | null;
  trend: {
    attempt_id: number;
    test_title: string;
    date: string;
    score: number;
    max_score: number;
    percent: number;
    accuracy: number;
    sections: string[];
  }[];
  sections: { name: string; correct: number; incorrect: number; unattempted: number; time_seconds: number; accuracy: number }[];
  weak_areas: string[];
  recent: Dashboard["trend"];
  pyq: PyqStats;
}
export interface Mistake {
  id: number;
  question_id: number;
  attempt_id: number;
  test_id: number;
  test_title: string;
  attempted_at: string | null;
  section: string;
  subject: string | null;
  topic: string | null;
  number: string;
  type: QuestionType;
  text: string;
  options: Option[];
  images: Figure[];
  response: string[] | string | null;
  answer: Answer;
  explanation: string | null;
  marks_awarded: number;
  time_spent_seconds: number;
}
export interface MistakeBook {
  total: number;
  items: Mistake[];
  tests: { id: number; title: string }[];
  sections: string[];
}
export interface ExamTarget {
  id: number;
  name: string;
  /** YYYY-MM-DD; the countdown runs to local midnight of this day. */
  target_date: string;
}

export interface AttemptSummary {
  id: number;
  test_id: number;
  test_title: string;
  status: string;
  score: number | null;
  max_score: number | null;
  accuracy: number | null;
  started_at: string;
  submitted_at: string | null;
}
