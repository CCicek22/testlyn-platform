/**
 * LogoBolt — alternative option C.
 *
 * Lightning bolt icon — speed / power reference.
 */

import { type SVGProps } from "react";

interface LogoProps extends SVGProps<SVGSVGElement> {
  wordmark?: boolean;
  size?: number;
}

export function LogoBolt({
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
        {/* Lightning bolt */}
        <path
          d="M16 4L8 16h7l-3 8 11-14h-7l3-6z"
          fill="white"
          strokeLinecap="round"
          strokeLinejoin="round"
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
