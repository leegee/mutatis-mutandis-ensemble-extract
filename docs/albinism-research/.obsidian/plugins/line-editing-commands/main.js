var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// main.ts
var main_exports = {};
__export(main_exports, {
  default: () => LineEditingCommandsPlugin
});
module.exports = __toCommonJS(main_exports);
var import_obsidian = require("obsidian");

// src/logic.ts
var Doc = class {
  constructor(text) {
    this.text = text;
    this.lines = text.split("\n");
    this.starts = [];
    let pos = 0;
    for (const l of this.lines) {
      this.starts.push(pos);
      pos += l.length + 1;
    }
  }
  lineOf(offset) {
    let lo2 = 0;
    let hi2 = this.starts.length - 1;
    while (lo2 < hi2) {
      const mid = lo2 + hi2 + 1 >> 1;
      if (this.starts[mid] <= offset)
        lo2 = mid;
      else
        hi2 = mid - 1;
    }
    return lo2;
  }
  lineStart(i) {
    return this.starts[i];
  }
  lineEnd(i) {
    return this.starts[i] + this.lines[i].length;
  }
};
function selLines(doc, s) {
  const from = Math.min(s.anchor, s.head);
  const to = Math.max(s.anchor, s.head);
  const a = doc.lineOf(from);
  let b = doc.lineOf(to);
  if (to > from && b > a && to === doc.lineStart(b))
    b -= 1;
  return [a, b];
}
function blocksOf(doc, sels) {
  const items = sels.map((s) => ({ s, r: selLines(doc, s) })).sort((x, y) => x.r[0] - y.r[0] || x.r[1] - y.r[1]);
  const blocks = [];
  for (const { s, r } of items) {
    const last = blocks[blocks.length - 1];
    if (last && r[0] <= last.end) {
      last.end = Math.max(last.end, r[1]);
      last.sels.push(s);
    } else {
      blocks.push({ start: r[0], end: r[1], sels: [s] });
    }
  }
  return blocks;
}
function blockText(doc, b) {
  return doc.lines.slice(b.start, b.end + 1).join("\n");
}
function headLines(doc, sels) {
  const seen = /* @__PURE__ */ new Set();
  const out = [];
  for (const s of [...sels].sort((x, y) => x.head - y.head)) {
    const line = doc.lineOf(s.head);
    if (seen.has(line))
      continue;
    seen.add(line);
    out.push({ line, head: s.head });
  }
  return out;
}
function duplicateLines(doc, sels, direction) {
  const changes = [];
  const selections2 = [];
  let delta = 0;
  for (const b of blocksOf(doc, sels)) {
    const text = blockText(doc, b);
    if (direction === "down") {
      changes.push({ from: doc.lineEnd(b.end), to: doc.lineEnd(b.end), insert: "\n" + text });
      const shift = delta + text.length + 1;
      for (const s of b.sels)
        selections2.push({ anchor: s.anchor + shift, head: s.head + shift });
    } else {
      changes.push({ from: doc.lineStart(b.start), to: doc.lineStart(b.start), insert: text + "\n" });
      for (const s of b.sels)
        selections2.push({ anchor: s.anchor + delta, head: s.head + delta });
    }
    delta += text.length + 1;
  }
  return { changes, selections: selections2 };
}
function insertBlankLine(doc, sels, where) {
  const changes = [];
  const selections2 = [];
  let delta = 0;
  for (const { line } of headLines(doc, sels)) {
    const indent = /^[ \t]*/.exec(doc.lines[line])[0];
    if (where === "below") {
      const at = doc.lineEnd(line);
      changes.push({ from: at, to: at, insert: "\n" + indent });
      const caret = at + delta + 1 + indent.length;
      selections2.push({ anchor: caret, head: caret });
    } else {
      const at = doc.lineStart(line);
      changes.push({ from: at, to: at, insert: indent + "\n" });
      const caret = at + delta + indent.length;
      selections2.push({ anchor: caret, head: caret });
    }
    delta += indent.length + 1;
  }
  return { changes, selections: selections2 };
}
function selectLines(doc, sels) {
  const selections2 = [];
  for (const b of blocksOf(doc, sels)) {
    const from = doc.lineStart(b.start);
    const lastLine = doc.lines.length - 1;
    const endOf = (l) => l < lastLine ? doc.lineStart(l + 1) : doc.lineEnd(l);
    const already = b.sels.some((s) => Math.min(s.anchor, s.head) === from && Math.max(s.anchor, s.head) === endOf(b.end));
    const end = already && b.end < lastLine ? b.end + 1 : b.end;
    selections2.push({ anchor: from, head: endOf(end) });
  }
  return { changes: [], selections: selections2 };
}
function joinLines(doc, sels) {
  const changes = [];
  const selections2 = [];
  let delta = 0;
  const lastLine = doc.lines.length - 1;
  const ranges = [];
  for (const b of blocksOf(doc, sels)) {
    const r = { start: b.start, end: b.start === b.end ? b.start + 1 : b.end };
    const prev = ranges[ranges.length - 1];
    if (prev && r.start <= prev.end)
      prev.end = Math.max(prev.end, r.end);
    else
      ranges.push(r);
  }
  for (const b of ranges) {
    const end = Math.min(b.end, lastLine);
    if (end <= b.start)
      continue;
    let acc = doc.lines[b.start];
    let caret = -1;
    for (let i = b.start + 1; i <= end; i++) {
      const next = doc.lines[i].replace(/^\s+/, "");
      if (next === "")
        continue;
      if (caret < 0)
        caret = acc.length;
      acc += (acc === "" || /\s$/.test(acc) ? "" : " ") + next;
    }
    const from = doc.lineStart(b.start);
    const to = doc.lineEnd(end);
    const before2 = doc.lines.slice(b.start, end + 1).join("\n");
    if (acc === before2)
      continue;
    changes.push({ from, to, insert: acc });
    const c = from + delta + (caret < 0 ? acc.length : caret);
    selections2.push({ anchor: c, head: c });
    delta += acc.length - (to - from);
  }
  return { changes, selections: selections2 };
}
function transformLines(lines, how) {
  const cmp = (a, b) => a.localeCompare(b, void 0, { numeric: true, sensitivity: "base" });
  switch (how) {
    case "sort-asc":
      return [...lines].sort(cmp);
    case "sort-desc":
      return [...lines].sort((a, b) => cmp(b, a));
    case "reverse":
      return [...lines].reverse();
    case "unique": {
      const seen = /* @__PURE__ */ new Set();
      return lines.filter((l) => seen.has(l) ? false : (seen.add(l), true));
    }
  }
}
function rewriteLines(doc, sels, how) {
  const changes = [];
  const selections2 = [];
  let delta = 0;
  for (const b of blocksOf(doc, sels)) {
    if (b.start === b.end)
      continue;
    const from = doc.lineStart(b.start);
    const to = doc.lineEnd(b.end);
    const insert = transformLines(doc.lines.slice(b.start, b.end + 1), how).join("\n");
    if (insert !== doc.text.slice(from, to))
      changes.push({ from, to, insert });
    const head = from + delta + insert.length + (insert.endsWith("\n") && b.end < doc.lines.length - 1 ? 1 : 0);
    selections2.push({ anchor: from + delta, head });
    delta += insert.length - (to - from);
  }
  return { changes, selections: selections2 };
}
function deleteToLineEdge(doc, sels, edge) {
  const changes = [];
  const selections2 = [];
  let delta = 0;
  for (const { line, head } of headLines(doc, sels)) {
    const from = edge === "start" ? doc.lineStart(line) : head;
    const to = edge === "start" ? head : doc.lineEnd(line);
    if (from < to)
      changes.push({ from, to, insert: "" });
    const caret = from + delta;
    selections2.push({ anchor: caret, head: caret });
    delta -= to - from;
  }
  return { changes, selections: selections2 };
}
function parseLineTarget(input, lineCount) {
  const m = /^\s*(\d+)\s*(?:[:,]\s*(\d+))?\s*$/.exec(input);
  if (!m)
    return null;
  const line = Math.min(Math.max(parseInt(m[1], 10), 1), Math.max(lineCount, 1));
  const col = m[2] ? Math.max(parseInt(m[2], 10), 1) : 1;
  return { line: line - 1, ch: col - 1 };
}

