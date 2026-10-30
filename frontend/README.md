# Passage Search UI

Vite-based SolidJS SPA for semantic passage search.

Ideally rewrite to use Vite, TS and JSX

## Routing

Hash-based, no external router dependency:

| Hash            | View                 |
|-----------------|----------------------|
| `#/`            | Semantic search      |
| `#/search`      | Semantic search      |
| `#/text`        | Postgres text search |
| anything else   | Not found            |

- `js/router.js` exports `route()` (reactive `{ path, params }`), `navigate(to)`, `match(pattern)`, and `ROUTES`.
- Browser query string (`?api=…&panes=…`) stays independent of the hash and is still read by `config.js`.
- To add a route later: register it in `ROUTES`, add a view component, and branch in `App.js` (or introduce a small `<Routes>` helper).

Examples:

```js
import { navigate, route, match } from "./router.js";

navigate("/search");
navigate("/search?focus=A", { replace: true });
if (match("/search")) { /* … */ }
const q = route().params.get("q");
```

## Running

Serve the directory over HTTP (modules need a real origin):

```bash
# from the parent of passage-search-ui, or adjust paths
python -m http.server 8080
# then open http://localhost:8080/passage-search-ui/
# → redirects to …/#/
```

Or let your FastAPI app mount this folder and serve `index.html`.

### Query params (not hash)

- `?api=https://…` — API base (default: same origin)
- `?panes=2` — enable multi-pane layout (1–6)

### Offline SolidJS

Download the four packages listed in the import map into `./vendor/` and change the map entries to `/ui/vendor/...` (or relative paths).

## Conventions

- Components receive a pane `id` (string) and read the store; they never receive callbacks as props.
- Actions live in `actions.js` and are imported where needed.
- Cross-pane features (`overlaps`) are memos over `store.panes`.
- Routing is hash-only so the app can be dropped behind any static file server without rewrite rules.
