/**
 * capture.mjs — 실행 중인 앱(jsdom + 실 브리지)의 "실제 DOM"을 PNG로 렌더링.
 *
 * 배경: 이 샌드박스는 Chromium 계열 브라우저 바이너리를 설치할 수 없다
 * (플레이라이트/퍼펫티어 CDN·데비안 미러 전부 네트워크 차단, QtWebEngine은
 * 시스템 라이브러리 17종 누락). 대신:
 *   1) jsdom으로 React 앱을 실제 기동(브리지/vite 프록시 통해 실 데이터)
 *   2) 컴파일된 Tailwind CSS를 파싱해 각 엘리먼트에 computed style 인라인화
 *      (미니 CSS 엔진: 셀렉터 매칭 + 캐스케이드 + var()/calc() 해석)
 *   3) satori(flexbox 레이아웃 엔진)로 SVG 생성
 *   4) @resvg/resvg-js로 PNG 래스터화 (Noto Sans KR 폰트 내장)
 *
 * 한계: block 레이아웃은 flex로 근사, box-shadow/filter 등 미지원 속성 생략.
 * 사용: cd frontend && npm run build && node capture.mjs
 * 산출물: ../screenshots/ui-basic-{dark,light}.png
 */
import fs from "node:fs";
import path from "node:path";

import { JSDOM, VirtualConsole } from "jsdom";
import satori from "satori";
import { Resvg } from "@resvg/resvg-js";

const BASE = "http://127.0.0.1:5173";
const W = 1280;
const H = 800;
const OUT_DIR = path.resolve("../screenshots");
const FONT_DIR = "./node_modules/@embedpdf/fonts-kr/fonts";
const FONT_NAME = "Noto Sans KR";

// ─────────────────────────── 1. jsdom 기동 (scenarios.mjs와 동일 스텁) ───────────────────────────

const vc = new VirtualConsole(); // 앱 console.error 무시(렌더만 관심)
const dom = new JSDOM('<!doctype html><html lang="ko" data-theme="dark"><body><div id="root"></div></body></html>', {
  url: `${BASE}/`,
  pretendToBeVisual: true,
  virtualConsole: vc,
});
const { window } = dom;
const { document } = window;

globalThis.window = window;
globalThis.document = document;
Object.defineProperty(globalThis, "navigator", { value: window.navigator, configurable: true });
globalThis.location = window.location;
globalThis.localStorage = window.localStorage;
globalThis.getComputedStyle = window.getComputedStyle.bind(window);
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16);
globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
globalThis.MutationObserver = window.MutationObserver;
for (const k of ["HTMLElement", "Element", "Node", "Event", "CustomEvent", "MouseEvent", "FocusEvent", "KeyboardEvent"]) {
  globalThis[k] = window[k];
}

Object.defineProperty(window.HTMLElement.prototype, "clientHeight", { get: () => 800, configurable: true });
Object.defineProperty(window.HTMLElement.prototype, "offsetHeight", { get: () => 800, configurable: true });
window.Element.prototype.scrollTo = function () {};

class EventSourceStub {
  static CLOSED = 2;
  constructor() { this.readyState = 1; }
  close() { this.readyState = 2; }
}
globalThis.EventSource = EventSourceStub;
window.EventSource = EventSourceStub;

const nodeFetch = globalThis.fetch;
const wrapped = (input, init) => nodeFetch(new URL(typeof input === "string" ? input : input.url, BASE), init);
globalThis.fetch = wrapped;
window.fetch = wrapped;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

async function invoke(cmd, params = {}) {
  const res = await wrapped(`${BASE}/sidecar/invoke`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd, params }),
  });
  return res.json();
}

function setInput(el, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(el, value);
  el.dispatchEvent(new window.Event("input", { bubbles: true }));
  el.dispatchEvent(new window.Event("change", { bubbles: true }));
}
const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
const footer = () => $("footer")?.textContent ?? "";
const searchInput = () => $('input[placeholder*="메일 검색"]');
const searchBtn = () => $$("button.btn-primary").find((b) => b.textContent.includes("검색"));

async function waitFor(fn, label, timeout = 20000) {
  const t0 = Date.now();
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() - t0 > timeout) throw new Error(`waitFor 타임아웃: ${label}`);
    await sleep(60);
  }
}

