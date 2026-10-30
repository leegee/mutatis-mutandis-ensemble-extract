import { createEffect, createMemo, For, Show } from "solid-js";
import { filterHits } from "../helpers.js";
import { store } from "../store.js";
import { exportTextResults, runTextSearch } from "../textActions.js";
import { setTextStore, textStore } from "../textStore.js";
import { navigateMode } from "../urlState.js";
import { FilterBar } from "./FilterBar.jsx";
import { TextHitCard } from "./TextHitCard.jsx";

export function TextSearchView() {
	const val = (key) => textStore.form[key] ?? "";
	const setField = (key) => (e) => setTextStore("form", { [key]: e.currentTarget.value });

	const visible = createMemo(() => filterHits(textStore.hits, textStore.filter));

	// Uncontrolled query input (see SearchForm for the rationale).
	let queryInput;
	let committed = textStore.form.query ?? "";

	createEffect(() => {
		const fromStore = textStore.form.query ?? "";
		if (fromStore !== committed) {
			committed = fromStore;
			if (queryInput && queryInput.value !== fromStore) queryInput.value = fromStore;
		}
	});

	function onSubmit(e) {
		e.preventDefault();
		const q = (queryInput?.value ?? "").trim();
		committed = q; // set BEFORE the store write
		setTextStore("form", { query: q });
		runTextSearch();
	}

	return (
		<>
			<header class="top">
				<h1>Passage Search</h1>
				<nav class="nav">
					<button type="button" class="btn small ghost" onClick={() => navigateMode("semantic")}>
						Semantic
					</button>
					<button type="button" class="btn small on">
						Text
					</button>
				</nav>
				<span class={`api${store.apiOk === true ? " ok" : store.apiOk === false ? " bad" : ""}`} title={store.apiError}>
					{store.apiOk === true ? "API connected" : store.apiOk === false ? "API unreachable" : "Checking API…"}
				</span>
				<span class="spacer" />
			</header>

			<main class="panes single">
				<section class="pane">
					<form class="form" onSubmit={onSubmit}>
						<label class="field wide">
							<span>Phrase or keywords</span>
							<input
								class="q"
								type="search"
								placeholder="e.g. white hair"
								autocomplete="off"
								ref={(el) => {
									queryInput = el;
									el.value = committed;
								}}
							/>
						</label>
						<div class="row">
							<label class="field num">
								<span>From year</span>
								<input type="text" inputmode="numeric" value={val("startYear")} onInput={setField("startYear")} />
							</label>
							<label class="field num">
								<span>To year</span>
								<input type="text" inputmode="numeric" value={val("endYear")} onInput={setField("endYear")} />
							</label>
							<label class="field num">
								<span>Limit</span>
								<input type="text" inputmode="numeric" value={val("limit")} onInput={setField("limit")} />
							</label>
							<label class="field num">
								<span>Window</span>
								<input
									type="text"
									inputmode="numeric"
									value={val("windowTokens")}
									onInput={setField("windowTokens")}
									title="Tokens of context on each side of the match"
								/>
							</label>
							<button class="btn primary" type="submit" disabled={textStore.status === "loading"}>
								{textStore.status === "loading" ? "Searching…" : "Search"}
							</button>
						</div>
						<p class="muted" style="font-size:12px;margin:0">
							Exact phrase match over tokenised text in Postgres (case-insensitive). Window is how many tokens of
							context are shown around each hit.
						</p>
					</form>

					<Show when={textStore.status === "error"}>
						<div class="banner error" role="alert">
							{textStore.error}
						</div>
					</Show>
					<Show when={textStore.warnings.length > 0}>
						<div class="banner warn">
							<For each={textStore.warnings}>{(w) => <div>{w}</div>}</For>
						</div>
					</Show>
					<Show when={!!textStore.lastRequest}>
						<div class="meta">
							<span>
								{textStore.hits.length} result{textStore.hits.length === 1 ? "" : "s"} · {textStore.elapsedMs} ms
							</span>
							<span class="spacer" />
							<button class="btn small ghost" type="button" onClick={() => exportTextResults("json")}>
								Export JSON
							</button>
							<button class="btn small ghost" type="button" onClick={() => exportTextResults("csv")}>
								Export CSV
							</button>
						</div>
					</Show>

					<Show when={textStore.hits.length > 0}>
						<FilterBar
							value={textStore.filter}
							shown={visible().length}
							total={textStore.hits.length}
							onChange={(v) => setTextStore("filter", v)}
						/>
					</Show>
					<ol class={`hits${textStore.status === "loading" ? " dim" : ""}`}>
						<For each={visible()}>{(hit) => <TextHitCard hit={hit} />}</For>
					</ol>
					<Show when={textStore.status === "ok" && textStore.hits.length > 0 && visible().length === 0}>
						<p class="empty">No results match the filter.</p>
					</Show>
					<Show when={textStore.status === "ok" && textStore.hits.length === 0}>
						<p class="empty">No passages matched this phrase in the selected year range.</p>
					</Show>
					<Show when={textStore.status === "idle"}>
						<p class="empty">Enter a phrase and press Search.</p>
					</Show>
				</section>
			</main>
		</>
	);
}
