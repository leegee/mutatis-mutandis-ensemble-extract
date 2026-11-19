import { createSignal, Show } from "solid-js";
import type { CopyControls } from "./useCopy";

export function CopyBar(props: { copy: CopyControls }) {
	const c = props.copy;
	const [open, setOpen] = createSignal(false);

	return (
		<div class="ml-auto flex items-center gap-2">
			<button
				type="button"
				class="rounded border border-[#3a4150] bg-[#252a34] px-2.5 py-1 hover:bg-[#2f3542]"
				title="Copy the point you last hovered (with the mouse over a point, press C)"
				onClick={() => c.copyHovered()}
			>
				Copy hovered point
			</button>
			<button
				type="button"
				class="rounded border border-[#3a4150] bg-[#252a34] px-2.5 py-1 hover:bg-[#2f3542]"
				title="Copy every point currently shown (year range, terms and legend apply)"
				onClick={() => c.copyVisible()}
			>
				Copy visible points
			</button>

			<div class="relative">
				<button
					type="button"
					class="rounded border border-[#3a4150] bg-[#252a34] px-2.5 py-1 hover:bg-[#2f3542]"
					aria-expanded={open()}
					onClick={(e) => {
						e.stopPropagation();
						setOpen((v) => !v);
					}}
				>
					⚙ Options
				</button>

				<Show when={open()}>
					<div
						class="absolute right-0 top-9 z-30 flex w-72 flex-col gap-2 rounded-lg border border-[#3a4150] bg-[#1d212b] p-3 shadow-xl"
						onClick={(e) => e.stopPropagation()}
					>
						<div class="font-semibold text-[#cfd5e1]">Copy format</div>
						<div class="flex gap-4">
							<label class="flex items-center gap-1.5">
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
							<label class="flex items-center gap-1.5">
								<input
									type="radio"
									name="fmt"
									checked={c.opts().format === "csv"}
									onChange={() => c.setOpts((o) => ({ ...o, format: "csv" }))}
								/>
								CSV
							</label>
						</div>

						<label class="flex items-center justify-between gap-2">
							Max points per copy
							<input
								type="number"
								min={0}
								step={1000}
								value={c.opts().limit}
								class="w-24 rounded border border-[#3a4150] bg-[#252a34] px-1.5 py-0.5"
								onChange={(e) => {
									const v = parseInt(e.currentTarget.value, 10);
									c.setOpts((o) => ({
										...o,
										limit: isNaN(v) || v < 0 ? o.limit : v,
									}));
								}}
							/>
						</label>
						<small class="text-[#9aa3b2] leading-snug">
							0 means no limit. Very large copies can hang the browser. Points
							are ordered by year, then cluster.
						</small>

						<label class="flex items-center gap-1.5">
							<input
								type="checkbox"
								checked={c.opts().onClick}
								onChange={(e) =>
									c.setOpts((o) => ({ ...o, onClick: e.currentTarget.checked }))
								}
							/>
							Copy a point when I click it
						</label>
						<small class="text-[#9aa3b2]">
							Shortcut: hover a point and press C.
						</small>
					</div>
				</Show>
			</div>

			{/* toast */}
			<Show when={c.toast()}>
				{(t) => (
					<div
						class={`fixed bottom-7 left-1/2 z-50 -translate-x-1/2 rounded-md border px-3.5 py-2 text-sm transition-opacity
              ${t().bad ? "border-[#b4545e] text-[#ffb4ba]" : "border-[#4a5568]"} bg-[#2b3140]`}
					>
						{t().msg}
					</div>
				)}
			</Show>
		</div>
	);
}
