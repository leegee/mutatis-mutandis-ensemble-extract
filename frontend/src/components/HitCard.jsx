import { Show } from "solid-js";
import { findSimilar, toggleNegative } from "../actions.js";
import { scoreLabel, scoreTitle, shortId } from "../helpers.js";
import { overlaps } from "../overlaps.js";
import { pane } from "../store.js";
import { copyText } from "../toast.js";
import { FilterMark } from "./FilterMark.jsx";
import { Highlight } from "./Highlight.jsx";

export function HitCard(props) {
	const id = props.paneId;
	const hit = props.hit;
	const p = () => pane(id);
	const isNeg = () => !!p()?.negatives.some((n) => n.id === hit.passage_id);
	const isSrc = () => p()?.lastRequest?.vector_id === hit.passage_id;
	const also = () => overlaps(id, hit);

	return (
		<li class={`hit${isNeg() ? " is-neg" : ""}${isSrc() ? " is-src" : ""}`}>
			<div class="hit-head">
				<span class="rank">{hit.rank}</span>
				<span class="year">{hit.pub_year}</span>
				<span title={scoreTitle(hit)}>{scoreLabel(hit)}</span>
				<Show when={isSrc()}>
					<span class="tag">query passage</span>
				</Show>
				<Show when={isNeg()}>
					<span class="tag neg">excluded</span>
				</Show>
				<Show when={also().length > 0}>
					<span class="tag also" title="A passage from the same document overlaps in the other pane(s)">
						also in {also().join(", ")}
					</span>
				</Show>
			</div>
			<p class="text">
				<Highlight paneId={id} text={hit.text ?? "[text unavailable]"} />
			</p>
			<div class="src">
				<span class="title">
					<FilterMark text={hit.title ?? "(untitled)"} filter={p()?.filter} />
				</span>
				<span>
					<FilterMark text={hit.author ?? "(unknown author)"} filter={p()?.filter} />
				</span>
				<span>
					{hit.corpus} / {hit.doc_id} · tokens {hit.token_start}:{hit.token_end}
				</span>
			</div>
			<div class="actions">
				<button
					class="btn small"
					type="button"
					title="Search for passages similar to this one"
					onClick={() => findSimilar(id, hit)}
				>
					Find similar
				</button>
				<button type="button" class={`btn small${isNeg() ? " on" : ""}`} onClick={() => toggleNegative(id, hit)}>
					{isNeg() ? "Undo exclude" : "Not relevant"}
				</button>
				<button class="btn small ghost" type="button" title={hit.passage_id} onClick={() => copyText(hit.passage_id)}>
					Copy ID {shortId(hit.passage_id)}
				</button>
			</div>
		</li>
	);
}
