import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";
import { ApiBanner } from "@/components/api-banner";
import { SiteHeader } from "@/components/site-header";
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
                <div className="flex min-h-screen flex-col">
                  <SiteHeader />
                  <ApiBanner />
                  <main className="mx-auto w-full max-w-[1320px] flex-1 px-5 pt-10 pb-20 lg:px-8">{children}</main>
                  <footer className="border-t border-border">
                    <div className="mx-auto flex max-w-[1320px] flex-wrap items-center justify-between gap-2 px-5 py-5 text-[12px] text-faint lg:px-8">
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
