/**
 * A2 — UI 시나리오 자동 검증 하니스 (jsdom + 실 브리지).
 *
 * 수동 시나리오 S2~S11,S14~S17을 브라우저 없이 "실제 DOM 조작"으로 검증한다.
 * 선행조건: dev_bridge.py + vite dev 실행 중 (npm run bridge / npm run dev --prefix frontend)
 * 사용: cd frontend && npm run scenarios
 *
 * 주의: 프로덕션 번들(dist)을 사용하므로 변경 후 npm run build 필수.
 */
import fs from "node:fs";

import { JSDOM, VirtualConsole } from "jsdom";

const BASE = "http://127.0.0.1:5173";

const vc = new VirtualConsole();
vc.on("jsdomError", (e) => console.log("[jsdomError]", e.message, (e.detail?.stack ?? "").split("\n")[1] ?? ""));
vc.forwardTo(console, { omitJSDOMErrors: true });
const dom = new JSDOM('<!doctype html><html data-theme="dark"><body><div id="root"></div></body></html>', {
  url: `${BASE}/`,
  pretendToBeVisual: true,
  virtualConsole: vc,
});

globalThis.window = dom.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
globalThis.location = dom.window.location;
globalThis.localStorage = dom.window.localStorage;
globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
globalThis.requestAnimationFrame = (cb) => setTimeout(() => cb(Date.now()), 16);
globalThis.cancelAnimationFrame = (id) => clearTimeout(id);
globalThis.MutationObserver = dom.window.MutationObserver;
globalThis.HTMLElement = dom.window.HTMLElement;
globalThis.Element = dom.window.Element;
globalThis.Node = dom.window.Node;
globalThis.Event = dom.window.Event;
globalThis.CustomEvent = dom.window.CustomEvent;

// 가상 스크롤(jsdom에 레이아웃 없음) — 뷰포트 크기 스텁
Object.defineProperty(dom.window.HTMLElement.prototype, "clientHeight", { get: () => 800, configurable: true });
Object.defineProperty(dom.window.HTMLElement.prototype, "offsetHeight", { get: () => 800, configurable: true });
dom.window.Element.prototype.scrollTo = function () {};

class EventSourceStub {
  static CLOSED = 2;
  constructor() {
    this.readyState = 1;
  }
  close() {
    this.readyState = 2;
  }
}
globalThis.EventSource = EventSourceStub;
dom.window.EventSource = EventSourceStub;

const nodeFetch = globalThis.fetch;
const wrapped = (input, init) => nodeFetch(new URL(typeof input === "string" ? input : input.url, BASE), init);
globalThis.fetch = wrapped;
dom.window.fetch = wrapped;

// ── 헬퍼 ──

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitFor(fn, label, timeout = 10000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    try {
      const v = fn();
      if (v) return v;
    } catch {
      /* retry */
    }
    await sleep(100);
  }
  throw new Error(`waitFor 타임아웃: ${label}`);
}

function setInput(el, value) {
  const proto =
    el.tagName === "SELECT"
      ? window.HTMLSelectElement.prototype
      : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new window.Event(el.tagName === "SELECT" ? "change" : "input", { bubbles: true }));
}

const click = (el) => el.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));

const footer = () => $("footer")?.textContent ?? "";
const resultCount = () => {
  const m = footer().match(/결과 ([\d,]+)건/);
  return m ? Number(m[1].replace(/,/g, "")) : null;
};
const idle = () => !footer().includes("검색 중") && resultCount() !== null;
const settle = () => sleep(250); // 로딩 상태 렌더 대기(구관 idle 오탐 방지)
const waitSearch = async (label) => { await settle(); await waitFor(idle, label); };
const cards = () => $$("main button").filter((b) => b.querySelector(".snippet"));
const searchInput = () => $('input[placeholder*="메일 검색"]');
const searchBtn = () => $$("button.btn-primary").find((b) => b.textContent.includes("검색"));
const dialog = () => $('[role="dialog"]');
const dialogButton = (text) =>
  [...dialog().querySelectorAll("button")].find((b) => b.textContent.includes(text));

async function invoke(cmd, params = {}) {
  const res = await wrapped(`${BASE}/sidecar/invoke`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ cmd, params }),
  });
  return res.json();
}

// ── 결과 수집 ──

