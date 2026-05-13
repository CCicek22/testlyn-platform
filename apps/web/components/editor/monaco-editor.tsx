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

// Testlyn dark theme — matches #0A0A0B dark surface
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
        { token: "keyword", foreground: "A78BFA" },
        { token: "string", foreground: "86EFAC" },
        { token: "number", foreground: "FCA5A5" },
        { token: "type", foreground: "7DD3FC" },
      ],
      colors: {
        "editor.background": "#0D0D0F",
        "editor.foreground": "#F4F4F5",
        "editor.lineHighlightBackground": "#1C1C21",
        "editorLineNumber.foreground": "#52525B",
        "editorLineNumber.activeForeground": "#A1A1AA",
        "editor.selectionBackground": "#3730A340",
        "editor.inactiveSelectionBackground": "#3730A320",
        "editorCursor.foreground": "#A78BFA",
        "editor.findMatchBackground": "#3730A360",
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
