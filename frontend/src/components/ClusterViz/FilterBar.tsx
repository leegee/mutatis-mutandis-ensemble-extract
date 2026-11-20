import { For, Show } from "solid-js";
import type { ClusterFilters } from "./useClusterFilters";

import "./FilterBar.css";

export function FilterBar(props: {
	filters: ClusterFilters;
	yearBounds: [number, number] | null;
}) {
	const f = props.filters;
	let inputEl: HTMLInputElement | undefined;

	function submit() {
		const v = inputEl?.value.trim();
		if (v) {
			f.addTerms(v);
			if (inputEl) inputEl.value = "";
		}
	}

	return (
		<>
			<Show when={props.yearBounds}>
				{(bounds) => (
					<div class="filter-row">
						<label class="filter-label">
							From
							<input
								type="range"
								min={bounds()[0]}
								max={bounds()[1]}
								value={f.yearLo()}
								onInput={(e) => f.setYears(+e.currentTarget.value, f.yearHi())}
								class="filter-range"
							/>
							<input
								type="number"
								min={bounds()[0]}
								max={bounds()[1]}
								value={f.yearLo()}
								onChange={(e) => f.setYears(+e.currentTarget.value, f.yearHi())}
								class="filter-number"
							/>
						</label>
						<label class="filter-label">
							To
							<input
								type="range"
								min={bounds()[0]}
								max={bounds()[1]}
								value={f.yearHi()}
								onInput={(e) => f.setYears(f.yearLo(), +e.currentTarget.value)}
								class="filter-range"
							/>
							<input
								type="number"
								min={bounds()[0]}
								max={bounds()[1]}
								value={f.yearHi()}
								onChange={(e) => f.setYears(f.yearLo(), +e.currentTarget.value)}
								class="filter-number"
							/>
						</label>
						<button
							type="button"
							class="filter-button filter-button-small"
							onClick={() => f.setYears(bounds()[0], bounds()[1])}
						>
							Reset
						</button>
					</div>
				)}
			</Show>

			<span class="filter-count">
				{f.shownCount().toLocaleString()} of {f.totalCount.toLocaleString()}{" "}
				points shown
			</span>

			<div class="filter-controls">
				<input
					ref={inputEl}
					type="text"
					placeholder="add term, press Enter  (comma = several, leading - = exclude)"
					class="filter-search"
					onKeyDown={(e) => {
						if (e.key === "Enter") {
							e.preventDefault();
							submit();
						} else if (
							e.key === "Backspace" &&
							!e.currentTarget.value &&
							f.terms().length
						) {
							f.removeTerm(f.terms().length - 1);
						}
					}}
				/>
				<button type="button" class="filter-button" onClick={submit}>
					Add
				</button>

				<div class="filter-terms">
					<For each={f.terms()}>
						{(t, idx) => (
							<span
								type="button"
								class={`term ${t.neg ? "term-negative" : ""} ${t.on ? "" : "term-off"}`}
								title={`${t.neg ? "Excluding" : "Including"} · click to ${t.on ? "switch off" : "switch on"}`}
								onClick={() => f.toggleTerm(idx())}
							>
								<span>
									{t.neg ? "−" : ""}
									{t.text}
								</span>
								<small class="filter-muted">
									{(f.termCounts()[idx()] ?? 0).toLocaleString()}
								</small>
								<button
									type="button"
									class="filter-remove"
									onClick={(e) => {
										e.stopPropagation();
										f.removeTerm(idx());
									}}
								>
									×
								</button>
							</span>
						)}
					</For>
				</div>

				<label class="filter-label filter-compact">
					match
					<select
						value={f.mode()}
						onChange={(e) => f.setMode(e.currentTarget.value as "any" | "all")}
						class="filter-select"
					>
						<option value="any">any</option>
						<option value="all">all</option>
					</select>
				</label>

				<label class="filter-label filter-compact">
					in
					<select
						value={f.scope()}
						onChange={(e) =>
							f.setScope(e.currentTarget.value as "passage" | "hit" | "context")
						}
						class="filter-select"
					>
						<option value="passage">passage</option>
						<option value="hit">hit word</option>
						<option value="context">context only</option>
					</select>
				</label>

				<label class="filter-label filter-compact">
					<input
						type="checkbox"
						checked={f.whole()}
						onChange={(e) => f.setWhole(e.currentTarget.checked)}
					/>
					whole words
				</label>

				<button
					type="button"
					class="filter-button filter-button-small"
					onClick={() => f.clearTerms()}
				>
					Clear terms
				</button>
			</div>
		</>
	);
}
