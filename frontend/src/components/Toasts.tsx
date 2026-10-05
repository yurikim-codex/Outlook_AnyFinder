import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";

import { useApp, type Toast } from "../lib/store";

const ICONS: Record<Toast["kind"], typeof Info> = {
  info: Info,
  success: CheckCircle2,
  warn: AlertTriangle,
  error: XCircle,
};

const COLORS: Record<Toast["kind"], string> = {
  info: "var(--accent)",
  success: "var(--ok)",
  warn: "var(--warn)",
  error: "var(--danger)",
};

export function Toasts() {
  const { toasts, dismissToast } = useApp();
  if (toasts.length === 0) return null;
  return (
    <div className="pointer-events-none fixed bottom-10 right-4 z-[60] flex w-80 flex-col gap-2">
      {toasts.map((t) => {
        const Icon = ICONS[t.kind];
        return (
          <div
            key={t.id}
            className="pointer-events-auto flex items-start gap-2 rounded-lg border border-[var(--border)] bg-[var(--bg-elev)] px-3 py-2 text-[13px] shadow-[var(--shadow)]"
          >
            <Icon size={15} style={{ color: COLORS[t.kind] }} className="mt-0.5 shrink-0" />
            <span className="flex-1 whitespace-pre-wrap break-words">{t.message}</span>
            <button className="btn-ghost btn p-0.5" onClick={() => dismissToast(t.id)} aria-label="닫기">
              <X size={13} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
