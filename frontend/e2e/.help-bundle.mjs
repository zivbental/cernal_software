// e2e/.help-entry.tsx
import { renderToStaticMarkup } from "react-dom/server";

// src/routes/guide.tsx
import { createFileRoute } from "@tanstack/react-router";
import { BookOpen } from "lucide-react";

// src/components/docs/CodeBlock.tsx
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";
var KEYWORDS = {
  python: [
    "import",
    "from",
    "as",
    "def",
    "class",
    "return",
    "if",
    "elif",
    "else",
    "for",
    "while",
    "try",
    "except",
    "finally",
    "raise",
    "with",
    "lambda",
    "None",
    "True",
    "False",
    "in",
    "is",
    "not",
    "and",
    "or",
    "print",
    "open"
  ],
  r: [
    "library",
    "function",
    "if",
    "else",
    "for",
    "while",
    "return",
    "NULL",
    "TRUE",
    "FALSE",
    "tryCatch",
    "stop",
    "message"
  ],
  matlab: [
    "function",
    "end",
    "if",
    "else",
    "elseif",
    "for",
    "while",
    "try",
    "catch",
    "classdef",
    "properties",
    "methods",
    "case",
    "switch",
    "otherwise",
    "return"
  ],
  bash: ["curl", "export", "echo", "jq"],
  json: [],
  shell: ["pip", "install", "addpath", "remotes"]
};
function keywordsFor(lang) {
  return KEYWORDS[lang] ?? [...KEYWORDS.python, ...KEYWORDS.bash];
}
function tokenizeLine(line, keywords) {
  if (!line) return [{ text: "", kind: "plain" }];
  const keywordPattern = keywords.length ? keywords.join("|") : "(?!x)x";
  const pattern = new RegExp(
    `(#.*|%.*|\\/\\/.*)|('(?:[^'\\\\]|\\\\.)*'|"(?:[^"\\\\]|\\\\.)*")|\\b(${keywordPattern})\\b|\\b(\\d+\\.?\\d*)\\b`,
    // number
    "g"
  );
  const segments = [];
  let last = 0;
  let match;
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
var SEGMENT_CLASS = {
  comment: "text-muted-foreground/70 italic",
  string: "text-mint",
  keyword: "font-semibold text-foreground",
  number: "text-foreground/75",
  plain: "text-foreground"
};
function Highlighted({ code, lang }) {
  const keywords = keywordsFor(lang);
  const lines = code.split("\n");
  return /* @__PURE__ */ jsx(Fragment, { children: lines.map((line, i) => /* @__PURE__ */ jsxs("span", { children: [
    tokenizeLine(line, keywords).map((seg, j) => /* @__PURE__ */ jsx("span", { className: SEGMENT_CLASS[seg.kind], children: seg.text }, j)),
    i < lines.length - 1 ? "\n" : ""
  ] }, i)) });
}
function CodeBlock({
  code,
  label,
  title
}) {
  const [copied, setCopied] = useState(false);
  const lang = (label ?? "").toLowerCase() === "curl" ? "bash" : (label ?? "plain").toLowerCase();
  async function onCopy() {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }
  return /* @__PURE__ */ jsxs("div", { className: "overflow-hidden rounded-xl border border-border bg-surface-2", children: [
    /* @__PURE__ */ jsxs("div", { className: "flex items-center justify-between border-b border-border px-4 py-2", children: [
      /* @__PURE__ */ jsx("span", { className: "font-mono text-[11px] uppercase tracking-wider text-muted-foreground", children: title ?? label ?? "code" }),
      /* @__PURE__ */ jsxs(
        "button",
        {
          onClick: onCopy,
          className: "inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground",
          children: [
            copied ? /* @__PURE__ */ jsx(Check, { className: "h-3.5 w-3.5 text-mint" }) : /* @__PURE__ */ jsx(Copy, { className: "h-3.5 w-3.5" }),
            copied ? "Copied" : "Copy"
          ]
        }
      )
    ] }),
    /* @__PURE__ */ jsx("pre", { className: "overflow-x-auto p-4", children: /* @__PURE__ */ jsx("code", { className: "whitespace-pre font-mono text-[13px] leading-relaxed", children: /* @__PURE__ */ jsx(Highlighted, { code, lang }) }) })
  ] });
}

// src/components/docs/HelpNav.tsx
import { jsx as jsx2 } from "react/jsx-runtime";
function Caveat({ children }) {
  return /* @__PURE__ */ jsx2("aside", { className: "rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-foreground", children });
}
function HelpLink({
  href,
  children
}) {
  return /* @__PURE__ */ jsx2(
    "a",
    {
      className: "text-mint underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint",
      href,
      children
    }
  );
}

// src/components/layout/AppShell.tsx
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { CircuitBoard, LogOut, Settings, User } from "lucide-react";

// src/assets/cernal-logo-animated.svg
var cernal_logo_animated_default = 'data:image/svg+xml,<?xml version="1.0"?>%0D%0A<svg data-dc-tpl="9" id="cernal-logo-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1180 320" width="100%" data-om-id="480ea089:15" style="display: block; overflow: visible;" xmlns:xlink="http://www.w3.org/1999/xlink">%0D%0A      <title data-dc-tpl="10">CERNAL \u2014 Compiler-like Engine for RNA Logic</title>%0D%0A      %0D%0A%0D%0A      %0D%0A      <g data-dc-tpl="12" class="mol" data-om-id="480ea089:16" style="offset-path: path(&%2334;M 40 -90 C 120 -70 150 44 190 44&%2334;); offset-rotate: auto; animation: 7s ease-in-out 0s infinite normal none running molDock;">%0D%0A        <g data-dc-tpl="13" class="molwave" data-om-id="480ea089:17">%0D%0A          <path data-dc-tpl="14" class="molbb" d="M -75.0 0.0 L -71.7 1.1 L -68.5 2.2 L -65.2 3.3 L -62.0 4.2 L -58.7 4.9 L -55.4 5.5 L -52.2 5.8 L -48.9 6.0 L -45.7 5.9 L -42.4 5.7 L -39.1 5.2 L -35.9 4.5 L -32.6 3.7 L -29.3 2.7 L -26.1 1.6 L -22.8 0.5 L -19.6 -0.7 L -16.3 -1.8 L -13.0 -2.8 L -9.8 -3.8 L -6.5 -4.6 L -3.3 -5.2 L 0.0 -5.7 L 3.3 -6.0 L 6.5 -6.0 L 9.8 -5.8 L 13.0 -5.4 L 16.3 -4.8 L 19.6 -4.0 L 22.8 -3.1 L 26.1 -2.1 L 29.3 -1.0 L 32.6 0.2 L 35.9 1.3 L 39.1 2.4 L 42.4 3.4 L 45.7 4.3 L 48.9 5.0 L 52.2 5.5 L 55.4 5.9 L 58.7 6.0 L 62.0 5.9 L 65.2 5.6 L 68.5 5.1 L 71.7 4.4 L 75.0 3.5" data-om-id="480ea089:18"></path>%0D%0A          <g data-dc-tpl="15" class="moltk" data-om-id="480ea089:19"><line data-dc-tpl="16" x1="-67.9" y1="10.8" x2="-63.3" y2="-4.5" data-om-id="480ea089:20"></line><line data-dc-tpl="17" x1="-46.7" y1="14.0" x2="-47.1" y2="-2.0" data-om-id="480ea089:21"></line><line data-dc-tpl="18" x1="-25.7" y1="9.9" x2="-30.6" y2="-5.3" data-om-id="480ea089:22"></line><line data-dc-tpl="19" x1="-7.3" y1="3.8" x2="-11.4" y2="-11.6" data-om-id="480ea089:23"></line><line data-dc-tpl="20" x1="8.7" y1="2.1" x2="10.0" y2="-13.8" data-om-id="480ea089:24"></line><line data-dc-tpl="21" x1="25.5" y1="6.2" x2="30.7" y2="-9.0" data-om-id="480ea089:25"></line><line data-dc-tpl="22" x1="45.1" y1="12.4" x2="48.7" y2="-3.2" data-om-id="480ea089:26"></line><line data-dc-tpl="23" x1="66.7" y1="13.5" x2="64.6" y2="-2.4" data-om-id="480ea089:27"></line></g>%0D%0A        </g>%0D%0A      </g>%0D%0A      <g data-dc-tpl="24" class="mol" data-om-id="480ea089:28" style="offset-path: path(&%2334;M 340 360 C 260 320 230 276 190 276&%2334;); offset-rotate: auto; animation: 7s ease-in-out -0.5s infinite normal none running molDock;">%0D%0A        <g data-dc-tpl="25" class="molwave" data-om-id="480ea089:29">%0D%0A          <path data-dc-tpl="26" class="molbb" d="M -75.0 5.3 L -71.7 5.8 L -68.5 6.0 L -65.2 6.0 L -62.0 5.7 L -58.7 5.3 L -55.4 4.7 L -52.2 3.9 L -48.9 2.9 L -45.7 1.9 L -42.4 0.8 L -39.1 -0.4 L -35.9 -1.5 L -32.6 -2.6 L -29.3 -3.6 L -26.1 -4.4 L -22.8 -5.1 L -19.6 -5.6 L -16.3 -5.9 L -13.0 -6.0 L -9.8 -5.9 L -6.5 -5.5 L -3.3 -5.0 L 0.0 -4.2 L 3.3 -3.4 L 6.5 -2.4 L 9.8 -1.3 L 13.0 -0.1 L 16.3 1.0 L 19.6 2.1 L 22.8 3.2 L 26.1 4.1 L 29.3 4.8 L 32.6 5.4 L 35.9 5.8 L 39.1 6.0 L 42.4 5.9 L 45.7 5.7 L 48.9 5.2 L 52.2 4.6 L 55.4 3.8 L 58.7 2.8 L 62.0 1.7 L 65.2 0.6 L 68.5 -0.5 L 71.7 -1.7 L 75.0 -2.7" data-om-id="480ea089:30"></path>%0D%0A          <g data-dc-tpl="27" class="moltk" data-om-id="480ea089:31"><line data-dc-tpl="28" x1="-65.4" y1="14.0" x2="-65.8" y2="-2.0" data-om-id="480ea089:32"></line><line data-dc-tpl="29" x1="-44.4" y1="9.9" x2="-49.3" y2="-5.3" data-om-id="480ea089:33"></line><line data-dc-tpl="30" x1="-26.1" y1="3.8" x2="-30.2" y2="-11.6" data-om-id="480ea089:34"></line><line data-dc-tpl="31" x1="-10.0" y1="2.1" x2="-8.7" y2="-13.8" data-om-id="480ea089:35"></line><line data-dc-tpl="32" x1="6.8" y1="6.2" x2="12.0" y2="-9.0" data-om-id="480ea089:36"></line><line data-dc-tpl="33" x1="26.3" y1="12.4" x2="29.9" y2="-3.2" data-om-id="480ea089:37"></line><line data-dc-tpl="34" x1="47.9" y1="13.5" x2="45.8" y2="-2.4" data-om-id="480ea089:38"></line><line data-dc-tpl="35" x1="68.3" y1="8.0" x2="63.0" y2="-7.1" data-om-id="480ea089:39"></line></g>%0D%0A        </g>%0D%0A      </g>%0D%0A      <g data-dc-tpl="36" class="mol" data-om-id="480ea089:40" style="offset-path: path(&%2334;M -120 260 C -40 230 74 230 74 160&%2334;); offset-rotate: auto; animation: 7s ease-in-out -0.25s infinite normal none running molDock;">%0D%0A        <g data-dc-tpl="37" class="molwave" data-om-id="480ea089:41">%0D%0A          <path data-dc-tpl="38" class="molbb" d="M -75.0 2.9 L -71.7 3.8 L -68.5 4.6 L -65.2 5.3 L -62.0 5.7 L -58.7 6.0 L -55.4 6.0 L -52.2 5.8 L -48.9 5.4 L -45.7 4.8 L -42.4 4.0 L -39.1 3.1 L -35.9 2.0 L -32.6 0.9 L -29.3 -0.2 L -26.1 -1.3 L -22.8 -2.4 L -19.6 -3.4 L -16.3 -4.3 L -13.0 -5.0 L -9.8 -5.6 L -6.5 -5.9 L -3.3 -6.0 L 0.0 -5.9 L 3.3 -5.6 L 6.5 -5.1 L 9.8 -4.4 L 13.0 -3.5 L 16.3 -2.5 L 19.6 -1.4 L 22.8 -0.3 L 26.1 0.9 L 29.3 2.0 L 32.6 3.0 L 35.9 3.9 L 39.1 4.7 L 42.4 5.3 L 45.7 5.8 L 48.9 6.0 L 52.2 6.0 L 55.4 5.7 L 58.7 5.3 L 62.0 4.7 L 65.2 3.9 L 68.5 2.9 L 71.7 1.9 L 75.0 0.8" data-om-id="480ea089:42"></path>%0D%0A          <g data-dc-tpl="39" class="moltk" data-om-id="480ea089:43"><line data-dc-tpl="40" x1="-67.0" y1="13.1" x2="-64.2" y2="-2.7" data-om-id="480ea089:44"></line><line data-dc-tpl="41" x1="-45.4" y1="12.9" x2="-48.4" y2="-2.8" data-om-id="480ea089:45"></line><line data-dc-tpl="42" x1="-25.5" y1="6.9" x2="-30.8" y2="-8.2" data-om-id="480ea089:46"></line><line data-dc-tpl="43" x1="-8.4" y1="2.3" x2="-10.4" y2="-13.5" data-om-id="480ea089:47"></line><line data-dc-tpl="44" x1="7.5" y1="3.3" x2="11.2" y2="-12.2" data-om-id="480ea089:48"></line><line data-dc-tpl="45" x1="25.6" y1="9.1" x2="30.7" y2="-6.0" data-om-id="480ea089:49"></line><line data-dc-tpl="46" x1="46.3" y1="13.9" x2="47.5" y2="-2.1" data-om-id="480ea089:50"></line><line data-dc-tpl="47" x1="67.7" y1="11.5" x2="63.5" y2="-4.0" data-om-id="480ea089:51"></line></g>%0D%0A        </g>%0D%0A      </g>%0D%0A      <g data-dc-tpl="48" class="mol" data-om-id="480ea089:52" style="offset-path: path(&%2334;M 420 40 C 360 90 306 90 306 160&%2334;); offset-rotate: auto; animation: 7s ease-in-out -0.7s infinite normal none running molDock;">%0D%0A        <g data-dc-tpl="49" class="molwave" data-om-id="480ea089:53">%0D%0A          <path data-dc-tpl="50" class="molbb" d="M -75.0 5.9 L -71.7 5.7 L -68.5 5.2 L -65.2 4.6 L -62.0 3.8 L -58.7 2.8 L -55.4 1.7 L -52.2 0.6 L -48.9 -0.5 L -45.7 -1.7 L -42.4 -2.7 L -39.1 -3.7 L -35.9 -4.5 L -32.6 -5.2 L -29.3 -5.7 L -26.1 -5.9 L -22.8 -6.0 L -19.6 -5.8 L -16.3 -5.5 L -13.0 -4.9 L -9.8 -4.1 L -6.5 -3.2 L -3.3 -2.2 L 0.0 -1.1 L 3.3 0.0 L 6.5 1.2 L 9.8 2.3 L 13.0 3.3 L 16.3 4.2 L 19.6 4.9 L 22.8 5.5 L 26.1 5.8 L 29.3 6.0 L 32.6 5.9 L 35.9 5.6 L 39.1 5.1 L 42.4 4.5 L 45.7 3.6 L 48.9 2.7 L 52.2 1.6 L 55.4 0.5 L 58.7 -0.7 L 62.0 -1.8 L 65.2 -2.9 L 68.5 -3.8 L 71.7 -4.6 L 75.0 -5.3" data-om-id="480ea089:54"></path>%0D%0A          <g data-dc-tpl="51" class="moltk" data-om-id="480ea089:55"><line data-dc-tpl="52" x1="-63.9" y1="12.5" x2="-67.4" y2="-3.1" data-om-id="480ea089:56"></line><line data-dc-tpl="53" x1="-44.3" y1="6.3" x2="-49.5" y2="-8.8" data-om-id="480ea089:57"></line><line data-dc-tpl="54" x1="-27.4" y1="2.2" x2="-28.9" y2="-13.8" data-om-id="480ea089:58"></line><line data-dc-tpl="55" x1="-11.4" y1="3.7" x2="-7.4" y2="-11.8" data-om-id="480ea089:59"></line><line data-dc-tpl="56" x1="6.9" y1="9.7" x2="11.9" y2="-5.5" data-om-id="480ea089:60"></line><line data-dc-tpl="57" x1="27.8" y1="14.0" x2="28.4" y2="-2.0" data-om-id="480ea089:61"></line><line data-dc-tpl="58" x1="49.1" y1="10.9" x2="44.6" y2="-4.4" data-om-id="480ea089:62"></line><line data-dc-tpl="59" x1="68.0" y1="4.7" x2="63.3" y2="-10.6" data-om-id="480ea089:63"></line></g>%0D%0A        </g>%0D%0A      </g>%0D%0A%0D%0A      %0D%0A      <rect data-dc-tpl="60" class="cring" x="158" y="128" width="64" height="64" rx="11" data-om-id="480ea089:64"></rect>%0D%0A      <rect data-dc-tpl="61" class="cring b" x="158" y="128" width="64" height="64" rx="11" data-om-id="480ea089:65"></rect>%0D%0A%0D%0A      %0D%0A      <g data-dc-tpl="62" fill="%23181113" data-om-id="480ea089:66">%0D%0A        <rect data-dc-tpl="63" x="146" y="52" width="16" height="30" rx="6" data-om-id="480ea089:67"></rect>%0D%0A        <rect data-dc-tpl="64" x="182" y="52" width="16" height="30" rx="6" data-om-id="480ea089:68"></rect>%0D%0A        <rect data-dc-tpl="65" x="218" y="52" width="16" height="30" rx="6" data-om-id="480ea089:69"></rect>%0D%0A        <rect data-dc-tpl="66" x="146" y="238" width="16" height="30" rx="6" data-om-id="480ea089:70"></rect>%0D%0A        <rect data-dc-tpl="67" x="182" y="238" width="16" height="30" rx="6" data-om-id="480ea089:71"></rect>%0D%0A        <rect data-dc-tpl="68" x="218" y="238" width="16" height="30" rx="6" data-om-id="480ea089:72"></rect>%0D%0A        <rect data-dc-tpl="69" x="82" y="116" width="30" height="16" rx="6" data-om-id="480ea089:73"></rect>%0D%0A        <rect data-dc-tpl="70" x="82" y="152" width="30" height="16" rx="6" data-om-id="480ea089:74"></rect>%0D%0A        <rect data-dc-tpl="71" x="82" y="188" width="30" height="16" rx="6" data-om-id="480ea089:75"></rect>%0D%0A        <rect data-dc-tpl="72" x="268" y="116" width="30" height="16" rx="6" data-om-id="480ea089:76"></rect>%0D%0A        <rect data-dc-tpl="73" x="268" y="152" width="30" height="16" rx="6" data-om-id="480ea089:77"></rect>%0D%0A        <rect data-dc-tpl="74" x="268" y="188" width="30" height="16" rx="6" data-om-id="480ea089:78"></rect>%0D%0A        <rect data-dc-tpl="75" x="110" y="80" width="160" height="160" rx="22" data-om-id="480ea089:79"></rect>%0D%0A      </g>%0D%0A      <g data-dc-tpl="76" fill="%232f2325" data-om-id="480ea089:80">%0D%0A        <circle data-dc-tpl="77" cx="136" cy="106" r="6" data-om-id="480ea089:81"></circle>%0D%0A        <circle data-dc-tpl="78" cx="244" cy="106" r="6" data-om-id="480ea089:82"></circle>%0D%0A        <circle data-dc-tpl="79" cx="136" cy="214" r="6" data-om-id="480ea089:83"></circle>%0D%0A        <circle data-dc-tpl="80" cx="244" cy="214" r="6" data-om-id="480ea089:84"></circle>%0D%0A      </g>%0D%0A%0D%0A      %0D%0A      <rect data-dc-tpl="81" class="cglow" x="156" y="126" width="68" height="68" rx="12" fill="%23ec4a3c" data-om-id="480ea089:85"></rect>%0D%0A      <rect data-dc-tpl="82" class="cdie" x="160" y="130" width="60" height="60" rx="9" fill="%234a4244" stroke="%23dcd0d1" stroke-width="3.5" data-om-id="480ea089:86"></rect>%0D%0A%0D%0A%0D%0A      %0D%0A      <text data-dc-tpl="83" class="cwm" x="432" y="214" data-om-id="480ea089:87">%0D%0A        <tspan data-dc-tpl="84" fill="%2316100f" data-om-id="480ea089:88">CE</tspan><tspan data-dc-tpl="85" class="crna" fill="%239e1a20" data-om-id="480ea089:89">RNA</tspan><tspan data-dc-tpl="86" fill="%2316100f" data-om-id="480ea089:90">L</tspan>%0D%0A      </text>%0D%0A      <text data-dc-tpl="87" class="ctag" x="436" y="263" data-om-id="480ea089:91">COMPILER-LIKE ENGINE FOR RNA LOGIC</text>%0D%0A    </svg>';

// src/api/queries.ts
import {
  useMutation,
  useQuery,
  useQueryClient
} from "@tanstack/react-query";

// src/api/client.ts
var BASE = "/api";
var ApiError = class extends Error {
  status;
  code;
  detail;
  constructor(status, code, message, detail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
  /** Missing and not-yours both return 404, so callers cannot tell them apart. */
  get isNotFound() {
    return this.status === 404;
  }
  get isUnauthenticated() {
    return this.status === 401;
  }
};
function readCookie(name) {
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[2]) : null;
}
var csrfPrimed = false;
async function primeCsrf() {
  if (csrfPrimed && readCookie("csrftoken")) return;
  const response = await fetch(`${BASE}/auth/csrf`, { credentials: "same-origin" });
  if (!response.ok) throw new ApiError(response.status, "csrf_error", "Could not initialize a secure session. Please retry.", {});
  csrfPrimed = true;
}
var WRITE_METHODS = /* @__PURE__ */ new Set(["POST", "PUT", "PATCH", "DELETE"]);
async function request(path, options = {}) {
  const method = options.method ?? "GET";
  const headers = {};
  if (WRITE_METHODS.has(method)) {
    await primeCsrf();
    const token = readCookie("csrftoken");
    if (token) headers["X-CSRFToken"] = token;
  }
  let body;
  if (options.form) {
    body = options.form;
  } else if (options.body !== void 0) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body,
    credentials: "same-origin",
    signal: options.signal
  });
  if (response.status === 204) return void 0;
  const isJson = response.headers.get("content-type")?.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const envelope = payload?.error;
    throw new ApiError(
      response.status,
      envelope?.code ?? "http_error",
      envelope?.message ?? `Request failed (${response.status})`,
      envelope?.detail ?? {}
    );
  }
  return payload;
}
var api = {
  get: (path, signal) => request(path, { signal }),
  post: (path, body) => request(path, { method: "POST", body }),
  patch: (path, body) => request(path, { method: "PATCH", body }),
  delete: (path) => request(path, { method: "DELETE" }),
  upload: (path, form) => request(path, { method: "POST", form }),
  /** Absolute URL for a download the browser should fetch itself. */
  url: (path) => `${BASE}${path}`
};