// src/cursors.ts
var WORD = /^[\p{L}\p{N}\p{M}_]$/u;
function isWordChar(ch) {
  return WORD.test(ch);
}
function before(text, i) {
  if (i <= 0)
    return "";
  const lo2 = text.charCodeAt(i - 1);
  if (lo2 >= 56320 && lo2 <= 57343 && i >= 2) {
    const hi2 = text.charCodeAt(i - 2);
    if (hi2 >= 55296 && hi2 <= 56319)
      return text.slice(i - 2, i);
  }
  return text[i - 1];
}
function after(text, i) {
  if (i >= text.length)
    return "";
  const hi2 = text.charCodeAt(i);
  if (hi2 >= 55296 && hi2 <= 56319 && i + 1 < text.length) {
    const lo2 = text.charCodeAt(i + 1);
    if (lo2 >= 56320 && lo2 <= 57343)
      return text.slice(i, i + 2);
  }
  return text[i];
}
function wordAt(text, offset) {
  let from = offset;
  let to = offset;
  while (from > 0 && isWordChar(before(text, from)))
    from -= before(text, from).length;
  while (to < text.length && isWordChar(after(text, to)))
    to += after(text, to).length;
  return from === to ? null : { anchor: from, head: to };
}
var lo = (s) => Math.min(s.anchor, s.head);
var hi = (s) => Math.max(s.anchor, s.head);
function normalize(sels, main) {
  const sorted = [...sels].sort((a, b) => lo(a) - lo(b) || hi(a) - hi(b));
  const out = [];
  for (const s of sorted) {
    const prev = out[out.length - 1];
    if (prev && (lo(s) < hi(prev) || lo(s) === hi(prev) && lo(s) === lo(prev)))
      continue;
    out.push(s);
  }
  let idx = out.findIndex((s) => s.anchor === main.anchor && s.head === main.head);
  if (idx < 0)
    idx = out.findIndex((s) => lo(s) <= lo(main) && hi(s) >= hi(main));
  return { sels: out, main: Math.max(idx, 0) };
}
function pickMain(sels, headOffset) {
  const i = sels.findIndex((s) => s.head === headOffset);
  return i >= 0 ? i : sels.length - 1;
}
function overlaps(sels, from, to) {
  return sels.some((s) => lo(s) < to && hi(s) > from);
}
function findNextOccurrence(text, needle, start, taken) {
  if (!needle)
    return null;
  const first = Math.min(Math.max(start, 0), text.length);
  let at = first;
  let wrapped = false;
  for (; ; ) {
    let i = text.indexOf(needle, at);
    if (i < 0 || wrapped && i >= first + needle.length) {
      if (wrapped)
        return null;
      wrapped = true;
      at = 0;
      i = text.indexOf(needle, at);
      if (i < 0 || i >= first + needle.length)
        return null;
    }
    if (!overlaps(taken, i, i + needle.length))
      return { anchor: i, head: i + needle.length };
    at = i + 1;
  }
}
function allOccurrences(text, needle) {
  const out = [];
  if (!needle)
    return out;
  for (let i = text.indexOf(needle); i >= 0; i = text.indexOf(needle, i + needle.length)) {
    out.push({ anchor: i, head: i + needle.length });
  }
  return out;
}
var textOf = (text, s) => text.slice(lo(s), hi(s));
function selectNext(text, sels, main) {
  if (sels.some((s) => s.anchor === s.head)) {
    let changed = false;
    const next = sels.map((s) => {
      if (s.anchor !== s.head)
        return s;
      const w = wordAt(text, s.head);
      if (!w)
        return s;
      changed = true;
      return w;
    });
    if (!changed)
      return null;
    const m2 = next[main];
    return normalize(next, m2);
  }
  const m = sels[main];
  const hit = findNextOccurrence(text, textOf(text, m), hi(m), sels);
  if (!hit)
    return null;
  return normalize([...sels, hit], hit);
}
function selectAll(text, sels, main) {
  var _a;
  let m = sels[main];
  if (m.anchor === m.head) {
    const w = wordAt(text, m.head);
    if (!w)
      return null;
    m = w;
  }
  const hits = allOccurrences(text, textOf(text, m));
  if (hits.length === 0)
    return null;
  const mainHit = (_a = hits.find((h) => h.anchor === lo(m))) != null ? _a : hits[0];
  return normalize(hits, mainHit);
}
function skipOccurrence(text, sels, main) {
  const m = sels[main];
  if (m.anchor === m.head)
    return selectNext(text, sels, main);
  const rest = sels.filter((_, i) => i !== main);
  const hit = findNextOccurrence(text, textOf(text, m), hi(m), rest);
  if (!hit || hit.anchor === lo(m) && hit.head === hi(m))
    return null;
  return normalize([...rest, hit], hit);
}
function lineStarts(text) {
  const starts = [0];
  for (let i = text.indexOf("\n"); i >= 0; i = text.indexOf("\n", i + 1))
    starts.push(i + 1);
  return starts;
}
function lineOf(starts, offset) {
  let l = 0;
  let h = starts.length - 1;
  while (l < h) {
    const mid = l + h + 1 >> 1;
    if (starts[mid] <= offset)
      l = mid;
    else
      h = mid - 1;
  }
  return l;
}
function addCursors(text, sels, main, dir) {
  const starts = lineStarts(text);
  const end = (l) => l + 1 < starts.length ? starts[l + 1] - 1 : text.length;
  const added = [];
  for (const s of sels) {
    const l = lineOf(starts, s.head);
    const target = dir === "above" ? l - 1 : l + 1;
    if (target < 0 || target >= starts.length)
      continue;
    const col = s.head - starts[l];
    const at = starts[target] + Math.min(col, end(target) - starts[target]);
    added.push({ anchor: at, head: at });
  }
  const before2 = normalize(sels, sels[main]);
  const all = normalize([...sels, ...added], sels[main]);
  if (all.sels.length === before2.sels.length)
    return null;
  const extra = dir === "above" ? added[0] : added[added.length - 1];
  return normalize(all.sels, extra != null ? extra : sels[main]);
}
function keepMain(sels, main) {
  if (sels.length < 2)
    return null;
  return { sels: [sels[main]], main: 0 };
}

