/**
 * Minimal hash-based router (no external dependency).
 *
 * Hash shapes supported:
 *   #/                  → { path: "/", params: URLSearchParams }
 *   #/search            → { path: "/search", ... }
 *   #/search?q=white    → path + params from the hash query string
 *
 * The browser query string (?api=…&panes=…) is left alone for CONFIG.
 * Extend by adding entries to ROUTES and matching in App (or a future
 * <Routes> component).
 */
import { createSignal } from "solid-js";

function parseHash() {
	// location.hash is "#/path?x=1" or ""
	const raw = (location.hash || "#/").replace(/^#/, "") || "/";
	const qIdx = raw.indexOf("?");
	const pathPart =
		(qIdx === -1 ? raw : raw.slice(0, qIdx)).replace(/\/+$/, "") || "/";
	const path = pathPart.startsWith("/") ? pathPart : `/${pathPart}`;
	const params = new URLSearchParams(qIdx === -1 ? "" : raw.slice(qIdx + 1));
	return { path, params };
}

const [route, setRoute] = createSignal(parseHash());

function syncFromLocation() {
	setRoute(parseHash());
}

if (typeof window !== "undefined") {
	window.addEventListener("hashchange", syncFromLocation);
	// Ensure we always have a hash so deep links and the back button behave.
	if (!location.hash || location.hash === "#") {
		history.replaceState(null, "", "#/");
		syncFromLocation();
	}
}

/**
 * Navigate within the hash router.
 * @param {string} to  Absolute path, e.g. "/search" or "/search?q=white"
 * @param {{ replace?: boolean }} opts
 */
export function navigate(to, opts = {}) {
	const path = to.startsWith("/") ? to : `/${to}`;
	const next = `#${path}`;
	if (opts.replace) {
		if (location.hash !== next) history.replaceState(null, "", next);
		syncFromLocation();
	} else {
		// Assigning location.hash always fires hashchange in modern browsers.
		if (location.hash === next) syncFromLocation();
		else location.hash = path;
	}
}

/** Build "#/path?qs" style target from path + URLSearchParams / string. */
export function hrefFor(path, params) {
	const base = path.startsWith("/") ? path : `/${path}`;
	const qs =
		typeof params === "string"
			? params
			: params && [...params.keys()].length
				? params.toString()
				: "";
	return qs ? `${base}?${qs}` : base;
}

/** Current route: { path, params }. Reactive. */
export { route };

/** Convenience: true when path matches (exact, or prefix if `path` ends with *). */
export function match(pattern) {
	const p = route().path;
	if (pattern.endsWith("*")) {
		const base = pattern.slice(0, -1);
		return p === base.slice(0, -1) || p.startsWith(base);
	}
	return p === pattern;
}

/**
 * Register a one-shot cleanup for the hashchange listener if a component
 * ever needs to tear the router down (rare in this SPA).
 */
export function disposeRouter() {
	window.removeEventListener("hashchange", syncFromLocation);
}

// Optional: list of known routes for future nav / guards.
export const ROUTES = {
	home: "/",
	search: "/search",
	text: "/text",
	// about: "/about",
};