const results = [];
async function scenario(id, name, fn) {
  try {
    const note = (await fn()) ?? "";
    if (!$("footer")) throw new Error("앱 트리 크래시(footer 소실)");
    results.push({ id, name, ok: true, note });
    console.log(`PASS ${id} — ${name}${note ? ` (${note})` : ""}`);
  } catch (e) {
    results.push({ id, name, ok: false, note: String(e.message ?? e) });
    console.log(`FAIL ${id} — ${name}: ${e.message ?? e}`);
  }
}

// ── 본론 ──

const bundle = `./dist/assets/${fs.readdirSync("./dist/assets").find((f) => f.startsWith("index-") && f.endsWith(".js"))}`;

// 준비: 앱 기동 "전에" 인덱스 구축 + 페이지 크기 5 (부트스트랩이 읽음 → S11 페이지네이션 표시)
const perPage = await invoke("settings.set", { patch: { search: { results_per_page: 5 } } });
if (!perPage.ok) throw new Error(`settings.set 실패: ${JSON.stringify(perPage.error)}`);
const built = await invoke("index.build");
if (!built.ok) throw new Error(`index.build 실패: ${JSON.stringify(built.error)}`);

await import(bundle);

// 준비: 사이드카 ready + 사이드바 폴더
await waitFor(() => footer().includes("사이드카 준비됨"), "사이드카 ready");
await waitFor(() => $("aside")?.textContent.includes("받은편지함"), "사이드바 폴더");

await scenario("S2", "포함 검색 vs 정확한 단어만", async () => {
  setInput(searchInput(), "견적");
  click(searchBtn());
  await waitSearch("S2 포함 검색 응답");
  const includes = resultCount();
  const label = $$("label").find((l) => l.textContent.includes("정확한 단어만"));
  click(label.querySelector("input"));
  await settle(); await waitFor(() => idle() && resultCount() !== includes, "S2 단어 검색 전환");
  const exact = resultCount();
  click(label.querySelector("input")); // 복원
  await waitSearch("S2 복원");
  if (!(includes > exact)) throw new Error(`포함(${includes}) > 단어(${exact}) 기대`);
  return `포함 ${includes}건 → 단어 ${exact}건`;
});

await scenario("S3", "다중 단어 AND (견적+검토)", async () => {
  setInput(searchInput(), "견적+검토");
  click(searchBtn());
  await waitSearch("S3 응답");
  const n = resultCount();
  if (!(n >= 1)) throw new Error(`1건 이상 기대, 실제 ${n}`);
  return `${n}건`;
});

await scenario("S6", "폴더 OR 필터 (받은+보낸 = 합집합)", async () => {
  const chip = (name) => $$("header button").find((b) => b.textContent.includes(name));
  setInput(searchInput(), "");
  click(searchBtn());
  await waitSearch("S6 전체");
  const total = resultCount();
  click(chip("받은편지함"));
  await waitSearch("S6 받은편지함");
  const inbox = resultCount();
  click(chip("보낸편지함"));
  await waitSearch("S6 OR");
  const both = resultCount();
  if (!(0 < inbox && inbox < total)) throw new Error(`받은편지함 ${inbox}건 비정상`);
  if (both !== total) throw new Error(`OR ${both} ≠ 전체 ${total} (합집합 실패)`);
  click(chip("받은편지함"));
  await waitSearch("S6 받은 해제");
  click(chip("보낸편지함"));
  await waitSearch("S6 복원");
  if (resultCount() !== total) throw new Error("필터 복원 실패");
  return `받은 ${inbox} + 보낸 ${both - inbox} = OR ${both} (legacy AND 버그 없음)`;
});

await scenario("S4", "메일 주소 검색 (발신자)", async () => {
  setInput(searchInput(), "kim.cs@company");
  click(searchBtn());
  await waitSearch("S4 주소 검색");
  const withAddr = resultCount();
  if (!withAddr) throw new Error("발신자 주소 검색 0건");
  setInput(searchInput(), "nobody@nowhere.dev");
  click(searchBtn());
  await waitSearch("S4 무관 주소");
  if (resultCount() !== 0) throw new Error(`무관 주소 ${resultCount()}건 (0 기대)`);
  return `kim.cs@company → ${withAddr}건 / 무관 주소 0건`;
});

