import { CONFIG } from "./config.js";
import { CSV_COLS, csvCell, formatDetail, toInt } from "./helpers.js";
import { hrefFor, navigate, ROUTES } from "./router.js";
import { persistTextForm, setTextStore, textStore } from "./textStore.js";
import { download } from "./toast.js";
import { canonicalParams, routeSync, textParamsFromForm } from "./urlState.js";

let inflight = null;

function buildTextRequest() {
	const f = textStore.form;
	const q = f.query.trim();
	if (!q) throw new Error("Enter a query");
	const req = {
		query: q,
		start_year: toInt(f.startYear, "Start year"),
		end_year: toInt(f.endYear, "End year"),
		limit: toInt(f.limit, "Limit"),
		window_tokens: toInt(f.windowTokens, "Window"),
	};
	if (req.start_year > req.end_year)
		throw new Error("Start year must not be after end year");
	return req;
}

/**
 * @param {{ updateUrl?: boolean, replaceUrl?: boolean }} [opts]
 */
export async function runTextSearch(opts = {}) {
	const { updateUrl = true, replaceUrl = false } = opts;

	let req;
	try {
		req = buildTextRequest();
	} catch (e) {
		setTextStore({ status: "error", error: e.message });
		return;
	}

	if (updateUrl) {
		const qs = canonicalParams(textParamsFromForm(textStore.form));
		const target = hrefFor(ROUTES.text, qs);
		if (location.hash !== `#${target}`) {
			routeSync.suppressApply = true;
			navigate(target, { replace: replaceUrl });
		}
	}

	inflight?.abort();
	const ctrl = new AbortController();
	inflight = ctrl;
	setTextStore({ status: "loading", error: "" });
	persistTextForm();
	const t0 = performance.now();

	try {
		const res = await fetch(`${CONFIG.apiBase}/text-search`, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(req),
			signal: ctrl.signal,
		});
		const body = await res.json().catch(() => null);
		if (!res.ok) throw new Error(formatDetail(body, res));
		if (inflight !== ctrl) return;
		setTextStore({
			status: "ok",
			error: "",
			hits: body.results ?? [],
			warnings: body.warnings ?? [],
			elapsedMs: Math.round(performance.now() - t0),
			lastRequest: req,
		});
	} catch (e) {
		if (e.name === "AbortError" || inflight !== ctrl) return;
		const msg =
			e instanceof TypeError
				? `Cannot reach the API at ${CONFIG.apiBase || location.origin}`
				: e.message || String(e);
		setTextStore({ status: "error", error: msg });
	} finally {
		if (inflight === ctrl) inflight = null;
	}
}

export function exportTextResults(kind) {
	const hits = textStore.hits;
	if (!hits.length) return;
	const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
	const base = `text-search-${stamp}`;
	if (kind === "json") {
		download(
			`${base}.json`,
			JSON.stringify(
				{
					request: textStore.lastRequest,
					count: hits.length,
					results: hits,
				},
				null,
				2,
			),
			"application/json",
		);
	} else {
		const cols = [...CSV_COLS, "match_start", "match_end"];
		const rows = [
			cols.join(","),
			...hits.map((h) => cols.map((c) => csvCell(h[c])).join(",")),
		];
		download(`${base}.csv`, `\ufeff${rows.join("\r\n")}`, "text/csv");
	}
}