// src/api/queries.ts
var keys = {
  me: ["me"],
  version: ["version"],
  datasets: ["datasets"],
  datasetPreview: (id) => ["dataset-preview", id],
  exampleDatasets: ["example-datasets"],
  publicExperiments: (organism) => ["public-experiments", organism],
  publicComparisons: (experimentKey) => ["public-comparisons", experimentKey],
  publicDatasetInfo: (comparisonKey) => ["public-dataset-info", comparisonKey],
  recentRuns: ["runs", "recent"],
  run: (id) => ["run", id],
  runStatus: (id) => ["run", id, "status"],
  candidates: (runId, params) => ["candidates", runId, params],
  candidate: (id) => ["candidate", id],
  candidateStructure: (id) => ["candidate", id, "structure"],
  artifacts: (runId) => ["artifacts", runId],
  annotations: (candidateId) => ["annotations", candidateId],
  apiKeys: ["api-keys"]
};
function useMe(options) {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => api.get("/auth/me").catch((error) => {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }),
    staleTime: 5 * 6e4,
    retry: false,
    ...options
  });
}
function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/auth/logout"),
    onSuccess: () => {
      queryClient.clear();
    }
  });
}
function useVersion() {
  return useQuery({
    queryKey: keys.version,
    queryFn: () => api.get("/version"),
    staleTime: Infinity
  });
}

