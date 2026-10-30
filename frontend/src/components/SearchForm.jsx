import { createEffect, For, Show } from "solid-js";
import { clearVectorSource, runSearch } from "../actions.js";
import { shortId } from "../helpers.js";
import { pane, store, update } from "../store.js";

export function SearchForm(props) {
	const id = props.id;
	const p = () => pane(id);
	const val = (key) => p()?.form[key] ?? "";
	const setField = (key) => (e) => update(id, "form", { [key]: e.currentTarget.value });

	// Uncontrolled query input: the DOM owns keystrokes until submit.
	// `committed` is the last value we know the store has; the input is only
	// written to when the store changes to something else (URL hydrate, etc.).
	let queryInput;
	let committed = p()?.source.text ?? "";

	createEffect(() => {
		if (p()?.source.mode === "vector") return;
		const fromStore = p()?.source.text ?? "";
		if (fromStore !== committed) {
			committed = fromStore;
			if (queryInput && queryInput.value !== fromStore) queryInput.value = fromStore;
		}
	});

	function onSubmit(e) {
		e.preventDefault();
		// In vector ("find similar") mode there is no query input on screen, and
		// queryInput points at a detached element. Keep the vector source and
		// just re-run with the new form values.
		if (p()?.source.mode === "vector") {
			runSearch(id);
			return;
		}
		const q = (queryInput?.value ?? "").trim();
		committed = q; // set BEFORE the store write so the effect above sees no change
		update(id, "source", { mode: "text", text: q, vectorId: "", vectorLabel: "" });
		runSearch(id);
	}

	return (
		<form class="form" onSubmit={onSubmit}>
			<Show
				when={p()?.source.mode === "vector"}
				fallback={
					<label class="field wide">
						<span>Query</span>
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
				}
			>
				<div class="field wide">
					<span>Passages similar to</span>
					<div class="vecchip">
						<code>{shortId(p()?.source.vectorId)}</code>
						<span class="muted">{p()?.source.vectorLabel}</span>
						<button
							class="btn small"
							type="button"
							onClick={() => {
								clearVectorSource(id);
								committed = pane(id)?.source.text ?? "";
								if (queryInput) queryInput.value = committed;
							}}
						>
							Use text query
						</button>
					</div>
				</div>
			</Show>

			<div class="row">
				<label class="field">
					<span>Representation</span>
					<select onChange={setField("representation")}>
						<For each={store.representations}>
							{(r) => (
								<option value={r} selected={p()?.form.representation === r}>
									{r}
								</option>
							)}
						</For>
					</select>
				</label>
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
				<button class="btn primary" type="submit" disabled={p()?.status === "loading"}>
					{p()?.status === "loading" ? "Searching…" : "Search"}
				</button>
			</div>

			<details class="adv">
				<summary>Re-ranking</summary>
				<div class="row">
					<label class="field num">
						<span>Beta</span>
						<input type="text" inputmode="decimal" value={val("beta")} onInput={setField("beta")} />
					</label>
					<label class="field num">
						<span>Overfetch</span>
						<input type="text" inputmode="numeric" value={val("overfetch")} onInput={setField("overfetch")} />
					</label>
					<span class="muted" style="font-size:12px;max-width:340px">
						Beta weighs the excluded passages against the query; overfetch is how many times <em>limit</em> candidates
						are drawn per table before re-ranking.
					</span>
				</div>
			</details>
		</form>
	);
}
