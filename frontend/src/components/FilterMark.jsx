import { splitFilter } from "../helpers.js";

/** Plain text with filter matches wrapped in <mark class="filter">. */
export function FilterMark(props) {
	return (
		<>{splitFilter(props.text ?? "", props.filter ?? "").map((s) => (s.m ? <mark class="filter">{s.t}</mark> : s.t))}</>
	);
}