// src/components/layout/AppShell.tsx
import { jsx as jsx3, jsxs as jsxs2 } from "react/jsx-runtime";
var NAV = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/guide", label: "Quick Guide" },
  { to: "/use-cases", label: "Use Cases" },
  { to: "/faq", label: "FAQ" },
  { to: "/api-docs", label: "API Reference" },
  { to: "/about", label: "About Us" }
];
function NewCircuitLink({ className = "" }) {
  return /* @__PURE__ */ jsxs2(
    Link,
    {
      to: "/compile",
      className: `inline-flex items-center gap-1.5 rounded-md bg-foreground px-3 py-1.5 text-sm font-medium text-background transition hover:opacity-90 ${className}`,
      children: [
        /* @__PURE__ */ jsx3(CircuitBoard, { className: "h-3.5 w-3.5" }),
        " New Circuit"
      ]
    }
  );
}
function Nav() {
  const { data: user } = useMe();
  const { data: version } = useVersion();
  const logout = useLogout();
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  async function onLogout() {
    try {
      await logout.mutateAsync();
      navigate({ to: "/login" });
    } catch {
    }
  }
  return /* @__PURE__ */ jsxs2("header", { className: "sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-xl", children: [
    logout.isError && /* @__PURE__ */ jsx3("p", { role: "alert", className: "text-xs text-destructive", children: "Sign out failed. Please retry." }),
    /* @__PURE__ */ jsxs2("div", { className: "mx-auto flex min-h-16 max-w-[1400px] items-center justify-between gap-3 px-4 py-2 sm:px-8", children: [
      /* @__PURE__ */ jsxs2("div", { className: "flex min-w-0 items-center gap-4 lg:gap-8", children: [
        /* @__PURE__ */ jsx3(Link, { to: "/dashboard", className: "flex items-center gap-2.5", children: /* @__PURE__ */ jsx3(
          "img",
          {
            src: cernal_logo_animated_default,
            alt: "CERNAL \u2014 Compiler-like Engine for RNA Logic",
            className: "h-9 w-auto"
          }
        ) }),
        /* @__PURE__ */ jsxs2("nav", { "aria-label": "Primary navigation", className: "hidden min-w-0 flex-wrap items-center gap-1 lg:flex", children: [
          /* @__PURE__ */ jsx3(NewCircuitLink, { className: "mr-1" }),
          NAV.map((item) => {
            const active = pathname.startsWith(item.to);
            return /* @__PURE__ */ jsx3(
              Link,
              {
                to: item.to,
                className: `rounded-md px-2 py-1.5 text-sm transition xl:px-3 ${active ? "bg-secondary font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`,
                children: item.label
              },
              item.to
            );
          })
        ] })
      ] }),
      /* @__PURE__ */ jsxs2("div", { className: "flex items-center gap-3", children: [
        /* @__PURE__ */ jsxs2(
          "div",
          {
            className: "hidden items-center gap-2 rounded-md border border-border bg-surface px-3 py-1.5 text-xs md:flex",
            title: version ? `Engine ${version.engine} ${version.engine_version}` : "Checking engine\u2026",
            children: [
              /* @__PURE__ */ jsx3(
                "span",
                {
                  className: `h-1.5 w-1.5 rounded-full ${version ? "bg-mint" : "bg-muted-foreground"}`
                }
              ),
              /* @__PURE__ */ jsx3("span", { className: "font-mono text-muted-foreground", children: "TAU iGEM Lab" })
            ]
          }
        ),
        /* @__PURE__ */ jsx3(
          Link,
          {
            to: "/settings",
            className: "rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground",
            "aria-label": "Settings",
            children: /* @__PURE__ */ jsx3(Settings, { className: "h-4 w-4" })
          }
        ),
        /* @__PURE__ */ jsx3(
          "div",
          {
            className: "grid h-9 w-9 place-items-center rounded-full bg-gradient-mint text-mint-foreground",
            title: user?.username,
            children: /* @__PURE__ */ jsx3(User, { className: "h-4 w-4" })
          }
        ),
        /* @__PURE__ */ jsx3(
          "button",
          {
            onClick: onLogout,
            disabled: logout.isPending,
            className: "rounded-md p-2 text-muted-foreground hover:bg-secondary hover:text-foreground",
            "aria-label": "Sign out",
            title: "Sign out",
            children: /* @__PURE__ */ jsx3(LogOut, { className: "h-4 w-4" })
          }
        )
      ] })
    ] }),
    /* @__PURE__ */ jsxs2(
      "nav",
      {
        "aria-label": "Primary navigation",
        className: "flex flex-wrap items-center gap-1 border-t border-border px-4 py-2 sm:px-8 lg:hidden",
        children: [
          /* @__PURE__ */ jsx3(NewCircuitLink, {}),
          NAV.map((item) => /* @__PURE__ */ jsx3(
            Link,
            {
              to: item.to,
              "aria-current": pathname.startsWith(item.to) ? "page" : void 0,
              className: `rounded-md px-2 py-1.5 text-sm transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint ${pathname.startsWith(item.to) ? "bg-secondary font-medium text-foreground" : "text-muted-foreground hover:text-foreground"}`,
              children: item.label
            },
            item.to
          ))
        ]
      }
    )
  ] });
}
function Footer() {
  const { data: version } = useVersion();
  return /* @__PURE__ */ jsxs2("footer", { className: "mx-auto flex max-w-[1400px] items-center justify-between border-t border-border px-8 py-6 font-mono text-[11px] text-muted-foreground", children: [
    /* @__PURE__ */ jsx3("div", { children: "CERNAL \xB7 Synthetic Biology Compiler \xB7 \xA9 2026" }),
    /* @__PURE__ */ jsxs2("div", { className: "flex items-center gap-4", children: [
      /* @__PURE__ */ jsx3("span", { children: version ? `v${version.app_version}` : "\u2014" }),
      /* @__PURE__ */ jsxs2("span", { className: "flex items-center gap-1.5", title: version?.engine_version, children: [
        /* @__PURE__ */ jsx3("span", { className: "h-1.5 w-1.5 rounded-full bg-mint" }),
        version?.engine ?? "\u2014"
      ] })
    ] })
  ] });
}
function AppShell({ children }) {
  return /* @__PURE__ */ jsxs2("div", { className: "flex min-h-screen flex-col bg-background", children: [
    /* @__PURE__ */ jsx3(Nav, {}),
    /* @__PURE__ */ jsx3("main", { className: "mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-8 sm:py-10", children }),
    /* @__PURE__ */ jsx3(Footer, {})
  ] });
}
function PageHeader({
  kicker,
  title,
  description,
  actions
}) {
  return /* @__PURE__ */ jsxs2("div", { className: "mb-8 flex flex-wrap items-end justify-between gap-6", children: [
    /* @__PURE__ */ jsxs2("div", { children: [
      /* @__PURE__ */ jsx3("div", { className: "flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.18em] text-muted-foreground", children: kicker }),
      /* @__PURE__ */ jsx3("h1", { className: "mt-2 text-3xl font-semibold tracking-tight text-foreground", children: title }),
      description && /* @__PURE__ */ jsx3("p", { className: "mt-1 max-w-2xl text-sm text-muted-foreground", children: description })
    ] }),
    actions && /* @__PURE__ */ jsx3("div", { className: "flex gap-2", children: actions })
  ] });
}

