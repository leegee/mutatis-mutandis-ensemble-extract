// types/cluster-viz.ts
export interface DocMeta {
	corpus: string;
	doc_id: string;
	author: string;
	title: string;
}

export interface PointCustom {
	// mirrors the original customdata columns
	yearText: string;
	heading: string;
	source: string;
	passageHtml: string; // with «hit»
	occurrenceId: string;
	membership: number;
	year: number | null;
	docIndex: number;
	hitIdx: number | null;
}

export interface ClusterTrace {
	cluster: number; // -1 = noise
	label: string; // "Cluster 3 · bodily whiteness" etc.
	category: string;
	x: number[];
	y: number[];
	customdata: PointCustom[];
	color: string;
	isNoise: boolean;
}

export interface ClusterVizPayload {
	runId: string;
	n_points: number;
	n_clusters: number;
	yearBounds: [number, number] | null;
	docs: DocMeta[];
	traces: ClusterTrace[];
	// optional seed for the term list
	seedTerms?: string[];
}
