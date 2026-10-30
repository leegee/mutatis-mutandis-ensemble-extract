import { createMemo, For, Show } from "solid-js";
import { filterHits } from "../helpers.js";
import { pane, update } from "../store.js";
import { FilterBar } from "./FilterBar.jsx";
import { HitCard } from "./HitCard.jsx";

export function Results(props) {
	const id = props.id;
	const p = () => pane(id);
	const visible = createMemo(() => filterHits(p()?.hits ?? [], p()?.filter ?? ""));
	return (
		<div>
			<Show when={(p()?.hits.length ?? 0) > 0}>
				<FilterBar
					value={p().filter}
					shown={visible().length}
					total={p().hits.length}
					onChange={(v) => update(id, "filter", v)}
				/>
			</Show>
			<ol class={`hits${p()?.status === "loading" ? " dim" : ""}`}>
				<For each={visible()}>{(hit) => <HitCard paneId={id} hit={hit} />}</For>
			</ol>
			<Show when={p()?.status === "ok" && p().hits.length > 0 && visible().length === 0}>
				<p class="empty">No results match the filter.</p>
			</Show>
			<Show when={p()?.status === "ok" && p().hits.length === 0}>
				<p class="empty">No passages found for this query and year range.</p>
			</Show>
			<Show when={p()?.status === "idle"}>
				<p class="empty">Enter a query and press Search.</p>
			</Show>
		</div>
	);
}