// src/components/layout/RequireAuth.tsx
import { Navigate, useRouterState as useRouterState2 } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { Fragment as Fragment2, jsx as jsx4, jsxs as jsxs3 } from "react/jsx-runtime";
function RequireAuth({ children }) {
  const { data: user, isLoading, isError, refetch } = useMe();
  const pathname = useRouterState2({ select: (s) => s.location.pathname });
  if (isLoading) {
    return /* @__PURE__ */ jsx4("div", { className: "grid min-h-screen place-items-center bg-background", children: /* @__PURE__ */ jsx4(Loader2, { className: "h-5 w-5 animate-spin text-muted-foreground" }) });
  }
  if (isError) return /* @__PURE__ */ jsxs3("p", { role: "alert", children: [
    "Could not check your session. ",
    /* @__PURE__ */ jsx4("button", { onClick: () => refetch(), children: "Retry" })
  ] });
  if (!user) {
    return /* @__PURE__ */ jsx4(Navigate, { to: "/login", search: { redirect: pathname }, replace: true });
  }
  return /* @__PURE__ */ jsx4(Fragment2, { children });
}

// src/components/layout/Primitives.tsx
import { CheckCircle2, ChevronDown, ChevronRight, Settings as Settings2 } from "lucide-react";
import { useState as useState2 } from "react";
import { jsx as jsx5, jsxs as jsxs4 } from "react/jsx-runtime";
function Panel({ children, className = "" }) {
  return /* @__PURE__ */ jsx5("section", { className: `rounded-2xl border border-border bg-card p-8 shadow-clinical ${className}`, children });
}

