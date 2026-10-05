"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowUp, ChevronRight, Square } from "lucide-react";
import { ArtifactView } from "@/components/finance/artifact";
import { FanLoader } from "@/components/kit";
import { useApp } from "@/lib/app-context";
import { useChat, type ChatMessage, type ToolRun } from "@/lib/chat-context";
import { cn } from "@/lib/utils";

const PROMPTS: { group: string; items: string[] }[] = [
  {
    group: "Plan",
    items: [
      "I have ₹2,00,000 for 3 years, medium risk, and want 12% a year. What should I invest in tomorrow?",
      "Compare all five strategies for my profile",
      "Should I invest now or spread it as a SIP?",
    ],
  },
  {
    group: "Test",
    items: ["Stress test my plan against a market crash", "What is the chance I reach my target?", "Backtest the strategies over three years"],
  },
  {
    group: "Act",
    items: ["Invest it in the recommended plan", "Check my portfolio and fix whatever it needs", "Sell all my TCS"],
  },
];

const QUICK = ["Invest it in the recommended plan", "Stress test my plan", "Check my portfolio and fix whatever it needs", "How is the market today?"];

const TOOL_LABEL: Record<string, string> = {
  set_profile: "profile",
  get_profile: "profile",
  get_investment_plan: "plan",
  compare_strategies: "strategies",
  run_monte_carlo: "monte carlo",
  stress_test: "stress test",
  compare_timing: "timing",
  run_backtest: "backtest",
  get_market_overview: "market",
  analyze_asset: "asset",
  get_model_report: "models",
  list_assets: "universe",
  wallet_status: "portfolio",
  wallet_history: "trades",
  invest_plan: "invest",
  trade: "trade",
  rebalance_portfolio: "rebalance",
  check_portfolio: "health check",
  auto_manage_portfolio: "auto-manage",
  set_autonomy: "autonomy",
  confirm_pending_order: "confirm",
  cancel_pending_order: "cancel",
  add_demo_funds: "add funds",
  reset_wallet: "reset",
  refresh_market_data: "refresh data",
};
const ACTION_TOOLS = new Set(["invest_plan", "trade", "rebalance_portfolio", "auto_manage_portfolio", "confirm_pending_order"]);

