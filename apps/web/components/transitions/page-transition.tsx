"use client";

import { motion, useReducedMotion } from "framer-motion";
import { pageVariants } from "@/lib/motion";

interface PageTransitionProps {
  children: React.ReactNode;
  /** key must change between routes for AnimatePresence to detect exits */
  className?: string;
}

/**
 * Wraps a page/view in a Framer Motion fade+slide transition.
 * Respects prefers-reduced-motion automatically via useReducedMotion().
 */
export function PageTransition({ children, className }: PageTransitionProps) {
  const reduced = useReducedMotion();

  if (reduced) {
    return <div className={className}>{children}</div>;
  }

  return (
    <motion.div
      className={className}
      initial="hidden"
      animate="visible"
      exit="exit"
      variants={pageVariants}
    >
      {children}
    </motion.div>
  );
}