// 데이터 준비: 앱 기동 "전에" 인덱스 + 검색 이력(연관 검색어 칩 노출용)
const built = await invoke("index.build");
if (!built.ok) throw new Error(`index.build 실패: ${JSON.stringify(built.error)}`);
for (const kw of ["견적요청", "견적", "계약 검토"]) {
  await invoke("search.query", { query: kw, record_history: true });
}

const bundle = `./dist/assets/${fs.readdirSync("./dist/assets").find((f) => f.startsWith("index-") && f.endsWith(".js"))}`;
await import(bundle);

await waitFor(() => footer().includes("사이드카 준비됨"), "사이드카 ready");
await waitFor(() => $("aside")?.textContent.includes("받은편지함"), "사이드바 폴더");

// 대표 화면: "견적서" 검색 결과 3건
setInput(searchInput(), "견적서");
click(searchBtn());
await sleep(250);
await waitFor(() => !footer().includes("검색 중") && /결과 \d+건/.test(footer()), "검색 완료");
await waitFor(() => document.body.textContent.includes("관련 검색어"), "연관 검색어 칩");
await sleep(300); // 관련 칩 fetch 완료 대기
console.log("[capture] DOM 준비 완료:", footer().slice(0, 60));

// ─────────────────────────── 2. CSS 파서 ───────────────────────────

const cssFile = fs.readdirSync("./dist/assets").find((f) => f.startsWith("index-") && f.endsWith(".css"));
const cssText = fs.readFileSync(`./dist/assets/${cssFile}`, "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");

/** 중괄호 블록 본문 추출: i는 '{' 위치 → [body, nextIdx] */
function takeBlock(css, i) {
  let depth = 0;
  const start = i;
  for (; i < css.length; i++) {
    const c = css[i];
    if (c === "{") depth++;
    else if (c === "}") {
      depth--;
      if (depth === 0) return [css.slice(start + 1, i), i + 1];
    }
  }
  throw new Error("CSS 블록 불일치");
}

