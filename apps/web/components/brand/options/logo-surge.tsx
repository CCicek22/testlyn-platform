/**
 * LogoSurge — alternative option B.
 *
 * A bold upward-arrow / chevron icon suggesting performance surge.
 */

import { type SVGProps } from "react";

interface LogoProps extends SVGProps<SVGSVGElement> {
  wordmark?: boolean;
  size?: number;
}

export function LogoSurge({
  wordmark = true,
  size = 28,
  className,
  ...props
}: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-2 ${className ?? ""}`}>
      <svg
        width={size}
        height={size}
        viewBox="0 0 28 28"
        fill="none"
        aria-hidden="true"
        {...props}
      >
        <rect width="28" height="28" rx="6" fill="#3730A3" />
        {/* Double chevron up */}
        <polyline
          points="7,18 14,10 21,18"
          stroke="white"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <polyline
          points="7,23 14,15 21,23"
          stroke="rgba(255,255,255,0.4)"
          strokeWidth="2.5"
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
