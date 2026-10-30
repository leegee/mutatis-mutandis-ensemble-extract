import { CONFIG } from "./config.js";
import { store, setStore, pane, update, newPane } from "./store.js";
import {
	CSV_COLS,
	csvCell,
	formatDetail,
	snippet,
	toInt,
	toNum,
} from "./helpers.js";
import { download } from "./toast.js";
import { navigate, hrefFor, ROUTES } from "./router.js";
import {
	semanticParamsFromPane,
	canonicalParams,
	routeSync,
} from "./urlState.js";

const inflight = new Map(); // pane id -> AbortController

export function buildRequest(p) {
	const f = p.form;
	const req = {
		representation: f.representation,
		start_year: toInt(f.startYear, "Start year"),
		end_year: toInt(f.endYear, "End year"),
		limit: toInt(f.limit, "Limit"),
		beta: toNum(f.beta, "Beta"),
		overfetch: toInt(f.overfetch, "Overfetch"),
		negative_ids: p.negatives.map((n) => n.id),
		include_text: true,
	};
	if (req.start_year > req.end_year)
		throw new Error("Start year must not be after end year");
	if (p.source.mode === "vector") {
		if (!p.source.vectorId) throw new Error("No passage selected");
		req.vector_id = p.source.vectorId;
	} else {
		const q = p.source.text.trim();
		if (!q) throw new Error("Enter a query");
		req.query = q;
	}
	return req;
}

/**
 * Write the first pane's (or this pane's, if it's the first) search into the hash.
 * Creates a history entry unless `replace` is set.
 */
export function syncSemanticUrl(id, { replace = false } = {}) {
	const first = store.panes[0];
	// Only the primary pane is mirrored in the URL.
	if (!first || first.id !== id) return;
	const qs = canonicalParams(semanticParamsFromPane(pane(id)));
	const target = hrefFor(ROUTES.search, qs);
	const nextHash = `#${target}`;
	if (location.hash === nextHash) return;
	routeSync.suppressApply = true;
	navigate(target, { replace });
}

/**
 * @param {string} id pane id
 * @param {{ updateUrl?: boolean, replaceUrl?: boolean }} [opts]
 */
export async function runSearch(id, opts = {}) {
	const { updateUrl = true, replaceUrl = false } = opts;
	const p = pane(id);
	if (!p) return;

	let req;
	try {
		req = buildRequest(p);
	} catch (e) {
		update(id, { status: "error", error: e.message });
		return;
	}

	if (updateUrl) syncSemanticUrl(id, { replace: replaceUrl });

	inflight.get(id)?.abort();
	const ctrl = new AbortController();
	inflight.set(id, ctrl);
	update(id, { status: "loading", error: "" });
	const t0 = performance.now();

	try {
		const res = await fetch(`${CONFIG.apiBase}/search`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(req),
			signal: ctrl.signal,
		});
		const body = await res.json().catch(() => null);
		if (!res.ok) throw new Error(formatDetail(body, res));
		if (inflight.get(id) !== ctrl) return; // superseded
		update(id, {
			status: "ok",
			error: "",
			hits: body.results,
			warnings: body.warnings ?? [],
			elapsedMs: Math.round(performance.now() - t0),
			lastRequest: req,
		});
	} catch (e) {
		if (e.name === "AbortError" || inflight.get(id) !== ctrl) return;
		const msg =
			e instanceof TypeError
				? `Cannot reach the API at ${CONFIG.apiBase || location.origin}`
				: e.message || String(e);
		update(id, { status: "error", error: msg });
	} finally {
		if (inflight.get(id) === ctrl) inflight.delete(id);
	}
}

export function addNegative(id, hit) {
	update(id, "negatives", (ns) =>
		ns.some((n) => n.id === hit.passage_id)
			? ns
			: [
					...ns,
					{
						id: hit.passage_id,
						year: hit.pub_year,
						snippet: snippet(hit.text, 120),
					},
				],
	);
}

export function toggleNegative(id, hit) {
	const p = pane(id);
	if (p.negatives.some((n) => n.id === hit.passage_id))
		removeNegative(id, hit.passage_id, false);
	else addNegative(id, hit);
	runSearch(id);
}

export function removeNegative(id, passageId, rerun = true) {
	update(id, "negatives", (ns) => ns.filter((n) => n.id !== passageId));
	if (rerun) runSearch(id);
}

export function clearNegatives(id) {
	update(id, "negatives", []);
	runSearch(id);
}

export function findSimilar(id, hit) {
	update(id, "source", {
		mode: "vector",
		vectorId: hit.passage_id,
		vectorLabel: `${hit.pub_year} · ${snippet(hit.text, 80)}`,
	});
	runSearch(id);
}

export function clearVectorSource(id) {
	update(id, "source", { mode: "text", vectorId: "", vectorLabel: "" });
}

export function narrowYears(id, start, end) {
	update(id, "form", { startYear: String(start), endYear: String(end) });
	runSearch(id);
}

export function addPane() {
	if (store.panes.length >= CONFIG.maxPanes) return;
	const last = store.panes[store.panes.length - 1];
	// New pane starts with the same settings but an empty query.
	const seed = last ? { form: JSON.parse(JSON.stringify(last.form)) } : {};
	setStore("panes", (ps) => [...ps, newPane(seed)]);
}

export function removePane(id) {
	inflight.get(id)?.abort();
	inflight.delete(id);
	setStore("panes", (ps) => ps.filter((p) => p.id !== id));
}

export async function checkApi() {
	try {
		const h = await fetch(`${CONFIG.apiBase}/health`);
		if (!h.ok) throw new Error(`HTTP ${h.status}`);
		setStore({ apiOk: true, apiError: "" });
		const r = await fetch(`${CONFIG.apiBase}/representations`);
		if (r.ok) {
			const { representations } = await r.json();
			if (Array.isArray(representations) && representations.length) {
				setStore("representations", representations);
				const fallback = representations.includes("l8")
					? "l8"
					: representations[0];
				for (const p of store.panes) {
					if (!representations.includes(p.form.representation)) {
						update(p.id, "form", { representation: fallback });
					}
				}
			}
		}
	} catch (e) {
		setStore({ apiOk: false, apiError: e.message || String(e) });
	}
}

export function exportPane(id, kind) {
	const p = pane(id);
	if (!p?.hits.length) return;
	const hits = JSON.parse(JSON.stringify(p.hits));
	const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
	const base = `passage-search-${p.label}-${stamp}`;
	if (kind === "json") {
		download(
			`${base}.json`,
			JSON.stringify(
				{
					request: JSON.parse(JSON.stringify(p.lastRequest)),
					count: hits.length,
					results: hits,
				},
				null,
				2,
			),
			"application/json",
		);
	} else {
		const rows = [
			CSV_COLS.join(","),
			...hits.map((h) => CSV_COLS.map((c) => csvCell(h[c])).join(",")),
		];
		download(`${base}.csv`, `\ufeff${rows.join("\r\n")}`, "text/csv");
	}
}

export function resetYears(id) {
	update(id, "form", { startYear: "0", endYear: "2030" });
	runSearch(id);
}