// main.ts
var rewrite = (how) => (doc, sels) => rewriteLines(doc, sels, how);
var SPECS = [
  { id: "duplicate-down", name: "Duplicate line or selection down", icon: "copy-plus", run: (d, s) => duplicateLines(d, s, "down") },
  { id: "duplicate-up", name: "Duplicate line or selection up", icon: "copy-plus", run: (d, s) => duplicateLines(d, s, "up") },
  { id: "blank-below", name: "Insert blank line below", icon: "corner-down-left", run: (d, s) => insertBlankLine(d, s, "below") },
  { id: "blank-above", name: "Insert blank line above", icon: "corner-up-left", run: (d, s) => insertBlankLine(d, s, "above") },
  { id: "select-line", name: "Select line (repeat to extend)", icon: "text-select", run: selectLines },
  { id: "join-lines", name: "Join lines", icon: "merge", run: joinLines },
  { id: "sort-asc", name: "Sort selected lines (A to Z)", icon: "arrow-down-narrow-wide", run: rewrite("sort-asc") },
  { id: "sort-desc", name: "Sort selected lines (Z to A)", icon: "arrow-up-wide-narrow", run: rewrite("sort-desc") },
  { id: "reverse-lines", name: "Reverse selected lines", icon: "arrow-up-down", run: rewrite("reverse") },
  { id: "unique-lines", name: "Remove duplicate lines in selection", icon: "list-minus", run: rewrite("unique") },
  { id: "delete-to-start", name: "Delete to line start", icon: "delete", run: (d, s) => deleteToLineEdge(d, s, "start") },
  { id: "delete-to-end", name: "Delete to line end", icon: "eraser", run: (d, s) => deleteToLineEdge(d, s, "end") }
];
function selections(editor) {
  return editor.listSelections().map((s) => ({ anchor: editor.posToOffset(s.anchor), head: editor.posToOffset(s.head) }));
}
function apply(editor, edit) {
  const changes = edit.changes.map((c) => ({
    from: editor.offsetToPos(c.from),
    to: editor.offsetToPos(c.to),
    text: c.insert
  }));
  const before2 = editor.getValue();
  const newText = applyToText(before2, edit);
  const posIn = (off) => {
    const lines = newText.slice(0, off).split("\n");
    return { line: lines.length - 1, ch: lines[lines.length - 1].length };
  };
  editor.transaction({
    changes,
    selections: edit.selections.map((s) => ({ from: posIn(s.anchor), to: posIn(s.head) }))
  });
}
function applyToText(text, edit) {
  let out = "";
  let at = 0;
  for (const c of edit.changes) {
    out += text.slice(at, c.from) + c.insert;
    at = c.to;
  }
  return out + text.slice(at);
}
var CURSOR_SPECS = [
  { id: "select-next", name: "Select word or next occurrence", icon: "text-cursor-input", run: selectNext },
  { id: "select-all-occurrences", name: "Select all occurrences", icon: "list-checks", run: selectAll },
  { id: "skip-occurrence", name: "Skip this occurrence and select the next", icon: "skip-forward", run: skipOccurrence },
  { id: "cursor-above", name: "Add cursor above", icon: "arrow-up-from-line", run: (t, s, m) => addCursors(t, s, m, "above") },
  { id: "cursor-below", name: "Add cursor below", icon: "arrow-down-from-line", run: (t, s, m) => addCursors(t, s, m, "below") },
  { id: "keep-main-cursor", name: "Keep only the main cursor", icon: "locate-fixed", run: (_t, s, m) => keepMain(s, m) }
];
var lastMain = /* @__PURE__ */ new WeakMap();
function runCursorCommand(editor, run) {
  const sels = selections(editor);
  const remembered = lastMain.get(editor);
  const known = remembered ? sels.findIndex((s) => s.anchor === remembered.anchor && s.head === remembered.head) : -1;
  const main = known >= 0 ? known : pickMain(sels, editor.posToOffset(editor.getCursor("head")));
  const result = run(editor.getValue(), sels, main);
  if (!result)
    return;
  editor.setSelections(
    result.sels.map((s) => ({ anchor: editor.offsetToPos(s.anchor), head: editor.offsetToPos(s.head) })),
    result.main
  );
  const m = result.sels[result.main];
  lastMain.set(editor, m);
  editor.scrollIntoView({ from: editor.offsetToPos(Math.min(m.anchor, m.head)), to: editor.offsetToPos(Math.max(m.anchor, m.head)) }, true);
}
var GoToLineModal = class extends import_obsidian.Modal {
  constructor(app, editor) {
    super(app);
    this.editor = editor;
  }
  onOpen() {
    const { contentEl, editor } = this;
    const count = editor.lineCount();
    this.setTitle("Go to line");
    let value = "";
    const go = () => {
      const target = parseLineTarget(value, count);
      if (!target) {
        new import_obsidian.Notice("Type a line number, or line:column.");
        return;
      }
      const ch = Math.min(target.ch, editor.getLine(target.line).length);
      editor.setCursor({ line: target.line, ch });
      editor.scrollIntoView({ from: { line: target.line, ch }, to: { line: target.line, ch } }, true);
      this.close();
    };
    new import_obsidian.Setting(contentEl).setName(`Line number (1 to ${count}), or line:column`).addText((t) => {
      t.setPlaceholder("42").onChange((v) => value = v);
      t.inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          go();
        }
      });
      window.setTimeout(() => t.inputEl.focus(), 0);
    });
    new import_obsidian.Setting(contentEl).addButton((b) => b.setButtonText("Go").setCta().onClick(go));
  }
  onClose() {
    this.contentEl.empty();
  }
};
var LineEditingCommandsPlugin = class extends import_obsidian.Plugin {
  onload() {
    for (const spec of SPECS) {
      this.addCommand({
        id: spec.id,
        name: spec.name,
        icon: spec.icon,
        editorCallback: (editor) => {
          const doc = new Doc(editor.getValue());
          const edit = spec.run(doc, selections(editor));
          if (edit.changes.length === 0 && edit.selections.length === 0)
            return;
          apply(editor, edit);
        }
      });
    }
    for (const spec of CURSOR_SPECS) {
      this.addCommand({
        id: spec.id,
        name: spec.name,
        icon: spec.icon,
        editorCallback: (editor) => runCursorCommand(editor, spec.run)
      });
    }
    this.addCommand({
      id: "go-to-line",
      name: "Go to line number",
      icon: "arrow-down-to-line",
      editorCallback: (editor) => new GoToLineModal(this.app, editor).open()
    });
  }
};

/* nosourcemap */