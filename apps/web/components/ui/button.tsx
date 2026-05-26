import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-dark disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "trace-glow bg-primary text-[#031111] shadow-lg shadow-primary/10 hover:bg-primary-100 hover:-translate-y-0.5",
        destructive:
          "bg-alert text-white shadow-lg shadow-alert/10 hover:bg-alert/90 hover:-translate-y-0.5",
        outline:
          "border border-zinc-300 bg-white/5 backdrop-blur-xl hover:border-primary/40 hover:bg-primary/10",
        secondary:
          "border border-zinc-800 bg-zinc-900/70 text-zinc-100 backdrop-blur-xl hover:border-primary/30 hover:bg-zinc-800",
        ghost:
          "hover:bg-primary/10 dark:text-zinc-100",
        link:
          "text-primary underline-offset-4 hover:underline dark:text-primary-300",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-7 rounded-md px-3 text-xs",
        lg: "h-11 rounded-md px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { buttonVariants };
