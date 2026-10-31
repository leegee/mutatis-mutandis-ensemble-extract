import { createStore } from "solid-js/store";
import { CONFIG, DEFAULT_START_YEAR, DEFAULT_END_YEAR } from "./config.js";

const TEXT_KEY = CONFIG.storageKey + ":text";

function loadTextForm() {
  try {
    const raw = JSON.parse(localStorage.getItem(TEXT_KEY) || "null");
    if (raw && typeof raw === "object") {
      return {
        query: String(raw.query ?? ""),
        startYear: String(raw.startYear ?? DEFAULT_START_YEAR),
        endYear: String(raw.endYear ?? DEFAULT_END_YEAR),
        limit: String(raw.limit ?? "30"),
        windowTokens: String(raw.windowTokens ?? "40"),
      };
    }
  } catch {
    /* ignore */
  }
  return {
    query: "",
    startYear: DEFAULT_START_YEAR,
    endYear: DEFAULT_END_YEAR,
    limit: "30",
    windowTokens: "40",
  };
}

export const [textStore, setTextStore] = createStore({
  form: loadTextForm(),
  filter: "", // client-side results filter
  status: "idle", // idle | loading | ok | error
  error: "",
  warnings: [],
  hits: [],
  elapsedMs: 0,
  lastRequest: null,
});

export function persistTextForm() {
  try {
    localStorage.setItem(TEXT_KEY, JSON.stringify({ ...textStore.form }));
  } catch {
    /* ignore */
  }
}
