"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api-client";
import type {
  WebhookEndpoint,
  WebhookDelivery,
  CreateWebhookEndpointRequest,
} from "@/lib/api-client";
import { useAuth } from "@/components/auth/auth-provider";
import type { MeResponse } from "@testlyn/shared";

// ─── Status chip ─────────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-emerald-500/15 text-emerald-400",
  pending: "bg-zinc-500/15 text-zinc-400",
  delivering: "bg-primary/15 text-primary",
  failed: "bg-amber-500/15 text-amber-400",
  abandoned: "bg-red-500/15 text-red-400",
};

function StatusChip({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? "bg-zinc-500/15 text-zinc-400";
  return (
    <span className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

// ─── Create endpoint modal ────────────────────────────────────────────────────

const KNOWN_EVENTS = [
  "test.completed",
  "test.failed",
  "threshold.breached",
  "scan.findings_published",
  "subscription.updated",
  "member.invited",
] as const;

function CreateEndpointModal({
  orgId,
  onClose,
}: {
  orgId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [selectedEvents, setSelectedEvents] = useState<string[]>([]);

  const create = useMutation({
    mutationFn: (body: CreateWebhookEndpointRequest) =>
      api.webhooks.createEndpoint(orgId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["webhook-endpoints", orgId] });
      onClose();
    },
  });

  function toggle(event: string) {
    setSelectedEvents((prev) =>
      prev.includes(event) ? prev.filter((e) => e !== event) : [...prev, event]
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-full max-w-md rounded-lg border border-zinc-800 bg-zinc-950 p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-zinc-100">
          New Webhook Endpoint
        </h2>

        <label className="mb-1 block text-sm font-medium text-zinc-300">
          URL
        </label>
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://your-server.com/webhook"
          className="mb-4 w-full rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-primary focus:outline-none"
        />

        <p className="mb-2 text-sm font-medium text-zinc-300">Events</p>
        <div className="mb-4 grid grid-cols-2 gap-2">
          {KNOWN_EVENTS.map((ev) => (
            <label key={ev} className="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer">
              <input
                type="checkbox"
                checked={selectedEvents.includes(ev)}
                onChange={() => toggle(ev)}
                className="accent-primary"
              />
              {ev}
            </label>
          ))}
        </div>

        {create.error && (
          <p className="mb-3 text-xs text-red-400">
            {String((create.error as Error).message)}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
          >
            Cancel
          </button>
          <button
            onClick={() => create.mutate({ url, events: selectedEvents })}
            disabled={!url || selectedEvents.length === 0 || create.isPending}
            className="rounded bg-primary px-4 py-2 text-sm font-medium text-[#031111] hover:bg-primary-100 disabled:opacity-40"
          >
            {create.isPending ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Delivery log table ───────────────────────────────────────────────────────

function DeliveryLog({ endpointId }: { endpointId: string }) {
  const qc = useQueryClient();

  const { data: deliveries = [], isLoading } = useQuery<WebhookDelivery[]>({
    queryKey: ["webhook-deliveries", endpointId],
    queryFn: () => api.webhooks.listDeliveries(endpointId),
    refetchInterval: 10_000,
  });

  const replay = useMutation({
    mutationFn: (deliveryId: string) => api.webhooks.replayDelivery(deliveryId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["webhook-deliveries", endpointId] });
    },
  });

  if (isLoading) {
    return <p className="py-4 text-sm text-zinc-500">Loading deliveries…</p>;
  }

  if (deliveries.length === 0) {
    return <p className="py-4 text-sm text-zinc-500">No deliveries yet.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm text-zinc-300">
        <thead>
          <tr className="border-b border-zinc-800 text-xs text-zinc-500 uppercase tracking-wider">
            <th className="py-2 pr-4 text-left">Event</th>
            <th className="py-2 pr-4 text-left">Status</th>
            <th className="py-2 pr-4 text-left">Attempts</th>
            <th className="py-2 pr-4 text-left">Created</th>
            <th className="py-2 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          {deliveries.map((d) => (
            <tr key={d.id} className="border-b border-zinc-800/50">
              <td className="py-2 pr-4 font-mono text-xs text-zinc-300">
                {d.event_type}
              </td>
              <td className="py-2 pr-4">
                <StatusChip status={d.status} />
              </td>
              <td className="py-2 pr-4 tabular-nums">{d.attempts}</td>
              <td className="py-2 pr-4 tabular-nums text-xs text-zinc-500">
                {new Date(d.created_at).toLocaleString()}
              </td>
              <td className="py-2 text-right">
                <button
                  onClick={() => replay.mutate(d.id)}
                  disabled={replay.isPending}
                  className="rounded px-2 py-1 text-xs text-primary hover:text-primary disabled:opacity-40"
                >
                  Replay
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Endpoint card ────────────────────────────────────────────────────────────

function EndpointCard({
  endpoint,
  orgId,
}: {
  endpoint: WebhookEndpoint;
  orgId: string;
}) {
  const qc = useQueryClient();
  const [showLog, setShowLog] = useState(false);

  const remove = useMutation({
    mutationFn: () => api.webhooks.deleteEndpoint(endpoint.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["webhook-endpoints", orgId] });
    },
  });

  const toggle = useMutation({
    mutationFn: () =>
      api.webhooks.patchEndpoint(endpoint.id, { active: !endpoint.active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["webhook-endpoints", orgId] });
    },
  });

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-sm text-zinc-100">{endpoint.url}</p>
          <p className="mt-1 text-xs text-zinc-500">
            {endpoint.events.join(", ") || "no events"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusChip status={endpoint.active ? "active" : "inactive"} />
          <button
            onClick={() => toggle.mutate()}
            disabled={toggle.isPending}
            className="rounded px-2 py-1 text-xs text-zinc-400 hover:text-zinc-200 disabled:opacity-40"
          >
            {endpoint.active ? "Disable" : "Enable"}
          </button>
          <button
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
            className="rounded px-2 py-1 text-xs text-red-400 hover:text-red-300 disabled:opacity-40"
          >
            Delete
          </button>
        </div>
      </div>

      <button
        onClick={() => setShowLog((v) => !v)}
        className="mt-3 text-xs text-primary hover:text-primary"
      >
        {showLog ? "Hide delivery log" : "Show delivery log"}
      </button>

      {showLog && (
        <div className="mt-3">
          <DeliveryLog endpointId={endpoint.id} />
        </div>
      )}
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function WebhooksPage() {
  const { user } = useAuth();
  const [showModal, setShowModal] = useState(false);

  // Resolve org id from auth context via /v1/me — never hardcode a UUID.
  const { data: me } = useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => api.me(),
    enabled: user != null,
    staleTime: 5 * 60_000,
  });

  const orgId = me?.memberships?.[0]?.org_id ?? null;

  const { data: endpoints = [], isLoading } = useQuery<WebhookEndpoint[]>({
    queryKey: ["webhook-endpoints", orgId],
    queryFn: () => api.webhooks.listEndpoints(orgId!),
    enabled: orgId != null,
  });

  if (orgId == null) {
    return (
      <div className="flex flex-col min-h-full">
        <div
          className="border-b border-zinc-800 px-6 py-4"
          style={{ borderTopColor: "#18F2C3", borderTopWidth: 3 }}
        >
          <h1 className="text-lg font-bold tracking-tight text-zinc-100">
            Webhooks
          </h1>
        </div>
        <div className="px-6 py-6">
          <p className="text-sm text-zinc-500">
            {me == null ? "Loading organization…" : "No organization available."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-full">
      {/* Page header */}
      <div
        className="border-b border-zinc-800 px-6 py-4"
        style={{ borderTopColor: "#18F2C3", borderTopWidth: 3 }}
      >
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold tracking-tight text-zinc-100">
              Webhooks
            </h1>
            <p className="text-sm text-zinc-500">
              Receive real-time events when tests complete, thresholds breach,
              and more.
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="rounded bg-primary px-4 py-2 text-sm font-medium text-[#031111] hover:bg-primary-100"
          >
            Add endpoint
          </button>
        </div>
      </div>

      {/* Endpoint list */}
      <div className="flex-1 px-6 py-6">
        {isLoading && (
          <p className="text-sm text-zinc-500">Loading endpoints…</p>
        )}

        {!isLoading && endpoints.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <p className="text-sm text-zinc-500">No webhook endpoints yet.</p>
            <button
              onClick={() => setShowModal(true)}
              className="mt-3 text-sm text-primary hover:text-primary"
            >
              Add your first endpoint →
            </button>
          </div>
        )}

        <div className="flex flex-col gap-3">
          {endpoints.map((ep) => (
            <EndpointCard key={ep.id} endpoint={ep} orgId={orgId} />
          ))}
        </div>
      </div>

      {showModal && (
        <CreateEndpointModal orgId={orgId} onClose={() => setShowModal(false)} />
      )}
    </div>
  );
}
