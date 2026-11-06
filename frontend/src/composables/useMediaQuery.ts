import { onBeforeUnmount, onMounted, ref, type Ref } from "vue";

/**
 * Reactive matchMedia wrapper used by the shell to swap the sidebar for a
 * drawer on narrow screens. Falls back safely when matchMedia is unavailable.
 */
export function useMediaQuery(query: string, fallback = false): Ref<boolean> {
  const matches = ref(fallback);
  let mediaQuery: MediaQueryList | undefined;

  const update = () => {
    matches.value = mediaQuery?.matches ?? fallback;
  };

  onMounted(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    mediaQuery = window.matchMedia(query);
    update();
    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", update);
    } else if (typeof mediaQuery.addListener === "function") {
      mediaQuery.addListener(update);
    }
  });

  onBeforeUnmount(() => {
    if (!mediaQuery) return;
    if (typeof mediaQuery.removeEventListener === "function") {
      mediaQuery.removeEventListener("change", update);
    } else if (typeof mediaQuery.removeListener === "function") {
      mediaQuery.removeListener(update);
    }
  });

  return matches;
}
