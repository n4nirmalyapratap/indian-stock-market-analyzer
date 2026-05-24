/**
 * useElementSize.ts
 * =================
 * Shared ResizeObserver hook.
 * Returns [ref, width, height] — attach `ref` to any DOM element to
 * receive live content-rect dimensions.
 *
 * Usage:
 *   const [containerRef, width, height] = useElementSize<HTMLDivElement>();
 *   return <div ref={containerRef}>…</div>;
 */

import { useRef, useState, useEffect } from "react";

export function useElementSize<T extends HTMLElement>() {
  const ref    = useRef<T>(null);
  const [width,  setWidth]  = useState(0);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      const r = entries[0]?.contentRect;
      if (r) {
        setWidth(r.width);
        setHeight(r.height);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return [ref, width, height] as const;
}
