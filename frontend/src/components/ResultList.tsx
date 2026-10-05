import { useEffect, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { ChevronLeft, ChevronRight, MailOpen, SearchX } from "lucide-react";

import { useApp } from "../lib/store";
import type { SearchItem } from "../lib/types";
import { MailCard } from "./MailCard";
import { RelatedChips } from "./RelatedChips";

export function ResultList() {
  const { search, doSearch, selected, selectItem, status } = useApp();
  const items = search.response?.items ?? [];
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 92,
    overscan: 8,
  });

  // 결과 교체 시 스크롤 맨 위로
  useEffect(() => {
    virtualizer.scrollToOffset(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search.response]);

  const resp = search.response;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <RelatedChips />
      <div ref={parentRef} className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
        {!status.ready && (
          <div className="flex h-full items-center justify-center text-[13px] text-faint">
            사이드카가 준비되면 검색을 시작할 수 있습니다…
          </div>
        )}
        {status.ready && !search.loading && !resp && (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-faint">
            <SearchX size={36} strokeWidth={1.2} />
            <div className="text-[13px]">검색어를 입력하고 Enter — 제목·본문·보낸사람을 한 번에 찾습니다</div>
          </div>
        )}
        {status.ready && !search.loading && resp && items.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-faint">
            <SearchX size={36} strokeWidth={1.2} />
            <div className="text-[13px]">결과 없음 — 필터(폴더/기간/첨부)를 확인하거나 "정확한 단어만"을 해제해 보세요</div>
          </div>
        )}
        {items.length > 0 && (
          <div style={{ height: virtualizer.getTotalSize(), position: "relative", width: "100%" }}>
            {virtualizer.getVirtualItems().map((vRow) => {
              const item = items[vRow.index] as SearchItem;
              return (
                <div
                  key={item.email.id}
                  data-index={vRow.index}
                  ref={virtualizer.measureElement}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${vRow.start}px)`,
                  }}
                >
                  <MailCard
                    item={item}
                    active={selected?.email.id === item.email.id}
                    onClick={() => selectItem(item)}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 페이지네이션 */}
      {resp && resp.total_pages > 1 && (
        <div className="flex items-center justify-center gap-2 border-t border-[var(--border)] px-3 py-1.5 text-[12px]">
          <button
            className="btn px-2 py-1"
            disabled={!resp.has_prev || search.loading}
            onClick={() => void doSearch({ page: resp.page - 1 }, { resetPage: false })}
          >
            <ChevronLeft size={13} /> 이전
          </button>
          <span className="text-dim">
            {resp.page} / {resp.total_pages}
          </span>
          <button
            className="btn px-2 py-1"
            disabled={!resp.has_next || search.loading}
            onClick={() => void doSearch({ page: resp.page + 1 }, { resetPage: false })}
          >
            다음 <ChevronRight size={13} />
          </button>
          <span className="ml-2 flex items-center gap-1 text-faint">
            <MailOpen size={12} /> 쪽당 {resp.per_page}통
          </span>
        </div>
      )}
    </div>
  );
}
