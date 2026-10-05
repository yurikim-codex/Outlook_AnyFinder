import { AppProvider, useApp } from "./lib/store";

import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";
import { ResultList } from "./components/ResultList";
import { MailPreview } from "./components/MailPreview";
import { StatusBar } from "./components/StatusBar";
import { Toasts } from "./components/Toasts";
import { SettingsDialog } from "./components/SettingsDialog";
import { SyncFolderDialog } from "./components/SyncFolderDialog";
import { FirstRunDialog } from "./components/FirstRunDialog";
import { Loader2 } from "lucide-react";

function Shell() {
  const { status, dialog, firstRun, transportKind } = useApp();

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <Header />
      {!status.ready && (
        <div className="flex items-center gap-2 border-b border-[var(--border)] bg-[var(--bg-elev)] px-4 py-1.5 text-xs text-dim">
          <Loader2 size={13} className="animate-spin" />
          {transportKind === "http"
            ? "브라우저 개발 모드 — dev_bridge.py 연결 확인 중… (npm run bridge)"
            : "사이드카 기동 중… 검색 엔진이 준비되면 자동으로 활성화됩니다."}
        </div>
      )}
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <main className="flex min-w-0 flex-1 flex-col">
          <ResultList />
        </main>
        <MailPreview />
      </div>
      <StatusBar />
      <Toasts />
      {dialog === "settings" && <SettingsDialog />}
      {dialog === "sync" && <SyncFolderDialog />}
      {firstRun && <FirstRunDialog />}
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
