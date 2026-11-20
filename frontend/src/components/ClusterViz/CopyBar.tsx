import { createSignal, Show } from "solid-js";
import type { CopyControls } from "./useCopy";

import "./CopyBar.css";

export function CopyBar(props: { copy: CopyControls }) {
	const c = props.copy;
	const [open, setOpen] = createSignal(false);

	return (
		<div class="copy-bar">
			<button
				type="button"
				class="copy-button"
				title="Copy the point you last hovered (with the mouse over a point, press C)"
				onClick={() => c.copyHovered()}
				title="Copy hovered point"
			>
				Copy
			</button>
			<button
				type="button"
				class="copy-button"
				title="Copy every point currently shown (year range, terms and legend apply)"
				onClick={() => c.copyVisible()}
				title="Copy all visible points"
			>
				Copy All
			</button>

			<div class="copy-menu">
				<button
					type="button"
					class="copy-button"
					aria-expanded={open()}
					onClick={(e) => {
						e.stopPropagation();
						setOpen((v) => !v);
					}}
					title="Copy optinos"
				>
					⚙
				</button>

				<Show when={open()}>
					<div
						class="copy-options"
						onClick={(e) => e.stopPropagation()}
					>
						<div class="copy-options-title">Copy format</div>
						<div class="copy-format-options">
							<label class="copy-label">
								<input
									type="radio"
									name="fmt"
									checked={c.opts().format === "markdown"}
									onChange={() =>
										c.setOpts((o) => ({ ...o, format: "markdown" }))
									}
								/>
								Markdown
							</label>
							<label class="copy-label">
								<input
									type="radio"
									name="fmt"
									checked={c.opts().format === "csv"}
									onChange={() => c.setOpts((o) => ({ ...o, format: "csv" }))}
								/>
								CSV
							</label>
						</div>

						<label class="copy-label copy-limit-label">
							Max points per copy
							<input
								type="number"
								min={0}
								step={1000}
								value={c.opts().limit}
								class="copy-number"
								onChange={(e) => {
									const v = parseInt(e.currentTarget.value, 10);
									c.setOpts((o) => ({
										...o,
										limit: Number.isNaN(v) || v < 0 ? o.limit : v,
									}));
								}}
							/>
						</label>
						<small class="copy-help copy-help-snug">
							0 means no limit. Very large copies can hang the browser. Points
							are ordered by year, then cluster.
						</small>

						<label class="copy-label">
							<input
								type="checkbox"
								checked={c.opts().onClick}
								onChange={(e) =>
									c.setOpts((o) => ({ ...o, onClick: e.currentTarget.checked }))
								}
							/>
							Copy a point when I click it
						</label>
						<small class="copy-help">
							Shortcut: hover a point and press C.
						</small>
					</div>
				</Show>
			</div>

			{/* toast */}
			<Show when={c.toast()}>
				{(t) => (
					<div class={`copy-toast ${t().bad ? "copy-toast-error" : ""}`}>
						{t().msg}
					</div>
				)}
			</Show>
		</div>
	);
}