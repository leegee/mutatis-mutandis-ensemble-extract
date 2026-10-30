import { createMemo, Show } from "solid-js";
import { queryTerms, shortId, splitFilter, splitHighlight } from "../helpers.js";
import { textStore } from "../textStore.js";
import { copyText } from "../toast.js";
import { FilterMark } from "./FilterMark.jsx";

function TextHighlight(props) {
	const parts = createMemo(() => {
		const q = textStore.lastRequest?.query;
		const base = splitHighlight(props.text, q ? queryTerms(q) : []);
		const f = textStore.filter.trim();
		if (!f) return base;
		return base.flatMap((seg) => splitFilter(seg.t, f).map((s) => ({ t: s.t, m: seg.m, f: s.m })));
	});
	return <span>{parts().map((s) => (s.f ? <mark class="filter">{s.t}</mark> : s.m ? <mark>{s.t}</mark> : s.t))}</span>;
}

export function TextHitCard(props) {
	const hit = props.hit;

	return (
		<li class="hit">
			<div class="hit-head">
				<span class="rank">{hit.rank}</span>
				<span class="year">{hit.pub_year || "—"}</span>
				<span class="tag">text match</span>
				<Show when={hit.match_start != null && hit.match_end != null}>
					<span class="muted" style="font-size:11px">
						match tokens {hit.match_start}:{hit.match_end}
					</span>
				</Show>
			</div>
			<p class="text">
				<TextHighlight text={hit.text ?? "[text unavailable]"} />
			</p>
			<div class="src">
				<span class="title">
					<FilterMark text={hit.title ?? "(untitled)"} filter={textStore.filter} />
				</span>
				<span>
					<FilterMark text={hit.author ?? "(unknown author)"} filter={textStore.filter} />
				</span>
				<span>
					{hit.corpus} / {hit.doc_id} · tokens {hit.token_start}:{hit.token_end}
				</span>
			</div>
			<div class="actions">
				<button class="btn small ghost" type="button" title={hit.passage_id} onClick={() => copyText(hit.passage_id)}>
					Copy ID {shortId(hit.passage_id)}
				</button>
			</div>
		</li>
	);
}
