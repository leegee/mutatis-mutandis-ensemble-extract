import { type Component, createEffect, onCleanup, onMount } from "solid-js";
import type { ClusterTrace } from "../../types/cluster-viz";

declare const Plotly: any; // or install @types/plotly.js

export const PlotCanvas: Component<{
	traces: ClusterTrace[]; // original (for legend etc.)
	filtered: ClusterTrace[]; // currently visible
	onHover: (h: { ti: number; i: number } | null) => void;
	onClick: (ti: number, i: number) => void;
}> = (props) => {
	let el: HTMLDivElement | undefined;
	let gd: any;

	onMount(() => {
		if (!el) return;

		const plotlyTraces = props.filtered.map((t) => ({
			x: t.x,
			y: t.y,
			customdata: t.customdata,
			mode: "markers",
			type: "scattergl",
			name: `${t.label} (n=${t.x.length.toLocaleString()})`,
			meta: { label: t.label, cluster: t.cluster, category: t.category },
			marker: {
				size: t.isNoise ? 3 : 5,
				color: t.color,
				opacity: t.isNoise ? 0.25 : 0.78,
			},
			hovertemplate:
				"<b>%{customdata.heading}</b><br>" +
				"%{customdata.yearText}<br>" +
				"<span style='color:#aaaaaa'>%{customdata.source}</span><br><br>" +
				"%{customdata.passageHtml}<br><br>" +
				"<span style='color:#aaaaaa'>" +
				"Membership: %{customdata.membership:.2f}<br>" +
				"Occurrence: %{customdata.occurrenceId}" +
				"</span><extra></extra>",
		}));

		const layout = {
			template: "plotly_dark",
			autosize: true,
			paper_bgcolor: "#111318",
			plot_bgcolor: "#171a21",
			font: {
				family: "Segoe UI, Arial, sans-serif",
				color: "#e2e5eb",
				size: 12,
			},
			hoverlabel: {
				bgcolor: "#252a34",
				bordercolor: "#596273",
				font: {
					family: "Segoe UI, Arial, sans-serif",
					size: 16,
					color: "#f2f3f5",
				},
				align: "left",
			},
			xaxis: {
				title: "UMAP 1",
				showgrid: true,
				gridcolor: "#292e38",
				zeroline: false,
			},
			yaxis: {
				title: "UMAP 2",
				showgrid: true,
				gridcolor: "#292e38",
				zeroline: false,
			},
			legend: {
				title: { text: "Clusters · click to hide/show" },
				bgcolor: "rgba(20,23,30,0.85)",
				bordercolor: "#343b48",
				borderwidth: 1,
				itemsizing: "constant",
				y: 1,
				yanchor: "top",
				x: 1.01,
			},
			margin: { l: 55, r: 230, t: 20, b: 50 },
			hovermode: "closest",
		};

		const config = {
			responsive: true,
			scrollZoom: true,
			displaylogo: false,
			toImageButtonOptions: { format: "png", scale: 2 },
		};

		Plotly.newPlot(el, plotlyTraces, layout, config).then((graphDiv: any) => {
			gd = graphDiv;

			gd.on("plotly_hover", (ev: any) => {
				const p = ev?.points?.[0];
				if (p) props.onHover({ ti: p.curveNumber, i: p.pointNumber });
			});
			gd.on("plotly_unhover", () => props.onHover(null));
			gd.on("plotly_click", (ev: any) => {
				const p = ev?.points?.[0];
				if (p) props.onClick(p.curveNumber, p.pointNumber);
			});
		});

		onCleanup(() => {
			if (el) Plotly.purge(el);
		});
	});

	// live filter updates
	createEffect(() => {
		const filtered = props.filtered;
		if (!gd) return;

		const xs = filtered.map((t) => t.x);
		const ys = filtered.map((t) => t.y);
		const cds = filtered.map((t) => t.customdata);
		const names = filtered.map(
			(t) =>
				`${t.label} (n=${t.x.length.toLocaleString()}${
					t.x.length !==
					props.traces.find((o) => o.cluster === t.cluster)?.x.length
						? ` of ${props.traces.find((o) => o.cluster === t.cluster)?.x.length.toLocaleString()}`
						: ""
				})`,
		);

		Plotly.restyle(gd, {
			x: xs,
			y: ys,
			customdata: cds,
			name: names,
		});
	});

	return <div ref={el} class="h-full w-full" />;
};
