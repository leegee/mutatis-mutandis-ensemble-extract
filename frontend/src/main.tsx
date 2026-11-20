import { HashRouter } from "@solidjs/router";
import { render } from "solid-js/web";

import { App } from "./components/App";
import { ClusterViz } from "./components/ClusterViz/ClusterViz";
import { NotFound } from "./components/NotFound";
import { SearchView } from "./components/SearchView";
import { TextSearchView } from "./components/TextSearchView";

render(
	() => (
		<HashRouter
			root={App}
			children={[
				{
					path: ["/", "/search"],
					component: SearchView,
				},
				{
					path: "/text",
					component: TextSearchView,
				},
				{
					path: "/cluster",
					component: () => (
						<ClusterViz runId="l8-target-form-20261118-083730" />
					),
				},
				{
					path: "*404",
					component: NotFound,
				},
			]}
		/>
	),
	document.getElementById("app"),
);
