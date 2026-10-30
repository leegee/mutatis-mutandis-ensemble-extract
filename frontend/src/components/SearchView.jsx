import { For, Show } from "solid-js";

import { addPane } from "../actions.js";
import { CONFIG } from "../config.js";
import { store } from "../store.js";
import { navigateMode } from "../urlState.js";
import { Pane } from "./Pane.jsx";

/**
 * The main multi-pane search UI. Rendered for `#/` and `#/search`.
 */
export function SearchView() {
	return (
		<>
			<header class="top">
				<h1>Passage Search</h1>
				<nav class="nav">
					<button type="button" class="btn small on">
						Semantic
					</button>
					<button
						type="button"
						class="btn small ghost"
						onClick={() => navigateMode("text")}
					>
						Text
					</button>
				</nav>
				<span
					class={
						"api" +
						(store.apiOk === true ? " ok" : store.apiOk === false ? " bad" : "")
					}
					title={store.apiError}
				>
					{store.apiOk === true
						? "API connected"
						: store.apiOk === false
							? "API unreachable"
							: "Checking API…"}
				</span>
				<span class="spacer" />
				<Show when={CONFIG.maxPanes > 1}>
					<button
						class="btn small"
						type="button"
						disabled={store.panes.length >= CONFIG.maxPanes}
						onClick={() => addPane()}
					>
						+ Add query
					</button>
				</Show>
			</header>
			<main
				class={`panes${store.panes.length === 1 ? " single" : ""}`}
				style={`--cols:${store.panes.length}`}
			>
				<For each={store.panes}>{(p) => <Pane id={p.id} />}</For>
			</main>
		</>
	);
}
