import { createMemo } from "solid-js";
import { queryTerms, splitFilter, splitHighlight } from "../helpers.js";
import { pane } from "../store.js";

export function Highlight(props) {
	const parts = createMemo(() => {
		const p = pane(props.paneId);
		const q = p?.lastRequest?.query;
		const base = splitHighlight(props.text, q ? queryTerms(q) : []);
		const f = p?.filter?.trim();
		if (!f) return base;
		// Layer filter matches on top of the query-term highlighting.
		return base.flatMap((seg) => splitFilter(seg.t, f).map((s) => ({ t: s.t, m: seg.m, f: s.m })));
	});
	return <span>{parts().map((s) => (s.f ? <mark class="filter">{s.t}</mark> : s.m ? <mark>{s.t}</mark> : s.t))}</span>;
}