await scenario("S5", "자동완성 드롭다운 + 기록", async () => {
  const input = searchInput();
  setInput(input, "견");
  input.dispatchEvent(new window.FocusEvent("focusin", { bubbles: true }));
  const list = await waitFor(() => $("ul.absolute"), "S5 드롭다운");
  const items = [...list.querySelectorAll("li button")].map((b) => b.textContent);
  if (items.length === 0) throw new Error("제안 없음");
  click(list.querySelector("li button"));
  await waitSearch("S5 제안 클릭 검색");
  return items.join(",");
});

await scenario("S7", "첨부 필터 칩", async () => {
  setInput(searchInput(), "");
  click(searchBtn());
  await waitSearch("S7 전체 검색");
  const all = resultCount();
  const chip = $$("button.chip").find((c) => c.textContent.includes("첨부"));
  click(chip);
  await settle(); await waitFor(() => idle() && chip.classList.contains("chip-active"), "S7 칩 활성");
  await waitSearch("S7 응답");
  const withAtt = resultCount();
  click(chip); // 해제
  await waitSearch("S7 해제");
  if (!(withAtt <= all)) throw new Error(`첨부(${withAtt}) <= 전체(${all})`);
  return `전체 ${all} → 첨부 ${withAtt}`;
});

await scenario("S8", "기간 필터 (에러 없이 응답)", async () => {
  const sel = $$("select").find((s) => [...s.options].some((o) => o.textContent.includes("최근 3개월")));
  setInput(sel, "3");
  await waitSearch("S8 기간 응답");
  setInput(sel, "0");
  await waitSearch("S8 복원");
  return "응답 정상";
});

await scenario("S9", "정렬 변경 시 순서 변화", async () => {
  const sel = $$("select").find((s) => [...s.options].some((o) => o.value === "rank"));
  setInput(sel, "oldest");
  await waitSearch("S9 oldest");
  await waitFor(() => cards().length > 0, "S9 카드");
  const firstOld = cards()[0].textContent;
  setInput(sel, "newest");
  await waitSearch("S9 newest");
  const firstNew = cards()[0].textContent;
  if (firstOld === firstNew) throw new Error("순서 변화 없음");
  return "순서 변경 확인";
});

await scenario("S10", "북마크 추가 → 사이드바 → 클릭 검색", async () => {
  setInput(searchInput(), "보고서");
  click(searchBtn());
  await waitSearch("S10 검색");
  click($('button[title="현재 검색어 북마크"]'));
  let bm = await waitFor(
    () => [...$$("aside button")].find((b) => b.textContent.includes("보고서") && b.title === "북마크 검색 실행"),
    "S10 사이드바 북마크",
  );
  setInput(searchInput(), "다른검색어");
  click(searchBtn());
  await waitSearch("S10 다른 검색");
  if (bm.textContent.includes("보고서") === false || !bm.isConnected) {
    bm = await waitFor(
      () => [...$$("aside button")].find((b) => b.textContent.includes("보고서") && b.title === "북마크 검색 실행"),
      "S10 북마크 재조회",
    );
  }
  click(bm);
  await settle(); await waitFor(() => idle() && searchInput().value === "보고서", "S10 북마크 클릭 검색");
  return "왕복 확인";
});

await scenario("S11", "가상 리스트 카드 렌더 + 상태바 쪽 정보", async () => {
  setInput(searchInput(), ""); // 전체 검색 → 15건 / 쪽당 5 = 3쪽 (준비 단계에서 per_page=5 설정)
  click(searchBtn());
  await waitSearch("S11 전체 검색");
  await waitFor(() => cards().length >= 1, "S11 카드");
  const n = cards().length;
  await waitFor(() => document.body.textContent.includes("쪽당"), "S11 쪽당 표시");
  if (!footer().includes("쪽")) throw new Error("상태바 쪽 정보 없음");
  return `카드 ${n}개 렌더 · 쪽당 표시 확인`;
});