function parseDecls(body) {
  const out = [];
  let depth = 0;
  let cur = "";
  for (const ch of body) {
    if (ch === "(" ) depth++;
    if (ch === ")") depth--;
    if (ch === ";" && depth === 0) {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  if (cur.trim()) out.push(cur);
  const decls = [];
  for (const d of out) {
    const ix = d.indexOf(":");
    if (ix < 0) continue;
    const prop = d.slice(0, ix).trim().toLowerCase();
    let value = d.slice(ix + 1).trim().replace(/!important$/g, "").trim();
    if (prop && value) decls.push([prop, value]);
  }
  return decls;
}

const rules = []; // {sel, decls, order}
const twProps = {}; // @property initial-value (--tw-*)
let order = 0;

function walkCSS(css) {
  let i = 0;
  while (i < css.length) {
    // 다음 '{' 또는 ';'까지 프리루드
    let j = i;
    let brace = -1;
    let semi = -1;
    for (; j < css.length; j++) {
      if (css[j] === "{") { brace = j; break; }
      if (css[j] === ";") { semi = j; break; }
    }
    if (brace < 0 && semi < 0) break;
    if (semi >= 0 && (brace < 0 || semi < brace)) {
      i = semi + 1; // @layer a,b; 같은 문장형 → 무시
      continue;
    }
    const prelude = css.slice(i, brace).trim();
    const [body, next] = takeBlock(css, brace);
    i = next;
    if (prelude.startsWith("@")) {
      const name = prelude.split(/[\s(]/)[0];
      if (name === "@property") {
        const m = prelude.match(/^@property\s+(--[\w-]+)/);
        const iv = body.match(/initial-value:\s*([^;]+)/);
        if (m && iv) twProps[m[1]] = iv[1].trim();
      } else if (name === "@media") {
        if (!/hover/.test(prelude)) walkCSS(body); // 프린트 등은 skip, 그 외 flatten
      } else if (name === "@supports" || name === "@layer" || name === "@container") {
        walkCSS(body); // layer는 파일 순서 = 캐스케이드 순서이므로 그대로 flatten
      } // @font-face, @keyframes → skip
      continue;
    }
    const decls = parseDecls(body);
    if (!decls.length) continue;
    for (const raw of prelude.split(",")) {
      const sel = raw.trim();
      if (sel) rules.push({ sel, decls, order: order++ });
    }
  }
}
walkCSS(cssText);
console.log(`[capture] CSS 규칙 ${rules.length}개, @property ${Object.keys(twProps).length}개`);

// ─────────────────────────── 3. 셀렉터 매칭 + 캐스케이드 ───────────────────────────

function unescapeCSS(s) {
  return s.replace(/\\([0-9a-fA-F]{1,6})\s?/g, (_, h) => String.fromCodePoint(parseInt(h, 16))).replace(/\\(.)/g, "$1");
}

function parseCompound(s) {
  const out = { tag: null, id: null, classes: [], attrs: [], pseudo: false };
  const re = /([#.])?([a-zA-Z-]+)?|\[([^\]]+)\]|(:{1,2}[a-z-]+(?:\([^)]*\))?)|(#[\w-]+)/g;
  // 단순 수동 파싱
  let i = 0;
  let tagBuf = "";
  while (i < s.length) {
    const c = s[i];
    if (c === ".") {
      if (tagBuf) { out.tag = tagBuf.toLowerCase(); tagBuf = ""; }
      let j = i + 1;
      let cls = "";
      while (j < s.length && !".#[: ".includes(s[j])) {
        if (s[j] === "\\") { cls += s[j] + (s[j + 1] ?? ""); j += 2; continue; }
        cls += s[j];
        j++;
      }
      out.classes.push(unescapeCSS(cls));
      i = j;
    } else if (c === "#") {
      if (tagBuf) { out.tag = tagBuf.toLowerCase(); tagBuf = ""; }
      let j = i + 1;
      let id = "";
      while (j < s.length && !".#[: ".includes(s[j])) { id += s[j]; j++; }
      out.id = unescapeCSS(id);
      i = j;
    } else if (c === "[") {
      if (tagBuf) { out.tag = tagBuf.toLowerCase(); tagBuf = ""; }
      const j = s.indexOf("]", i);
      out.attrs.push(s.slice(i + 1, j));
      i = j + 1;
    } else if (c === ":") {
      out.pseudo = true; // 의사 클래스/엘리먼트 있는 규칙은 스크린샷에서 무시
      break;
    } else if (/[a-zA-Z*-]/.test(c)) {
      tagBuf += c;
      i++;
    } else {
      i++;
    }
  }
  if (tagBuf) out.tag = tagBuf.toLowerCase();
  return out;
}

function compoundMatches(el, cp) {
  if (cp.pseudo) return false;
  if (cp.tag && cp.tag !== "*" && cp.tag !== el.tagName.toLowerCase()) return false;
  if (cp.id && cp.id !== el.id) return false;
  for (const cls of cp.classes) if (!el.classList.contains(cls)) return false;
  for (const a of cp.attrs) {
    const m = a.match(/^([\w-]+)(?:([~|^$*]?=)(?:"([^"]*)"|'([^']*)'|([^\]]*)))?$/);
    if (!m) return false;
    const [, name, op, v1, v2, v3] = m;
    const val = el.getAttribute(name);
    if (op === undefined) {
      if (val === null) return false;
    } else {
      const want = v1 ?? v2 ?? v3 ?? "";
      if (val === null) return false;
      if (op === "=" && val !== want) return false;
      if (op === "*=" && !val.includes(want)) return false;
      if (op === "^=" && !val.startsWith(want)) return false;
      if (op === "$=" && !val.endsWith(want)) return false;
    }
  }
  return true;
}

function splitSelector(sel) {
  // 콤비네이터(공백/>) 기준으로 [ {comb, cp} ... ] (왼쪽→오른쪽)
  const parts = sel.trim().split(/\s*(>)\s*|\s+/).filter((x) => x !== undefined && x !== "");
  const out = [];
  for (const p of parts) {
    if (p === ">") { out.push({ comb: ">" }); continue; }
    out.push({ cp: parseCompound(p) });
  }
  return out;
}

function selectorMatches(el, sel) {
  const parts = splitSelector(sel); // [{cp} | {comb:'>'} ...] 왼쪽→오른쪽
  if (!parts.length || !parts[parts.length - 1].cp) return false;
  let idx = parts.length - 1;
  if (!compoundMatches(el, parts[idx].cp)) return false;
  idx--;
  let node = el.parentElement;
  while (idx >= 0) {
    const part = parts[idx];
    if (part.comb === ">") {
      idx--;
      if (idx < 0 || !parts[idx].cp || !node || !compoundMatches(node, parts[idx].cp)) return false;
      node = node.parentElement;
      idx--;
      continue;
    }
    if (!part.cp) { idx--; continue; }
    let found = false;
    while (node) {
      if (compoundMatches(node, part.cp)) {
        found = true;
        node = node.parentElement;
        break;
      }
      node = node.parentElement;
    }
    if (!found) return false;
    idx--;
  }
  return true;
}

function specificity(sel) {
  let a = 0; let b = 0; let c = 0;
  for (const ch of sel) {
    if (ch === "#") a++;
    else if (ch === "." || ch === "[") b++;
  }
  c = (sel.match(/(?:^|[\s>])([a-zA-Z][\w-]*)/g) || []).length;
  return [a, b, c];
}

// ─────────────────────────── 4. var()/calc() 해석 ───────────────────────────

function buildVars(theme) {
  const vars = { ...twProps };
  const wanted = new Set([":root", ":host", `[data-theme=${theme}]`]);
  for (const r of rules) {
    const sel = r.sel.trim();
    if (wanted.has(sel)) {
      for (const [p, v] of r.decls) if (p.startsWith("--")) vars[p] = v;
    }
  }
  return vars;
}

/** var(...) 치환 — 중첩 폴백 지원. 미해석 시 "" */
function resolveVars(value, vars, depth = 0) {
  if (depth > 6 || !value.includes("var(")) return value;
  let out = "";
  let i = 0;
  while (i < value.length) {
    if (value.startsWith("var(", i)) {
      let j = i + 4;
      let d = 1;
      while (j < value.length && d > 0) {
        if (value[j] === "(") d++;
        else if (value[j] === ")") d--;
        j++;
      }
      const inner = value.slice(i + 4, j - 1);
      const comma = findTopComma(inner);
      const name = (comma < 0 ? inner : inner.slice(0, comma)).trim();
      const fallback = comma < 0 ? "" : inner.slice(comma + 1).trim();
      const resolved = vars[name] !== undefined ? vars[name] : fallback;
      out += resolveVars(resolved, vars, depth + 1);
      i = j;
    } else {
      out += value[i];
      i++;
    }
  }
  return resolveVars(out, vars, depth + 1);
}
function findTopComma(s) {
  let d = 0;
  for (let i = 0; i < s.length; i++) {
    const c = s[i];
    if (c === "(" || c === "[") d++;
    else if (c === ")" || c === "]") d--;
    else if (c === "," && d === 0) return i;
  }
  return -1;
}

/** calc() — px/무단위 숫자 산술만 지원, 그 외 null */
function evalCalc(value) {
  if (!value.startsWith("calc(")) return value;
  const expr = value.slice(5, -1);
  if (expr.includes("%")) return null; // % 산술은 근사 불가
  const hasUnit = /px|rem/.test(expr);
  const js = expr
    .replace(/(-?[\d.]+)px/g, "$1")
    .replace(/(-?[\d.]+)rem/g, (_, n) => String(Number(n) * 16));
  if (/[^-+*/().\d\s]/.test(js)) return null;
  try {
    // eslint-disable-next-line no-eval
    const n = Function(`"use strict";return (${js})`)();
    if (typeof n !== "number" || !Number.isFinite(n)) return null;
    const r = Math.round(n * 1000) / 1000;
    return hasUnit ? `${r}px` : String(r);
  } catch {
    return null;
  }
}

// ─────────────────────────── 5. 엘리먼트별 computed style ───────────────────────────

const KEEPCATS = [
  /^display$/, /^flex/, /^gap$/, /^row-gap$/, /^column-gap$/, /^align-/, /^justify-/,
  /^position$/, /^top$/, /^left$/, /^right$/, /^bottom$/,
  /^width$/, /^height$/, /^min-/, /^max-/,
  /^margin/, /^padding/, /^overflow/, /^border(?!-image)/, /^border-radius/,
  /^background(-color)?$/, /^color$/, /^font-/, /^line-height$/, /^letter-spacing$/,
  /^text-align$/, /^text-overflow$/, /^white-space$/, /^text-transform$/, /^opacity$/,
];

function computedFor(el, themeVars) {
  const matched = [];
  for (const r of rules) {
    if (selectorMatches(el, r.sel)) matched.push(r);
  }
  matched.sort((x, y) => {
    const sx = specificity(x.sel);
    const sy = specificity(y.sel);
    for (let k = 0; k < 3; k++) if (sx[k] !== sy[k]) return sx[k] - sy[k];
    return x.order - y.order;
  });
  const merged = {};
  for (const r of matched) for (const [p, v] of r.decls) merged[p] = v;

  const style = {};
  for (const [p, raw] of Object.entries(merged)) {
    if (p.startsWith("--")) continue;
    if (!KEEPCATS.some((re) => re.test(p))) continue;
    let v = resolveVars(raw, themeVars).trim();
    if (!v || v.includes("color-mix") || v.includes("env(") || v.includes("var(")) continue;
    if (/^[\d.\s]+$/.test(v) && p.startsWith("background")) continue; // "background: 0 0" 리셋 값 — satori 파싱 불가
    if (["inherit", "initial", "unset", "revert", "revert-layer", "currentcolor"].includes(v.toLowerCase())) continue;
    if (v.startsWith("calc(")) {
      v = evalCalc(v);
      if (v === null) continue;
    }
    style[p] = v;
  }

  // 속성 정규화
  if (style["font-family"]) style["font-family"] = FONT_NAME;
  if (style.position === "sticky" || style.position === "fixed") style.position = "absolute";
  if (style.position === "absolute" && style.top === "50%") style.top = "30%"; // translateY(-50%) 미지원 근사
  if (style.overflow === "auto" || style.overflow === "scroll") style.overflow = "hidden";
  if (style["overflow-y"] === "auto" || style["overflow-y"] === "scroll") style["overflow-y"] = "hidden";
  if (style["line-height"] === "normal") delete style["line-height"];
  // satori 허용값: flex | block | contents | none | -webkit-box
  const disp = style.display;
  if (disp === "inline-flex") style.display = "flex";
  else if (disp === "inline-block" || disp === "list-item" || disp === "grid") style.display = "block";
  else if (disp === "inline") delete style.display;
  // camelCase 변환
  const out = {};
  for (const [p, v] of Object.entries(style)) {
    out[p.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = v;
  }
  return { style: out, hasDisplayNone: merged.display === "none" || merged.visibility === "hidden" };
}

// ─────────────────────────── 6. satori 트리 변환 ───────────────────────────

const TAG_MAP = {
  aside: "div", main: "div", header: "div", footer: "div", section: "div", nav: "div",
  ul: "div", ol: "div", li: "div", button: "div", a: "div", label: "div", form: "div",
  article: "div", fieldset: "div", h1: "div", h2: "div", h3: "div", h4: "div", h5: "div", h6: "div",
};

const SVG_PASSTHROUGH = ["d", "cx", "cy", "r", "rx", "ry", "x", "y", "x1", "y1", "x2", "y2", "points", "width", "height"];
const SVG_STYLEABLE = ["fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "opacity", "stroke-dasharray"];

function convertSvg(svgEl, inheritedColor) {
  const attrs = {};
  for (const a of svgEl.attributes) attrs[a.name] = a.value;
  const style = computedFor(svgEl, currentVars).style;
  const w = style.width ?? attrs.width ?? "24";
  const h = style.height ?? attrs.height ?? "24";
  const root = {
    fill: "none",
    stroke: "currentColor",
    "stroke-width": "2",
    "stroke-linecap": "round",
    "stroke-linejoin": "round",
    ...Object.fromEntries(Object.entries(attrs).filter(([k]) => SVG_STYLEABLE.includes(k))),
  };
  const children = [];
  const walkSvg = (node) => {
    for (const child of node.children) {
      const tag = child.tagName.toLowerCase();
      if (["path", "circle", "rect", "line", "polyline", "polygon", "ellipse"].includes(tag)) {
        const props = {};
        for (const a of child.attributes) {
          if (SVG_PASSTHROUGH.includes(a.name) || SVG_STYLEABLE.includes(a.name)) props[a.name] = a.value;
        }
        for (const k of SVG_STYLEABLE) if (props[k] === undefined && root[k] !== undefined) props[k] = root[k];
        for (const k of ["fill", "stroke"]) if (props[k] === "currentColor") props[k] = inheritedColor;
        children.push({ type: tag, props });
      } else if (["g", "svg"].includes(tag)) {
        walkSvg(child);
      }
    }
  };
  walkSvg(svgEl);
  const svgStyle = { display: "flex", flexShrink: "0" };
  for (const k of ["position", "left", "top", "right", "bottom", "opacity", "color"]) {
    if (style[k]) svgStyle[k] = style[k];
  }
  const node = {
    type: "svg",
    props: { width: w, height: h, viewBox: attrs.viewBox ?? `0 0 24 24`, style: svgStyle, children },
  };
  if (style.opacity) node.props.opacity = style.opacity;
  return node;
}

let currentVars = {};

function convertNode(node) {
  if (node.nodeType === 3) {
    const t = node.textContent;
    return t.trim() ? t.replace(/\s+/g, " ") : null;
  }
  if (node.nodeType !== 1) return null;
  const tag = node.tagName.toLowerCase();
  if (["style", "script", "noscript", "template", "option", "optgroup", "br", "head", "title", "meta", "link"].includes(tag)) {
    if (tag === "br") return "\n";
    return null;
  }

  const { style, hasDisplayNone } = computedFor(node, currentVars);
  if (hasDisplayNone) return null;
  if (node.classList.contains("invisible") || node.classList.contains("sr-only")) return null;

  const color = style.color ?? currentVars["--text"] ?? "#000";

  // SVG 아이콘
  if (tag === "svg") return convertSvg(node, color);

  // input 계열 특수 렌더
  if (tag === "input") {
    const type = (node.getAttribute("type") ?? "text").toLowerCase();
    if (type === "checkbox" || type === "radio") {
      const size = style.width ?? style.height ?? "16px";
      const checked = node.checked;
      const boxStyle = {
        width: size, height: size,
        border: `1px solid ${checked ? currentVars["--accent"] : currentVars["--border-strong"]}`,
        borderRadius: type === "radio" ? "50%" : "4px",
        background: checked ? currentVars["--accent"] : "transparent",
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: "0",
      };
      return {
        type: "div",
        props: { style: boxStyle },
        children: checked ? [{ type: "span", props: { style: { color: "#fff", fontSize: "10px", lineHeight: "1" }, children: ["✓"] } }] : [],
      };
    }
    const value = node.value ?? "";
    const placeholder = node.getAttribute("placeholder") ?? "";
    const inputStyle = { ...style, display: "flex", alignItems: "center" };
    return {
      type: "div",
      props: {
        style: inputStyle,
        children: [
          {
            type: "span",
            props: {
              style: {
                color: value ? (style.color ?? "#000") : (currentVars["--text-faint"] ?? "#888"),
                fontSize: style.fontSize ?? "13px",
                overflow: "hidden",
                whiteSpace: "pre",
              },
              children: [value || placeholder],
            },
          },
        ],
      },
    };
  }

  if (tag === "select") {
    const selected = node.selectedOptions?.[0];
    const text = selected?.textContent ?? node.options?.[0]?.textContent ?? "";
    const selStyle = { ...style, display: "flex", alignItems: "center" };
    return {
      type: "div",
      props: {
        style: selStyle,
        children: [
          { type: "span", props: { style: { fontSize: style.fontSize ?? "13px", overflow: "hidden", whiteSpace: "pre" }, children: [text] } },
          { type: "span", props: { style: { marginLeft: "auto", fontSize: "10px", color: currentVars["--text-dim"] ?? "#888", paddingLeft: "4px" }, children: ["▼"] } },
        ],
      },
    };
  }

  const type = TAG_MAP[tag] ?? (["div", "span", "p", "b", "i", "u", "strong", "em", "img", "code", "pre", "hr"].includes(tag) ? tag : "div");
  const children = [];
  for (const child of node.childNodes) {
    const c = convertNode(child);
    if (c !== null && c !== undefined) children.push(c);
  }
  // 인접 문자열 병합
  const mergedChildren = [];
  for (const c of children) {
    if (typeof c === "string" && typeof mergedChildren[mergedChildren.length - 1] === "string") {
      mergedChildren[mergedChildren.length - 1] += c;
    } else mergedChildren.push(c);
  }
  // satori: children 배열을 가진 div는 display:flex/contents/none 명시 필수
  if (mergedChildren.length && type === "div") {
    const d = style.display;
    if (!["flex", "contents", "none"].includes(d)) {
      const INLINE = new Set(["span", "b", "i", "u", "em", "strong", "code", "small", "sup", "sub"]);
      const isAbs = (c) => typeof c !== "string" && c.props?.style?.position === "absolute";
      const flowKids = mergedChildren.filter((c) => !isAbs(c));
      const inlineFlow =
        (mergedChildren.some(isAbs) && flowKids.length === 1) || // absolute 오버레이(아이콘) + 본문 1개 래퍼
        (flowKids.some((c) => typeof c === "string") && flowKids.every((c) => typeof c === "string" || INLINE.has(c.type)));
      style.display = "flex";
      if (!style.flexDirection) style.flexDirection = inlineFlow ? "row" : "column";
      if (inlineFlow) {
        if (!style.flexWrap) style.flexWrap = "wrap";
        if (!style.alignItems) style.alignItems = "baseline";
      }
    }
  }
  const props = { style };
  if (mergedChildren.length) props.children = mergedChildren;
  return { type, props };
}

// ─────────────────────────── 7. 렌더 ───────────────────────────

const TTF_DIR = "./node_modules/@expo-google-fonts/noto-sans-kr";
const fonts = [
  { name: FONT_NAME, data: fs.readFileSync(path.join(TTF_DIR, "400Regular/NotoSansKR_400Regular.ttf")), weight: 400, style: "normal" },
  { name: FONT_NAME, data: fs.readFileSync(path.join(TTF_DIR, "500Medium/NotoSansKR_500Medium.ttf")), weight: 500, style: "normal" },
  { name: FONT_NAME, data: fs.readFileSync(path.join(TTF_DIR, "600SemiBold/NotoSansKR_600SemiBold.ttf")), weight: 600, style: "normal" },
  { name: FONT_NAME, data: fs.readFileSync(path.join(TTF_DIR, "700Bold/NotoSansKR_700Bold.ttf")), weight: 700, style: "normal" },
];

async function renderTheme(theme, outPath) {
  document.documentElement.dataset.theme = theme;
  await sleep(100);
  currentVars = buildVars(theme);
  const bodyStyle = {
    width: `${W}px`,
    height: `${H}px`,
    display: "flex",
    flexDirection: "column",
    background: currentVars["--bg"] ?? "#fff",
    color: currentVars["--text"] ?? "#000",
    fontFamily: FONT_NAME,
    fontSize: "14px",
    overflow: "hidden",
  };
  const children = [];
  for (const child of document.body.childNodes) {
    const c = convertNode(child);
    if (c !== null && c !== undefined) children.push(c);
  }
  const tree = { type: "div", props: { style: bodyStyle, children } };

  let svg;
  try {
    svg = await satori(tree, { width: W, height: H, fonts });
  } catch (e) {
    console.log(`[debug:${theme}] satori 실패: ${e.message?.slice(0, 80)} — 문제 노드 탐색 중...`);
    const probe = async (n, path) => {
      if (typeof n === "string") {
        try {
          await satori({ type: "div", props: { style: { display: "flex", fontFamily: FONT_NAME, fontSize: "14px" }, children: [n] } }, { width: 400, height: 60, fonts });
        } catch { console.log(`  TEXT BAD @${path}: ${JSON.stringify(n).slice(0, 80)}`); }
        return;
      }
      const kids = n.props?.children ?? [];
      try {
        await satori({ ...n, props: { ...n.props, style: { display: "flex", ...n.props?.style } } }, { width: 800, height: 600, fonts });
      } catch {
        console.log(`  NODE BAD @${path} <${n.type}> style=${JSON.stringify(n.props?.style ?? {}).slice(0, 200)}`);
        for (let i = 0; i < kids.length; i++) await probe(kids[i], `${path}/${n.type}[${i}]`);
      }
    };
    for (let i = 0; i < children.length; i++) await probe(children[i], `#${i}`);
    throw e;
  }

  const png = new Resvg(svg, {
    fitTo: { mode: "width", value: W * 2 }, // 2x = 레티나 급 선명도
    background: currentVars["--bg"] ?? "#ffffff",
  }).render().asPng();
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(outPath, png);
  console.log(`[capture] 저장: ${outPath} (${(png.length / 1024).toFixed(0)} KB)`);
}

await renderTheme("dark", path.join(OUT_DIR, "ui-basic-dark.png"));
await renderTheme("light", path.join(OUT_DIR, "ui-basic-light.png"));
console.log("CAPTURE_OK");
process.exit(0);
