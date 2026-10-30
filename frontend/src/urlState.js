/**
 * Encode / decode search form state in the hash query string so the
 * browser back/forward buttons restore (and re-run) searches.
 *
 * Shared params (both modes):
 *   q, from, to, limit
 *
 * Semantic-only:
 *   vid, vl, rep, beta, overfetch, neg
 *
 * Text-only:
 *   window
 *
 * Examples:
 *   #/search?q=white+hair&from=1500&to=1700&limit=30&rep=l8&beta=0.5&neg=…
 *   #/search?vid=<passage_id>&vl=…&from=1500&to=1700
 *   #/text?q=white+hair&from=1500&to=1700&limit=30&window=40
 *
 * Multi-pane: only the first pane is mirrored in the URL. Other panes stay
 * in localStorage only.
 */

import { hrefFor, navigate, ROUTES, route } from "./router.js";
import { pane, store, update } from "./store.js";
import { setTextStore, textStore } from "./textStore.js";

/** When true, App should not re-apply route params (we just wrote them). */
export const routeSync = { suppressApply: false };

/** Param names used by both Semantic and Text modes. */
export const SHARED_PARAM_KEYS = ["q", "from", "to", "limit"];

const DEFAULTS = {
	from: "0",
	to: "2030",
	limit: "30",
	rep: "l8",
	beta: "0.5",
	overfetch: "5",
	window: "40",
};

/** Stable string form of URLSearchParams (sorted keys). */
export function canonicalParams(sp) {
	const keys = [...new Set([...sp.keys()])].sort();
	const out = new URLSearchParams();
	for (const k of keys) {
		for (const v of sp.getAll(k)) out.append(k, v);
	}
	return out.toString();
}

function setIfNotDefault(sp, key, value, defaultValue) {
	const v = value == null ? "" : String(value).trim();
	if (!v) return;
	if (defaultValue != null && v === String(defaultValue)) return;
	sp.set(key, v);
}

/** Copy only the shared keys from any params object. */
export function pickSharedParams(params) {
	const sp = new URLSearchParams();
	const q = params.get("q")?.trim();
	if (q) sp.set("q", q);
	setIfNotDefault(sp, "from", params.get("from"), DEFAULTS.from);
	setIfNotDefault(sp, "to", params.get("to"), DEFAULTS.to);
	setIfNotDefault(sp, "limit", params.get("limit"), DEFAULTS.limit);
	return sp;
}

/**
 * Shared fields from the mode we're leaving (so current form values win).
 * @param {"text"|"semantic"} leaving
 */
export function sharedParamsFromStores(leaving) {
	const sp = new URLSearchParams();
	const first = store.panes[0];

	let q = "";
	let from = DEFAULTS.from;
	let to = DEFAULTS.to;
	let limit = DEFAULTS.limit;

	if (leaving === "text") {
		q = (textStore.form.query || "").trim();
		from = textStore.form.startYear || DEFAULTS.from;
		to = textStore.form.endYear || DEFAULTS.to;
		limit = textStore.form.limit || DEFAULTS.limit;
		if (!q && first?.source?.mode === "text") {
			q = (first.source.text || "").trim();
		}
	} else {
		if (first?.source?.mode === "text") {
			q = (first.source.text || "").trim();
		} else if (!(first?.source?.mode === "vector" && first.source.vectorId)) {
			q = (textStore.form.query || "").trim();
		}
		from = first?.form?.startYear || textStore.form.startYear || DEFAULTS.from;
		to = first?.form?.endYear || textStore.form.endYear || DEFAULTS.to;
		limit = first?.form?.limit || textStore.form.limit || DEFAULTS.limit;
	}

	if (q) sp.set("q", q);
	setIfNotDefault(sp, "from", from, DEFAULTS.from);
	setIfNotDefault(sp, "to", to, DEFAULTS.to);
	setIfNotDefault(sp, "limit", limit, DEFAULTS.limit);
	return sp;
}

/**
 * Switch Semantic ↔ Text while keeping shared params (q, from, to, limit).
 */
export function navigateMode(mode) {
	const path = mode === "text" ? ROUTES.text : ROUTES.search;
	const leaving = route().path === ROUTES.text ? "text" : "semantic";
	const shared = sharedParamsFromStores(leaving);
	navigate(hrefFor(path, shared));
}

export function semanticParamsFromPane(p) {
	const sp = new URLSearchParams();
	if (!p) return sp;

	if (p.source.mode === "vector" && p.source.vectorId) {
		sp.set("vid", p.source.vectorId);
		if (p.source.vectorLabel) sp.set("vl", p.source.vectorLabel.slice(0, 120));
	} else {
		const q = (p.source.text || "").trim();
		if (q) sp.set("q", q);
	}

	const f = p.form;
	setIfNotDefault(sp, "rep", f.representation, DEFAULTS.rep);
	setIfNotDefault(sp, "from", f.startYear, DEFAULTS.from);
	setIfNotDefault(sp, "to", f.endYear, DEFAULTS.to);
	setIfNotDefault(sp, "limit", f.limit, DEFAULTS.limit);
	setIfNotDefault(sp, "beta", f.beta, DEFAULTS.beta);
	setIfNotDefault(sp, "overfetch", f.overfetch, DEFAULTS.overfetch);

	for (const n of p.negatives || []) {
		if (n.id) sp.append("neg", n.id);
	}
	return sp;
}

