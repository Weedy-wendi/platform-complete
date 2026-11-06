import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import App from "./App.vue";
import router from "./router";
import { i18n } from "./i18n";
import { reportError } from "./observability/errors";
import { observeLcp } from "./perf/webVitals";
import "./styles/main.css";

const app = createApp(App);

app.config.errorHandler = (error) => {
  reportError(error);
};

window.addEventListener("error", (event) => {
  reportError(event.error ?? event.message);
});

window.addEventListener("unhandledrejection", (event) => {
  reportError(event.reason);
});

app.use(createPinia()).use(router).use(i18n).use(ElementPlus).mount("#app");

observeLcp();
