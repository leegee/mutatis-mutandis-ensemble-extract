/** Runtime configuration from URL params. */
const params = new URLSearchParams(location.search);

export const CONFIG = {
	// "" = same origin as this page (the FastAPI app serves both).
	apiBase: (params.get("api") ?? "").replace(/\/$/, ""),
	// Preview the multi-pane layout with ?panes=2 (up to 6).
	maxPanes: Math.max(1, Math.min(6, Number(params.get("panes")) || 2)),
	storageKey: "passage-search-ui:v1",
};
