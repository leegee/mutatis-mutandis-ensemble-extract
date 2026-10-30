/** biome-ignore-all lint/suspicious/noAssignInExpressions: <prototype> */
export const shortId = (id) => (id ? id.slice(0, 8) : "");

export const snippet = (text, n = 90) => {
	const t = (text ?? "").replace(/\s+/g, " ").trim();
	return t.length > n ? `${t.slice(0, n - 1)}…` : t;
};

export function toInt(s, name) {
	const t = String(s ?? "").trim();
	if (t === "" || !Number.isInteger(Number(t))) throw new Error(`${name} must be a whole number`);
	return Number(t);
}

export function toNum(s, name) {
	const t = String(s ?? "").trim();
	if (t === "" || !Number.isFinite(Number(t))) throw new Error(`${name} must be a number`);
	return Number(t);
}

export function formatDetail(body, res) {
	const d = body?.detail;
	if (typeof d === "string") return d;
	if (Array.isArray(d)) {
		return d.map((x) => `${(x.loc || []).slice(1).join(".") || "request"}: ${x.msg}`).join("; ");
	}
	return `HTTP ${res.status} ${res.statusText}`.trim();
}

const STOP = new Set(
	(
		"the and for with from that this was were are his her its not but you all can had has have " +
		"him who what when will one our out their they them then than there these those into over upon shall unto"
	).split(" "),
);

export const queryTerms = (q) => [
	...new Set((q.toLowerCase().match(/[a-z\u00c0-\u024f']+/g) ?? []).filter((w) => w.length >= 3 && !STOP.has(w))),
];

export const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function splitHighlight(text, terms) {
	if (!terms.length) return [{ t: text, m: false }];
	const re = new RegExp(`\\b(${terms.map(escapeRe).join("|")})\\b`, "gi");
	const out = [];
	let last = 0,
		m;
	while ((m = re.exec(text))) {
		if (m.index > last) out.push({ t: text.slice(last, m.index), m: false });
		out.push({ t: m[0], m: true });
		last = m.index + m[0].length;
	}
	if (last < text.length) out.push({ t: text.slice(last), m: false });
	return out;
}

export function computeBins(hits) {
	if (!hits.length) return [];
	const years = hits.map((h) => h.pub_year);
	const min = Math.min(...years),
		max = Math.max(...years);
	const size = [1, 5, 10, 25, 50, 100, 250].find((s) => (max - min) / s <= 40) ?? 500;
	const first = Math.floor(min / size) * size;
	const bins = [];
	for (let s = first; s <= max; s += size) bins.push({ start: s, end: s + size - 1, count: 0 });
	for (const y of years) bins[Math.floor((y - first) / size)].count++;
	return bins;
}

export const scoreLabel = (h) => (h.score != null ? `score ${h.score.toFixed(3)}` : `dist ${h.distance.toFixed(4)}`);

export const scoreTitle = (h) =>
	`distance ${h.distance.toFixed(4)}` +
	(h.sim_q != null ? ` · sim(query) ${h.sim_q.toFixed(4)} · sim(negatives) ${h.sim_neg.toFixed(4)}` : "");

export const csvCell = (v) => {
	const s = v == null ? "" : String(v);
	return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export const CSV_COLS = [
	"rank",
	"passage_id",
	"pub_year",
	"distance",
	"score",
	"sim_q",
	"sim_neg",
	"corpus",
	"doc_id",
	"title",
	"author",
	"filepath",
	"token_start",
	"token_end",
	"text",
];

// ---- Client-side result filter -------------------------------------------
// Case-insensitive substring match on passage text, title or author; any run of whitespace in
// the needle matches any run of whitespace in the text (passages can contain
// newlines).
const filterRe = (needle, flags = "i") => {
	const n = (needle ?? "").trim();
	return n ? new RegExp(escapeRe(n).replace(/\s+/g, "\\s+"), flags) : null;
};

export function filterHits(hits, needle) {
	const re = filterRe(needle);
	return re ? hits.filter((h) => [h.text, h.title, h.author].some((v) => re.test(v ?? ""))) : hits;
}

/** Split text into [{t, m}] segments where m marks a filter match. */
export function splitFilter(text, needle) {
	const re = filterRe(needle, "gi");
	if (!re) return [{ t: text, m: false }];
	const out = [];
	let last = 0,
		m;
	while ((m = re.exec(text))) {
		if (!m[0]) {
			re.lastIndex++;
			continue;
		}
		if (m.index > last) out.push({ t: text.slice(last, m.index), m: false });
		out.push({ t: m[0], m: true });
		last = m.index + m[0].length;
	}
	if (last < text.length) out.push({ t: text.slice(last), m: false });
	return out;
}
