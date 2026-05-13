/**
 * Typed fetch wrapper.
 * Injects the Firebase IdP token (or dev-bypass token) into every request.
 * Builds on @testlyn/shared types.
 */

import { getIdToken } from "@/lib/firebase";

const BASE_URL =
  process.env["NEXT_PUBLIC_API_BASE_URL"] ?? "http://localhost:8080";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown
  ) {
    super(`API error ${status}`);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const token = await getIdToken();

  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    throw new ApiError(res.status, body);
  }

  // 204 No Content
  if (res.status === 204) return undefined as T;

  return res.json() as Promise<T>;
}

// ─── Raw streaming helper (returns Response, not parsed JSON) ────────────────

async function requestRaw(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await getIdToken();

  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    throw new ApiError(res.status, body);
  }

  return res;
}

// ─── Typed endpoint helpers ─────────────────────────────────────────────────

import type {
  MeResponse,
  Org,
  Project,
  Test,
  TestRun,
  CreateOrgRequest,
  CreateProjectRequest,
  CreateTestRequest,
  PatchTestRequest,
} from "@testlyn/shared";

// ─── Audit types (inline until shared-types is regenerated from OpenAPI) ─────

export interface AuditLogEntry {
  id: string;
  org_id: string;
  actor_user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
  user_agent: string | null;
  created_at: string;
}

export interface AuditLogPage {
  items: AuditLogEntry[];
  cursor: string | null;
}

export interface AuditListParams {
  limit?: number;
  cursor?: string;
  action?: string;
  actor_id?: string;
  from_dt?: string;
  to_dt?: string;
}

// ─── Webhook types (inline until shared-types is regenerated from OpenAPI) ───

