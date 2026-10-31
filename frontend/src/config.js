/** Runtime configuration from URL params. */
const params = new URLSearchParams(location.search);

export const CONFIG = {
  // "" = same origin as this page (the FastAPI app serves both).
  apiBase: (params.get("api") ?? "").replace(/\/$/, ""),
  // Preview the multi-pane layout with ?panes=2 (up to 6).
  maxPanes: Math.max(1, Math.min(6, Number(params.get("panes")) || 1)),
  // v3: saved panes from earlier versions carry old end-year defaults (3000, then 2030),
  // which the API now rejects as being in the future.
  storageKey: "passage-search-ui:v3",
};

/** Year-range defaults. The API accepts years up to the current year. */
export const DEFAULT_START_YEAR = "0";
export const DEFAULT_END_YEAR = String(new Date().getFullYear());