// src/routes/guide.tsx
import { Fragment as Fragment3, jsx as jsx6, jsxs as jsxs5 } from "react/jsx-runtime";
var BASE2 = "https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f";
var Route = createFileRoute("/guide")({
  component: () => /* @__PURE__ */ jsx6(RequireAuth, { children: /* @__PURE__ */ jsx6(AppShell, { children: /* @__PURE__ */ jsx6(GuideContent, {}) }) })
});
var SETUP = `# From the repository root
uv sync --locked --extra dev
cd frontend
npm ci
npm run build:fast
npm run build
cd ..
./do migrate
./do superuser`;
var RUN = `# Web server and supervised worker, from the repository root
./do dev`;
function GuideSection({
  id,
  title,
  children
}) {
  return /* @__PURE__ */ jsx6(Panel, { children: /* @__PURE__ */ jsxs5("div", { id, className: "scroll-mt-48 lg:scroll-mt-24", children: [
    /* @__PURE__ */ jsx6("h2", { className: "text-xl font-semibold tracking-tight text-foreground", children: title }),
    /* @__PURE__ */ jsx6("div", { className: "mt-4 space-y-4 text-sm leading-6 text-muted-foreground", children })
  ] }) });
}
function GuideContent() {
  return /* @__PURE__ */ jsxs5(Fragment3, { children: [
    /* @__PURE__ */ jsx6(
      PageHeader,
      {
        kicker: /* @__PURE__ */ jsxs5(Fragment3, { children: [
          /* @__PURE__ */ jsx6(BookOpen, { className: "h-3 w-3" }),
          " Quick Guide"
        ] }),
        title: "How to compile a circuit",
        description: "A task-first path from a supported input to an inspectable run."
      }
    ),
    /* @__PURE__ */ jsxs5(
      "nav",
      {
        "aria-label": "On this page",
        className: "mb-6 rounded-xl border border-border bg-surface p-4",
        children: [
          /* @__PURE__ */ jsx6("h2", { className: "text-sm font-semibold text-foreground", children: "On this page" }),
          /* @__PURE__ */ jsxs5("ol", { className: "mt-2 flex flex-wrap gap-x-5 gap-y-2 text-sm text-mint", children: [
            /* @__PURE__ */ jsx6("li", { children: /* @__PURE__ */ jsx6("a", { href: "#before-running", children: "Before running" }) }),
            /* @__PURE__ */ jsx6("li", { children: /* @__PURE__ */ jsx6("a", { href: "#local-setup", children: "Local setup" }) }),
            /* @__PURE__ */ jsx6("li", { children: /* @__PURE__ */ jsx6("a", { href: "#choose-input", children: "Choose input" }) }),
            /* @__PURE__ */ jsx6("li", { children: /* @__PURE__ */ jsx6("a", { href: "#configure", children: "Configure" }) }),
            /* @__PURE__ */ jsx6("li", { children: /* @__PURE__ */ jsx6("a", { href: "#payload-vector", children: "Payload and vector" }) }),
            /* @__PURE__ */ jsx6("li", { children: /* @__PURE__ */ jsx6("a", { href: "#submit", children: "Submit" }) }),
            /* @__PURE__ */ jsx6("li", { children: /* @__PURE__ */ jsx6("a", { href: "#interpret", children: "Interpret" }) }),
            /* @__PURE__ */ jsx6("li", { children: /* @__PURE__ */ jsx6("a", { href: "#record", children: "Reproducibility" }) })
          ] })
        ]
      }
    ),
    /* @__PURE__ */ jsxs5("div", { className: "space-y-6", children: [
      /* @__PURE__ */ jsxs5(GuideSection, { id: "before-running", title: "Before running", children: [
        /* @__PURE__ */ jsx6("p", { children: "An administrator must approve a newly registered account; no approval email is sent. Ask the administrator directly, then sign in." }),
        /* @__PURE__ */ jsxs5(Caveat, { children: [
          "The only engine is ",
          /* @__PURE__ */ jsx6("strong", { children: "LocalEngine" }),
          ", which reports real measurements from an incomplete pipeline \u2014 never simulated numbers. Check",
          " ",
          /* @__PURE__ */ jsx6(HelpLink, { href: "/api/version", children: "/api/version" }),
          ":",
          " ",
          /* @__PURE__ */ jsx6("code", { children: "engine_version" }),
          " identifies the build, while capability listings show availability\u2014not scientific completeness. A family can be listed as available and still refuse to build for want of a payload library."
        ] }),
        /* @__PURE__ */ jsxs5("p", { children: [
          "See the repository's",
          " ",
          /* @__PURE__ */ jsx6(HelpLink, { href: `${BASE2}/docs/development.md`, children: "development setup" }),
          ", ",
          /* @__PURE__ */ jsx6(HelpLink, { href: `${BASE2}/docs/engine.md`, children: "engine scope" }),
          ", and the ",
          /* @__PURE__ */ jsx6(HelpLink, { href: "/faq#engine-mode", children: "engine-mode FAQ" }),
          "."
        ] })
      ] }),
      /* @__PURE__ */ jsxs5(GuideSection, { id: "local-setup", title: "Reproducible local setup", children: [
        /* @__PURE__ */ jsxs5("p", { children: [
          "A ",
          /* @__PURE__ */ jsx6("code", { children: ".env" }),
          " file is optional for local development because settings have defaults. Use the repository-pinned Python 3.13,",
          " ",
          /* @__PURE__ */ jsx6("code", { children: "uv" }),
          ", and Node 22+."
        ] }),
        /* @__PURE__ */ jsx6(CodeBlock, { code: SETUP, label: "bash" }),
        /* @__PURE__ */ jsxs5("p", { children: [
          "Run the web process and supervised worker together, then open",
          " ",
          /* @__PURE__ */ jsx6(HelpLink, { href: "http://localhost:8000", children: "http://localhost:8000" }),
          ". The worker starts automatically and restarts if it exits."
        ] }),
        /* @__PURE__ */ jsx6(CodeBlock, { code: RUN, label: "bash" })
      ] }),
      /* @__PURE__ */ jsxs5(GuideSection, { id: "choose-input", title: "1. Choose the host and input", children: [
        /* @__PURE__ */ jsxs5("p", { children: [
          /* @__PURE__ */ jsx6("strong", { children: "Differential Expression:" }),
          " choose a public catalog comparison or upload an existing DE result, not raw counts. This flow does not run differential-expression analysis. LocalEngine supports this path for E. coli, yeast, C. acnes, and Human; gene identifiers must resolve in the bundled reference."
        ] }),
        /* @__PURE__ */ jsxs5("p", { children: [
          /* @__PURE__ */ jsx6("strong", { children: "Direct Trigger mRNA:" }),
          " paste the known transcript sequence. This bypasses DE discovery and supports E. coli, yeast, C. acnes, and Human expression constructs. Human uses a CMV promoter and hGH polyadenylation signal; upload a custom mammalian backbone for a complete vector, or choose no backbone for an expression cassette.",
          " ",
          /* @__PURE__ */ jsx6("strong", { children: "Specific Gene:" }),
          " resolve a stable gene ID or an unambiguous symbol to its bundled reference transcript, then submit directly."
        ] }),
        /* @__PURE__ */ jsxs5(Caveat, { children: [
          "Upload validation accepts ",
          /* @__PURE__ */ jsx6("code", { children: ".csv" }),
          ", ",
          /* @__PURE__ */ jsx6("code", { children: ".tsv" }),
          ",",
          " ",
          /* @__PURE__ */ jsx6("code", { children: ".txt" }),
          ", and ",
          /* @__PURE__ */ jsx6("code", { children: ".xlsx" }),
          ", and all four formats are read by the engine. The default upload limit is 100 MB and is configurable with ",
          /* @__PURE__ */ jsx6("code", { children: "MAX_DATASET_MB" }),
          ". A \u201CVALID\u201D upload is shallow file validation."
        ] }),
        /* @__PURE__ */ jsxs5("p", { children: [
          "Include a recognized gene identifier and fold-change column.",
          " ",
          /* @__PURE__ */ jsx6("code", { children: "FC" }),
          " and ",
          /* @__PURE__ */ jsx6("code", { children: "fold_change" }),
          " are treated as already-log2 values. Supply ",
          /* @__PURE__ */ jsx6("code", { children: "log2(target/control)" }),
          " values and prefer ",
          /* @__PURE__ */ jsx6("code", { children: "log2FoldChange" }),
          "."
        ] })
      ] }),
      /* @__PURE__ */ jsxs5(GuideSection, { id: "configure", title: "2. Validate and configure logic", children: [
        /* @__PURE__ */ jsx6("p", { children: "Confirm the chosen dataset or transcript. The current LocalEngine builds a single-trigger path. The A/B fields illustrate future logic; arbitrary A AND NOT B and multi-gene Boolean design are not implemented." }),
        /* @__PURE__ */ jsx6("p", { children: "Choose only mechanisms reported available. Capability availability does not imply a complete scientific pipeline." })
      ] }),
      /* @__PURE__ */ jsxs5(
        GuideSection,
        {
          id: "payload-vector",
          title: "3. Choose a payload and vector",
          children: [
            /* @__PURE__ */ jsx6("p", { children: "Select at least one downstream output. Selecting several asks the engine for separate output-specific candidates; it does not create one fused, multi-output plasmid. \u201COther\u201D requires a custom coding sequence. A displayed output can still be unbuildable for the chosen host; inspect warnings or the failure summary rather than assuming every UI selection is supported by LocalEngine." }),
            /* @__PURE__ */ jsxs5("p", { children: [
              "Choose a catalog vector, no backbone, or Custom. Custom requires GenBank input. Yeast has no bundled catalog backbone, so use a custom backbone or accept no backbone. \u201CNo backbone\u201D is a bare construct, not a promised complete orderable vector. See",
              " ",
              /* @__PURE__ */ jsx6(HelpLink, { href: "/faq#payload-vector", children: "payload and host issues" }),
              "."
            ] })
          ]
        }
      ),
      /* @__PURE__ */ jsx6(GuideSection, { id: "submit", title: "4. Submit and observe status", children: /* @__PURE__ */ jsxs5("p", { children: [
        "Submit with ",
        /* @__PURE__ */ jsx6("strong", { children: "Compile & Optimize" }),
        ". The configuration is frozen and queued. Keep the run URL and watch its status; ",
        /* @__PURE__ */ jsx6("code", { children: "./do dev" }),
        " includes the worker. A failed run exposes its safe ",
        /* @__PURE__ */ jsx6("code", { children: "error_summary" }),
        "."
      ] }) }),
      /* @__PURE__ */ jsxs5(GuideSection, { id: "interpret", title: "5. Interpret results and downloads", children: [
        /* @__PURE__ */ jsxs5("p", { children: [
          "Open a completed run, select a candidate, then choose ",
          /* @__PURE__ */ jsx6("strong", { children: "RNA Structure" }),
          " ",
          "beside Plasmid Map and Logic Circuit. The cernal-rnaviz drawing shows the saved switch structure; zoom, rotate, or select a nucleotide to inspect it. Region labels appear only when the saved architecture matches the sequence. An ",
          /* @__PURE__ */ jsx6("strong", { children: "Intended target structure" }),
          " is the designed pairing pattern, not a predicted OFF/ON fold or experimental validation. Missing structures are shown as unavailable, and historical multi-gate candidates show only their primary switch. Viewing a structure does not refold or modify the run."
        ] }),
        /* @__PURE__ */ jsxs5("p", { children: [
          "Scores are weighted rankings, not probabilities of experimental success. Missing metrics mean \u201Cnot measured,\u201D not zero. In Precision Filters, enable ",
          /* @__PURE__ */ jsx6("strong", { children: "Show rejected candidates" }),
          " to see stored rejected rows and their reasons. Trigger windows filtered or skipped before candidate creation may instead be summarized in run warnings."
        ] }),
        /* @__PURE__ */ jsx6("p", { children: "For bacterial toeholds, leakage is AUG-only mean marginal accessibility over three bases, not the wider initiation footprint; the target leaves AUG in an unpaired bulge. Dynamic range divides ON accessibility by OFF accessibility with a 0.001 denominator floor, not measured expression. The success sigmoid is not a calibrated cellular probability. Ensemble defect has no calibrated functional cutoff. These metrics do not establish transcriptome-wide off-target or wet-lab validation." }),
        /* @__PURE__ */ jsxs5("p", { children: [
          "The results page currently does not render run-level warnings. Inspect them in ",
          /* @__PURE__ */ jsxs5("code", { children: [
            "GET /api/runs/",
            "{run_id}"
          ] }),
          " through the",
          " ",
          /* @__PURE__ */ jsx6(HelpLink, { href: "/api-docs", children: "API Reference" }),
          ", or download",
          " ",
          /* @__PURE__ */ jsx6("code", { children: "manifest.json" }),
          ". Inspect the frozen configuration through",
          " ",
          /* @__PURE__ */ jsxs5("code", { children: [
            "GET /api/runs/",
            "{run_id}",
            "/detail"
          ] }),
          "."
        ] }),
        /* @__PURE__ */ jsxs5("p", { children: [
          "Every successfully imported run gets the platform's per-run candidate table ",
          /* @__PURE__ */ jsx6("code", { children: "summary.csv" }),
          " and",
          " ",
          /* @__PURE__ */ jsx6("code", { children: "manifest.json" }),
          ". LocalEngine additionally emits the per-run",
          " ",
          /* @__PURE__ */ jsx6("code", { children: "candidates.csv" }),
          ", plus FASTA, GenBank and SBOL files for accepted switch candidates. Those sequence files appear only once the safety screen releases a sequence; with no screening adapter provisioned the gate holds every one, leaving the candidate table and per-candidate safety audits. ZIP downloads package the existing artifacts. The current LocalEngine does not generate PDF, structure-figure, or circuit-diagram artifacts; the in-app schematic views are separate. Partner ordering is disabled."
        ] })
      ] }),
      /* @__PURE__ */ jsxs5(GuideSection, { id: "record", title: "6. Keep a reproducibility record", children: [
        /* @__PURE__ */ jsx6("p", { children: "The manifest records parameters, engine version, scoring-profile label, seed, warnings, timestamps, candidate count, and the input mode plus trigger sequence or dataset name. It is useful provenance, but not the whole reproducibility record." }),
        /* @__PURE__ */ jsxs5("p", { children: [
          "Preserve the original DE file, dataset and artifact checksums, idempotency key, Git commit, and dependency environment separately. Reusing an idempotency key returns the existing run rather than recomputing it. The engine is seeded from the run's seed, so a new seed can change simulated output even with the same seed. Different engines, versions, profiles, or environments need not produce byte-identical output. Continue with the",
          " ",
          /* @__PURE__ */ jsx6(HelpLink, { href: "/faq#reproducibility", children: "reproducibility FAQ" }),
          "."
        ] })
      ] })
    ] })
  ] });
}

