"use client";

import dynamic from "next/dynamic";
import type { OnMount } from "@monaco-editor/react";
import { Skeleton } from "@/components/ui/skeleton";

// Lazy-load Monaco to avoid SSR issues and reduce initial bundle
const MonacoEditorCore = dynamic(
  () => import("@monaco-editor/react").then((m) => m.default),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full">
        <Skeleton className="h-full w-full rounded-none" />
      </div>
    ),
  }
);

interface MonacoEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language?: string;
  readOnly?: boolean;
  height?: string;
  className?: string;
}

// Testlyn dark theme matched to the liquid-glass signal palette.
const TESTLYN_THEME = "testlyn-dark";

export function MonacoEditor({
  value,
  onChange,
  language = "javascript",
  readOnly = false,
  height = "400px",
  className,
}: MonacoEditorProps) {
  const handleMount: OnMount = (_editor, monaco) => {
    monaco.editor.defineTheme(TESTLYN_THEME, {
      base: "vs-dark",
      inherit: true,
      rules: [
        { token: "comment", foreground: "6A7385", fontStyle: "italic" },
        { token: "keyword", foreground: "7CFFE1" },
        { token: "string", foreground: "5CFF93" },
        { token: "number", foreground: "FFD166" },
        { token: "type", foreground: "3DDCFF" },
      ],
      colors: {
        "editor.background": "#05090B",
        "editor.foreground": "#E8FBFF",
        "editor.lineHighlightBackground": "#0D1B1F",
        "editorLineNumber.foreground": "#5D7378",
        "editorLineNumber.activeForeground": "#B9FFF0",
        "editor.selectionBackground": "#18F2C340",
        "editor.inactiveSelectionBackground": "#18F2C320",
        "editorCursor.foreground": "#18F2C3",
        "editor.findMatchBackground": "#18F2C360",
        "scrollbarSlider.background": "#3F3F4680",
        "scrollbarSlider.hoverBackground": "#3F3F46B0",
      },
    });
    monaco.editor.setTheme(TESTLYN_THEME);
  };

  return (
    <div className={`overflow-hidden rounded-lg border border-zinc-800 ${className ?? ""}`}>
      <MonacoEditorCore
        height={height}
        language={language}
        value={value}
        onChange={(v) => onChange?.(v ?? "")}
        onMount={handleMount}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontSize: 13,
          fontFamily: '"JetBrains Mono", "Fira Code", monospace',
          fontLigatures: true,
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          tabSize: 2,
          wordWrap: "on",
          padding: { top: 12, bottom: 12 },
        }}
      />
    </div>
  );
}
