import { useEffect, useState } from "react";

/** Counts down whole seconds from `seconds` to 0. Returns 0 when there is nothing to wait for. */
export function useCountdown(seconds?: number): number {
  const [remaining, setRemaining] = useState(seconds ?? 0);
  useEffect(() => {
    setRemaining(seconds ?? 0);
    if (!seconds) return;
    const timer = window.setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) { window.clearInterval(timer); return 0; }
        return r - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [seconds]);
  return remaining;
}