// src/routes/use-cases.tsx
import { createFileRoute as createFileRoute2 } from "@tanstack/react-router";
import { Lightbulb } from "lucide-react";
import { Fragment as Fragment4, jsx as jsx7, jsxs as jsxs6 } from "react/jsx-runtime";
var Route2 = createFileRoute2("/use-cases")({
  component: () => /* @__PURE__ */ jsx7(RequireAuth, { children: /* @__PURE__ */ jsx7(AppShell, { children: /* @__PURE__ */ jsx7(UseCasesContent, {}) }) })
});
var WORKFLOWS = [
  {
    id: "explore-interface",
    title: "Explore the interface on a small real run",
    goal: "Learn the submission, status, ranking, rejection, and download screens on a run small enough to finish quickly.",
    input: "A public dataset or a pasted transcript, on the default LocalEngine installation.",
    output: "Real, reproducible candidates and artifacts \u2014 the same ones a full run produces, just fewer.",
    limit: "The pipeline is incomplete: off-target specificity is not measured, and state separation and orthogonality are not computed by any gate family, so they report blank. Candidates are designs to test, not validated predictions.",
    href: "/guide#before-running",
    next: "Check what the engine supports"
  },
  {
    id: "de-comparison",
    title: "Start from a differential-expression comparison",
    goal: "Rank single-gene trigger candidates from an existing target-versus-control comparison.",
    input: "A catalog comparison or a UTF-8 CSV/TSV table with a gene identifier and an explicit log2FoldChange column.",
    output: "Ranked candidates, rejection reasons, warnings, and the artifacts actually emitted by the run.",
    limit: "LocalEngine DE processing is currently scoped to E. coli and yeast. Upload acceptance does not prove the engine can parse or scientifically use a file.",
    href: "/guide#choose-input",
    next: "Prepare a DE input"
  },
  {
    id: "known-transcript",
    title: "Start from a known transcript",
    goal: "Skip gene discovery and scan one transcript for candidate trigger windows.",
    input: "The exact trigger mRNA sequence pasted into Direct Trigger mRNA.",
    output: "Candidate switches for that transcript, with scores, filters, warnings, and available sequence artifacts.",
    limit: "Specific Gene records a label only; it does not resolve a gene to a sequence. Direct input is a single-transcript workflow, not a multi-gene Boolean compiler.",
    href: "/guide#choose-input",
    next: "Use direct input"
  },
  {
    id: "api-runs",
    title: "Repeat and inspect runs through the API",
    goal: "Submit, poll, compare, and download runs from Python, R, MATLAB, or curl.",
    input: "An API key plus the same frozen input and parameters used for the browser workflow.",
    output: "A run ID, status, candidates, errors, and downloadable artifacts exposed by that run.",
    limit: "Idempotency prevents duplicate submission; it does not guarantee byte-identical output across different engines, versions, profiles, or environments.",
    href: "/api-docs",
    next: "Open the API Reference"
  }
];
function UseCasesContent() {
  return /* @__PURE__ */ jsxs6(Fragment4, { children: [
    /* @__PURE__ */ jsx7(
      PageHeader,
      {
        kicker: /* @__PURE__ */ jsxs6(Fragment4, { children: [
          /* @__PURE__ */ jsx7(Lightbulb, { className: "h-3 w-3" }),
          " Use Cases"
        ] }),
        title: "Choose a supported workflow",
        description: "Start with the input you have and the kind of inspection you need."
      }
    ),
    /* @__PURE__ */ jsxs6(Caveat, { children: [
      /* @__PURE__ */ jsx7("strong", { children: "Scope:" }),
      " the current LocalEngine designs from one transcript or selects single-gene triggers from DE data. Multi-gene Boolean circuit design is future work."
    ] }),
    /* @__PURE__ */ jsx7("div", { className: "mt-6 grid gap-4 lg:grid-cols-2", children: WORKFLOWS.map((item) => /* @__PURE__ */ jsx7(Panel, { children: /* @__PURE__ */ jsxs6("div", { id: item.id, className: "scroll-mt-48 lg:scroll-mt-24", children: [
      /* @__PURE__ */ jsx7("h2", { className: "text-lg font-semibold text-foreground", children: item.title }),
      /* @__PURE__ */ jsx7("dl", { className: "mt-4 space-y-3 text-sm", children: [
        ["Goal", item.goal],
        ["Required input", item.input],
        ["Observable output", item.output],
        ["Limitation", item.limit]
      ].map(([label, value]) => /* @__PURE__ */ jsxs6("div", { children: [
        /* @__PURE__ */ jsx7("dt", { className: "font-mono text-[11px] uppercase tracking-wider text-mint", children: label }),
        /* @__PURE__ */ jsx7("dd", { className: "mt-1 text-muted-foreground", children: value })
      ] }, label)) }),
      /* @__PURE__ */ jsxs6(
        "a",
        {
          href: item.href,
          className: "mt-5 inline-block text-sm font-medium text-mint underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mint",
          children: [
            item.next,
            " \u2192"
          ]
        }
      )
    ] }) }, item.id)) }),
    /* @__PURE__ */ jsx7(Panel, { className: "mt-6", children: /* @__PURE__ */ jsxs6("div", { id: "not-established", className: "scroll-mt-48 lg:scroll-mt-24", children: [
      /* @__PURE__ */ jsx7("h2", { className: "text-lg font-semibold text-foreground", children: "What CERNAL does not establish" }),
      /* @__PURE__ */ jsx7("p", { className: "mt-2 text-sm text-muted-foreground", children: "A ranking is not experimental validation, a success probability, a clinical or therapeutic claim, proof of safety, proof of specificity, or an orderable complete vector. LocalEngine does not perform real off-target scanning; human DE processing, arbitrary A AND NOT B logic, multi-gene construction, PDF reports, and partner ordering are not complete pipelines." })
    ] }) })
  ] });
}