export function textParamsFromForm(form) {
	const sp = new URLSearchParams();
	const q = (form.query || "").trim();
	if (q) sp.set("q", q);
	setIfNotDefault(sp, "from", form.startYear, DEFAULTS.from);
	setIfNotDefault(sp, "to", form.endYear, DEFAULTS.to);
	setIfNotDefault(sp, "limit", form.limit, DEFAULTS.limit);
	setIfNotDefault(sp, "window", form.windowTokens, DEFAULTS.window);
	return sp;
}

export function hasSemanticQuery(params) {
	return !!(params.get("q")?.trim() || params.get("vid")?.trim());
}

export function hasTextQuery(params) {
	return !!params.get("q")?.trim();
}

/** Keep the other mode's shared form fields aligned with what we just applied. */
function syncSharedToStores({ q, from, to, limit }, source) {
	if (source !== "text") {
		const patch = {};
		if (q !== undefined) patch.query = q;
		if (from != null) patch.startYear = from;
		if (to != null) patch.endYear = to;
		if (limit != null) patch.limit = limit;
		if (Object.keys(patch).length) setTextStore("form", patch);
	}
	if (source !== "semantic") {
		const first = store.panes[0];
		if (!first) return;
		if (q !== undefined && first.source.mode !== "vector") {
			update(first.id, "source", { text: q });
		}
		const formPatch = {};
		if (from != null) formPatch.startYear = from;
		if (to != null) formPatch.endYear = to;
		if (limit != null) formPatch.limit = limit;
		if (Object.keys(formPatch).length) update(first.id, "form", formPatch);
	}
}

/**
 * Apply hash params to the first semantic pane.
 * Shared keys (q/from/to/limit) also update the text form.
 */
export function applySemanticParams(params, paneId) {
	const p = pane(paneId);
	if (!p) return false;

	const before = canonicalParams(semanticParamsFromPane(p));

	const vid = params.get("vid")?.trim() || "";
	const q = params.get("q")?.trim() || "";
	if (vid) {
		update(paneId, "source", {
			mode: "vector",
			vectorId: vid,
			vectorLabel: params.get("vl")?.trim() || vid.slice(0, 8),
		});
	} else {
		update(paneId, "source", {
			mode: "text",
			text: q,
			vectorId: "",
			vectorLabel: "",
		});
	}

	const form = { ...p.form };
	if (params.has("rep")) form.representation = params.get("rep");
	if (params.has("from")) form.startYear = params.get("from");
	if (params.has("to")) form.endYear = params.get("to");
	if (params.has("limit")) form.limit = params.get("limit");
	if (params.has("beta")) form.beta = params.get("beta");
	if (params.has("overfetch")) form.overfetch = params.get("overfetch");
	update(paneId, "form", form);

	if (params.has("neg")) {
		const negIds = params.getAll("neg").filter(Boolean);
		const negatives = negIds.map((id) => {
			const existing = (p.negatives || []).find((n) => n.id === id);
			return existing || { id, year: "", snippet: id.slice(0, 8) };
		});
		update(paneId, "negatives", negatives);
	}

	syncSharedToStores(
		{
			q: vid ? undefined : q,
			from: form.startYear,
			to: form.endYear,
			limit: form.limit,
		},
		"semantic",
	);

	const after = canonicalParams(semanticParamsFromPane(pane(paneId)));
	return before !== after || hasSemanticQuery(params);
}

/**
 * Apply hash params to the text-search form.
 * Shared keys also update the first semantic pane (years/limit; q if not vector mode).
 */
export function applyTextParams(params) {
	const form = {
		query: params.has("q")
			? params.get("q")?.trim() || ""
			: textStore.form.query,
		startYear: params.has("from")
			? params.get("from")
			: textStore.form.startYear || DEFAULTS.from,
		endYear: params.has("to")
			? params.get("to")
			: textStore.form.endYear || DEFAULTS.to,
		limit: params.has("limit")
			? params.get("limit")
			: textStore.form.limit || DEFAULTS.limit,
		windowTokens: params.has("window")
			? params.get("window")
			: textStore.form.windowTokens || DEFAULTS.window,
	};
	setTextStore("form", form);

	syncSharedToStores(
		{
			q: form.query,
			from: form.startYear,
			to: form.endYear,
			limit: form.limit,
		},
		"text",
	);

	return !!(form.query || "").trim();
}
