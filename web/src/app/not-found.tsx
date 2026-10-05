import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { FanLoader } from "@/components/kit";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <div className="card-x mx-auto flex max-w-xl flex-col items-center px-8 py-14 text-center">
      <FanLoader className="h-12 w-auto" />
      <div className="label mt-6">Error 404</div>
      <h1 className="display mt-2 text-[2.2rem] leading-tight">This future wasn&apos;t simulated</h1>
      <p className="mt-3 max-w-sm text-[14px] leading-relaxed text-muted-foreground">
        The page you asked for doesn&apos;t exist. Head back to the overview or ask the agent what you were looking for.
      </p>
      <div className="mt-7 flex flex-wrap justify-center gap-2.5">
        <Link href="/" className={cn(buttonVariants(), "h-9 px-4")}>
          Back to overview
        </Link>
        <Link href="/agent" className={cn(buttonVariants({ variant: "outline" }), "h-9 px-4")}>
          Ask the agent <ArrowRight />
        </Link>
      </div>
    </div>
  );
}
