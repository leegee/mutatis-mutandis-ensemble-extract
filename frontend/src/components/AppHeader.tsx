import { useLocation, useNavigate } from "@solidjs/router";
import { Show } from "solid-js";
import { addPane } from "../actions";
import { CONFIG } from "../config.jsx";
import { store } from "../store.js";
import { navigateMode } from "../urlState";

export function AppHeader(props) {
	const location = useLocation();
	const navigate = useNavigate();

	return (
		<header class="top">
			<h1>Passage Search</h1>
			<nav class="nav">
				<button
					type="button"
					class={`btn small ${props.mode === "semantic" ? "on" : "ghost"}`}
					onClick={() => navigateMode("semantic", location.pathname, navigate)}
				>
					Semantic
				</button>
				<button
					type="button"
					class={`btn small ${props.mode === "text" ? "on" : "ghost"}`}
					onClick={() => navigateMode("text", location.pathname, navigate)}
				>
					Text
				</button>
				<button
					type="button"
					class={`btn small ${props.mode === "cluster" ? "on" : "ghost"}`}
					onClick={() => navigateMode("cluster", location.pathname, navigate)}
				>
					Cluster
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
