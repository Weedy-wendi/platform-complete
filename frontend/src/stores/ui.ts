import { defineStore } from "pinia";

export const useUiStore = defineStore("ui", {
  state: () => ({ titleKey: "app.title", error: "" as string }),
  actions: {
    setTitleKey(titleKey: string) {
      this.titleKey = titleKey;
    },
    setError(error: string) {
      this.error = error;
    },
    clearError() {
      this.error = "";
    },
  },
});
