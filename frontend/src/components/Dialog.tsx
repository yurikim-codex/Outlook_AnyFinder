import type { ReactNode } from "react";
import { X } from "lucide-react";

interface Props {
  title: string;
  width?: number;
  onClose?: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

/** 공통 모달 다이얼로그 셸 */
export function Dialog({ title, width = 560, onClose, children, footer }: Props) {
  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose?.()}>
      <div className="dialog-card" style={{ width }} role="dialog" aria-modal="true">
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          {onClose && (
            <button className="btn btn-ghost p-1" onClick={onClose} aria-label="닫기">
              <X size={16} />
            </button>
          )}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t border-[var(--border)] px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
