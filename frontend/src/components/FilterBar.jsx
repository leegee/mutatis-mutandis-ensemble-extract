import { Show } from "solid-js";

/**
 * Live client-side filter over already-fetched results.
 * Deliberately NOT inside the search <form>, so Enter never re-runs a search.
 */
export function FilterBar(props) {
	const active = () => props.value.trim() !== "";
	return (
		<div class="filterbar">
			<input
				class="filter"
				type="search"
				placeholder="Filter by text, title or author…"
				autocomplete="off"
				value={props.value}
				onInput={(e) => props.onChange(e.currentTarget.value)}
				onKeyDown={(e) => e.key === "Escape" && props.onChange("")}
			/>
			<Show when={active()}>
				<span class="muted">
					{props.shown} of {props.total}
				</span>
				<button class="btn small ghost" type="button" onClick={() => props.onChange("")}>
					Clear
				</button>
			</Show>
		</div>
	);
}
