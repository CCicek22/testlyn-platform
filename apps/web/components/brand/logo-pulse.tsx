/**
 * LogoPulse — default Testlyn logo.
 *
 * A minimal wordmark with an indigo "pulse" waveform icon to the left.
 * The waveform references load testing + the primary brand color (#3730A3).
 */

import { type SVGProps } from "react";

interface LogoProps extends SVGProps<SVGSVGElement> {
  /** Show text wordmark alongside the icon (default true). */
  wordmark?: boolean;
  /** Icon size in px (default 28). */
  size?: number;
}

export function LogoPulse({
  wordmark = true,
  size = 28,
  className,
  ...props
}: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-2 ${className ?? ""}`}>
      {/* Waveform icon */}
      <svg
        width={size}
        height={size}
        viewBox="0 0 28 28"
        fill="none"
        aria-hidden="true"
        {...props}
      >
        {/* Background rounded square */}
        <rect width="28" height="28" rx="6" fill="#3730A3" />
        {/* Pulse waveform path */}
        <polyline
          points="3,14 7,14 9,8 11,20 13,10 15,18 17,12 19,16 21,14 25,14"
          stroke="white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>

      {wordmark && (
        <span
          className="font-semibold tracking-tight text-zinc-900 dark:text-zinc-100"
          style={{ fontSize: size * 0.75, lineHeight: 1 }}
        >
          Testlyn
        </span>
      )}
    </span>
  );
}

// Default export = chosen logo option
export default LogoPulse;
