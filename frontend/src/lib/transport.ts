/**
 * IPC 트랜스포트 추상화 (Phase 3-1).
 *
 * - TauriTransport : 프로덕션 — invoke("sidecar_request") + listen("sidecar://event")
 * - HttpTransport  : 브라우저 개발 모드 — dev_bridge.py(8765)를 vite 프록시(/sidecar)로 경유
 *
 * 두 모드 모두 동일한 Envelope 계약을 사용하므로 컴포넌트는 모드를 알 필요가 없다.
 */
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import type { Envelope, SidecarErrorInfo, SidecarStatus } from "./types";

export class SidecarError extends Error {
  code: string;
  retryable: boolean;
  details?: unknown;
  constructor(info: SidecarErrorInfo) {
    super(info.message);
    this.name = "SidecarError";
    this.code = info.code;
    this.retryable = info.retryable ?? false;
    this.details = info.details;
  }
}

export type EventCallback = (event: string, data: unknown) => void;
export type StatusCallback = (status: SidecarStatus) => void;

export interface Transport {
  readonly kind: "tauri" | "http";
  /** ok:false면 SidecarError를 던진다 (비즈니스 오류) */
  request<T>(cmd: string, params?: Record<string, unknown>): Promise<T>;
  /** 원본 엔벨로프 (ok:false를 예외로 만들지 않고 직접 검사하고 싶은 경우) */
  envelope<T>(cmd: string, params?: Record<string, unknown>): Promise<Envelope<T>>;
  onEvent(cb: EventCallback): Promise<() => void>;
  onStatus(cb: StatusCallback): Promise<() => void>;
  status(): Promise<SidecarStatus>;
  restart(): Promise<void>;
  frontendLog(message: string): void;
}

export const isTauri =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

function unwrap<T>(env: Envelope<T>): T {
  if (!env.ok) {
    throw new SidecarError(
      env.error ?? { code: "UNKNOWN", message: "응답에 오류 정보가 없습니다" },
    );
  }
  return env.result as T;
}

// ── Tauri (프로덕션) ──

class TauriTransport implements Transport {
  readonly kind = "tauri" as const;

  async envelope<T>(cmd: string, params: Record<string, unknown> = {}): Promise<Envelope<T>> {
    return invoke<Envelope<T>>("sidecar_request", { cmd, params });
  }

  async request<T>(cmd: string, params: Record<string, unknown> = {}): Promise<T> {
    return unwrap(await this.envelope<T>(cmd, params));
  }

  async onEvent(cb: EventCallback): Promise<() => void> {
    const un: UnlistenFn = await listen<unknown>("sidecar://event", (msg) => {
      const payload = msg.payload as { event?: string; data?: unknown };
      if (payload && typeof payload.event === "string") cb(payload.event, payload.data);
    });
    return un;
  }

  async onStatus(cb: StatusCallback): Promise<() => void> {
    const un: UnlistenFn = await listen<SidecarStatus>("sidecar://status", (msg) =>
      cb(msg.payload),
    );
    return un;
  }

  status(): Promise<SidecarStatus> {
    return invoke<SidecarStatus>("sidecar_status");
  }

  restart(): Promise<void> {
    return invoke<void>("sidecar_restart");
  }

  frontendLog(message: string): void {
    void invoke("frontend_log", { message }).catch(() => undefined);
  }
}

// ── HTTP (브라우저 개발 모드) ──

const HTTP_BASE = "/sidecar";

class HttpTransport implements Transport {
  readonly kind = "http" as const;
  private eventSource: EventSource | null = null;
  private eventHandlers = new Set<EventCallback>();

  async envelope<T>(cmd: string, params: Record<string, unknown> = {}): Promise<Envelope<T>> {
    const res = await fetch(`${HTTP_BASE}/invoke`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cmd, params }),
    });
    if (!res.ok) {
      throw new SidecarError({
        code: "BRIDGE_HTTP",
        message: `브리지 HTTP ${res.status} — dev_bridge.py가 실행 중인지 확인하세요`,
      });
    }
    return (await res.json()) as Envelope<T>;
  }

  async request<T>(cmd: string, params: Record<string, unknown> = {}): Promise<T> {
    return unwrap(await this.envelope<T>(cmd, params));
  }

  private ensureEventSource(): EventSource {
    if (!this.eventSource || this.eventSource.readyState === EventSource.CLOSED) {
      const es = new EventSource(`${HTTP_BASE}/events`);
      es.onmessage = (ev) => {
        try {
          const payload = JSON.parse(ev.data) as { event?: string; data?: unknown };
          if (payload && typeof payload.event === "string") {
            for (const cb of this.eventHandlers) cb(payload.event, payload.data);
          }
        } catch {
          /* 무시 */
        }
      };
      this.eventSource = es;
    }
    return this.eventSource;
  }

  async onEvent(cb: EventCallback): Promise<() => void> {
    this.eventHandlers.add(cb);
    this.ensureEventSource();
    return () => this.eventHandlers.delete(cb);
  }

  async onStatus(cb: StatusCallback): Promise<() => void> {
    // 브리지 모드에서는 폴링으로 상태 전달 (5초)
    const timer = window.setInterval(() => {
      void this.status().then(cb).catch(() => undefined);
    }, 5000);
    void this.status().then(cb).catch(() => undefined);
    return () => window.clearInterval(timer);
  }

  async status(): Promise<SidecarStatus> {
    const res = await fetch(`${HTTP_BASE}/status`);
    if (!res.ok) {
      return { ready: false, running: false, restarts: 0, state: "bridge_down" };
    }
    return (await res.json()) as SidecarStatus;
  }

  async restart(): Promise<void> {
    const res = await fetch(`${HTTP_BASE}/restart`, { method: "POST" });
    if (!res.ok) throw new SidecarError({ code: "BRIDGE_RESTART", message: "브리지 재시작 실패" });
  }

  frontendLog(message: string): void {
    console.debug("[frontend]", message);
  }
}

let singleton: Transport | null = null;

export function getTransport(): Transport {
  if (!singleton) singleton = isTauri ? new TauriTransport() : new HttpTransport();
  return singleton;
}
