/**
 * 버전 계약 (Phase 4-4).
 *
 * - PROTOCOL_VERSION: JSON Lines IPC 프로토콜 버전 — sidecar/README.md §4와 쌍.
 *   사이드카 system.info.protocol_version과 다르면 UI는 경고 배너를 띄운다.
 * - SIDECAR_MIN/MAX: 이 프런트엔드가 동작을 보장하는 사이드카 버전 범위.
 */
export const APP_VERSION = "1.0.0-react";
/** sidecar/__init__.py PROTOCOL_VERSION과 문자열 동등 비교 */
export const PROTOCOL_VERSION = "1.0";
export const SIDECAR_VERSION_MIN = "1.1.0";

export function compareSemver(a: string, b: string): number {
  const pa = a.split(".").map((n) => parseInt(n, 10) || 0);
  const pb = b.split(".").map((n) => parseInt(n, 10) || 0);
  for (let i = 0; i < 3; i++) {
    if ((pa[i] ?? 0) > (pb[i] ?? 0)) return 1;
    if ((pa[i] ?? 0) < (pb[i] ?? 0)) return -1;
  }
  return 0;
}
