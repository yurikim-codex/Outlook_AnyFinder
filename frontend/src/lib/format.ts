/** 표시용 포맷 헬퍼 (한국어 로캘 기준). */

export function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return value;
  const now = new Date();
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();
  if (sameDay) {
    return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" });
  }
  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString("ko-KR", {
    year: sameYear ? undefined : "numeric",
    month: "numeric",
    day: "numeric",
  });
}

export function formatFullDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value.replace(" ", "T"));
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return "방금";
  if (sec < 3600) return `${Math.floor(sec / 60)}분 전`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}시간 전`;
  if (sec < 86400 * 30) return `${Math.floor(sec / 86400)}일 전`;
  return formatDate(value);
}

export function formatCount(n: number): string {
  return n.toLocaleString("ko-KR");
}

export function formatMb(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb.toFixed(1)} MB`;
}

/**
 * FTS 스니펫 안전 렌더링용 — <b> 외 모든 태그 제거.
 * 사이드카 스니펫은 로컬 DB 콘텐츠이지만 방어적으로 sanitizer를 거친다.
 */
export function sanitizeSnippet(html: string): string {
  return html
    .replace(/<(?!\/?b\b)[^>]*>/gi, "")
    .replace(/<script[\s\S]*?<\/script>/gi, "");
}

export function splitAttachmentNames(raw: string): string[] {
  if (!raw) return [];
  return raw
    .split(/[;,|]/)
    .map((s) => s.trim())
    .filter(Boolean);
}
