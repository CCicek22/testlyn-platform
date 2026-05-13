import { ImageResponse } from "next/og";

export const runtime = "edge";

export const alt = "Testlyn — Load testing that lives where your code does.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OgImage() {
  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          width: "100%",
          height: "100%",
          background: "#0A0A0B",
          padding: "80px",
          fontFamily: "sans-serif",
        }}
      >
        {/* Logo mark */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "40px" }}>
          <svg
            width="48"
            height="48"
            viewBox="0 0 28 28"
            fill="none"
          >
            <rect width="28" height="28" rx="6" fill="#3730A3" />
            <polyline
              points="3,14 7,14 9,8 11,20 13,10 15,18 17,12 19,16 21,14 25,14"
              stroke="white"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span
            style={{
              fontSize: "36px",
              fontWeight: "700",
              color: "#FAFAFA",
              letterSpacing: "-0.02em",
            }}
          >
            Testlyn
          </span>
        </div>

        {/* Headline */}
        <div
          style={{
            fontSize: "56px",
            fontWeight: "800",
            color: "#FAFAFA",
            lineHeight: "1.1",
            letterSpacing: "-0.03em",
            maxWidth: "900px",
            marginBottom: "24px",
          }}
        >
          Load testing that lives{" "}
          <span style={{ color: "#6366F1" }}>where your code does.</span>
        </div>

        {/* Subhead */}
        <div
          style={{
            fontSize: "24px",
            color: "#71717A",
            maxWidth: "800px",
            lineHeight: "1.4",
          }}
        >
          k6 + BigQuery streaming + AI digests — no AGPL surface.
        </div>

        {/* Bottom bar */}
        <div
          style={{
            position: "absolute",
            bottom: "48px",
            left: "80px",
            right: "80px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span style={{ fontSize: "18px", color: "#52525B" }}>testlyn.io</span>
          <span
            style={{
              fontSize: "14px",
              color: "#3730A3",
              background: "rgba(55,48,163,0.15)",
              padding: "6px 14px",
              borderRadius: "100px",
              border: "1px solid rgba(55,48,163,0.3)",
            }}
          >
            Phase 1 — Load Testing
          </span>
        </div>
      </div>
    ),
    { ...size }
  );
}
