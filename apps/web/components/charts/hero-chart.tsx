/**
 * HeroChart — a static, decorative chart for the marketing landing page.
 * No real data. No stock photos. SVG + gradient only.
 */

export function HeroChart() {
  // Simulated p95 latency curve: starts around 80ms, peaks at 340ms under load, settles
  const points = [
    { x: 0, y: 80 },
    { x: 60, y: 82 },
    { x: 120, y: 90 },
    { x: 180, y: 95 },
    { x: 240, y: 130 },
    { x: 300, y: 210 },
    { x: 360, y: 340 },
    { x: 420, y: 310 },
    { x: 480, y: 260 },
    { x: 540, y: 190 },
    { x: 600, y: 145 },
    { x: 660, y: 120 },
    { x: 720, y: 112 },
    { x: 780, y: 108 },
    { x: 840, y: 105 },
    { x: 900, y: 103 },
  ];

  // Error rate (right axis 0-100, scaled for display)
  const errorPoints = [
    { x: 0, y: 2 },
    { x: 60, y: 2 },
    { x: 120, y: 3 },
    { x: 180, y: 3 },
    { x: 240, y: 5 },
    { x: 300, y: 12 },
    { x: 360, y: 28 },
    { x: 420, y: 22 },
    { x: 480, y: 14 },
    { x: 540, y: 8 },
    { x: 600, y: 4 },
    { x: 660, y: 3 },
    { x: 720, y: 2 },
    { x: 780, y: 2 },
    { x: 840, y: 2 },
    { x: 900, y: 1 },
  ];

  const W = 900;
  const H = 300;
  // Map latency (0-400ms) → y pixel (inverted)
  const scaleY = (v: number) => H - (v / 400) * H;
  // Map error (0-30) → y pixel (inverted), shifted down for overlay
  const scaleEY = (v: number) => H - (v / 30) * (H * 0.4) - H * 0.1;

  const toPath = (pts: { x: number; y: number }[], scale: (v: number) => number) =>
    pts
      .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${scale(p.y)}`)
      .join(" ");

  const areaPath =
    toPath(points, scaleY) +
    ` L ${points[points.length - 1]!.x} ${H} L ${points[0]!.x} ${H} Z`;

  const latencyPath = toPath(points, scaleY);
  const errorPath = toPath(errorPoints, scaleEY);

  return (
    <div className="relative w-full overflow-hidden rounded-xl border border-zinc-800 bg-[#0D0D0F] shadow-2xl">
      {/* Chart header bar */}
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-2">
        <span className="font-mono text-xs text-zinc-500">
          run · production-stress-v3 · 500 VUs · 10min
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2 w-2 animate-pulse rounded-full bg-success" />
          <span className="font-mono text-xs text-success">running</span>
        </span>
      </div>

      {/* Axis labels */}
      <div className="relative px-2 pt-2">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          preserveAspectRatio="none"
          className="w-full"
          style={{ height: 220 }}
          aria-label="Live load test chart showing p95 latency over time"
          role="img"
        >
          <defs>
            <linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3730A3" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#3730A3" stopOpacity="0" />
            </linearGradient>
            {/* Subtle grid */}
            <pattern id="grid" width="90" height="60" patternUnits="userSpaceOnUse">
              <path
                d={`M ${W} 0 L 0 0 0 ${H}`}
                fill="none"
                stroke="#27272A"
                strokeWidth="0.5"
              />
            </pattern>
          </defs>

          <rect width={W} height={H} fill="url(#grid)" />

          {/* Area fill */}
          <path d={areaPath} fill="url(#heroFill)" />

          {/* p95 latency line */}
          <path
            d={latencyPath}
            fill="none"
            stroke="#3730A3"
            strokeWidth="2.5"
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* Error rate line */}
          <path
            d={errorPath}
            fill="none"
            stroke="#EF4444"
            strokeWidth="1.5"
            strokeLinejoin="round"
            strokeLinecap="round"
            strokeDasharray="4 3"
          />

          {/* Annotations */}
          {/* Peak marker */}
          <circle cx="360" cy={scaleY(340)} r="5" fill="#3730A3" opacity="0.9" />
          <line
            x1="360"
            y1={scaleY(340) - 6}
            x2="360"
            y2={scaleY(340) - 40}
            stroke="#3730A3"
            strokeWidth="1"
            strokeDasharray="3 2"
          />
          <rect
            x="250"
            y={scaleY(340) - 58}
            width="220"
            height="20"
            rx="4"
            fill="#1E1B4B"
            opacity="0.9"
          />
          <text
            x="360"
            y={scaleY(340) - 44}
            textAnchor="middle"
            fill="#A5B4FC"
            fontSize="10"
            fontFamily="JetBrains Mono, monospace"
          >
            peak p95: 340ms @ 500 VUs
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-6 border-t border-zinc-800 px-4 py-2">
        <span className="flex items-center gap-1.5 font-mono text-xs text-zinc-400">
          <span
            className="inline-block h-0.5 w-4"
            style={{ backgroundColor: "#3730A3" }}
          />
          p95 latency
        </span>
        <span className="flex items-center gap-1.5 font-mono text-xs text-zinc-400">
          <span
            className="inline-block h-0.5 w-4"
            style={{
              backgroundColor: "#EF4444",
              borderTop: "1.5px dashed #EF4444",
            }}
          />
          error rate
        </span>
        <span className="ml-auto font-mono text-xs text-zinc-600">
          {/* TODO: real data */}
          p50: 112ms · p99: 402ms · errors: 0.4%
        </span>
      </div>
    </div>
  );
}
