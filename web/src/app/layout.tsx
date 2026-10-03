import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";
import { ApiBanner } from "@/components/api-banner";
import { AppBackground } from "@/components/app-background";
import { DockHeader } from "@/components/dock-header";
import { MarketStrip } from "@/components/market-strip";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppProvider } from "@/lib/app-context";
import { ChatProvider } from "@/lib/chat-context";

const sans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const display = Instrument_Serif({ variable: "--font-display", subsets: ["latin"], weight: "400", style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: { default: "If I Invest Tomorrow", template: "%s · If I Invest Tomorrow" },
  description: "A financial decision simulator for Indian markets: plan, simulate, stress-test and trade with demo money.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${sans.variable} ${mono.variable} ${display.variable} h-full`}>
      <body className="min-h-full">
        <ThemeProvider>
          <TooltipProvider delay={250}>
            <AppProvider>
              <ChatProvider>
                <div className="relative flex min-h-screen flex-col">
                  <AppBackground />
                  <DockHeader />
                  <div className="h-[66px]" aria-hidden />
                  <MarketStrip />
                  <ApiBanner />
                  <main className="page-x mx-auto w-full flex-1 pt-10 pb-20">{children}</main>
                  <footer className="border-t border-border">
                    <div className="page-x mx-auto flex flex-wrap items-center justify-between gap-2 py-5 text-[12px] text-faint">
                      <span>Model-based simulations on historical data. Demo money only; not investment advice.</span>
                      <span>23CSE322 Financial Engineering · Team 01</span>
                    </div>
                  </footer>
                </div>
              </ChatProvider>
              <Toaster position="bottom-right" />
            </AppProvider>
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
