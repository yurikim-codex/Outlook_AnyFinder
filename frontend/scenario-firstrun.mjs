/**
 * scenario-firstrun.mjs — S13(첫 실행 온보딩) UI 경로 자동 검증.
 *
 * 빈 DB로 앱을 기동하면 FirstRunDialog가 떠야 하고, "인덱스 만들기 시작" →
 * 진행률 → 완료 후 검색이 가능해야 한다. DB 리셋이 선행돼야 하므로
 * 메인 하네스(scenarios.mjs)와 분리해 별도 프로세스로 실행한다.
 *
 * 선행조건: dev_bridge.py + vite dev 실행 중
 * 사용: cd frontend && node scenario-firstrun.mjs   (npm run scenarios에 체인됨)
 */
import fs from "node:fs";

import { JSDOM, VirtualConsole } from "jsdom";

const BASE = "http://127.0.0.1:5173";

const vc = new VirtualConsole();
vc.on("jsdomError", (e) => console.log("[jsdomError]", e.message));
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
for (const k of ["HTMLElement", "Element", "Node", "Event", "CustomEvent", "MouseEvent", "FocusEvent"]) {
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
const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
const setInput = (el, value) => {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  setter.call(el, value);
  el.dispatchEvent(new window.Event("input", { bubbles: true }));
};
const footer = () => $("footer")?.textContent ?? "";
const dialogText = () => document.body.textContent ?? "";

async function waitFor(fn, label, timeout = 30000) {
  const t0 = Date.now();
  for (;;) {
    const v = fn();
    if (v) return v;
    if (Date.now() - t0 > timeout) throw new Error(`waitFor 타임아웃: ${label}`);
    await sleep(80);
  }
}

let failed = false;
try {
  // 1) 빈 DB 준비 (앱 기동 전)
  const reset = await invoke("db.reset_all", { confirm: true });
  if (!reset.ok) throw new Error(`db.reset_all 실패: ${JSON.stringify(reset.error)}`);

  // 2) 앱 기동
  const bundle = `./dist/assets/${fs.readdirSync("./dist/assets").find((f) => f.startsWith("index-") && f.endsWith(".js"))}`;
  await import(bundle);

  // 3) FirstRunDialog 노출
  await waitFor(() => dialogText().includes("오신 것을 환영합니다"), "S13 환영 다이얼로그");
  console.log("PASS S13-1 — 빈 DB 기동 시 FirstRunDialog 노출");

  // 4) 인덱싱 시작 → 진행률/완료
  const start = $$("button").find((b) => b.textContent.includes("인덱스 만들기 시작"));
  if (!start) throw new Error("인덱스 시작 버튼 없음");
  click(start);
  await sleep(300);
  const sawProgress =
    dialogText().includes("인덱싱") || dialogText().includes("진행");
  await waitFor(() => !dialogText().includes("오신 것을 환영합니다"), "S13 다이얼로그 종료", 60000);
  // 다이얼로그는 빌드 시작과 동시에 닫힘 → 상태바 인덱스 작업 종료까지 대기
  await waitFor(() => !footer().includes("인덱싱"), "S13 인덱스 작업 종료", 60000);
  console.log(`PASS S13-2 — 인덱싱 완료 후 다이얼로그 종료 (진행률 노출: ${sawProgress})`);

  // 5) 검색 가능
  await waitFor(() => footer().includes("사이드카 준비됨"), "S13 상태바 ready");
  const input = $('input[placeholder*="메일 검색"]');
  setInput(input, "견적서");
  const btn = $$("button.btn-primary").find((b) => b.textContent.includes("검색"));
  click(btn);
  await sleep(250);
  await waitFor(() => !footer().includes("검색 중") && /결과 \d+건/.test(footer()), "S13 검색 응답");
  const m = footer().match(/결과 (\d+)건/);
  if (!m || Number(m[1]) < 1) throw new Error(`인덱싱 후 검색 0건: ${footer()}`);
  console.log(`PASS S13-3 — 온보딩 후 검색 동작 (${m[1]}건)`);
  console.log("S13_OK");
} catch (e) {
  failed = true;
  console.log(`FAIL S13 — ${e.message}`);
  console.log("S13_FAIL");
}
process.exit(failed ? 1 : 0);
