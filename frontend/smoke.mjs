/**
 * 프런트엔드 런타임 스모크 테스트 (jsdom) — 브라우저 없이 React 렌더 크래시 검출.
 * 실제 dev 서버(5173)의 /sidecar 프록시를 fetch로 경유해 목 사이드카와 통신한다.
 *
 * 선행조건 (별도 터미널 2개):
 *   python frontend/dev_bridge.py      (또는 루트에서 npm run bridge)
 *   npm run dev --prefix frontend
 * 사용:
 *   cd frontend && npm run smoke
 */
import fs from "node:fs";

import { JSDOM } from "jsdom";

const BASE = "http://127.0.0.1:5173";

const dom = new JSDOM('<!doctype html><html data-theme="dark"><body><div id="root"></div></body></html>', {
  url: `${BASE}/`,
  pretendToBeVisual: true,
});

globalThis.window = dom.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
globalThis.location = dom.window.location;
globalThis.localStorage = dom.window.localStorage;
globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
globalThis.MutationObserver = dom.window.MutationObserver;
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.Element = dom.window.Element;
globalThis.Node = dom.window.Node;
globalThis.Event = dom.window.Event;
globalThis.CustomEvent = dom.window.CustomEvent;
globalThis.CSS = dom.window.CSS;
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16);
globalThis.cancelAnimationFrame = (id) => clearTimeout(id);

// EventSource 스 (SSE 미사용 시나리오 충분)
class EventSourceStub {
  static CLOSED = 2;
  constructor(url) {
    this.url = url;
    this.readyState = 1;
    setTimeout(() => this.onopen?.(), 0);
  }
  close() {
    this.readyState = 2;
  }
}
globalThis.EventSource = EventSourceStub;
dom.window.EventSource = EventSourceStub;

// 상대 URL fetch → dev 서버로
const nodeFetch = globalThis.fetch;
const wrapped = (input, init) => {
  const url = typeof input === "string" ? new URL(input, BASE) : input;
  return nodeFetch(url, init);
};
globalThis.fetch = wrapped;
dom.window.fetch = wrapped;

const errors = [];
dom.window.addEventListener("error", (e) => errors.push(String(e.message)));
process.on("unhandledRejection", (r) => errors.push(`unhandledRejection: ${r}`));

const bundle =
  process.argv[2] ||
  `./dist/assets/${fs
    .readdirSync("./dist/assets")
    .find((f) => f.startsWith("index-") && f.endsWith(".js"))}`;
await import(bundle);

// 렌더 + 초기 데이터 로드 대기
await new Promise((r) => setTimeout(r, 3500));

const html = dom.window.document.body.innerHTML;
const checks = [
  ["앱 셸 타이틀", html.includes("OutLook AnyFinder")],
  ["검색 입력창", html.includes("메일 검색")],
  ["사이드바 폴더(mock)", html.includes("받은편지함")],
  ["상태바", html.includes("사이드카")],
];

let fail = 0;
for (const [name, ok] of checks) {
  console.log(`${ok ? "PASS" : "FAIL"} — ${name}`);
  if (!ok) fail++;
}
if (errors.length) {
  console.log("RUNTIME ERRORS:");
  for (const e of errors.slice(0, 10)) console.log("  ", e);
  fail++;
}
console.log(fail === 0 ? "SMOKE_OK" : `SMOKE_FAIL(${fail})`);
process.exit(fail === 0 ? 0 : 1);
