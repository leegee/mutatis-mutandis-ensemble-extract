import { createStore } from "solid-js/store";
import { CONFIG } from "./config.js";

const TEXT_KEY = `${CONFIG.storageKey}:text`;

function loadTextForm() {
	try {
		const raw = JSON.parse(localStorage.getItem(TEXT_KEY) || "null");
		if (raw && typeof raw === "object") {
			return {
				query: String(raw.query ?? ""),
				startYear: String(raw.startYear ?? "0"),
				endYear: String(raw.endYear ?? "2030"),
				limit: String(raw.limit ?? "30"),
				windowTokens: String(raw.windowTokens ?? "40"),
			};
		}
	} catch {
		/* ignore */
	}
	return {
		query: "",
		startYear: "0",
		endYear: "2030",
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
