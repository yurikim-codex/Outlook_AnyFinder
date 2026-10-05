import { Sparkles } from "lucide-react";

import { useApp } from "../lib/store";

/**
 * 연관 검색어 칩 (Parity 체크리스트 #7 — legacy 결과 하단 연관 검색어 대응).
 * 검색 완료 시 store가 search.related를 자동 조회하고, 칩 클릭은 즉시 재검색.
 */
export function RelatedChips() {
  const { relatedKeywords, doSearch, search } = useApp();
  if (!search.response || relatedKeywords.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-[var(--border)] px-3 py-1.5">
      <span className="flex shrink-0 items-center gap-1 text-[11px] text-faint">
        <Sparkles size={11} /> 관련 검색어
      </span>
      {relatedKeywords.map((kw) => (
        <button
          key={kw}
          className="chip"
          onClick={() => void doSearch({ query: kw })}
          title={`"${kw}" 로 검색`}
        >
          {kw}
        </button>
      ))}
    </div>
  );
}
