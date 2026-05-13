/**
 * @testlyn/shared — hand-authored TypeScript types.
 * TODO: regenerate from OpenAPI spec once Stream C (API backend) publishes it.
 */

// ─── Enums ───────────────────────────────────────────────────────────────────

export type OrgPlan = "free" | "hobby" | "pro" | "business" | "enterprise";

export type OrgMemberRole = "owner" | "admin" | "member";

export type RunState =
  | "queued"
  | "running"
  | "done"
  | "error"
  | "cancelled";

export type TestProduct = "load" | "functional" | "a11y"; // Phase 1: load. Phase 2+: functional, a11y

// ─── Core entities ────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  name: string;
  avatar_url: string | null;
  firebase_uid: string | null;
  created_at: string; // ISO-8601
  updated_at: string;
}

export interface Org {
  id: string;
  name: string;
  slug: string;
  plan: OrgPlan;
  stripe_customer_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface OrgMember {
  org_id: string;
  user_id: string;
  role: OrgMemberRole;
  user: User;
}

export interface Project {
  id: string;
  org_id: string;
  name: string;
  slug: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

export interface TestConfig {
  script: string;
  vus: number;
  /** Duration in seconds */
  duration: number;
  thresholds: Record<string, string[]>;
}

export interface Test {
  id: string;
  project_id: string;
  name: string;
  product: TestProduct;
  config: TestConfig;
  created_by: string; // user id
  created_at: string;
  updated_at: string;
}

export interface TestRun {
  id: string;
  test_id: string;
  state: RunState;
  config: TestConfig;
  runner_id: string | null;
  region: string;
  started_at: string | null;
  finished_at: string | null;
  summary_uri: string | null;
  error_reason: string | null;
  product: TestProduct;
  triggered_by: string; // user id
  created_at: string;
  updated_at: string;
}

// ─── API request / response shapes ───────────────────────────────────────────

export interface MeResponse {
  user: User;
  memberships: Array<{ org: Org; role: OrgMemberRole }>;
}

export interface CreateOrgRequest {
  name: string;
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
}

export interface CreateTestRequest {
  name: string;
  product: TestProduct;
  config: TestConfig;
}

export interface PatchTestRequest {
  name?: string;
  config?: Partial<TestConfig>;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
}

// ─── SSE event payloads ───────────────────────────────────────────────────────

/**
 * One 1-second aggregated sample emitted by /v1/runs/:id/stream.
 * Mirrors the BigQuery `samples_1s` row for metric_name='http_req_duration'.
 */
export interface LiveSample {
  /** ISO-8601 timestamp of the 1s window start */
  ts: string;
  run_id: string;
  metric_name: string;
  /** p95 latency in ms */
  p95: number;
  /** p50 latency in ms */
  p50: number;
  /** Error rate 0–1 */
  error_rate: number;
  vu_count: number;
}

export interface RunStateEvent {
  run_id: string;
  state: RunState;
  timestamp: string;
}

export type SSEEventPayload =
  | { type: "sample"; data: LiveSample }
  | { type: "state"; data: RunStateEvent }
  | { type: "done" };

// ─── Phase 2: Target entity ───────────────────────────────────────────────────

export type TargetKind = "web" | "mobile" | "api";

export interface Target {
  id: string;
  org_id: string;
  name: string;
  kind: TargetKind;
  base_url: string;
  auth_config: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

// ─── Phase 2: Runner registry ─────────────────────────────────────────────────

export interface RunnerRegistryEntry {
  name: string; // PK
  product: TestProduct;
  image_uri: string;
  cpu: string;
  memory_mb: number;
  capabilities: Record<string, unknown>;
}

// ─── Phase 2: Functional run shape ───────────────────────────────────────────

export interface FunctionalRunSummary {
  run_id: string;
  tests_passed: number;
  tests_failed: number;
  tests_healed: number;
  duration_ms: number;
}

// ─── Phase 2: A11y run shape ──────────────────────────────────────────────────

export interface A11yRunSummary {
  run_id: string;
  urls_scanned: number;
  violations_critical: number;
  violations_serious: number;
  violations_moderate: number;
  violations_minor: number;
}
