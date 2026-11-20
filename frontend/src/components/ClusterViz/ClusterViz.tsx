// components/ClusterViz/ClusterViz.tsx
import { type Component, createResource, Show } from "solid-js";
import { CONFIG } from "./../../config";
import type { ClusterVizPayload } from "../../types/cluster-viz";
import { CopyBar } from "./CopyBar";
import { FilterBar } from "./FilterBar";
import { PlotCanvas } from "./PlotCanvas";
import { useClusterFilters } from "./useClusterFilters";
import { useCopy } from "./useCopy";

async function fetchViz(runId: string): Promise<ClusterVizPayload> {
	console.log("Enter fetchViz", runId);
	const res = await fetch(
		`${CONFIG.apiBase}/target-runs/${runId}/visualization`,
	);
	if (!res.ok) throw new Error(await res.text());
	console.log("Leave fetchViz");
	return res.json();
}

export const ClusterViz: Component<{ runId: string }> = (props) => {
	console.log("Enter ClusterViz");
	const [payload] = createResource(() => {
		console.log("Resource source:", props.runId);
		return props.runId;
	}, fetchViz);

	return (
		<Show
			when={payload()}
			fallback={
				<Show
					when={!payload.error}
					fallback={<div class="text-error">{payload.error.message}</div>}
				>
					<div class="text-muted">Loading visualisation…</div>
				</Show>
			}
		>
			{(data) => <ClusterVizInner data={data()} />}
		</Show>
	);
};

function ClusterVizInner(props: { data: ClusterVizPayload }) {
	const filters = useClusterFilters(props.data);
	const copy = useCopy(props.data, filters);

	console.log(props.data);

	return (
		<div id="plotwrap">
			<nav>
				<span class="font-semibold">
					Target occurrence clusters · {props.data.runId}
				</span>
				<span style="color:#9aa3b2">
					{props.data.n_points.toLocaleString()} points ·{" "}
					{props.data.n_clusters} clusters
				</span>
				<FilterBar filters={filters} yearBounds={props.data.yearBounds} />
				<CopyBar copy={copy} />
			</nav>

			<PlotCanvas
				traces={props.data.traces}
				filtered={filters.filteredTraces()}
				onHover={copy.setHovered}
				onClick={copy.handleClick}
			/>
		</div>
	);
}