function Trace({ tools }: { tools: ToolRun[] }) {
  const [open, setOpen] = React.useState(false);
  if (!tools.length) return null;
  return (
    <div className="mb-3">
      <button onClick={() => setOpen((o) => !o)} className="group flex flex-wrap items-center gap-x-1.5 gap-y-1 font-mono text-[11.5px] text-faint">
        <ChevronRight className={cn("size-3 transition-transform", open && "rotate-90")} />
        {tools.map((t, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 ? <span className="text-rule">/</span> : null}
            <span
              className={cn(
                t.status === "running" && "animate-pulse text-muted-foreground",
                t.status === "error" && "text-negative",
                t.status === "ok" && ACTION_TOOLS.has(t.name) && "text-brand",
              )}
            >
              {TOOL_LABEL[t.name] ?? t.name}
            </span>
          </span>
        ))}
      </button>
      {open ? (
        <div className="mt-2 space-y-2">
          {tools.map((t, i) => (
            <pre key={i} className="max-h-56 overflow-auto rounded-md border border-border bg-surface p-3 font-mono text-[11px] leading-relaxed text-muted-foreground">
              {t.name}({JSON.stringify(t.args)}){"\n"}→ {JSON.stringify(t.result ?? "…", null, 2)}
            </pre>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Attachment({ a }: { a: ChatMessage["artifacts"][number] }) {
  const [open, setOpen] = React.useState(true);
  return (
    <div className="card-x">
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left">
        <span className="label">{a.title}</span>
        <ChevronRight className={cn("size-3.5 text-faint transition-transform", open && "rotate-90")} />
      </button>
      {open ? (
        <div className="border-t border-border px-4 pt-5 pb-5 sm:px-6">
          <ArtifactView a={a} />
        </div>
      ) : null}
    </div>
  );
}

function Message({ m }: { m: ChatMessage }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-lg bg-foreground/[0.055] px-4 py-2.5 text-[14px] leading-relaxed">{m.text}</div>
      </div>
    );
  }
  return (
    <div className="min-w-0">
      <Trace tools={m.tools} />
      {m.text ? (
        <div
          className={cn(
            "prose prose-neutral max-w-[78ch] text-[14.5px] leading-[1.7] dark:prose-invert",
            "prose-p:my-2 prose-ul:my-2 prose-li:my-0.5 prose-strong:font-semibold prose-headings:font-semibold prose-headings:text-[15px]",
            "prose-table:text-[13px] prose-th:font-medium prose-th:text-muted-foreground",
            m.error && "text-negative",
          )}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
          {m.streaming ? <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse bg-foreground" /> : null}
        </div>
      ) : m.streaming ? (
        <div className="flex w-full flex-col items-center justify-center gap-3 py-16 text-[13px] text-muted-foreground" role="status" aria-live="polite">
          <FanLoader className="h-11 w-auto" />
          {m.tools.some((t) => t.status === "running") ? "Running the numbers…" : "Thinking…"}
        </div>
      ) : null}
      {m.artifacts.length ? (
        <div className="mt-5 space-y-3">
          {m.artifacts.map((a, i) => (
            <Attachment key={i} a={a} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ChatPanel() {
  const { messages, busy, send, stop, clear } = useChat();
  const { state } = useApp();
  const [input, setInput] = React.useState("");
  const taRef = React.useRef<HTMLTextAreaElement>(null);
  const last = messages[messages.length - 1];

  React.useEffect(() => {
    if (messages.length) window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  }, [messages.length, last?.text, last?.artifacts.length]);

  React.useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(180, el.scrollHeight) + "px";
  }, [input]);

  function submit(text?: string) {
    const t = (text ?? input).trim();
    if (!t || busy) return;
    void send(t);
    setInput("");
  }

  return (
    <div className="flex min-h-[calc(100dvh-220px)] flex-col">
      <div className="flex-1">
        {messages.length === 0 ? (
          <div className="pt-4 pb-10">
            <h2 className="display text-[2.4rem] leading-[1.08] sm:text-[2.8rem]">
              What should your money
              <br />
              <span className="italic">do tomorrow?</span>
            </h2>
            <p className="mt-4 max-w-xl text-[14.5px] leading-relaxed text-muted-foreground">
              Describe your amount, horizon, risk and goal. The agent builds a plan, simulates it, stress-tests it and, when you tell it to, invests,
              sells or rebalances with demo money. {state ? (state.autonomy === "auto" ? "Auto-trade is on." : "Auto-trade is off, so it will ask before every order.") : null}
            </p>
            <div className="mt-10 grid gap-4 md:grid-cols-3">
              {PROMPTS.map((g) => (
                <div key={g.group} className="card-x p-2">
                  <div className="label px-3 pt-2 pb-1.5">{g.group}</div>
                  <ul>
                    {g.items.map((p) => (
                      <li key={p}>
                        <button onClick={() => submit(p)} className="group flex w-full items-start justify-between gap-3 rounded-xl px-3 py-2.5 text-left text-[13.5px] leading-snug transition-colors hover:bg-muted hover:text-foreground">
                          <span className="text-muted-foreground group-hover:text-foreground">{p}</span>
                          <ChevronRight className="mt-0.5 size-3.5 shrink-0 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-9 pb-8">
            {messages.map((m) => (
              <Message key={m.id} m={m} />
            ))}
          </div>
        )}
      </div>

      <div className="sticky bottom-0 -mx-1 bg-background px-1 pt-3 pb-5 before:pointer-events-none before:absolute before:inset-x-0 before:-top-8 before:h-8 before:bg-gradient-to-t before:from-background before:to-transparent">
        {messages.length > 0 ? (
          <div className="mb-2.5 flex flex-wrap items-center gap-x-4 gap-y-1">
            {QUICK.map((q) => (
              <button key={q} disabled={busy} onClick={() => submit(q)} className="text-[12px] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline disabled:opacity-40">
                {q}
              </button>
            ))}
            <button onClick={() => void clear()} className="ml-auto text-[12px] text-faint hover:text-foreground">
              New conversation
            </button>
          </div>
        ) : null}
        <div className="card-x flex items-end gap-2 p-2 pl-4 focus-within:border-foreground/30 focus-within:ring-3 focus-within:ring-brand/15">
          <textarea
            ref={taRef}
            value={input}
            rows={1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Ask, plan or instruct — e.g. put ₹50,000 in a low-risk plan for a year and invest it"
            className="max-h-44 min-h-9 flex-1 resize-none bg-transparent py-2 text-[14px] leading-relaxed outline-none placeholder:text-faint"
          />
          {busy ? (
            <button onClick={stop} aria-label="Stop" className="flex size-9 shrink-0 items-center justify-center rounded-md border border-border text-muted-foreground hover:text-foreground">
              <Square className="size-3.5 fill-current" />
            </button>
          ) : (
            <button
              onClick={() => submit()}
              disabled={!input.trim()}
              aria-label="Send"
              className="flex size-9 shrink-0 items-center justify-center rounded-md bg-foreground text-background transition-opacity disabled:opacity-25"
            >
              <ArrowUp className="size-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
