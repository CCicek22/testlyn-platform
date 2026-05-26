import { ImageResponse } from "next/og";

export const runtime = "edge";

export const alt = "Testlyn — Load testing that lives where your code does.";
// Twitter summary_large_image card
export const size = { width: 1200, height: 628 };
export const contentType = "image/png";

export default function TwitterImage() {
  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          width: "100%",
          height: "100%",
          background: "#05090B",
          padding: "72px",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "14px", marginBottom: "36px" }}>
          <svg width="44" height="44" viewBox="0 0 28 28" fill="none">
            <rect width="28" height="28" rx="6" fill="#18F2C3" />
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
              fontSize: "32px",
              fontWeight: "700",
              color: "#FAFAFA",
              letterSpacing: "-0.02em",
            }}
          >
            Testlyn
          </span>
        </div>

        <div
          style={{
            fontSize: "52px",
            fontWeight: "800",
            color: "#FAFAFA",
            lineHeight: "1.1",
            letterSpacing: "-0.03em",
            maxWidth: "920px",
            marginBottom: "20px",
          }}
        >
          Load testing that lives{" "}
          <span style={{ color: "#18F2C3" }}>where your code does.</span>
        </div>

        <div
          style={{
            fontSize: "22px",
            color: "#71717A",
            maxWidth: "760px",
          }}
        >
          k6 + BigQuery streaming + AI digests — no AGPL surface.
        </div>
      </div>
    ),
    { ...size }
  );
}
