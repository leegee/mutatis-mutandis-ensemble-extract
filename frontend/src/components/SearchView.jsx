import { For } from "solid-js";

import { store } from "../store.js";
import { Pane } from "./Pane.jsx";

/**
 * The main multi-pane search UI. Rendered for `#/` and `#/search`.
 */
export function SearchView() {
	return (
		<main
			class={`panes${store.panes.length === 1 ? " single" : ""}`}
			style={`--cols:${store.panes.length}`}
		>
			<For each={store.panes}>{(p) => <Pane id={p.id} />}</For>
		</main>
	);
}
