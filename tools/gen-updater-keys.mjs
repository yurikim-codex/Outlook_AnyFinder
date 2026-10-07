/**
 * 업dater 서명 키쌍 생성 + tauri.conf.json pubkey 자동 반영 (Phase 5-6).
 *
 * 사용 (저장소 루트에서):
 *   node tools/gen-updater-keys.mjs            # 키쌍 생성(첫 1회) + conf pubkey 패치
 *   node tools/gen-updater-keys.mjs --patch-only  # 기존 키의 pubkey만 conf에 재반영
 *
 * 산출물:
 *   tools/updater-keys/updater.key      — ★비밀키★ (gitignore 됨. 릴리스 관리자 보관)
 *   tools/updater-keys/updater.key.pub  — 공개키 (conf에 자동 삽입)
 *
 * 릴리스 빌드 시 환경변수:
 *   TAURI_SIGNING_PRIVATE_KEY = updater.key 내용
 *   TAURI_SIGNING_PRIVATE_KEY_PASSWORD = (비밀번호 없음 = 빈 문자열)
 */
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const KEY_DIR = path.join(ROOT, "tools", "updater-keys");
const KEY_PATH = path.join(KEY_DIR, "updater.key");
const PUB_PATH = path.join(KEY_DIR, "updater.key.pub");
const CONF_PATH = path.join(ROOT, "src-tauri", "tauri.conf.json");

const patchOnly = process.argv.includes("--patch-only");

if (!patchOnly) {
  if (fs.existsSync(KEY_PATH)) {
    console.log("키가 이미 존재합니다 — 생성 건너뛰기 (--patch-only 와 동일하게 동작)");
  } else {
    fs.mkdirSync(KEY_DIR, { recursive: true });
    console.log("updater 서명 키쌍 생성 중…");
    // Windows: npx는 npx.cmd라 execFileSync로 직접 spawn 불가(ENOENT/EINVAL).
    // shell 경유 execSync + 수동 인용부호로 해결 (빈 비밀번호 "" 보존 포함,
    // Track B 실측 5호).
    execSync(`npx tauri signer generate -w "${KEY_PATH}" -p ""`, {
      cwd: ROOT,
      stdio: "inherit",
    });
  }
}

if (!fs.existsSync(PUB_PATH)) {
  console.error(`공개키 없음: ${PUB_PATH} — 먼저 키 생성을 실행하세요`);
  process.exit(1);
}

const pubkey = fs.readFileSync(PUB_PATH, "utf8").trim();
const conf = JSON.parse(fs.readFileSync(CONF_PATH, "utf8"));
conf.plugins ??= {};
conf.plugins.updater ??= {};
const prev = conf.plugins.updater.pubkey;
conf.plugins.updater.pubkey = pubkey;
fs.writeFileSync(CONF_PATH, JSON.stringify(conf, null, 2) + "\n", "utf8");

console.log(`pubkey 반영 완료: ${prev ? "갱신" : "신규"} → ${pubkey.slice(0, 24)}…`);
console.log("릴리스 빌드 전에 tools/updater-keys/updater.key 를 환경변수 TAURI_SIGNING_PRIVATE_KEY 로 설정하세요.");