// src/routes/faq.tsx
import { createFileRoute as createFileRoute3 } from "@tanstack/react-router";
import { CircleHelp } from "lucide-react";
import { Fragment as Fragment5, jsx as jsx8, jsxs as jsxs7 } from "react/jsx-runtime";
var BASE3 = "https://github.com/zivbental/cernal_software/blob/417f8385725a99f2d7d4bc835eeedeb5903d399f";
var Route3 = createFileRoute3("/faq")({
  component: () => /* @__PURE__ */ jsx8(RequireAuth, { children: /* @__PURE__ */ jsx8(AppShell, { children: /* @__PURE__ */ jsx8(FaqContent, {}) }) })
});
var GROUPS = [
  {
    id: "setup-access",
    title: "Setup and access",
    items: [
      {
        id: "pending-approval",
        question: "Why can\u2019t I sign in after registering?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "Accounts begin inactive until a staff administrator approves them. No approval email is sent, so contact the administrator directly. See ",
          /* @__PURE__ */ jsx8(HelpLink, { href: "/guide#before-running", children: "Before running" }),
          "."
        ] })
      },
      {
        id: "queued-worker",
        question: "Why is my run still queued?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "A worker must be running. ",
          /* @__PURE__ */ jsx8("code", { children: "./do dev" }),
          " starts and supervises it automatically. If the worker is offline, the run screen says so; your submission stays saved until it reconnects. See",
          " ",
          /* @__PURE__ */ jsx8(HelpLink, { href: "/guide#local-setup", children: "local setup" }),
          "."
        ] })
      },
      {
        id: "engine-mode",
        question: "Which engine am I running?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "Check ",
          /* @__PURE__ */ jsx8(HelpLink, { href: "/api/version", children: "/api/version" }),
          ". There is only one engine: ",
          /* @__PURE__ */ jsx8("code", { children: "LocalEngine" }),
          ", the real pipeline, and it is the default. The simulated MockEngine was removed \u2014 the product reports real measurements or it reports a failure, never fabricated numbers. Set",
          " ",
          /* @__PURE__ */ jsx8("code", { children: "CERNAL_ENGINE=engine.client.LocalEngine" }),
          " for both the web and worker processes. A local ",
          /* @__PURE__ */ jsx8("code", { children: ".env" }),
          " is optional because defaults exist. See",
          " ",
          /* @__PURE__ */ jsx8(HelpLink, { href: `${BASE3}/.env.example`, children: ".env.example" }),
          " and",
          " ",
          /* @__PURE__ */ jsx8(HelpLink, { href: `${BASE3}/docs/development.md`, children: "setup documentation" }),
          "."
        ] })
      },
      {
        id: "upload-limit",
        question: "How large can an upload be?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "The default dataset limit is 100 MB. Operators can change",
          " ",
          /* @__PURE__ */ jsx8("code", { children: "MAX_DATASET_MB" }),
          "; users cannot override it per upload. See",
          " ",
          /* @__PURE__ */ jsx8(HelpLink, { href: "/guide#choose-input", children: "input preparation" }),
          "."
        ] })
      }
    ]
  },
  {
    id: "inputs-workflows",
    title: "Inputs and supported workflows",
    items: [
      {
        id: "upload-parsing",
        question: "Why can a valid upload fail when the engine runs?",
        answer: /* @__PURE__ */ jsx8(Fragment5, { children: "Upload validation is shallow and accepts .csv, .tsv, .txt, and .xlsx. LocalEngine reads UTF-8 CSV/TSV text, requires a recognized gene identifier and usable fold-change value, and can reject or drop rows later." })
      },
      {
        id: "fold-change",
        question: "What does FC or fold_change mean?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "Those aliases are consumed as log2 fold change and are not transformed. Provide log2(target/control) values;",
          " ",
          /* @__PURE__ */ jsx8("code", { children: "log2FoldChange" }),
          " is the clearest header."
        ] })
      },
      {
        id: "gene-picker",
        question: "Does Specific Gene fetch a transcript sequence?",
        answer: /* @__PURE__ */ jsx8(Fragment5, { children: "No. It records the selection for context, then requires you to paste the exact sequence through Direct Trigger mRNA." })
      },
      {
        id: "host-scope",
        question: "Which hosts does LocalEngine support?",
        answer: /* @__PURE__ */ jsx8(Fragment5, { children: "Direct, DE, and Specific Gene input are supported for E. coli, yeast, C. acnes, and Human. Human constructs use a CMV promoter and hGH polyadenylation signal with a custom mammalian backbone or no backbone. Human discovery uses mature transcripts from Ensembl release 116." })
      },
      {
        id: "families",
        question: "Does an available gate family mean the whole pipeline is complete?",
        answer: /* @__PURE__ */ jsx8(Fragment5, { children: "No. Availability is a capability flag, not proof of scientific completeness. Follow the run warnings and current engine/version scope." })
      },
      {
        id: "boolean-logic",
        question: "Can LocalEngine compile arbitrary A AND NOT B logic?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "No. The current real path is single-trigger/single-gene. Multi-gene Boolean design remains future work. See",
          " ",
          /* @__PURE__ */ jsx8(HelpLink, { href: "/guide#configure", children: "configure logic" }),
          "."
        ] })
      },
      {
        id: "payload-vector",
        question: "How do payload and vector choices work?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "Choose at least one output. \u201COther\u201D needs a custom coding sequence, and a Custom vector needs GenBank input. Multiple outputs create separate output-specific candidates, not a fused plasmid. Yeast has no bundled catalog backbone. See",
          " ",
          /* @__PURE__ */ jsx8(HelpLink, { href: "/guide#payload-vector", children: "the payload/vector step" }),
          "."
        ] })
      }
    ]
  },
  {
    id: "results-limitations",
    title: "Results and limitations",
    items: [
      {
        id: "scores",
        question: "Is a score a probability of success?",
        answer: /* @__PURE__ */ jsx8(Fragment5, { children: "No. It is a weighted ranking under a scoring profile. It does not establish experimental success, safety, specificity, or therapeutic suitability." })
      },
      {
        id: "missing-metrics",
        question: "Does a missing metric mean zero?",
        answer: /* @__PURE__ */ jsx8(Fragment5, { children: "No. Missing means it was not measured or could not be computed, not that its raw value was zero. The scoring profile controls the penalty; the default missing-value policy treats it as worst at full weight." })
      },
      {
        id: "off-targets",
        question: "Does CERNAL perform real off-target scanning?",
        answer: /* @__PURE__ */ jsx8(Fragment5, { children: "No. LocalEngine currently uses placeholder off-target values and warnings; it does not run a real transcriptome matcher." })
      },
      {
        id: "missing-candidates",
        question: "Why are candidates absent?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "Precision Filters may hide stored rejected or low-scoring rows. Enable ",
          /* @__PURE__ */ jsx8("strong", { children: "Show rejected candidates" }),
          " to inspect stored rejection reasons. Trigger windows filtered or skipped earlier may only be summarized in warnings, rather than becoming one rejected row each."
        ] })
      },
      {
        id: "warnings",
        question: "Where are warnings and the frozen configuration?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "The run page does not currently render run-level warnings. Use the",
          " ",
          /* @__PURE__ */ jsx8(HelpLink, { href: "/api-docs", children: "API Reference" }),
          ":",
          " ",
          /* @__PURE__ */ jsxs7("code", { children: [
            "GET /api/runs/",
            "{run_id}"
          ] }),
          " returns warnings, and",
          " ",
          /* @__PURE__ */ jsxs7("code", { children: [
            "GET /api/runs/",
            "{run_id}",
            "/detail"
          ] }),
          " returns the frozen configuration. Warnings are also in ",
          /* @__PURE__ */ jsx8("code", { children: "manifest.json" }),
          "."
        ] })
      },
      {
        id: "failed-run",
        question: "Where do I find the cause of a failed run?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "The run response and page expose a safe ",
          /* @__PURE__ */ jsx8("code", { children: "error_summary" }),
          ". Report that summary and run ID\u2014not secrets or sensitive inputs."
        ] })
      },
      {
        id: "downloads",
        question: "What does a successful run provide?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "The platform creates the per-run candidate table",
          " ",
          /* @__PURE__ */ jsx8("code", { children: "summary.csv" }),
          " and ",
          /* @__PURE__ */ jsx8("code", { children: "manifest.json" }),
          ". LocalEngine additionally emits ",
          /* @__PURE__ */ jsx8("code", { children: "candidates.csv" }),
          " and, once the safety screen releases a sequence, accepted-candidate FASTA, GenBank and SBOL files. With no screening adapter provisioned the release gate holds every sequence, so a run yields the candidate table and per-candidate safety audits only. ZIP downloads bundle stored artifacts. PDF, structure-figure, and circuit-diagram downloads are not generated by LocalEngine; the in-app schematic views are separate."
        ] })
      },
      {
        id: "sharing",
        question: "Can I share a run by sending its URL?",
        answer: /* @__PURE__ */ jsx8(Fragment5, { children: "Run URLs are owner-scoped, with authorized staff access. Sharing a URL does not grant another user permission to view the run." })
      }
    ]
  },
  {
    id: "reproducibility",
    title: "Reproducibility and contributing",
    items: [
      {
        id: "repeatability",
        question: "What does manifest.json preserve?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "It records parameters, engine version, scoring-profile label, seed, warnings, timestamps, candidate count, and input mode plus trigger sequence or dataset name. Separately preserve the original DE file, dataset/artifact checksums, idempotency key, Git commit, and dependency environment. Reusing an idempotency key returns the existing run, not a fresh computation. See",
          " ",
          /* @__PURE__ */ jsx8(HelpLink, { href: "/guide#record", children: "the reproducibility checklist" }),
          "."
        ] })
      },
      {
        id: "contributing",
        question: "How should I contribute a fix?",
        answer: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          "Create a focused branch, update tests, run the documented checks, and open a pull request. Start with",
          " ",
          /* @__PURE__ */ jsx8(HelpLink, { href: `${BASE3}/docs/development.md`, children: "development.md" }),
          ", ",
          /* @__PURE__ */ jsx8(HelpLink, { href: `${BASE3}/docs/engine.md`, children: "engine.md" }),
          ", and",
          " ",
          /* @__PURE__ */ jsx8(HelpLink, { href: `${BASE3}/frontend/src/routes/compile.tsx`, children: "the compiler source" }),
          ". Source code wins when historical prose disagrees."
        ] })
      },
      {
        id: "security-privacy",
        question: "What belongs in a bug report?",
        answer: /* @__PURE__ */ jsx8(Fragment5, { children: "Include reproducible steps, safe error text, versions, and non-sensitive fixtures. Remove secrets, personal information, unpublished sequences, and sensitive datasets." })
      }
    ]
  }
];
function FaqContent() {
  return /* @__PURE__ */ jsxs7(Fragment5, { children: [
    /* @__PURE__ */ jsx8(
      PageHeader,
      {
        kicker: /* @__PURE__ */ jsxs7(Fragment5, { children: [
          /* @__PURE__ */ jsx8(CircleHelp, { className: "h-3 w-3" }),
          " FAQ"
        ] }),
        title: "Frequently asked questions",
        description: "Direct answers about setup, supported inputs, results, and repeatability."
      }
    ),
    /* @__PURE__ */ jsx8(
      "nav",
      {
        "aria-label": "FAQ topics",
        className: "mb-6 flex flex-wrap gap-3 text-sm text-mint",
        children: GROUPS.map((group) => /* @__PURE__ */ jsx8("a", { href: `#${group.id}`, children: group.title }, group.id))
      }
    ),
    /* @__PURE__ */ jsx8("div", { className: "space-y-6", children: GROUPS.map((group) => /* @__PURE__ */ jsx8(Panel, { children: /* @__PURE__ */ jsxs7(
      "section",
      {
        id: group.id,
        className: "scroll-mt-48 lg:scroll-mt-24",
        "aria-labelledby": `${group.id}-heading`,
        children: [
          /* @__PURE__ */ jsx8(
            "h2",
            {
              id: `${group.id}-heading`,
              className: "text-xl font-semibold text-foreground",
              children: group.title
            }
          ),
          /* @__PURE__ */ jsx8("div", { className: "mt-5 space-y-6", children: group.items.map((item) => /* @__PURE__ */ jsxs7("article", { id: item.id, className: "scroll-mt-48 lg:scroll-mt-24", children: [
            /* @__PURE__ */ jsx8("h3", { className: "text-base font-semibold text-foreground", children: item.question }),
            /* @__PURE__ */ jsx8("div", { className: "mt-1 text-sm leading-6 text-muted-foreground", children: item.answer })
          ] }, item.id)) })
        ]
      }
    ) }, group.id)) })
  ] });
}