export interface WebhookEndpoint {
  id: string;
  org_id: string;
  url: string;
  events: string[];
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WebhookDelivery {
  id: string;
  endpoint_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  status: string;
  attempts: number;
  last_error: string | null;
  next_retry_at: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface CreateWebhookEndpointRequest {
  url: string;
  events: string[];
  active?: boolean;
}

export interface PatchWebhookEndpointRequest {
  url?: string;
  events?: string[];
  active?: boolean;
}

export const api = {
  me: () => request<MeResponse>("/v1/me"),

  orgs: {
    create: (body: CreateOrgRequest) =>
      request<Org>("/v1/orgs", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    get: (id: string) => request<Org>(`/v1/orgs/${id}`),
    projects: (id: string) =>
      request<Project[]>(`/v1/orgs/${id}/projects`),
    createProject: (id: string, body: CreateProjectRequest) =>
      request<Project>(`/v1/orgs/${id}/projects`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },

  projects: {
    tests: (id: string) => request<Test[]>(`/v1/projects/${id}/tests`),
    createTest: (id: string, body: CreateTestRequest) =>
      request<Test>(`/v1/projects/${id}/tests`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
  },

  tests: {
    get: (id: string) => request<Test>(`/v1/tests/${id}`),
    patch: (id: string, body: PatchTestRequest) =>
      request<Test>(`/v1/tests/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    startRun: (id: string) =>
      request<TestRun>(`/v1/tests/${id}/runs`, { method: "POST", body: "{}" }),
  },

  runs: {
    get: (id: string) => request<TestRun>(`/v1/runs/${id}`),
    list: (product: string, limit = 50) =>
      request<TestRun[]>(`/v1/runs?product=${product}&limit=${limit}`),
    summary: (id: string, product: string) =>
      request<unknown>(`/v1/runs/${id}/summary?product=${product}`),
    cancel: (id: string) =>
      request<void>(`/v1/runs/${id}/cancel`, { method: "POST" }),
    streamUrl: (id: string) => `${BASE_URL}/v1/runs/${id}/stream`,
  },

  webhooks: {
    listEndpoints: (orgId: string) =>
      request<WebhookEndpoint[]>(`/v1/webhooks-admin/orgs/${orgId}/endpoints`),
    createEndpoint: (orgId: string, body: CreateWebhookEndpointRequest) =>
      request<WebhookEndpoint>(`/v1/webhooks-admin/orgs/${orgId}/endpoints`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    getEndpoint: (id: string) =>
      request<WebhookEndpoint>(`/v1/webhooks-admin/endpoints/${id}`),
    patchEndpoint: (id: string, body: PatchWebhookEndpointRequest) =>
      request<WebhookEndpoint>(`/v1/webhooks-admin/endpoints/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    deleteEndpoint: (id: string) =>
      request<void>(`/v1/webhooks-admin/endpoints/${id}`, { method: "DELETE" }),

    listDeliveries: (endpointId: string, status?: string, limit = 50) => {
      const params = new URLSearchParams({ endpoint_id: endpointId, limit: String(limit) });
      if (status) params.set("status", status);
      return request<WebhookDelivery[]>(`/v1/webhooks-admin/deliveries?${params}`);
    },
    replayDelivery: (deliveryId: string) =>
      request<WebhookDelivery>(
        `/v1/webhooks-admin/deliveries/${deliveryId}/replay`,
        { method: "POST" }
      ),
  },

  audit: {
    list: (orgId: string, params: AuditListParams = {}) => {
      const p = new URLSearchParams();
      if (params.limit) p.set("limit", String(params.limit));
      if (params.cursor) p.set("cursor", params.cursor);
      if (params.action) p.set("action", params.action);
      if (params.actor_id) p.set("actor_id", params.actor_id);
      if (params.from_dt) p.set("from_dt", params.from_dt);
      if (params.to_dt) p.set("to_dt", params.to_dt);
      const qs = p.toString();
      return request<AuditLogPage>(
        `/v1/orgs/${orgId}/audit-log${qs ? `?${qs}` : ""}`
      );
    },

    exportCsv: async (orgId: string, params: Omit<AuditListParams, "cursor"> = {}) => {
      const p = new URLSearchParams();
      if (params.limit) p.set("limit", String(params.limit));
      if (params.action) p.set("action", params.action);
      if (params.actor_id) p.set("actor_id", params.actor_id);
      if (params.from_dt) p.set("from_dt", params.from_dt);
      if (params.to_dt) p.set("to_dt", params.to_dt);
      const qs = p.toString();
      return requestRaw(
        `/v1/orgs/${orgId}/audit-log.csv${qs ? `?${qs}` : ""}`
      );
    },

    exportJson: async (orgId: string, params: Omit<AuditListParams, "cursor"> = {}) => {
      const p = new URLSearchParams();
      if (params.limit) p.set("limit", String(params.limit));
      if (params.action) p.set("action", params.action);
      if (params.actor_id) p.set("actor_id", params.actor_id);
      if (params.from_dt) p.set("from_dt", params.from_dt);
      if (params.to_dt) p.set("to_dt", params.to_dt);
      const qs = p.toString();
      return requestRaw(
        `/v1/orgs/${orgId}/audit-log.json${qs ? `?${qs}` : ""}`
      );
    },
  },

  insights: {
    latest: <T>(orgId: string) =>
      request<T>(`/v1/orgs/${orgId}/insights/latest`),
    snapshots: <T>(orgId: string, limit = 24) =>
      request<T[]>(`/v1/orgs/${orgId}/insights/snapshots?limit=${limit}`),
  },

  syntheticData: {
    getJob: <T>(jobId: string) =>
      request<T>(`/v1/products/synthetic-data/jobs/${jobId}`),
    generate: (body: Record<string, unknown>) =>
      request<{ job_id: string; status: string }>(
        "/v1/products/synthetic-data/generate",
        { method: "POST", body: JSON.stringify(body) }
      ),
  },

  apiContract: {
    getScan: <T>(scanId: string) =>
      request<T>(`/v1/products/api-contract/scans/${scanId}`),
    scan: (body: Record<string, unknown>) =>
      request<{ scan_id: string; status: string }>(
        "/v1/products/api-contract/scan",
        { method: "POST", body: JSON.stringify(body) }
      ),
  },

  security: {
    getScan: <T>(scanId: string) =>
      request<T>(`/v1/products/security/scans/${scanId}`),
    scan: (body: Record<string, unknown>) =>
      request<{ scan_id: string; status: string }>(
        "/v1/products/security/scan",
        { method: "POST", body: JSON.stringify(body) }
      ),
  },
} as const;
