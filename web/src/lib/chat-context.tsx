"use client";

import * as React from "react";
import { toast } from "sonner";
import { api, streamChat } from "./api";
import { useApp } from "./app-context";
import type { Artifact } from "./types";

export interface ToolRun {
  name: string;
  args: Record<string, unknown>;
  status: "running" | "ok" | "error";
  result?: Record<string, unknown>;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  tools: ToolRun[];
  artifacts: Artifact[];
  streaming?: boolean;
  error?: boolean;
}

interface Ctx {
  messages: ChatMessage[];
  busy: boolean;
  send: (text: string) => Promise<void>;
  stop: () => void;
  clear: () => Promise<void>;
}

const ChatCtx = React.createContext<Ctx | null>(null);
const uid = () => Math.random().toString(36).slice(2);

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const { apply } = useApp();
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [busy, setBusy] = React.useState(false);
  const abort = React.useRef<AbortController | null>(null);

  const patchLast = React.useCallback((fn: (m: ChatMessage) => ChatMessage) => {
    setMessages((ms) => (ms.length ? [...ms.slice(0, -1), fn(ms[ms.length - 1])] : ms));
  }, []);

  const send = React.useCallback(
    async (text: string) => {
      const t = text.trim();
      if (!t || busy) return;
      setBusy(true);
      setMessages((ms) => [
        ...ms,
        { id: uid(), role: "user", text: t, tools: [], artifacts: [] },
        { id: uid(), role: "assistant", text: "", tools: [], artifacts: [], streaming: true },
      ]);
      const ctl = new AbortController();
      abort.current = ctl;
      try {
        await streamChat(
          t,
          (e) => {
            if (e.type === "tool_call") {
              patchLast((m) => ({ ...m, tools: [...m.tools, { name: e.name, args: e.args, status: "running" }] }));
            } else if (e.type === "tool_result") {
              patchLast((m) => {
                const tools = [...m.tools];
                for (let i = tools.length - 1; i >= 0; i--) {
                  if (tools[i].name === e.name && tools[i].status === "running") {
                    tools[i] = { ...tools[i], status: e.ok ? "ok" : "error", result: e.result };
                    break;
                  }
                }
                return { ...m, tools };
              });
            } else if (e.type === "text") {
              patchLast((m) => ({ ...m, text: m.text + e.delta }));
            } else if (e.type === "error") {
              patchLast((m) => ({ ...m, text: e.message, error: true, streaming: false }));
            } else if (e.type === "done") {
              patchLast((m) => ({ ...m, text: e.text, artifacts: e.artifacts, streaming: false }));
              apply({ wallet: e.wallet, state: e.state });
              const ex = e.artifacts.find((a) => a.kind === "orders" && a.data.executed);
              if (ex) toast.success("The agent executed trades with demo money");
            }
          },
          ctl.signal,
        );
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          patchLast((m) => ({ ...m, text: err instanceof Error ? err.message : String(err), error: true, streaming: false }));
        } else {
          patchLast((m) => ({ ...m, streaming: false, text: m.text || "(stopped)" }));
        }
      } finally {
        setBusy(false);
        abort.current = null;
      }
    },
    [apply, busy, patchLast],
  );

  const stop = React.useCallback(() => abort.current?.abort(), []);
  const clear = React.useCallback(async () => {
    setMessages([]);
    try {
      await api.chatReset();
    } catch {
      /* ignore */
    }
  }, []);

  return <ChatCtx.Provider value={{ messages, busy, send, stop, clear }}>{children}</ChatCtx.Provider>;
}

export function useChat() {
  const c = React.useContext(ChatCtx);
  if (!c) throw new Error("useChat must be used inside <ChatProvider>");
  return c;
}
