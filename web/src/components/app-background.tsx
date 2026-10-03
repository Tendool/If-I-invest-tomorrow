"use client";

/**
 * Full-viewport animated backdrop: ThreeUI's PredictiveArcCanvas (WebGL) with the pasted settings
 * (speed 1, hue 0, saturation 1, brightness 1). The shader's own dark/light mode follows the app theme.
 * It sits behind everything, never takes pointer events, and is skipped for reduced-motion users.
 */
import * as React from "react";
import { useTheme } from "next-themes";
import { PredictiveArcCanvas } from "@designcodeio/threeui";
import "@designcodeio/threeui/style.css";

function useReducedMotion() {
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

export function AppBackground() {
  const { resolvedTheme } = useTheme();
  const reduced = useReducedMotion();
  const mode = resolvedTheme === "dark" ? "dark" : "light";
  if (reduced || !resolvedTheme) return <div aria-hidden className="app-backdrop" />;
  return (
    <div aria-hidden className="app-backdrop">
      <PredictiveArcCanvas key={mode} mode={mode} speed={1.0} hue={0} saturation={1.0} brightness={1.0} />
    </div>
  );
}
