import { createStore } from "solid-js/store";
import { CONFIG } from "./config.js";

let paneSeq = 0;

export function newPane(seed = {}) {
	const n = ++paneSeq;
	return {
		id: `p${n}`,
		label: seed.label ?? String.fromCharCode(65 + ((n - 1) % 26)),
		// What we are searching for: free text, or "passages like this one".
		source: {
			mode: "text",
			text: "",
			vectorId: "",
			vectorLabel: "",
			...seed.source,
		},
		form: {
			representation: "l8",
			startYear: "0",
			endYear: "2030",
			limit: "30",
			beta: "0.5",
			overfetch: "5",
			...seed.form,
		},
		negatives: seed.negatives ?? [], // [{id, year, snippet}]
		filter: "", // client-side results filter (not persisted, not in URL)
		// Results of the last request:
		status: "idle", // idle | loading | ok | error
		error: "",
		warnings: [],
		hits: [],
		elapsedMs: 0,
		lastRequest: null,
	};
}

function loadSaved() {
	try {
		const arr = JSON.parse(localStorage.getItem(CONFIG.storageKey) || "null");
		if (!Array.isArray(arr) || !arr.length) return null;
		return arr.slice(0, CONFIG.maxPanes).map(newPane);
	} catch {
		return null;
	}
}

export const [store, setStore] = createStore({
	panes: loadSaved() ?? [newPane()],
	representations: ["l8", "mean4"],
	apiOk: null, // null = unknown, true/false after the health check
	apiError: "",
});

export const pane = (id) => store.panes.find((p) => p.id === id);

/** Shallow-merge into one pane (or into pane.<key> when a path is given). */
export const update = (id, ...rest) =>
	setStore("panes", (p) => p.id === id, ...rest);
