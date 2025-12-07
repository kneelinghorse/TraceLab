import { useEffect, useRef } from "react";

/**
 * A hook that calls a function at a regular interval.
 * Automatically handles cleanup and pauses when callback is null.
 */
export function useInterval(callback: (() => void) | null, delay: number | null) {
  const savedCallback = useRef<(() => void) | null>(null);

  // Remember the latest callback
  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  // Set up the interval
  useEffect(() => {
    if (delay === null || callback === null) {
      return;
    }

    const tick = () => {
      savedCallback.current?.();
    };

    const id = setInterval(tick, delay);
    return () => clearInterval(id);
  }, [delay, callback]);
}
