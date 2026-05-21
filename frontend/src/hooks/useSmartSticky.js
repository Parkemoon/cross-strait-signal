import { useEffect, useRef } from "react";

/**
 * Attaches "scroll-naturally-then-pin-to-bottom" sticky behaviour.
 *
 * The default `position: sticky; top: 0` keeps the sidebar pinned at the
 * viewport top throughout the entire feed scroll, which hides anything
 * below the viewport fold. Pure-CSS `bottom: 0` doesn't do what we want
 * either — it pins from the start for short sidebars and never engages
 * the way we want for tall ones across all browsers consistently.
 *
 * This hook picks the right sticky mode based on actual measured
 * heights. For sidebars that exceed the viewport, it sets a NEGATIVE
 * `top` offset equal to `(viewport - sidebar)`, so the sticky threshold
 * is past the top — letting the element scroll naturally with the page
 * until the bottom of the sidebar reaches the bottom of the viewport,
 * at which point it pins there. For short sidebars (fits in viewport),
 * it falls back to `top: 0` so the sidebar stays anchored at the top.
 *
 * Re-runs on window resize and on any sidebar content size change via
 * ResizeObserver — handles filter changes that grow/shrink the sidebar.
 */
export function useSmartSticky() {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const update = () => {
      const viewportH = window.innerHeight;
      const sidebarH = el.scrollHeight;
      if (sidebarH <= viewportH) {
        // Fits in viewport — pin to top so it stays visible always.
        el.style.top = "0px";
      } else {
        // Taller than viewport — negative offset means the sticky
        // threshold is above viewport top by (sidebarH - viewportH),
        // so the element scrolls naturally for that distance before
        // pinning with its bottom at viewport bottom.
        el.style.top = `${viewportH - sidebarH}px`;
      }
    };

    update();

    window.addEventListener("resize", update);
    const ro = new ResizeObserver(update);
    ro.observe(el);

    return () => {
      window.removeEventListener("resize", update);
      ro.disconnect();
    };
  }, []);

  return ref;
}
