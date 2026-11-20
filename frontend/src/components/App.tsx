import { useLocation, useNavigate } from "@solidjs/router";
import type { JSX } from "solid-js";
import { createEffect, onMount, untrack } from "solid-js";

import {
	checkApiHealth,
	fetchApiDictionaries,
	runSearch,
	setRouterNavigate,
} from "../actions";

import { CONFIG } from "../config.jsx";
import { store } from "../store.js";
import { runTextSearch } from "../textactions";
import { toast } from "../toast.js";

import {
	applySemanticParams,
	applyTextParams,
	hasSemanticQuery,
	hasTextQuery,
	routeSync,
} from "../urlState";

import { AppHeader } from "./AppHeader";

import "../css/styles.css";

export function App(props: { children?: JSX.Element }) {
	const location = useLocation();
	const navigate = useNavigate();

	setRouterNavigate(navigate);

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

	// Hydrate from the URL on load and on back/forward navigation.
	//
	// IMPORTANT: only location.pathname and location.search are
	// tracked here. The functions called inside untrack() read
	// stores, and must not cause this effect to rerun when form
	// state changes.
	createEffect(() => {
		const pathname = location.pathname;
		const params = new URLSearchParams(location.search);

		untrack(() => {
			if (routeSync.suppressApply) {
				routeSync.suppressApply = false;
				return;
			}

			const firstId = store.panes[0]?.id;

			if (pathname === "/" || pathname === "/search") {
				if (firstId && hasSemanticQuery(params)) {
					applySemanticParams(params, firstId);
					runSearch(firstId, { updateUrl: false });
				}
			} else if (pathname === "/text") {
				if (hasTextQuery(params)) {
					applyTextParams(params);
					runTextSearch({ updateUrl: false });
				}
			}
		});
	});

	return (
		<div class="shell">
			<AppHeader />

			{props.children}

			<aside class={`toast${toast() ? " show" : ""}`} role="status">
				{toast()}
			</aside>
		</div>
	);
}
