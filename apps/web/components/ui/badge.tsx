import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold backdrop-blur-xl transition-colors",
  {
    variants: {
      variant: {
        default:
          "border-primary/30 bg-primary/15 text-primary",
        success:
          "border-transparent bg-success/20 text-success dark:bg-success/10",
        warn:
          "border-transparent bg-warn/20 text-warn dark:bg-warn/10",
        alert:
          "border-transparent bg-alert/20 text-alert dark:bg-alert/10",
        outline: "text-zinc-700 dark:text-zinc-300",
        secondary:
          "border-zinc-800 bg-zinc-900/70 text-zinc-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}
