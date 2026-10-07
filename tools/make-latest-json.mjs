/**
 * latest.json 생성 — Tauri v2 업데이터 manifest (Track B 실측 6호).
 *
 * Tauri v2 CLI는 createUpdaterArtifacts: true여도 빌드 시 *.exe.sig만 만들고
 * latest.json은 만들지 않는다 — 릴리스 담당자가 직접 생성해야 한다.
 *
 * 사용 (저장소 루트에서, npm run build 완료 후):
 *   node tools/make-latest-json.mjs                     # 버전/태그는 conf 기준
 *   node tools/make-latest-json.mjs --notes "수정 내역"  # 릴리스 노트
 *   node tools/make-latest-json.mjs --tag v1.0.0        # 태그 오버라이드
 *
 * 산출물: src-tauri/target/release/bundle/nsis/latest.json
 * GitHub Release 업로드 3종: *-setup.exe, *-setup.exe.sig, latest.json
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CONF_PATH = path.join(ROOT, "src-tauri", "tauri.conf.json");
const NSIS_DIR = path.join(ROOT, "src-tauri", "target", "release", "bundle", "nsis");

const conf = JSON.parse(fs.readFileSync(CONF_PATH, "utf8"));
const version = conf.version;

const argv = process.argv.slice(2);
const opt = (name, def) => {
  const i = argv.indexOf(`--${name}`);
  return i !== -1 && argv[i + 1] !== undefined ? argv[i + 1] : def;
};
const tag = opt("tag", `v${version}`);
const notes = opt("notes", `OutLook AnyFinder ${version} 릴리스`);

// 리포 URL은 updater endpoint에서 역산 (단일 진실 공급원)
const endpoint = conf.plugins?.updater?.endpoints?.[0] ?? "";
const m = endpoint.match(/^(https:\/\/github\.com\/[^/]+\/[^/]+)\/releases\//);
if (!m) {
  console.error("conf plugins.updater.endpoints[0]에서 리포 URL을 역산할 수 없습니다:", endpoint);
  process.exit(1);
}
const repoBase = m[1];

if (!fs.existsSync(NSIS_DIR)) {
  console.error(`NSIS 산출물 디렉터리가 없습니다 — 먼저 npm run build: ${NSIS_DIR}`);
  process.exit(1);
}
const sigFile = fs.readdirSync(NSIS_DIR).find((f) => f.endsWith("-setup.exe.sig"));
if (!sigFile) {
  console.error("*-setup.exe.sig 가 없습니다 — TAURI_SIGNING_PRIVATE_KEY 설정 후 빌드했는지 확인하세요.");
  process.exit(1);
}
const exeFile = sigFile.slice(0, -".sig".length);
const signature = fs.readFileSync(path.join(NSIS_DIR, sigFile), "utf8").trim();

const latest = {
  version,
  notes,
  pub_date: new Date().toISOString(),
  platforms: {
    "windows-x86_64": {
      signature,
      url: `${repoBase}/releases/download/${tag}/${encodeURIComponent(exeFile)}`,
    },
  },
};

const out = path.join(NSIS_DIR, "latest.json");
fs.writeFileSync(out, JSON.stringify(latest, null, 2) + "\n", "utf8");
console.log(`latest.json 생성 완료: ${out}`);
console.log(JSON.stringify(latest, null, 2));
