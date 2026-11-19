// components/ClusterViz/ClusterViz.tsx
import { type Component, createResource } from "solid-js";

import type { ClusterVizPayload } from "../../types/cluster-viz";

import { CopyBar } from "./CopyBar";
import { FilterBar } from "./FilterBar";
import { PlotCanvas } from "./PlotCanvas";
import { useClusterFilters } from "./useClusterFilters";
import { useCopy } from "./useCopy";

async function fetchViz(runId: string): Promise<ClusterVizPayload> {
  const res = await fetch(`/api/target-runs/${runId}/visualization`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const ClusterViz: Component<{ runId: string }> = (props) => {
  const [payload] = createResource(() => props.runId, fetchViz);

  return (
    <Show when={payload()} fallback={<div class="p-8 text-muted">Loading visualisation…</div>}>
      {(data) => <ClusterVizInner data={data()} />}
    </Show>
  );
};

function ClusterVizInner(props: { data: ClusterVizPayload }) {
  const filters = useClusterFilters(props.data);
  const copy = useCopy(props.data, filters);

  return (
    <div class="flex h-full flex-col bg-[#111318] text-[#e2e5eb]">
      <div class="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-[#2a2f3a] bg-[#171a21] px-4 py-2 text-sm">
        <span class="font-semibold">
          Target occurrence clusters · {props.data.runId}
        </span>
        <span class="text-[#9aa3b2]">
          {props.data.nPoints.toLocaleString()} points · {props.data.nClusters} clusters
        </span>

        <FilterBar filters={filters} yearBounds={props.data.yearBounds} />
        <CopyBar copy={copy} />
      </div>

      <div class="min-h-0 flex-1">
        <PlotCanvas
          traces={props.data.traces}
          filtered={filters.filteredTraces()}
          onHover={copy.setHovered}
          onClick={copy.handleClick}
        />
      </div>
    </div>
  );
}
