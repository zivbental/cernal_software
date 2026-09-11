/**
 * A copyable code sample with light, theme-native syntax highlighting.
 *
 * No highlighting library — one regex pass per line is enough for snippets this short,
 * and it stays inside the app's own three ink tokens (mint / foreground / muted) rather
 * than importing a library's own color scheme that would clash in dark mode.
 */

import { Check, Copy } from "lucide-react";
import { useState } from "react";

const KEYWORDS: Record<string, string[]> = {
  python: [
    "import", "from", "as", "def", "class", "return", "if", "elif", "else", "for",
    "while", "try", "except", "finally", "raise", "with", "lambda", "None", "True",
    "False", "in", "is", "not", "and", "or", "print", "open",
  ],
  r: [
    "library", "function", "if", "else", "for", "while", "return", "NULL", "TRUE",
    "FALSE", "tryCatch", "stop", "message",
  ],
  matlab: [
    "function", "end", "if", "else", "elseif", "for", "while", "try", "catch",
    "classdef", "properties", "methods", "case", "switch", "otherwise", "return",
  ],
  bash: ["curl", "export", "echo", "jq"],
  json: [],
  shell: ["pip", "install", "addpath", "remotes"],
};

/** Any language falls back to the python ∪ bash union — misses cost nothing but a bold word. */
function keywordsFor(lang: string): string[] {
  return KEYWORDS[lang] ?? [...KEYWORDS.python, ...KEYWORDS.bash];
}

type Segment = { text: string; kind: "comment" | "string" | "keyword" | "number" | "plain" };

function tokenizeLine(line: string, keywords: string[]): Segment[] {
  if (!line) return [{ text: "", kind: "plain" }];

  const keywordPattern = keywords.length ? keywords.join("|") : "(?!x)x";
  const pattern = new RegExp(
    `(#.*|%.*|\\/\\/.*)` + // comment (python/r/bash # · matlab % · // )
      `|('(?:[^'\\\\]|\\\\.)*'|"(?:[^"\\\\]|\\\\.)*")` + // string
      `|\\b(${keywordPattern})\\b` + // keyword
      `|\\b(\\d+\\.?\\d*)\\b`, // number
    "g",
  );

  const segments: Segment[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(line)) !== null) {
    if (match.index > last) {
      segments.push({ text: line.slice(last, match.index), kind: "plain" });
    }
    const [full, comment, string, keyword, number] = match;
    if (comment) segments.push({ text: comment, kind: "comment" });
    else if (string) segments.push({ text: string, kind: "string" });
    else if (keyword) segments.push({ text: keyword, kind: "keyword" });
    else if (number) segments.push({ text: number, kind: "number" });
    last = match.index + full.length;
  }
  if (last < line.length) segments.push({ text: line.slice(last), kind: "plain" });
  return segments;
}

const SEGMENT_CLASS: Record<Segment["kind"], string> = {
  comment: "text-muted-foreground/70 italic",
  string: "text-mint",
  keyword: "font-semibold text-foreground",
  number: "text-foreground/75",
  plain: "text-foreground",
};

function Highlighted({ code, lang }: { code: string; lang: string }) {
  const keywords = keywordsFor(lang);
  const lines = code.split("\n");
  return (
    <>
      {lines.map((line, i) => (
        <span key={i}>
          {tokenizeLine(line, keywords).map((seg, j) => (
            <span key={j} className={SEGMENT_CLASS[seg.kind]}>
              {seg.text}
            </span>
          ))}
          {i < lines.length - 1 ? "\n" : ""}
        </span>
      ))}
    </>
  );
}

export function CodeBlock({
  code,
  label,
  title,
}: {
  code: string;
  /** Doubles as the language key for highlighting (e.g. "python", "r", "matlab", "curl", "json"). */
  label?: string;
  /** Optional filename-style caption shown above the label, e.g. "quickstart.py". */
  title?: string;
}) {
  const [copied, setCopied] = useState(false);
  const lang = (label ?? "").toLowerCase() === "curl" ? "bash" : (label ?? "plain").toLowerCase();

  async function onCopy() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface-2">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          {title ?? label ?? "code"}
        </span>
        <button
          onClick={onCopy}
          className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-mint" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-4">
        <code className="whitespace-pre font-mono text-[13px] leading-relaxed">
          <Highlighted code={code} lang={lang} />
        </code>
      </pre>
    </div>
  );
}