await scenario("S14", "설정: 테마 즉시 적용 + 간격 저장", async () => {
  click($('button[title="설정"]'));
  await waitFor(dialog, "S14 다이얼로그");
  dialogButton("화면") && click(dialogButton("화면"));
  await waitFor(() => dialog().querySelector('input[name="theme"]'), "S14 테마 라디오");
  const radios = [...dialog().querySelectorAll('input[name="theme"]')];
  click(radios[1]); // light
  await waitFor(() => document.documentElement.dataset.theme === "light", "S14 테마 적용");
  click(dialogButton("동기화"));
  const intervalSel = await waitFor(
    () => [...dialog().querySelectorAll("select")].find((s) => [...s.options].some((o) => o.textContent === "15분")),
    "S14 간격 셀렉트",
  );
  setInput(intervalSel, "15");
  await sleep(300);
  click(dialog().querySelector('button[aria-label="닫기"]'));
  const conf = await invoke("settings.get");
  const minutes = conf.result?.settings?.sync?.interval_minutes;
  if (minutes !== 15) throw new Error(`interval_minutes=${minutes}`);
  // 복원
  await invoke("settings.set", { patch: { ui: { theme: "dark" }, sync: { interval_minutes: 10 } } });
  return "light 적용 + interval 15 저장 확인";
});

await scenario("S15", "자동 동기화 ON → 상태바 카운트다운", async () => {
  click($('button[title="설정"]'));
  await waitFor(dialog, "S15 다이얼로그");
  dialogButton("동기화") && click(dialogButton("동기화"));
  const label = await waitFor(
    () => [...dialog().querySelectorAll("label")].find((l) => l.textContent.includes("자동 동기화 사용")),
    "S15 자동동기화 라벨",
  );
  const box = label.querySelector("input");
  if (!box.checked) click(box);
  await sleep(300);
  click(dialog().querySelector('button[aria-label="닫기"]'));
  await waitFor(() => footer().includes("자동 동기화"), "S15 카운트다운 노출");
  // 복원
  await invoke("settings.set", { patch: { sync: { auto_sync: false } } });
  return "카운트다운 텍스트 확인";
});

await scenario("S16", "폴더 동기화: 계획 → 승인 → 완료", async () => {
  await invoke("db.reset_all", { confirm: true }); // plan이 차이나도록 인덱스 초기화
  await sleep(300);
  click($('button[title="폴더 선택 동기화"]'));
  await waitFor(dialog, "S16 다이얼로그");
  const boxes = await waitFor(
    () => {
      const list = [...dialog().querySelectorAll("input[type=checkbox]")];
      return list.length > 0 ? list : null;
    },
    "S16 폴더 목록",
  );
  for (const box of boxes) if (!box.checked) click(box); // 전체 선택
  await waitFor(() => !dialogButton("변경 계획 미리보기")?.disabled, "S16 미리보기 활성");
  click(dialogButton("변경 계획 미리보기"));
  await waitFor(() => dialog().textContent.includes("Outlook 전체:"), "S16 계획 뷰");
  const planText = dialog().textContent;
  if (!planText.includes("신규")) throw new Error("계획 수치 없음");
  const exec = await waitFor(() => dialogButton("동기화 실행"), "S16 실행 버튼");
  if (exec.disabled) throw new Error("실행 버튼 비활성 (has_changes false?)");
  click(exec);
  await waitFor(() => dialog().textContent.includes("동기화 완료"), "S16 완료 뷰", 30000);
  click(dialogButton("닫기"));
  return "plan→execute→done 흐름";
});

await scenario("S17", "장애 회복: 사이드카 응답 불가 → 오류 표시 → 복구", async () => {
  const direct = (p, init) => nodeFetch(`http://127.0.0.1:8765${p}`, init);
  const errShown = () => Boolean($('footer span[class*="--danger"]'));
  // 장애 주입(브리지 /fault) — 실 프로세스 종료는 Rust 셸 영역(Windows S17)
  const f = await (await direct("/fault", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ count: 50 }) })).json();
  if (!f.ok) throw new Error("fault 주입 실패");
  setInput(searchInput(), "견적서");
  click(searchBtn());
  await waitFor(errShown, "S17 오류 표시", 8000);
  // 해제 → 자동 복구
  await direct("/fault", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ count: 0 }) });
  click(searchBtn());
  await waitSearch("S17 복구 검색");
  if (!resultCount()) throw new Error("복구 후 검색 0건");
  if (errShown()) throw new Error("복구 후에도 오류 표시 잔존");
  return "오류 표시 → 장애 해제 → 검색 복구";
});

// ── 집계 ──

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} 시나리오 PASS`);
if (failed.length) {
  for (const f of failed) console.log(`  ✗ ${f.id} ${f.name}: ${f.note}`);
}
console.log(failed.length === 0 ? "SCENARIOS_OK" : "SCENARIOS_FAIL");
process.exit(failed.length === 0 ? 0 : 1);
