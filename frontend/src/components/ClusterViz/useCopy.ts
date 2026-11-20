import { createEffect, createSignal, onCleanup, onMount } from "solid-js";
import type {
	ClusterTrace,
	ClusterVizPayload,
	DocMeta,
} from "../../types/cluster-viz";
import type { ClusterFilters } from "./useClusterFilters";

type Opts = {
	format: "markdown" | "csv";
	limit: number;
	onClick: boolean;
};

const OPT_KEY = "cluster-copy-options";
const COLS = [
	"occurrence_id",
	"cluster",
	"category",
	"year",
	"author",
	"title",
	"corpus",
	"doc_id",
	"hit_idx",
	"hit_word",
	"membership",
	"umap_x",
	"umap_y",
	"passage",
] as const;

function plain(html: string) {
	return html
		.replace(/<br>/g, " ")
		.replace(/&lt;/g, "<")
		.replace(/&gt;/g, ">")
		.replace(/&quot;/g, '"')
		.replace(/&#x27;/g, "'")
		.replace(/&amp;/g, "&");
}

function record(trace: ClusterTrace, i: number, docs: DocMeta[]) {
	const cd = trace.customdata[i];
	const d = docs[cd.docIndex] ?? {
		corpus: "",
		doc_id: "",
		author: "",
		title: "",
	};
	const p = plain(cd.passageHtml || "");
	const a = p.indexOf("«");
	const b = p.indexOf("»");
	return {
		occurrence_id: cd.occurrenceId,
		cluster: trace.cluster,
		category: trace.category,
		year: cd.year ?? cd.yearText,
		author: d.author,
		title: d.title,
		corpus: d.corpus,
		doc_id: d.doc_id,
		hit_idx: cd.hitIdx ?? "",
		hit_word: a >= 0 && b > a ? p.slice(a + 1, b) : "",
		membership: cd.membership,
		umap_x: trace.x[i],
		umap_y: trace.y[i],
		passage: p,
	};
}

function csvCell(v: unknown) {
	if (v == null) return "";
	const s =
		typeof v === "number" && !Number.isInteger(v)
			? String(Math.round(v * 1e4) / 1e4)
			: String(v);
	return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function toCSV(recs: ReturnType<typeof record>[]) {
	const lines = [COLS.join(",")];
	for (const r of recs) {
		lines.push(COLS.map((c) => csvCell((r as any)[c])).join(","));
	}
	return lines.join("\n") + "\n";
}

function mdEsc(s: unknown) {
	return String(s ?? "").replace(/([\\`*_\[\]<>])/g, "\\$1");
}

function mdPassage(p: string) {
	return mdEsc(p).replace(/«([^»]*)»/g, (_m, h) => (h ? `**${h}**` : ""));
}

function mdEntry(r: ReturnType<typeof record>, n?: number) {
	const who =
		(r.author ? mdEsc(r.author) : "") +
		(r.author && r.title ? ", " : "") +
		mdEsc(r.title);
	const lines: string[] = [];
	lines.push(
		`### ${n ? n + ". " : ""}${who || "(untitled)"}${
			r.year !== "" && r.year != null ? ` (${r.year})` : ""
		}`,
	);
	lines.push("");
	const cl =
		r.cluster === -1
			? "Noise"
			: `Cluster ${r.cluster}${r.category ? ` · ${mdEsc(r.category)}` : ""}`;
	lines.push(`- **Cluster:** ${cl}`);
	lines.push(
		`- **Source:** \`${r.corpus} / ${r.doc_id}\`${
			r.hit_idx !== "" ? `, token ${r.hit_idx}` : ""
		}`,
	);
	lines.push(
		`- **Occurrence:** \`${r.occurrence_id}\`${
			Number.isFinite(r.membership)
				? ` · membership ${Number(r.membership).toFixed(2)}`
				: ""
		}`,
	);
	lines.push("");
	lines.push(`> ${mdPassage(r.passage)}`);
	return lines.join("\n");
}

export function useCopy(data: ClusterVizPayload, filters: ClusterFilters) {
	const [opts, setOpts] = createSignal<Opts>({
		format: "markdown",
		limit: 20000,
		onClick: false,
	});
	const [hovered, setHovered] = createSignal<{ ti: number; i: number } | null>(
		null,
	);
	const [last, setLast] = createSignal<{ ti: number; i: number } | null>(null);
	const [toast, setToast] = createSignal<{ msg: string; bad?: boolean } | null>(
		null,
	);

	// load options
	try {
		const s = JSON.parse(localStorage.getItem(OPT_KEY) || "null");
		if (s) {
			setOpts({
				format: s.format === "csv" ? "csv" : "markdown",
				limit: Number.isFinite(s.limit) && s.limit >= 0 ? s.limit : 20000,
				onClick: !!s.onClick,
			});
		}
	} catch {}

	// persist options
	createEffect(() => {
		try {
			localStorage.setItem(OPT_KEY, JSON.stringify(opts()));
		} catch {}
	});

	let toastTimer: number | undefined;
	function say(msg: string, bad = false) {
		setToast({ msg, bad });
		window.clearTimeout(toastTimer);
		toastTimer = window.setTimeout(() => setToast(null), 3400);
	}

	async function copyText(text: string) {
		try {
			if (navigator.clipboard?.writeText) {
				await navigator.clipboard.writeText(text);
			} else {
				// legacy fallback
				const ta = document.createElement("textarea");
				ta.value = text;
				ta.style.position = "fixed";
				ta.style.opacity = "0";
				document.body.appendChild(ta);
				ta.select();
				document.execCommand("copy");
				document.body.removeChild(ta);
			}
			return true;
		} catch {
			return false;
		}
	}

	function finish(text: string, n: number, total: number, what: string) {
		copyText(text).then((ok) => {
			if (!ok) {
				say("The browser blocked copying. Try clicking the page first.", true);
				return;
			}
			let msg = `Copied ${what} as ${opts().format === "csv" ? "CSV" : "Markdown"}`;
			if (n < total) {
				msg += ` — first ${n.toLocaleString()} of ${total.toLocaleString()} (raise the limit in Options)`;
			}
			say(msg);
		});
	}

	function copyPoint(ti: number, i: number) {
		const traces = filters.filteredTraces();
		const t = traces[ti];
		if (!t || i == null || i >= t.customdata.length) return false;
		const r = record(t, i, data.docs);
		const text = opts().format === "csv" ? toCSV([r]) : mdEntry(r) + "\n";
		finish(text, 1, 1, "1 point");
		return true;
	}

	function copyVisible() {
		const traces = filters.filteredTraces();
		const refs: [number, number][] = [];
		traces.forEach((t, ti) => {
			// respect legend visibility if Plotly has set it
			for (let i = 0; i < t.customdata.length; i++) refs.push([ti, i]);
		});
		if (!refs.length) {
			say("No points are visible", true);
			return;
		}
		const total = refs.length;

		refs.sort((a, b) => {
			const ya = traces[a[0]].customdata[a[1]].year ?? Infinity;
			const yb = traces[b[0]].customdata[b[1]].year ?? Infinity;
			if (ya !== yb) return ya - yb;
			const ca = traces[a[0]].cluster;
			const cb = traces[b[0]].cluster;
			if (ca !== cb) return ca - cb;
			return String(traces[a[0]].customdata[a[1]].occurrenceId).localeCompare(
				String(traces[b[0]].customdata[b[1]].occurrenceId),
			);
		});

		const limit = opts().limit;
		const sliced =
			limit > 0 && refs.length > limit ? refs.slice(0, limit) : refs;
		const recs = sliced.map(([ti, i]) => record(traces[ti], i, data.docs));

		const text =
			opts().format === "csv"
				? toCSV(recs)
				: toMarkdown(recs, recs.length, total, data.runId, filters);

		finish(
			text,
			recs.length,
			total,
			`${recs.length.toLocaleString()} visible point${recs.length === 1 ? "" : "s"}`,
		);
	}

	function handleClick(ti: number, i: number) {
		if (opts().onClick) copyPoint(ti, i);
	}

	// keyboard C
	onMount(() => {
		const onKey = (e: KeyboardEvent) => {
			if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
			if (e.key !== "c" && e.key !== "C") return;
			const el = e.target as HTMLElement;
			const tag = el?.tagName?.toLowerCase() ?? "";
			if (
				tag === "input" ||
				tag === "textarea" ||
				tag === "select" ||
				el?.isContentEditable
			)
				return;
			e.preventDefault();
			const h = hovered();
			if (h) copyPoint(h.ti, h.i);
			else say("Hover a point, then press C", true);
		};
		document.addEventListener("keydown", onKey);
		onCleanup(() => document.removeEventListener("keydown", onKey));
	});

	return {
		opts,
		setOpts,
		hovered,
		setHovered: (h: { ti: number; i: number } | null) => {
			setHovered(h);
			if (h) setLast(h);
		},
		last,
		toast,
		copyHovered: () => {
			const l = last();
			if (l) copyPoint(l.ti, l.i);
			else say("Hover a point first (then press C, or use this button)", true);
		},
		copyVisible,
		handleClick,
	};
}

function toMarkdown(
	recs: ReturnType<typeof record>[],
	shown: number,
	total: number,
	runId: string,
	filters: ClusterFilters,
) {
	const head = [
		"# Occurrences",
		"",
		`Run \`${runId}\` · ${shown.toLocaleString()} point${shown === 1 ? "" : "s"}${
			shown < total
				? ` (first ${shown.toLocaleString()} of ${total.toLocaleString()} visible, by year)`
				: ""
		}.`,
		`Filter: ${describeFilter(filters)}.`,
		"",
	];
	return (
		head.join("\n") +
		"\n" +
		recs.map((r, i) => mdEntry(r, i + 1)).join("\n\n") +
		"\n"
	);
}

function describeFilter(f: ClusterFilters) {
	const parts: string[] = [];
	const ts = f.terms();
	const inc = ts.filter((t) => t.on && !t.neg).map((t) => t.text);
	const exc = ts.filter((t) => t.on && t.neg).map((t) => t.text);
	if (inc.length) parts.push(`include ${f.mode()} of [${inc.join(", ")}]`);
	if (exc.length) parts.push(`exclude [${exc.join(", ")}]`);
	if (inc.length || exc.length) {
		const scopeLabel =
			{
				passage: "the passage",
				hit: "the hit word",
				context: "the context only",
			}[f.scope()] ?? f.scope();
		parts.push(`in ${scopeLabel}${f.whole() ? ", whole words" : ""}`);
	}
	const [b0, b1] = f.yearBounds;
	if (f.yearLo() > b0 || f.yearHi() < b1) {
		parts.push(`years ${f.yearLo()}–${f.yearHi()}`);
	}
	return parts.length ? parts.join("; ") : "none";
}

export type CopyControls = ReturnType<typeof useCopy>;
