import { createMemo, createRoot } from "solid-js";
import { store } from "./store.js";

/**
 * Cross-pane derivations: the seed of "compare n queries".
 * `overlaps(paneId, hit)` lists the OTHER panes whose results contain a
 * passage from the same document with an intersecting token range.
 */
const docIndex = createRoot(() =>
  createMemo(() => {
    const idx = new Map(); // paneId -> Map(docKey -> hits[])
    for (const p of store.panes) {
      const byDoc = new Map();
      for (const h of p.hits) {
        const k = `${h.corpus}\u0000${h.doc_id}`;
        (byDoc.get(k) ?? byDoc.set(k, []).get(k)).push(h);
      }
      idx.set(p.id, byDoc);
    }
    return idx;
  })
);

export function overlaps(paneId, hit) {
  const out = [];
  const key = `${hit.corpus}\u0000${hit.doc_id}`;
  for (const p of store.panes) {
    if (p.id === paneId) continue;
    const others = docIndex().get(p.id)?.get(key) ?? [];
    if (others.some((o) => o.token_start < hit.token_end && hit.token_start < o.token_end)) {
      out.push(p.label);
    }
  }
  return out;
}
