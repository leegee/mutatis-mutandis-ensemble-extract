import { createMemo, For, Show } from "solid-js";

import { narrowYears, resetYears } from "../actions.js";
import { computeBins } from "../helpers.js";
import { pane } from "../store.js";

export function Histogram(props) {
	const id = props.id;
	const bins = createMemo(() => computeBins(pane(id)?.hits ?? []));
	const maxCount = createMemo(() => Math.max(1, ...bins().map((b) => b.count)));

	// A year restriction exists when the form differs from the defaults (0–2030).
	const form = () => pane(id)?.form;
	const yearsActive = () => {
		const f = form();
		return !!f && (f.startYear.trim() !== "0" || f.endYear.trim() !== "2030");
	};
	const reset = () => (
		<button class="linkbtn" type="button" onClick={() => resetYears(id)}>
			reset years
		</button>
	);

	return (
		<>
			<Show when={bins().length > 1}>
				<div class="hist">
					<div class="bars">
						<For each={bins()}>
							{(b) => (
								<button
									class="bar"
									type="button"
									title={`${b.start}–${b.end}: ${b.count} hit${b.count === 1 ? "" : "s"}`}
									onClick={() => narrowYears(id, b.start, b.end)}
								>
									<span
										class="fill"
										style={{
											height: `${Math.round((100 * b.count) / maxCount())}%`,
										}}
									/>
								</button>
							)}
						</For>
					</div>
					<div class="axis">
						<span>{bins()[0]?.start}</span>
						<span class="hint">
							click a bar to narrow the years
							<Show when={yearsActive()}>
								{" · "}
								{reset()}
							</Show>
						</span>
						<span>{bins()[bins().length - 1]?.end}</span>
					</div>
				</div>
			</Show>

			{/* With 0–1 bins the histogram is hidden, but the user may still need a way out
          (e.g. a narrow range that returned few or no hits). */}
			<Show when={bins().length <= 1 && yearsActive()}>
				<div class="hist">
					<div class="axis">
						<span class="hint">
							Years limited to {form()?.startYear}–{form()?.endYear} · {reset()}
						</span>
					</div>
				</div>
			</Show>
		</>
	);
}
