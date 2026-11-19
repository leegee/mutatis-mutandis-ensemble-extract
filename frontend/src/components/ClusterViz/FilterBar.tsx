import { For, Show } from "solid-js";
import type { ClusterFilters } from "./useClusterFilters";

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
				<div class="flex items-center gap-2">
					<label class="flex items-center gap-2">
						From
						<input
							type="range"
							min={f.yearBounds[0]}
							max={f.yearBounds[1]}
							value={f.yearLo()}
							onInput={(e) => f.setYears(+e.currentTarget.value, f.yearHi())}
							class="w-40 accent-[#7aa2ff]"
						/>
						<input
							type="number"
							min={f.yearBounds[0]}
							max={f.yearBounds[1]}
							value={f.yearLo()}
							onChange={(e) => f.setYears(+e.currentTarget.value, f.yearHi())}
							class="w-16 rounded border border-[#3a4150] bg-[#252a34] px-1.5 py-0.5"
						/>
					</label>
					<label class="flex items-center gap-2">
						To
						<input
							type="range"
							min={f.yearBounds[0]}
							max={f.yearBounds[1]}
							value={f.yearHi()}
							onInput={(e) => f.setYears(f.yearLo(), +e.currentTarget.value)}
							class="w-40 accent-[#7aa2ff]"
						/>
						<input
							type="number"
							min={f.yearBounds[0]}
							max={f.yearBounds[1]}
							value={f.yearHi()}
							onChange={(e) => f.setYears(f.yearLo(), +e.currentTarget.value)}
							class="w-16 rounded border border-[#3a4150] bg-[#252a34] px-1.5 py-0.5"
						/>
					</label>
					<button
						type="button"
						class="rounded border border-[#3a4150] bg-[#252a34] px-2 py-0.5 hover:bg-[#2f3542]"
						onClick={() => f.setYears(f.yearBounds[0], f.yearBounds[1])}
					>
						Reset
					</button>
				</div>
			</Show>

			<span class="text-[#9aa3b2]">
				{f.shownCount().toLocaleString()} of {f.totalCount.toLocaleString()}{" "}
				points shown
			</span>

			<div class="flex flex-1 flex-wrap items-center gap-2">
				<input
					ref={inputEl}
					type="text"
					placeholder="add term, press Enter  (comma = several, leading - = exclude)"
					class="w-72 rounded border border-[#3a4150] bg-[#252a34] px-2 py-1"
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
				<button
					type="button"
					class="rounded border border-[#3a4150] bg-[#252a34] px-2 py-1 hover:bg-[#2f3542]"
					onClick={submit}
				>
					Add
				</button>

				<div class="flex flex-wrap gap-1.5">
					<For each={f.terms()}>
						{(t, idx) => (
							<span
								class={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm
                  ${t.neg ? "border-[#b4545e] text-[#ffb4ba]" : "border-[#4a5568]"}
                  ${t.on ? "" : "opacity-40 line-through"}`}
								title={`${t.neg ? "Excluding" : "Including"} · click to ${t.on ? "switch off" : "switch on"}`}
								onClick={() => f.toggleTerm(idx())}
							>
								<span>
									{t.neg ? "−" : ""}
									{t.text}
								</span>
								<small class="text-[#9aa3b2]">
									{(f.termCounts()[idx()] ?? 0).toLocaleString()}
								</small>
								<button
									type="button"
									class="rounded-full px-1 hover:bg-[#3a4150]"
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

				<label class="flex items-center gap-1">
					match
					<select
						value={f.mode()}
						onChange={(e) => f.setMode(e.currentTarget.value as "any" | "all")}
						class="rounded border border-[#3a4150] bg-[#252a34] px-1.5 py-0.5"
					>
						<option value="any">any</option>
						<option value="all">all</option>
					</select>
				</label>

				<label class="flex items-center gap-1">
					in
					<select
						value={f.scope()}
						onChange={(e) =>
							f.setScope(e.currentTarget.value as "passage" | "hit" | "context")
						}
						class="rounded border border-[#3a4150] bg-[#252a34] px-1.5 py-0.5"
					>
						<option value="passage">passage</option>
						<option value="hit">hit word</option>
						<option value="context">context only</option>
					</select>
				</label>

				<label class="flex items-center gap-1">
					<input
						type="checkbox"
						checked={f.whole()}
						onChange={(e) => f.setWhole(e.currentTarget.checked)}
					/>
					whole words
				</label>

				<button
					type="button"
					class="rounded border border-[#3a4150] bg-[#252a34] px-2 py-0.5 hover:bg-[#2f3542]"
					onClick={() => f.clearTerms()}
				>
					Clear terms
				</button>
			</div>
		</>
	);
}
