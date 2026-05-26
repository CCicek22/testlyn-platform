"use client";

import { useEffect, useReducer, useRef } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { SAMPLE_TEST } from "./sample-data";

const STORAGE_KEY = "testlyn:tour:dismissed";

// ─── Tour step definitions ───────────────────────────────────────────────────

interface TourStep {
  title: string;
  body: string;
  cta: string;
  /** Optional anchor element selector to highlight. Cosmetic only. */
  anchor?: string;
}

const STEPS: TourStep[] = [
  {
    title: "Welcome to Testlyn",
    body: "You're 60 seconds away from your first load test. We'll walk you through it.",
    cta: "Let's go",
  },
  {
    title: "Pick a product",
    body: "Start with Load Testing — the default. Switch products any time from the sidebar.",
    cta: "Got it",
    anchor: "[aria-label='Product switcher']",
  },
  {
    title: "Your test script",
    body: "Paste or edit a k6 script in the editor. We've pre-loaded a sample that ramps to 50 VUs.",
    cta: "Nice",
    anchor: "[data-tour='editor']",
  },
  {
    title: "Hit Run",
    body: "Click Run Test — metrics stream live to the chart below. Results land in BigQuery.",
    cta: "Start testing",
  },
];

// ─── State ───────────────────────────────────────────────────────────────────

interface State {
  step: number;
  visible: boolean;
}

type Action =
  | { type: "next" }
  | { type: "skip" }
  | { type: "restore"; payload: State };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "next":
      if (state.step >= STEPS.length - 1) {
        return { step: 0, visible: false };
      }
      return { ...state, step: state.step + 1 };
    case "skip":
      return { step: 0, visible: false };
    case "restore":
      return action.payload;
    default:
      return state;
  }
}

// ─── Component ───────────────────────────────────────────────────────────────

interface ProductTourProps {
  /** Pass product id to scope welcome message. Defaults to "load". */
  product?: string;
}

export function ProductTour({ product: _product = "load" }: ProductTourProps) {
  const router = useRouter();
  const reduced = useReducedMotion();
  const [state, dispatch] = useReducer(reducer, { step: 0, visible: false });
  const dismissed = useRef(false);

  useEffect(() => {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "true") {
      dismissed.current = true;
      return;
    }
    dispatch({ type: "restore", payload: { step: 0, visible: true } });
  }, []);

  // Persist dismissed state
  useEffect(() => {
    if (!state.visible && dismissed.current === false) {
      // Only persist after first hide (not initial invisible render)
    }
  }, [state.visible]);

  function handleNext() {
    const isLast = state.step >= STEPS.length - 1;
    dispatch({ type: "next" });

    if (isLast) {
      localStorage.setItem(STORAGE_KEY, "true");
      dismissed.current = true;
      // Navigate to the editor for the relevant product
      router.push(`/projects`);
    }
  }

  function handleSkip() {
    dispatch({ type: "skip" });
    localStorage.setItem(STORAGE_KEY, "true");
    dismissed.current = true;
  }

  const step = STEPS[state.step];
  if (!step) return null;

  const stepCount = `${state.step + 1} / ${STEPS.length}`;

  return (
    <AnimatePresence>
      {state.visible && (
        <motion.div
          role="dialog"
          aria-modal="false"
          aria-label="Product tour"
          className={cn(
            // Sit above the chat composer at small widths so the card never
            // overlays the page's interactive controls (send button etc.).
            "fixed bottom-24 right-4 z-40 w-[calc(100%-2rem)] max-w-80",
            "sm:bottom-6 sm:right-6 sm:w-80",
            "overflow-hidden rounded-xl",
            "border border-zinc-700 bg-zinc-900 shadow-2xl"
          )}
          initial={reduced ? undefined : { opacity: 0, y: 16, scale: 0.97 }}
          animate={reduced ? undefined : { opacity: 1, y: 0, scale: 1, transition: { duration: 0.2 } }}
          exit={reduced ? undefined : { opacity: 0, y: 16, scale: 0.97, transition: { duration: 0.15 } }}
        >
          {/* Accent bar */}
          <div className="h-0.5 w-full bg-primary" />

          <div className="p-4">
            {/* Progress dots */}
            <div className="mb-3 flex items-center gap-1.5" aria-label={`Step ${stepCount}`}>
              {STEPS.map((_, i) => (
                <span
                  key={i}
                  className={cn(
                    "h-1.5 rounded-full transition-all duration-200",
                    i === state.step
                      ? "w-4 bg-primary"
                      : i < state.step
                      ? "w-1.5 bg-zinc-600"
                      : "w-1.5 bg-zinc-700"
                  )}
                  aria-hidden="true"
                />
              ))}
              <span className="ml-auto text-xs text-zinc-500">{stepCount}</span>
            </div>

            {/* Content */}
            <AnimatePresence mode="wait">
              <motion.div
                key={state.step}
                initial={reduced ? undefined : { opacity: 0, x: 8 }}
                animate={reduced ? undefined : { opacity: 1, x: 0, transition: { duration: 0.15 } }}
                exit={reduced ? undefined : { opacity: 0, x: -8, transition: { duration: 0.1 } }}
              >
                <h3 className="mb-1 text-sm font-semibold text-zinc-100">
                  {step.title}
                </h3>
                <p className="text-sm leading-relaxed text-zinc-400">
                  {step.body}
                </p>
              </motion.div>
            </AnimatePresence>

            {/* Sample script hint on step 2 (editor step) */}
            {state.step === 2 && (
              <div className="mt-2 rounded-md bg-zinc-800/60 px-2 py-1.5">
                <code className="text-[10px] leading-relaxed text-zinc-400">
                  {SAMPLE_TEST.script.split("\n").slice(0, 4).join("\n")}
                  {"\n…"}
                </code>
              </div>
            )}
          </div>

          {/* Footer actions */}
          <div className="flex items-center justify-between border-t border-zinc-800 px-4 py-3">
            <button
              onClick={handleSkip}
              className="text-xs text-zinc-500 transition-colors hover:text-zinc-300"
            >
              Skip tour
            </button>
            <button
              onClick={handleNext}
              className={cn(
                "rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-[#031111]",
                "transition-colors hover:bg-primary/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              )}
            >
              {step.cta}
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