// src/components/docs/MetricsChart.tsx
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { jsx as jsx9, jsxs as jsxs8 } from "react/jsx-runtime";
var METRICS = [
  { name: "state_separation", label: "State separation", direction: "higher", weight: 3, validRange: [0, 10], unit: "log2 fold", description: "Log2 fold between the base and target expression state." },
  { name: "predicted_leakage", label: "Predicted leakage", direction: "lower", weight: 2.5, validRange: [0, 1], unit: "fraction 0\u20131", description: "Bacterial loop layout: AUG-only three-base mean marginal accessibility, not the wider initiation footprint or measured leakage." },
  { name: "trigger_accessibility", label: "Trigger accessibility", direction: "higher", weight: 2, validRange: [0, 1], unit: "fraction 0\u20131", description: "Fraction of the trigger region predicted free of self-structure." },
  { name: "gate_folding_energy", label: "Gate folding energy", direction: "lower", weight: 2, validRange: [-60, 0], unit: "kcal/mol", description: "Predicted MFE of the gate. More negative is more stable." },
  { name: "dynamic_range", label: "Dynamic range", direction: "higher", weight: 2, validRange: [1, 500], unit: "accessibility ratio", description: "ON/OFF marginal accessibility ratio with a 0.001 denominator floor; not measured expression fold change." },
  { name: "orthogonality", label: "Orthogonality", direction: "higher", weight: 1.5, validRange: [0, 1], unit: "fraction 0\u20131", description: "Predicted independence from other gates in the same circuit." },
  { name: "predicted_success_rate", label: "Binding heuristic", direction: "higher", weight: 1, validRange: [0, 1], unit: "fraction 0\u20131", description: "Uncalibrated binding-energy sigmoid; not a cellular success probability." },
  { name: "circuit_complexity", label: "Circuit complexity", direction: "lower", weight: 1, validRange: [1, 10], unit: "component count", description: "Component count penalty. Simpler circuits are easier to build." },
  { name: "gc_content", label: "GC content", direction: "higher", weight: 0.5, validRange: [30, 70], unit: "percent 0\u2013100", description: "Percent GC of the regulatory-switch sequence, not the full assembled construct." }
];

// e2e/.help-entry.tsx
import { jsx as jsx10 } from "react/jsx-runtime";
globalThis.__metricHelp = METRICS;
globalThis.__help = {
  "/guide": renderToStaticMarkup(/* @__PURE__ */ jsx10(GuideContent, {})),
  "/use-cases": renderToStaticMarkup(/* @__PURE__ */ jsx10(UseCasesContent, {})),
  "/faq": renderToStaticMarkup(/* @__PURE__ */ jsx10(FaqContent, {}))
};
