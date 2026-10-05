"use client";

/**
 * Full-viewport animated backdrop: ThreeUI's PredictiveArcCanvas (WebGL), hue-shifted and toned down to the
 * brand's money green (#5fbf96 dark / #0e5a43 light). The shader's own dark/light mode follows the app theme.
 * It sits behind everything, never takes pointer events, and is skipped for reduced-motion users.
 */
import * as React from "react";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { PredictiveArcCanvas } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

export function useReducedMotion() {
  const [reduced, setReduced] = React.useState(true); // assume reduced until we know (no flash of motion)
  React.useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return reduced;
}

/** Light theme only: the brand mark drawn large on the right of the header, history running into "tomorrow",
 *  then a fan of simulated futures (median in green). Purely decorative; it draws itself in once. */
function HeroFan() {
  return (
    <svg aria-hidden className="hero-fan" viewBox="0 0 600 320" preserveAspectRatio="xMaxYMid meet">
      <path className="hero-fan-cone" d="M240 190 C330 152 470 85 600 40 L600 296 C470 254 330 216 240 190Z" />
          <path key="0" d="M240 190 C330 152 470 78 600 40" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 0 * 0.05}s` }} />
          <path key="1" d="M240 190 C330 158 470 94 600 62" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 1 * 0.05}s` }} />
          <path key="2" d="M240 190 C330 164 470 110 600 84" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 2 * 0.05}s` }} />
          <path key="3" d="M240 190 C330 168 470 126 600 104" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 3 * 0.05}s` }} />
          <path key="4" d="M240 190 C330 173 470 139 600 122" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 4 * 0.05}s` }} />
          <path key="5" d="M240 190 C330 178 470 152 600 140" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 5 * 0.05}s` }} />
          <path key="6" d="M240 190 C330 182 470 166 600 158" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 6 * 0.05}s` }} />
          <path key="7" d="M240 190 C330 186 470 180 600 176" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 7 * 0.05}s` }} />
          <path key="8" d="M240 190 C330 192 470 194 600 196" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 8 * 0.05}s` }} />
          <path key="9" d="M240 190 C330 197 470 211 600 218" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 9 * 0.05}s` }} />
          <path key="10" d="M240 190 C330 203 470 229 600 242" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 10 * 0.05}s` }} />
          <path key="11" d="M240 190 C330 210 470 248 600 268" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 11 * 0.05}s` }} />
          <path key="12" d="M240 190 C330 216 470 270 600 296" pathLength={1} className="hero-fan-path" style={{ animationDelay: `${0.5 + 12 * 0.05}s` }} />
      <path d="M240 190 C330 182 470 150 600 128" pathLength={1} className="hero-fan-path hero-fan-median" style={{ animationDelay: "0.9s" }} />
      <path d="M0 236 L28 222 L52 230 L78 204 L104 214 L130 192 L152 200 L176 182 L200 196 L220 186 L240 190" pathLength={1} className="hero-fan-history" />
      <circle cx="240" cy="190" r="7" className="hero-fan-dot" />
    </svg>
  );
}

export function AppBackground() {
  const { resolvedTheme } = useTheme();
  const reduced = useReducedMotion();
  const mode = resolvedTheme === "dark" ? "dark" : "light";
  const fan = <HeroFan />; // always rendered (the theme is unknown on the server); CSS hides it in dark mode
  // the dashboard has its own shader hero; two WebGL loops at once is too heavy for modest GPUs
  const ownHero = usePathname() === "/";
  if (reduced || !resolvedTheme || ownHero) return <div aria-hidden className="app-backdrop">{fan}</div>;
  return (
    <div aria-hidden className="app-backdrop">
      {fan}
      <PredictiveArcCanvas key={mode} mode={mode} speed={1.0} hue={235} saturation={mode === "dark" ? 0.5 : 1} brightness={mode === "dark" ? 0.9 : 1} />
    </div>
  );
}
