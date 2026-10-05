import { ExternalLink, Loader2, Save, X } from "lucide-react";

import * as api from "../lib/api";
import { formatFullDate, splitAttachmentNames } from "../lib/format";
import { getTransport } from "../lib/transport";
import { useApp } from "../lib/store";

/**
 * 메일 미리보기 패널 — preview.mail(본문 평문) 계약 사용.
 * 본문은 DB에 평문으로 저장되어 있어 iframe/sanitize 불필요 (XSS 공격면 0).
 */
export function MailPreview() {
  const { selected, selectItem, previewEmail, previewLoading, toast } = useApp();
  if (!selected) return null;
  const mail = previewEmail ?? selected.email;
  const attachments =
    (previewEmail as { attachments?: string[] } | null)?.attachments ??
    splitAttachmentNames(mail.attachment_names);
  const transport = getTransport();

  return (
    <aside className="flex w-[420px] shrink-0 flex-col border-l border-[var(--border)] bg-[var(--bg-panel)]">
      <div className="flex items-start gap-2 border-b border-[var(--border)] px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold leading-snug">{mail.subject || "(제목 없음)"}</div>
          <div className="mt-1 text-[12px] text-dim">
            {mail.sender_name} &lt;{mail.sender_email}&gt;
          </div>
          <div className="mt-0.5 text-[11px] text-faint">
            {formatFullDate(mail.received_at)} · {mail.folder_name}
          </div>
          {mail.recipients && (
            <div className="mt-0.5 truncate text-[11px] text-faint" title={mail.recipients}>
              받음: {mail.recipients}
            </div>
          )}
        </div>
        <button className="btn btn-ghost p-1" onClick={() => selectItem(null)} aria-label="미리보기 닫기">
          <X size={15} />
        </button>
      </div>

      <div className="flex items-center gap-1.5 border-b border-[var(--border)] px-3 py-2">
        <button
          className="btn btn-ghost px-2 py-1 text-[12px]"
          onClick={() =>
            api
              .mailOpen(transport, mail.entry_id)
              .then(() => toast("Outlook에서 여는 중…", "info"))
              .catch((e) => toast(`열기 실패: ${String(e)}`, "error"))
          }
          title="Outlook 기본 클라이언트에서 원본 열기 (Windows)"
        >
          <ExternalLink size={13} /> Outlook에서 열기
        </button>
        <button
          className="btn btn-ghost px-2 py-1 text-[12px]"
          onClick={() =>
            api
              .mailExport(transport, mail.entry_id)
              .then((r) => toast(r.path ? `내보내기 완료: ${r.path}` : "내보내기 완료", "success"))
              .catch((e) => toast(`내보내기 실패: ${String(e)}`, "error"))
          }
          title="파일로 저장"
        >
          <Save size={13} /> 내보내기
        </button>
      </div>

      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-1 border-b border-[var(--border)] px-3 py-2">
          {attachments.map((a) => (
            <span key={a} className="chip cursor-default">
              {a}
            </span>
          ))}
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {previewLoading ? (
          <div className="flex h-full items-center justify-center gap-2 text-[12px] text-dim">
            <Loader2 size={14} className="animate-spin" /> 본문 로드 중…
          </div>
        ) : mail.body_text ? (
          <pre className="whitespace-pre-wrap break-words [font-family:inherit] text-[13px] leading-relaxed text-[var(--text)]">
            {mail.body_text}
          </pre>
        ) : (
          <div className="flex h-full items-center justify-center text-[12px] text-faint">
            미리보기 본문이 없습니다
          </div>
        )}
      </div>
    </aside>
  );
}
