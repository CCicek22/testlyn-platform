/**
 * Shared Framer Motion variants for Testlyn.
 * Import these to keep transitions consistent across components.
 */

import type { Variants } from "framer-motion";

/** Standard page entrance — fade + slide up. */
export const pageVariants: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.18, ease: [0.25, 0.46, 0.45, 0.94] },
  },
  exit: {
    opacity: 0,
    y: -4,
    transition: { duration: 0.12, ease: "easeIn" },
  },
};

/** Command palette overlay fade. */
export const overlayVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { duration: 0.12 } },
  exit: { opacity: 0, transition: { duration: 0.1 } },
};

/** Command palette panel scale-in. */
export const paletteVariants: Variants = {
  hidden: { opacity: 0, scale: 0.97, y: -4 },
  visible: {
    opacity: 1,
    scale: 1,
    y: 0,
    transition: { duration: 0.15, ease: [0.25, 0.46, 0.45, 0.94] },
  },
  exit: {
    opacity: 0,
    scale: 0.97,
    y: -4,
    transition: { duration: 0.1 },
  },
};

/** Button micro-interaction — subtle press scale. */
export const pressVariants: Variants = {
  rest: { scale: 1 },
  pressed: { scale: 0.97, transition: { duration: 0.08 } },
};

/** Copy success — scale + check reveal. */
export const copySuccessVariants: Variants = {
  hidden: { opacity: 0, scale: 0.8 },
  visible: { opacity: 1, scale: 1, transition: { duration: 0.15 } },
  exit: { opacity: 0, scale: 0.8, transition: { duration: 0.1 } },
};
