import { Show } from "solid-js";

import { addPane } from "../actions.js";
import { CONFIG } from "../config.js";
import { store } from "../store.js";
import { navigateMode } from "../urlState.js";

export function AppHeader(props) {
	return (
		<header class="top">
			<h1>Passage Search</h1>
			<nav class="nav">
				<button
					type="button"
					class={`btn small ${props.mode === "semantic" ? "on" : "ghost"}`}
					onClick={() => navigateMode("semantic")}
				>
					Semantic
				</button>
				<button
					type="button"
					class={`btn small ${props.mode === "text" ? "on" : "ghost"}`}
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

			<Show when={props.mode === "semantic" && CONFIG.maxPanes > 1}>
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
	);
}
