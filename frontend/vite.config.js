import { defineConfig } from "vite";
import solid from "vite-plugin-solid";

// Where the FastAPI app runs during development.
// Override with: VITE_API_TARGET=http://host:port npm run dev
const API_TARGET = process.env.VITE_API_TARGET || "http://localhost:8000";

export default defineConfig({
	plugins: [solid()],

	// Relative asset URLs so the build works when FastAPI serves it from any
	// mount point. Safe here because routing is hash-based.
	base: "./",

	server: {
		port: 5173,
		// The app calls same-origin endpoints (CONFIG.apiBase = ""), so proxy them
		// to FastAPI in dev. Anchored regex keeps the page itself out of the proxy.
		proxy: {
			"^/(search|text-search|health|representations)$": {
				target: API_TARGET,
				changeOrigin: true,
			},
		},
	},

	build: {
		outDir: "dist",
		sourcemap: true,
		target: "es2022",
	},
});
