"use client";

/**
 * Dashboard hero: a dark showcase card on ThreeUI's EmeraldHorizonBackground (WebGL, natively in the brand's green).
 * It stays dark in both themes, so the light theme gets a strong focal point instead of a flat header.
 * Left: the promise and the two ways in. Right: tomorrow's plan at a glance (or how to get one).
 */
import * as React from "react";
import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";
import { EmeraldHorizonBackground } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";
import { useReducedMotion } from "@/components/app-background";
import type { PlanData } from "@/lib/types";
import { inr, pct, shortDate, years } from "@/lib/format";

export function DashboardHero({ asOf, plan, planLoading }: { asOf?: string; plan: PlanData | null; planLoading: boolean }) {
  const reduced = useReducedMotion();
  // run the WebGL shader only while the hero is on screen; below the fold it costs GPU time for nothing
  const ref = React.useRef<HTMLElement>(null);
  const [visible, setVisible] = React.useState(true);
  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { rootMargin: "80px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <section ref={ref} className="dash-hero relative isolate overflow-hidden rounded-3xl border border-white/10 bg-[#050807] text-white shadow-[0_30px_60px_-30px_rgba(6,40,28,0.55)]">
      <div aria-hidden className="absolute inset-0 -z-10">
        {reduced || !visible ? <div className="dash-hero-static size-full" /> : <EmeraldHorizonBackground speed={0.6} glow={0.9} vignette={1.1} />}
        {/* keep the text side legible over the glow */}
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(3,6,5,0.88)_0%,rgba(3,6,5,0.6)_45%,rgba(3,6,5,0.15)_100%)]" />
      </div>

      <div className="grid gap-10 p-7 sm:p-10 lg:grid-cols-[minmax(0,1fr)_minmax(300px,380px)] lg:items-end lg:p-12">
        <div className="max-w-xl">
          <div className="text-[11px] font-medium tracking-[0.12em] text-white/55 uppercase">
            {asOf ? `Overview · close of ${shortDate(asOf)}` : "Overview"}
          </div>
          <h1 className="display mt-4 text-[2.6rem] leading-[1.02] sm:text-[3.4rem]">
            If you invest <span className="italic text-[#8fe0bb]">tomorrow</span>
          </h1>
          <p className="mt-4 max-w-md text-[14.5px] leading-relaxed text-white/65">
            What to buy, how much of each, and the probability that it reaches your goal — simulated ten thousand ways,
            stress-tested, and executable with demo money.
          </p>
          <div className="mt-8 flex flex-wrap gap-2.5">
            <Link
              href="/agent"
              className="cta-glow inline-flex h-10 items-center gap-2 rounded-xl bg-white px-4 text-[13.5px] font-medium text-[#0b0f0d] transition hover:bg-white/90"
            >
              <Sparkles className="size-4" /> Ask the agent
            </Link>
            <Link
              href="/planner"
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-white/15 bg-white/[0.06] px-4 text-[13.5px] font-medium text-white backdrop-blur transition hover:bg-white/[0.12]"
            >
              Build a plan <ArrowRight className="size-4" />
            </Link>
          </div>
        </div>

        <div className="rounded-2xl border border-white/12 bg-white/[0.06] p-5 backdrop-blur-md">
          {plan ? (
            <>
              <div className="flex items-baseline justify-between gap-3">
                <div className="text-[11px] font-medium tracking-[0.12em] text-white/55 uppercase">Tomorrow&apos;s plan</div>
                <div className="text-[12px] text-white/55">
                  {inr(plan.profile.amount)} · {years(plan.profile.horizon_years)}
                </div>
              </div>
              <div className="display mt-2 text-[1.7rem] leading-tight">{plan.strategy}</div>
              <div className="mt-5 grid grid-cols-3 gap-3">
                <HeroStat label="Reach target" value={pct(plan.evaluation.mc.stats.prob_target, 0)} accent />
                <HeroStat label="Exp. return" value={pct(plan.evaluation.stats.exp_return)} />
                <HeroStat label="Chance of gain" value={pct(plan.evaluation.mc.stats.prob_positive, 0)} />
              </div>
              <div className="mt-5 flex items-center justify-between border-t border-white/10 pt-4 text-[12.5px]">
                <span className="text-white/55">Median outcome</span>
                <span className="num font-medium">{inr(plan.evaluation.mc.stats.median_final)}</span>
              </div>
            </>
          ) : (
            <>
              <div className="text-[11px] font-medium tracking-[0.12em] text-white/55 uppercase">Tomorrow&apos;s plan</div>
              <div className="display mt-2 text-[1.5rem] leading-tight">{planLoading ? "Building your plan…" : "No plan yet"}</div>
              <p className="mt-2 text-[13px] leading-relaxed text-white/60">
                Tell the planner (or the agent) your amount, horizon, risk and target to get tomorrow&apos;s allocation.
              </p>
              <Link href="/planner" className="mt-4 inline-flex items-center gap-1 text-[13px] font-medium text-[#8fe0bb] hover:underline">
                Set your profile <ArrowRight className="size-3.5" />
              </Link>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function HeroStat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div className="num text-[1.35rem] leading-none font-medium tracking-[-0.02em]" style={accent ? { color: "#8fe0bb" } : undefined}>
        {value}
      </div>
      <div className="mt-1.5 text-[11px] leading-tight text-white/50">{label}</div>
    </div>
  );
}
