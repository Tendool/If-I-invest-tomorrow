"use client";

import { useApp } from "@/lib/app-context";

export function ApiBanner() {
  const { error, refresh } = useApp();
  if (!error) return null;
  return (
    <div className="border-b border-negative/30 bg-negative/[0.06]">
      <div className="mx-auto flex max-w-[1320px] flex-wrap items-center gap-x-4 gap-y-1 px-5 py-2.5 text-[13px] lg:px-8">
        <span className="font-medium text-negative">The analytics service is not reachable.</span>
        <span className="text-muted-foreground">
          Start it with <code className="font-mono text-[12px]">docker compose up</code> or{" "}
          <code className="font-mono text-[12px]">start.bat</code>.
        </span>
        <button onClick={() => void refresh()} className="ml-auto text-[13px] font-medium underline underline-offset-4">
          Retry
        </button>
      </div>
    </div>
  );
}
