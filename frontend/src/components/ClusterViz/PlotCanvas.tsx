import type {
	Config,
	Data,
	Layout,
	PlotlyHTMLElement,
} from "plotly.js-dist-min";

import Plotly from "plotly.js-dist-min";

import {
	type Component,
	createEffect,
	createSignal,
	onCleanup,
	onMount,
} from "solid-js";

import type { ClusterTrace } from "../../types/cluster-viz";

interface PlotCanvasProps {
	traces: ClusterTrace[];
	filtered: ClusterTrace[];
	onHover: (h: { ti: number; i: number } | null) => void;
	onClick: (ti: number, i: number) => void;
	onRightClick: (ti: number, i: number) => void;
}

function toPlotlyTrace(t: ClusterTrace, name?: string): Data {
	return {
		x: t.x,
		y: t.y,
		customdata: t.customdata.map((p) => [
			p.heading,
			p.yearText,
			p.source,
			p.passageHtml,
			p.occurrenceId,
			p.membership,
			p.year,
			p.docIndex,
			p.hitIdx,
		]),
		mode: "markers",
		type: "scattergl",
		name: name ?? `${t.label} (n=${t.x.length.toLocaleString()})`,
		meta: {
			label: t.label,
			cluster: t.cluster,
			category: t.category,
		},
		marker: {
			size: t.isNoise ? 3 : 5,
			color: t.color,
			opacity: t.isNoise ? 0.25 : 0.78,
		},
		hovertemplate:
			"<b>%{customdata[0]}</b><br>" +
			"%{customdata[1]}<br>" +
			"<span style='color:#aaaaaa'>%{customdata[2]}</span><br><br>" +
			"%{customdata[3]}<br><br>" +
			"<span style='color:#aaaaaa'>" +
			"Membership: %{customdata[5]:.2f}<br>" +
			"Occurrence: %{customdata[4]}" +
			"</span><extra></extra>",
	};
}

export const PlotCanvas: Component<PlotCanvasProps> = (props) => {
	let el: HTMLDivElement | undefined;

	const [gd, setGd] = createSignal<PlotlyHTMLElement>();

	const layout: Partial<Layout> = {
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
			title: { text: "UMAP 1" },
			showgrid: true,
			gridcolor: "#292e38",
			zeroline: false,
		},
		yaxis: {
			title: { text: "UMAP 2" },
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

	const config: Partial<Config> = {
		responsive: true,
		scrollZoom: true,
		displaylogo: false,
		toImageButtonOptions: {
			format: "png",
			scale: 2,
		},
	};

	onMount(async () => {
		if (!el) return;

		let disposed = false;

		onCleanup(() => {
			disposed = true;

			const graph = gd();
			if (graph) {
				Plotly.purge(graph);
				setGd(undefined);
			}
		});

		try {
			const initialTraces = props.filtered.map((t) => toPlotlyTrace(t));

			const graphDiv = await Plotly.newPlot(el, initialTraces, layout, config);

			if (disposed) {
				Plotly.purge(graphDiv);
				return;
			}

			setGd(graphDiv);

			let hoveredPoint:
				| {
						curveNumber: number;
						pointNumber: number;
				  }
				| undefined;

			graphDiv.on("plotly_hover", (ev) => {
				const p = ev.points?.[0];

				if (p) {
					hoveredPoint = {
						curveNumber: p.curveNumber,
						pointNumber: p.pointNumber,
					};

					props.onHover({
						ti: p.curveNumber,
						i: p.pointNumber,
					});
				}
			});

			graphDiv.on("plotly_unhover", () => {
				hoveredPoint = undefined;
				props.onHover(null);
			});

			graphDiv.on("plotly_click", (ev) => {
				const p = ev.points?.[0];

				if (p) {
					props.onClick(p.curveNumber, p.pointNumber);
				}
			});

			graphDiv.addEventListener("contextmenu", (ev) => {
				ev.preventDefault();

				if (hoveredPoint) {
					props.onRightClick(
						hoveredPoint.curveNumber,
						hoveredPoint.pointNumber,
					);
				}
			});
		} catch (error) {
			if (!disposed) {
				console.error("Failed to initialise Plotly:", error);
			}
		}
	});

	// Update traces when filtering changes.
	createEffect(() => {
		const filtered = props.filtered;
		const graph = gd();

		if (!graph) return;

		const plotlyTraces = filtered.map((t) => {
			const originalCount = props.traces.find(
				(original) => original.cluster === t.cluster,
			)?.x.length;

			const filteredCount = t.x.length;

			const countLabel =
				originalCount !== undefined && filteredCount !== originalCount
					? ` of ${originalCount.toLocaleString()}`
					: "";

			return toPlotlyTrace(
				t,
				`${t.label} (n=${filteredCount.toLocaleString()}${countLabel})`,
			);
		});

		void Plotly.react(graph, plotlyTraces, layout, config);
	});

	return <div id="plot" ref={el} />;
};
