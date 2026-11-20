import { createEffect, Match, onMount, Switch, untrack } from "solid-js";

import { checkApiHealth, fetchApiDictionaries, runSearch } from "../actions.js";
import { CONFIG } from "../config";
import { match, ROUTES, route } from "../router.js";
import { store } from "../store.js";
import { runTextSearch } from "../textActions.js";
import { toast } from "../toast.js";
import {
	applySemanticParams,
	applyTextParams,
	hasSemanticQuery,
	hasTextQuery,
	routeSync,
} from "../urlState.js";

import { AppHeader } from "./AppHeader.jsx";
import { ClusterViz } from "./ClusterViz/ClusterViz";
import { NotFound } from "./NotFound.jsx";
import { SearchView } from "./SearchView.jsx";
import { TextSearchView } from "./TextSearchView.jsx";

export function App() {
	onMount(() => {
		fetchApiDictionaries();
		setInterval(checkApiHealth, 10_000);
	});

	// Persist the form state (not the results) across reloads.
	createEffect(() => {
		const snap = store.panes.map((p) => ({
			label: p.label,
			source: { ...p.source },
			form: { ...p.form },
			negatives: p.negatives.map((n) => ({ ...n })),
		}));
		try {
			localStorage.setItem(CONFIG.storageKey, JSON.stringify(snap));
		} catch {
			/* ignore */
		}
	});

	// Hydrate from hash on load and on back/forward (and deep links).
	// IMPORTANT: only route() may be tracked here. applySemanticParams,
	// applyTextParams, runSearch and runTextSearch all read the stores; if they
	// ran tracked, every keystroke/commit in a form field would re-run this
	// effect and re-apply the *previous* URL over what the user just entered.
	createEffect(() => {
		const r = route(); // the only dependency
		untrack(() => {
			if (routeSync.suppressApply) {
				routeSync.suppressApply = false;
				return;
			}

			const firstId = store.panes[0]?.id;
			if (match(ROUTES.home) || match(ROUTES.search)) {
				if (firstId && hasSemanticQuery(r.params)) {
					applySemanticParams(r.params, firstId);
					runSearch(firstId, { updateUrl: false });
				}
			} else if (match(ROUTES.text)) {
				if (hasTextQuery(r.params)) {
					applyTextParams(r.params);
					runTextSearch({ updateUrl: false });
				}
			}
		});
	});

	const mode = () => {
		if (match(ROUTES.home) || match(ROUTES.search)) return "search";
		if (match(ROUTES.text)) return "semantic";
		if (match(ROUTES.cluster)) return "cluster";
		return null;
	};

	return (
		<div class="shell">
			<AppHeader mode={mode()} />

			<Switch fallback={<NotFound />}>
				<Match when={match(ROUTES.home) || match(ROUTES.search)}>
					<SearchView />
				</Match>
				<Match when={match(ROUTES.text)}>
					<TextSearchView />
				</Match>
				<Match when={match(ROUTES.cluster)}>
					<ClusterViz runId="l8-target-form-20261118-083730" />
				</Match>
			</Switch>

			<aside class={`toast${toast() ? " show" : ""}`} role="status">
				{toast()}
			</aside>
		</div>
	);
}
