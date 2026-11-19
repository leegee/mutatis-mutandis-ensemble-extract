import { createEffect, createMemo, createSignal, onCleanup } from "solid-js";
import type {
	ClusterTrace,
	ClusterVizPayload,
	PointCustom,
} from "../../types/cluster-viz";

export type Term = {
	text: string;
	neg: boolean;
	on: boolean;
};

export type FilterState = {
	terms: Term[];
	mode: "any" | "all";
	scope: "passage" | "hit" | "context";
	whole: boolean;
	yearLo: number;
	yearHi: number;
};

function fold(s: string): string {
	return s.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "");
}

function plain(html: string): string {
	return html
		.replace(/<br>/g, " ")
		.replace(/&lt;/g, "<")
		.replace(/&gt;/g, ">")
		.replace(/&quot;/g, '"')
		.replace(/&#x27;/g, "'")
		.replace(/&amp;/g, "&");
}

function extractText(p: PointCustom, scope: FilterState["scope"]): string {
	const raw = plain(p.passageHtml || "");
	if (scope === "hit") {
		const a = raw.indexOf("«");
		const b = raw.indexOf("»");
		return a >= 0 && b > a ? raw.slice(a + 1, b) : "";
	}
	if (scope === "context") {
		return raw.replace(/«[^»]*»/, " ");
	}
	return raw.replace(/[«»]/g, "");
}

function makeMatcher(term: string, whole: boolean) {
	const needle = fold(term);
	if (!whole) return (s: string) => s.includes(needle);
	const esc = needle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
	const rx = new RegExp(`(?:^|[^\\p{L}\\p{N}])${esc}(?![\\p{L}\\p{N}])`, "u");
	return (s: string) => rx.test(s);
}

export function useClusterFilters(data: ClusterVizPayload) {
	const storageKey = `cluster-terms:${data.runId}`;
	const bounds = data.yearBounds ?? [0, 9999];

	// ---------- state ----------
	const [terms, setTerms] = createSignal<Term[]>([]);
	const [mode, setMode] = createSignal<"any" | "all">("any");
	const [scope, setScope] = createSignal<"passage" | "hit" | "context">(
		"passage",
	);
	const [whole, setWhole] = createSignal(false);
	const [yearLo, setYearLo] = createSignal(bounds[0]);
	const [yearHi, setYearHi] = createSignal(bounds[1]);

	// ---------- restore ----------
	try {
		const raw = localStorage.getItem(storageKey);
		if (raw) {
			const s = JSON.parse(raw);
			if (Array.isArray(s.terms)) {
				setTerms(
					s.terms
						.filter((t: any) => t?.text)
						.map((t: any) => ({
							text: String(t.text),
							neg: !!t.neg,
							on: t.on !== false,
						})),
				);
			}
			if (s.mode === "all" || s.mode === "any") setMode(s.mode);
			if (["passage", "hit", "context"].includes(s.scope)) setScope(s.scope);
			if (typeof s.whole === "boolean") setWhole(s.whole);
		}
	} catch {
		/* ignore corrupt storage */
	}

	// seed from API if provided and nothing was restored
	if (data.seedTerms?.length && terms().length === 0) {
		addTerms(data.seedTerms.join(","));
	}

	// ---------- persistence ----------
	createEffect(() => {
		const payload = {
			terms: terms().map((t) => ({ text: t.text, neg: t.neg, on: t.on })),
			mode: mode(),
			scope: scope(),
			whole: whole(),
		};
		try {
			localStorage.setItem(storageKey, JSON.stringify(payload));
		} catch {
			/* quota / private mode */
		}
	});

	// ---------- helpers ----------
	function addTerms(raw: string) {
		const next = [...terms()];
		for (const piece of raw.split(",")) {
			let s = piece.trim();
			let neg = false;
			if (s.startsWith("-") || s.startsWith("−")) {
				neg = true;
				s = s.slice(1).trim();
			}
			if (!s) continue;
			const exists = next.some(
				(t) => t.neg === neg && t.text.toLowerCase() === s.toLowerCase(),
			);
			if (!exists) next.push({ text: s, neg, on: true });
		}
		setTerms(next);
	}

	function toggleTerm(idx: number) {
		setTerms((ts) => ts.map((t, i) => (i === idx ? { ...t, on: !t.on } : t)));
	}

	function removeTerm(idx: number) {
		setTerms((ts) => ts.filter((_, i) => i !== idx));
	}

	function clearTerms() {
		setTerms([]);
	}

	function setYears(lo: number, hi: number) {
		const a = Math.min(Math.max(lo, bounds[0]), bounds[1]);
		const b = Math.min(Math.max(hi, bounds[0]), bounds[1]);
		setYearLo(Math.min(a, b));
		setYearHi(Math.max(a, b));
	}

	// ---------- derived: filtered traces + per-term counts ----------
	const filtered = createMemo(() => {
		const ts = terms();
		const m = mode();
		const sc = scope();
		const wh = whole();
		const yLo = yearLo();
		const yHi = yearHi();
		const yFull = yLo <= bounds[0] && yHi >= bounds[1];

		// pre-compute matchers
		const matchers = ts.map((t) => ({
			...t,
			match: makeMatcher(t.text, wh),
		}));

		const counts = new Array(ts.length).fill(0);
		const result: ClusterTrace[] = [];

		for (const trace of data.traces) {
			const xs: number[] = [];
			const ys: number[] = [];
			const cds: PointCustom[] = [];

			for (let i = 0; i < trace.x.length; i++) {
				const cd = trace.customdata[i];

				// year
				if (!yFull) {
					const yr = cd.year;
					if (yr == null) continue;
					if (yr < yLo || yr > yHi) continue;
				}

				// terms
				if (matchers.length) {
					const text = fold(extractText(cd, sc));
					let incHits = 0;
					let excHit = false;
					const nInc = matchers.filter((t) => t.on && !t.neg).length;

					for (let k = 0; k < matchers.length; k++) {
						const t = matchers[k];
						const hit = t.match(text);
						if (hit) counts[k]++;
						if (t.on && hit) {
							if (t.neg) excHit = true;
							else incHits++;
						}
					}
					const okInc =
						nInc === 0 || (m === "all" ? incHits === nInc : incHits > 0);
					if (!okInc || excHit) continue;
				}

				xs.push(trace.x[i]);
				ys.push(trace.y[i]);
				cds.push(cd);
			}

			result.push({
				...trace,
				x: xs,
				y: ys,
				customdata: cds,
			});
		}

		// attach live counts back onto terms (for chips)
		// we return both so the UI can read them
		return { traces: result, counts };
	});

	const shownCount = createMemo(() =>
		filtered().traces.reduce((s, t) => s + t.x.length, 0),
	);

	return {
		// state
		terms,
		mode,
		scope,
		whole,
		yearLo,
		yearHi,
		yearBounds: bounds,

		// setters
		setMode,
		setScope,
		setWhole,
		setYears,
		addTerms,
		toggleTerm,
		removeTerm,
		clearTerms,

		// derived
		filteredTraces: () => filtered().traces,
		termCounts: () => filtered().counts,
		shownCount,
		totalCount: data.nPoints,
	};
}

export type ClusterFilters = ReturnType<typeof useClusterFilters>;
