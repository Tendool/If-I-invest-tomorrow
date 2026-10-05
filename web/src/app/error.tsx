"use client";

import * as React from "react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Route-level error boundary: a broken view shows a retry instead of a blank page; the dock and ticker stay usable. */
export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  React.useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="card-x mx-auto flex max-w-xl flex-col items-center px-8 py-14 text-center">
      <div className="label">Something went wrong</div>
      <h1 className="display mt-2 text-[2rem] leading-tight">This view could not be drawn</h1>
      <p className="mt-3 max-w-sm text-[14px] leading-relaxed text-muted-foreground">
        {error.message || "An unexpected error occurred."} Your demo wallet is unaffected.
      </p>
      <div className="mt-7 flex flex-wrap justify-center gap-2.5">
        <button type="button" onClick={reset} className={cn(buttonVariants(), "h-9 px-4")}>
          Try again
        </button>
        <Link href="/" className={cn(buttonVariants({ variant: "outline" }), "h-9 px-4")}>
          Back to overview
        </Link>
      </div>
    </div>
  );
}
