/**
 * 릴리스 버전 일괄 범프 (Phase 5-8).
 *
 * 사용: node tools/bump-version.mjs 1.0.1 [사이드카 버전]
 *   - 앱 버전 3곳(Cargo/conf/APP_VERSION)은 항상 동기화
 *   - 사이드카 __version__은 별도 라인(프로토콜 호환 지표) — 두 번째 인자 있을 때만 갱신
 *
 * 예: node tools/bump-version.mjs 1.0.1          # 사이드카 버전 유지
 *     node tools/bump-version.mjs 1.0.1 1.2.0    # 사이드카도 함께
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const next = process.argv[2];
const nextSidecar = process.argv[3];
if (!/^\d+\.\d+\.\d+$/.test(next ?? "") || (nextSidecar && !/^\d+\.\d+\.\d+$/.test(nextSidecar))) {
  console.error("사용법: node tools/bump-version.mjs <app semver> [sidecar semver]");
  process.exit(1);
}

const edits = [
  {
    file: "src-tauri/Cargo.toml",
    replacer: (s) => s.replace(/^version = "\d+\.\d+\.\d+"$/m, `version = "${next}"`),
  },
  {
    file: "src-tauri/tauri.conf.json",
    replacer: (s) => {
      const conf = JSON.parse(s);
      conf.version = next;
      return JSON.stringify(conf, null, 2) + "\n";
    },
  },
  {
    file: "frontend/src/lib/version.ts",
    replacer: (s) => s.replace(/export const APP_VERSION = "[^"]+"/, `export const APP_VERSION = "${next}"`),
  },
  // 사이드카는 별도 버전 라인 — 명시할 때만
  ...(nextSidecar
    ? [
        {
          file: "sidecar/__init__.py",
          replacer: (s) => s.replace(/^__version__ = "\d+\.\d+\.\d+"$/m, `__version__ = "${nextSidecar}"`),
        },
      ]
    : []),
];

for (const { file, replacer } of edits) {
  const p = path.join(ROOT, file);
  const before = fs.readFileSync(p, "utf8");
  const after = replacer(before);
  if (after === before) console.warn(`  · 변경 없음(이미 동일): ${file}`);
  fs.writeFileSync(p, after, "utf8");
  console.log(`  ✔ ${file} → ${next}`);
}
console.log(`버전 범프 완료: ${next} — 커밋 전 git diff 확인하세요.`);
