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
} as const;
