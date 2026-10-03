"use client";

import Link from "next/link";
import { ChatPanel } from "@/components/chat/chat-panel";
import { KV } from "@/components/kit";
import { useApp } from "@/lib/app-context";
import { inr, pct, pctSigned } from "@/lib/format";
import { cn } from "@/lib/utils";

export default function AgentPage() {
  const { state } = useApp();
  const p = state?.profile;
  return (
    <div className="grid gap-12 lg:grid-cols-[minmax(0,1fr)_280px]">
      <div className="min-w-0">
        <div className="label mb-6">Agent · {state?.llm ?? "qwen3.5:4b"} running locally</div>
        <ChatPanel />
      </div>

      <aside className="hidden lg:block">
        <div className="sticky top-32 space-y-8 text-[13px]">
          <div>
            <div className="label mb-2 border-b border-rule pb-2">Trading mode</div>
            {state ? (
              <>
                <div className="flex items-center gap-2 py-1.5">
                  <span className={cn("size-1.5 rounded-full", state.autonomy === "auto" ? "bg-brand" : "bg-caution")} />
                  <span className="font-medium">{state.autonomy === "auto" ? "Auto-trade" : "Ask first"}</span>
                </div>
                <p className="text-[12.5px] leading-relaxed text-muted-foreground">
                  {state.autonomy === "auto"
                    ? "Instructions such as “invest it” or “sell TCS” execute immediately. Questions never trade."
                    : "Every order is staged and waits for your confirmation."}
                </p>
              </>
            ) : (
              <p className="py-1.5 text-faint">—</p>
            )}
          </div>

          <div>
            <div className="label mb-1 border-b border-rule pb-2">Profile</div>
            {p ? (
              <>
                <KV k="Amount" v={inr(p.amount)} />
                <KV k="Horizon" v={`${p.horizon_years} yr`} />
                <KV k="Risk" v={<span className="capitalize">{p.risk}</span>} />
                <KV k="Target" v={`${p.target_return_pct}% p.a.`} />
                <KV k="Sectors" v={p.preferred_sectors.length ? p.preferred_sectors.join(", ") : "Any"} />
                {!state?.profile_set ? <p className="mt-1 text-[12px] text-faint">Defaults. Tell the agent yours.</p> : null}
              </>
            ) : null}
          </div>

          <div>
            <div className="label mb-1 border-b border-rule pb-2">Portfolio</div>
            {state ? (
              <>
                <KV k="Value" v={inr(state.wallet.total_value)} />
                <KV k="Cash" v={inr(state.wallet.cash)} />
                <KV
                  k="Since start"
                  v={<span className={state.wallet.pnl > 0 ? "text-positive" : state.wallet.pnl < 0 ? "text-negative" : "text-muted-foreground"}>{pctSigned(state.wallet.pnl_pct, 2)}</span>}
                />
                {state.recommended ? <KV k="Recommended" v={state.recommended} /> : null}
                {state.wallet.pending ? (
                  <Link href="/wallet" className="mt-2 block text-[12.5px] font-medium text-caution underline-offset-4 hover:underline">
                    Orders awaiting confirmation →
                  </Link>
                ) : null}
              </>
            ) : null}
          </div>
          <p className="text-[11.5px] leading-relaxed text-faint">
            Demo money only. Figures come from the simulation engine; the language model only chooses tools and explains results. Cash share{" "}
            {state ? pct(state.wallet.cash / Math.max(state.wallet.total_value, 1), 0) : "—"}.
          </p>
        </div>
      </aside>
    </div>
  );
}
