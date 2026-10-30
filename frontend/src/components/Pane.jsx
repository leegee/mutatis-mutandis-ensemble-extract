import { Show } from "solid-js";

import { removePane } from "../actions.js";
import { pane, store } from "../store.js";

import { Histogram } from "./Histogram.jsx";
import { Negatives } from "./Negatives.jsx";
import { Results } from "./Results.jsx";
import { SearchForm } from "./SearchForm.jsx";
import { StatusBar } from "./StatusBar.jsx";

export function Pane(props) {
	const id = props.id;
	return (
		<section class="pane">
			<div class="pane-head">
				<span class="badge">{pane(id)?.label}</span>
				<span class="spacer" />
				<Show when={store.panes.length > 1}>
					<button
						class="btn small ghost"
						type="button"
						onClick={() => removePane(id)}
					>
						Remove
					</button>
				</Show>
			</div>
			<SearchForm id={id} />
			<Negatives id={id} />
			<StatusBar id={id} />
			<Histogram id={id} />
			<Results id={id} />
		</section>
	);
}
