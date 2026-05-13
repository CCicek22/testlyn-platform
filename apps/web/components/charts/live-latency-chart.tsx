"use client";

import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { LiveSample } from "@testlyn/shared";

interface ChartDatum {
  ts: string; // formatted label
  p95: number | null;
  errorRate: number | null;
  vus: number | null;
}

interface LiveLatencyChartProps {
  samples: LiveSample[];
  /** Max number of samples to keep in the rolling window (default 60). */
  windowSize?: number;
}

function formatTs(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
}

export function LiveLatencyChart({
  samples,
  windowSize = 60,
}: LiveLatencyChartProps) {
  const window = samples.slice(-windowSize);

  const data: ChartDatum[] = window.map((s) => ({
    ts: formatTs(s.ts),
    p95: s.p95,
    errorRate: s.error_rate !== null ? s.error_rate * 100 : null, // convert to %
    vus: s.vu_count,
  }));

  const isEmpty = data.length === 0;

  return (
    <div className="relative w-full">
      {isEmpty && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Waiting for samples…
          </p>
        </div>
      )}

      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart
          data={isEmpty ? placeholderData : data}
          margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="p95Fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3730A3" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#3730A3" stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid
            strokeDasharray="3 3"
            stroke={isEmpty ? "#27272A30" : "#27272A"}
            vertical={false}
          />

          <XAxis
            dataKey="ts"
            tick={{ fill: "#71717A", fontSize: 11, fontFamily: "JetBrains Mono" }}
            tickLine={false}
            axisLine={false}
          />

          {/* Left Y: p95 latency (ms) */}
          <YAxis
            yAxisId="latency"
            orientation="left"
            tick={{ fill: "#71717A", fontSize: 11, fontFamily: "JetBrains Mono" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `${v}ms`}
            width={60}
          />

          {/* Right Y: error rate (%) + VU count — shared scale for simplicity */}
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fill: "#71717A", fontSize: 11, fontFamily: "JetBrains Mono" }}
            tickLine={false}
            axisLine={false}
            width={50}
          />

          <Tooltip
            contentStyle={{
              backgroundColor: "#18181B",
              border: "1px solid #3F3F46",
              borderRadius: "8px",
              fontSize: 12,
              fontFamily: "JetBrains Mono",
            }}
            labelStyle={{ color: "#A1A1AA" }}
            formatter={(value: unknown, name: string) => {
              if (name === "p95") return [`${String(value)}ms`, "p95 latency"];
              if (name === "errorRate") return [`${String(value)}%`, "Error rate"];
              if (name === "vus") return [String(value), "VUs"];
              return [String(value), name];
            }}
          />

          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            formatter={(value) => {
              if (value === "p95") return "p95 latency (ms)";
              if (value === "errorRate") return "Error rate (%)";
              if (value === "vus") return "Virtual users";
              return value;
            }}
          />

          {/* p95 latency — area */}
          <Area
            yAxisId="latency"
            type="monotone"
            dataKey="p95"
            stroke="#3730A3"
            strokeWidth={2}
            fill="url(#p95Fill)"
            dot={false}
            activeDot={{ r: 4, fill: "#3730A3" }}
            connectNulls
          />

          {/* Error rate — line */}
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="errorRate"
            stroke="#EF4444"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3 }}
            connectNulls
          />

          {/* VU count — line */}
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="vus"
            stroke="#10B981"
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3 }}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Placeholder data shown when chart is empty ────────────────────────────
// Renders a flat ghost-chart so layout doesn't shift on first sample.
const placeholderData: ChartDatum[] = Array.from({ length: 30 }, (_, i) => ({
  ts: `00:${String(i).padStart(2, "0")}`,
  p95: null,
  errorRate: null,
  vus: null,
}));
