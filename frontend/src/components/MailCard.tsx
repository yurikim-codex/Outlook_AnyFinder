import { Paperclip } from "lucide-react";
import clsx from "clsx";

import { formatDate, sanitizeSnippet, splitAttachmentNames } from "../lib/format";
import type { SearchItem } from "../lib/types";

interface Props {
  item: SearchItem;
  active: boolean;
  onClick: () => void;
}

export function MailCard({ item, active, onClick }: Props) {
  const mail = item.email;
  const attachments = splitAttachmentNames(mail.attachment_names);

  return (
    <button
      onClick={onClick}
      className={clsx(
        "mb-1.5 block w-full rounded-lg border px-3 py-2 text-left transition-colors",
        active
          ? "border-[var(--accent)] bg-[var(--accent-soft)]"
          : "border-[var(--border)] bg-[var(--bg-panel)] hover:bg-[var(--bg-hover)]",
      )}
    >
      <div className="flex items-baseline gap-2">
        <span className="min-w-0 shrink-0 max-w-[180px] truncate text-[12px] font-semibold text-dim">
          {mail.sender_name || mail.sender_email || "(보낸사람 없음)"}
        </span>
        <span
          className="snippet min-w-0 flex-1 truncate text-[13.5px] font-semibold"
          dangerouslySetInnerHTML={{ __html: sanitizeSnippet(item.title_snippet || mail.subject || "(제목 없음)") }}
        />
        <span className="shrink-0 text-[11px] text-faint">{formatDate(mail.received_at)}</span>
      </div>
      <div
        className="snippet mt-0.5 line-clamp-2 text-[12px] leading-relaxed text-dim"
        dangerouslySetInnerHTML={{ __html: sanitizeSnippet(item.body_snippet || "") }}
      />
      <div className="mt-1 flex items-center gap-2 text-[11px] text-faint">
        <span className="rounded bg-[var(--bg-elev)] px-1.5 py-0.5">{mail.folder_name}</span>
        {attachments.length > 0 && (
          <span className="flex items-center gap-1" title={attachments.join(", ")}>
            <Paperclip size={11} /> {attachments.length}
          </span>
        )}
        {mail.importance === 2 && <span className="text-[var(--danger)]">중요</span>}
        {!mail.is_read && <span className="text-[var(--accent)]">안읽음</span>}
      </div>
    </button>
  );
}
