#!/usr/bin/env python
"""
45_visualise_clusters.py - interactive dark UMAP plot of a clustering run.

Reads the .npz written by 41_cluster_targets.py and passage text/metadata from
Postgres. Writes a self-contained HTML plot (Plotly JS is embedded) that fills
the browser window, with two live filters that combine:

  Year range   "From" / "To" sliders (and number boxes).
  Term list    Type a term and press Enter to add it to the list. Points are shown
               only if their passage text matches the list.

Term list, in the page
  * Enter adds a term; commas add several at once ("wool, hair, snow").
  * A leading "-" excludes: "-black" hides every passage containing "black".
  * Click a chip to switch it off/on without losing it; "x" removes it;
    Backspace in the empty box removes the last one.
  * match any / all: combine the included terms with OR or AND.
  * in passage / hit word / context only: where to look. "context only" ignores the
    highlighted hit word itself, so "white" finds passages that mention white
    NEARBY rather than every passage whose hit word is white.
  * whole words: "wool" will not match "woollen".
  * Matching ignores case and accents ("hwit" finds "hwit" and "hwit" with a macron).
  * Each chip shows how many points match it overall.
  * The list is remembered in this browser, per run. --term / --exclude seed it
    instead (argparse reads "--term -x" as a flag, so use --exclude x or --term=-x).

Copying points out of the plot
  * Hover a point and press C: copies that point.
  * "Copy hovered point" copies the point you hovered last (moving the mouse to the
    button un-hovers, so the plot remembers the last one).
  * "Copy visible points" copies everything currently shown: the year range, the term
    list and the legend (clusters you have hidden are left out) all apply.
  * Options (top right): Markdown or CSV, a cap on points per copy, and "copy a point
    when I click it". Options are remembered in this browser.
  * Markdown gives one readable entry per point with the hit in bold; CSV gives one
    row per point (occurrence_id, cluster, category, year, author, title, corpus,
    doc_id, hit_idx, hit_word, membership, umap_x, umap_y, passage), where the passage
    keeps the hit marked «like this». Points are ordered by year, then cluster.

The filter searches the hover passage, i.e. +/- --words tokens around the hit,
not the whole document. Raise --words to search a wider window (copies contain the
same passage).

Year filtering on the command line (--min-year / --max-year) drops points before
the passage text is fetched, which keeps the HTML small for big runs.

Examples:
    python 45_visualise_clusters.py --run-id l8-target-form-20261118-101500
    python 45_visualise_clusters.py --run-id YOUR_RUN --words 30
    python 45_visualise_clusters.py --run-id YOUR_RUN --min-year 1500 --max-year 1800
    python 45_visualise_clusters.py --run-id YOUR_RUN --term wool --exclude black
    python 45_visualise_clusters.py --run-id YOUR_RUN --out out/target_runs/clusters.html

Install:
    pip install plotly
"""

from __future__ import annotations

import argparse
import html
import json
import textwrap
from pathlib import Path

import numpy as np

from mutatis_mutandis.lib.corpus_config import OUT_DIR
from mutatis_mutandis.lib.corpus_db import get_connection
from mutatis_mutandis.lib.corpus_logging import logger

PLOT_DIV_ID = "cluster-plot"

PAGE_CSS = """
html, body { height: 100%; margin: 0; background: #111318; color: #e2e5eb;
             font-family: "Segoe UI", Arial, sans-serif; }
body { display: flex; flex-direction: column; overflow: hidden; }
#bar { flex: 0 0 auto; display: flex; flex-wrap: wrap; align-items: center;
       gap: 6px 22px; padding: 8px 14px; background: #171a21;
       border-bottom: 1px solid #2a2f3a; font-size: 13px; }
#bar .title { font-weight: 600; font-size: 14px; }
#bar .stat { color: #9aa3b2; }
#bar .years { display: flex; align-items: center; gap: 10px; }
#bar label { display: flex; align-items: center; gap: 8px; }
#bar input[type=range] { width: 220px; accent-color: #7aa2ff; }
#bar input[type=number], #bar input[type=text], #bar select {
       background: #252a34; color: #e2e5eb; border: 1px solid #3a4150;
       border-radius: 4px; padding: 3px 6px; font-size: 13px; }
#bar input[type=number] { width: 66px; }
#bar button { background: #252a34; color: #e2e5eb; border: 1px solid #3a4150;
       border-radius: 4px; padding: 3px 10px; cursor: pointer; }
#bar button:hover { background: #2f3542; }
#bar .terms { flex: 1 1 100%; display: flex; flex-wrap: wrap; align-items: center;
       gap: 6px 14px; }
#term-in { width: 300px; }
#chips { display: inline-flex; flex-wrap: wrap; gap: 6px; }
.chip { display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
        background: #252a34; border: 1px solid #4a5568; border-radius: 13px;
        padding: 2px 4px 2px 10px; user-select: none; }
.chip small { color: #9aa3b2; }
.chip.neg { border-color: #b4545e; color: #ffb4ba; }
.chip.off { opacity: .4; text-decoration: line-through; }
.chip button.x { border: 0; background: transparent; color: inherit; padding: 0 6px;
        font-size: 15px; line-height: 1; border-radius: 10px; }
.chip button.x:hover { background: #3a4150; }
#bar .copybar { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.optwrap { position: relative; }
#opt-panel { position: absolute; right: 0; top: 34px; z-index: 30; width: 300px;
        display: flex; flex-direction: column; gap: 9px; background: #1d212b;
        border: 1px solid #3a4150; border-radius: 8px; padding: 12px 14px;
        box-shadow: 0 8px 24px rgba(0,0,0,.45); }
#opt-panel[hidden] { display: none; }
#opt-panel .opt-title { font-weight: 600; color: #cfd5e1; }
#opt-panel .opt-row { justify-content: space-between; }
#opt-panel .opt-formats { display: flex; gap: 18px; }
#opt-panel small { color: #9aa3b2; line-height: 1.4; }
#toast { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%);
        background: #2b3140; border: 1px solid #4a5568; border-radius: 6px;
        padding: 8px 14px; font-size: 13px; opacity: 0; pointer-events: none;
        transition: opacity .18s; z-index: 50; max-width: 80vw; }
#toast.show { opacity: 1; }
#toast.bad { border-color: #b4545e; color: #ffb4ba; }
#plotwrap { flex: 1 1 auto; min-height: 0; }
#plotwrap > div { height: 100%; width: 100%; }
.plotly-graph-div { height: 100% !important; width: 100% !important; }
"""

# Live filters (year range + term list). The original arrays are kept by reference
# (the figure is built with plain lists, so gd.data holds them as given). Every change
# re-sends only the points that pass both filters. customdata: [3] = hover passage
# (HTML), [6] = numeric year. Search text is derived from [3] on first use, so the
# page does not carry a second copy of the passages.
FILTER_JS = r"""
(function () {
  var gd = document.getElementById('__DIV__');
  if (!gd) { return; }
  var RUN = __RUN__, SEED = __SEED__;
  var FOLD = true;                       // match "hwit" against "hwit" with a macron
  var $ = function (id) { return document.getElementById(id); };

  var lo = $('yr-lo'), hi = $('yr-hi'), loN = $('yr-lo-num'), hiN = $('yr-hi-num');
  var yrReset = $('yr-reset'), count = $('shown-count');
  var hasYears = !!(lo && hi && loN && hiN);
  var MIN = hasYears ? +lo.min : 0, MAX = hasYears ? +lo.max : 0;

  var inp = $('term-in'), addBtn = $('term-add'), chipsEl = $('chips');
  var modeEl = $('term-mode'), scopeEl = $('term-scope'), wholeEl = $('term-whole');
  var clearBtn = $('term-clear');

  var orig = gd.data.map(function (t) {
    return { x: t.x, y: t.y, cd: t.customdata, label: (t.meta && t.meta.label) || t.name };
  });
  var total = orig.reduce(function (s, o) { return s + o.x.length; }, 0);
  var textPass = orig.map(function () { return null; });   // null = every point passes
  var texts = {};                                          // scope -> per-trace strings
  var terms = [];                                          // {text, neg, on, n, m}
  var pending = false;

  /* ---------- text preparation ---------- */
  function fold(s) {
    s = s.toLowerCase();
    return FOLD ? s.normalize('NFD').replace(/\p{M}/gu, '') : s;
  }
  function plain(h) {
    return h.replace(/<br>/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
            .replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&amp;/g, '&');
  }
  function textsFor(scope) {
    if (texts[scope]) { return texts[scope]; }
    texts[scope] = orig.map(function (o) {
      var out = new Array(o.cd.length);
      for (var i = 0; i < o.cd.length; i++) {
        var p = plain(String(o.cd[i][3] || '')), s;
        if (scope === 'hit') {
          var a = p.indexOf('«'), b = p.indexOf('»');
          s = (a >= 0 && b > a) ? p.slice(a + 1, b) : '';
        } else if (scope === 'context') {
          s = p.replace(/«[^»]*»/, ' ');
        } else {
          s = p.replace(/[«»]/g, '');
        }
        out[i] = fold(s);
      }
      return out;
    });
    return texts[scope];
  }
  function esc(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function matcher(term, whole) {
    var needle = fold(term);
    if (!whole) { return function (s) { return s.indexOf(needle) !== -1; }; }
    var rx = new RegExp('(?:^|[^\\p{L}\\p{N}])' + esc(needle) + '(?![\\p{L}\\p{N}])', 'u');
    return function (s) { return rx.test(s); };
  }

  /* ---------- term filter ---------- */
  function recomputeText() {
    var all = modeEl.value === 'all', whole = wholeEl.checked;
    terms.forEach(function (t) { t.n = 0; t.m = matcher(t.text, whole); });
    var nInc = terms.filter(function (t) { return t.on && !t.neg; }).length;
    if (!terms.length) { textPass = orig.map(function () { return null; }); return; }
    var T = textsFor(scopeEl.value);
    textPass = orig.map(function (o, ti) {
      var arr = T[ti], pass = new Uint8Array(arr.length);
      for (var i = 0; i < arr.length; i++) {
        var s = arr[i], incHits = 0, excHit = false;
        for (var k = 0; k < terms.length; k++) {
          var t = terms[k], m = t.m(s);
          if (m) { t.n++; }
          if (t.on && m) { if (t.neg) { excHit = true; } else { incHits++; } }
        }
        var okInc = nInc === 0 || (all ? incHits === nInc : incHits > 0);
        pass[i] = (okInc && !excHit) ? 1 : 0;
      }
      return pass;
    });
  }

  function renderChips() {
    chipsEl.textContent = '';
    terms.forEach(function (t, idx) {
      var chip = document.createElement('span');
      chip.className = 'chip' + (t.on ? '' : ' off') + (t.neg ? ' neg' : '');
      chip.title = (t.neg ? 'Excluding' : 'Including') + ' · click to ' + (t.on ? 'switch off' : 'switch on');
      var label = document.createElement('span');
      label.textContent = (t.neg ? '\u2212' : '') + t.text;
      var n = document.createElement('small');
      n.textContent = t.n ? t.n.toLocaleString() : '0';
      var x = document.createElement('button');
      x.type = 'button'; x.className = 'x'; x.title = 'Remove'; x.textContent = '\u00d7';
      chip.addEventListener('click', function () { t.on = !t.on; changed(); });
      x.addEventListener('click', function (e) { e.stopPropagation(); terms.splice(idx, 1); changed(); });
      chip.append(label, n, x);
      chipsEl.appendChild(chip);
    });
  }

  function addTerms(raw) {
    String(raw).split(',').forEach(function (piece) {
      var s = piece.trim(), neg = false;
      if (s.charAt(0) === '-' || s.charAt(0) === '\u2212') { neg = true; s = s.slice(1).trim(); }
      if (!s) { return; }
      var dup = terms.some(function (t) { return t.neg === neg && t.text.toLowerCase() === s.toLowerCase(); });
      if (!dup) { terms.push({ text: s, neg: neg, on: true, n: 0, m: null }); }
    });
  }

  var KEY = 'cluster-terms:' + RUN;
  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify({
        terms: terms.map(function (t) { return { text: t.text, neg: t.neg, on: t.on }; }),
        mode: modeEl.value, scope: scopeEl.value, whole: wholeEl.checked
      }));
    } catch (e) { /* storage unavailable: the list just won't persist */ }
  }
  function restore() {
    try {
      var s = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (!s) { return; }
      (s.terms || []).forEach(function (t) {
        if (t && t.text) { terms.push({ text: String(t.text), neg: !!t.neg, on: t.on !== false, n: 0, m: null }); }
      });
      if (s.mode === 'all' || s.mode === 'any') { modeEl.value = s.mode; }
      if (['passage', 'hit', 'context'].indexOf(s.scope) >= 0) { scopeEl.value = s.scope; }
      wholeEl.checked = !!s.whole;
    } catch (e) { /* ignore a corrupt saved list */ }
  }

  /* ---------- applying both filters ---------- */
  function apply() {
    pending = false;
    var a = hasYears ? +lo.value : 0, b = hasYears ? +hi.value : 0;
    var yFull = !hasYears || (a <= MIN && b >= MAX);
    var xs = [], ys = [], cds = [], names = [], shown = 0;
    for (var t = 0; t < orig.length; t++) {
      var o = orig[t], tp = textPass[t], X = [], Y = [], C = [];
      for (var i = 0; i < o.x.length; i++) {
        if (tp && !tp[i]) { continue; }
        if (hasYears) {
          var yr = o.cd[i][6];
          if (yr === null || yr === undefined) { if (!yFull) { continue; } }
          else if (yr < a || yr > b) { continue; }
        }
        X.push(o.x[i]); Y.push(o.y[i]); C.push(o.cd[i]);
      }
      xs.push(X); ys.push(Y); cds.push(C);
      names.push(o.label + ' (n=' + X.length.toLocaleString() +
                 (X.length !== o.x.length ? ' of ' + o.x.length.toLocaleString() : '') + ')');
      shown += X.length;
    }
    Plotly.restyle(gd, { x: xs, y: ys, customdata: cds, name: names });
    count.textContent = shown.toLocaleString() + ' of ' + total.toLocaleString() + ' points shown';
    if (typeof gd.__onApply === 'function') { gd.__onApply(); }   // copy code forgets stale hovers
  }
  function schedule() { if (!pending) { pending = true; requestAnimationFrame(apply); } }
  function changed() { recomputeText(); renderChips(); save(); schedule(); }

  // Read by the copy code so a copy can say which filter produced it.
  gd.__filterInfo = function () {
    return {
      terms: terms.map(function (t) { return { text: t.text, neg: t.neg, on: t.on }; }),
      mode: modeEl.value, scope: scopeEl.value, whole: wholeEl.checked,
      years: hasYears ? [+lo.value, +hi.value] : null,
      yearBounds: hasYears ? [MIN, MAX] : null
    };
  };

  /* ---------- year controls ---------- */
  function clamp(v) { v = Math.round(+v); return Math.min(MAX, Math.max(MIN, isNaN(v) ? MIN : v)); }
  function setYears(a, b) {
    a = clamp(a); b = clamp(b);
    if (a > b) { var tmp = a; a = b; b = tmp; }
    lo.value = loN.value = a; hi.value = hiN.value = b;
    schedule();
  }
  if (hasYears) {
    lo.addEventListener('input', function () { setYears(Math.min(+lo.value, +hi.value), hi.value); });
    hi.addEventListener('input', function () { setYears(lo.value, Math.max(+hi.value, +lo.value)); });
    loN.addEventListener('change', function () { setYears(loN.value, hi.value); });
    hiN.addEventListener('change', function () { setYears(lo.value, hiN.value); });
    yrReset.addEventListener('click', function () { setYears(MIN, MAX); });
  }

  /* ---------- term controls ---------- */
  function submit() { if (inp.value.trim()) { addTerms(inp.value); inp.value = ''; changed(); } }
  addBtn.addEventListener('click', submit);
  inp.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { e.preventDefault(); submit(); }
    else if (e.key === 'Backspace' && !inp.value && terms.length) { terms.pop(); changed(); }
  });
  [modeEl, scopeEl, wholeEl].forEach(function (el) { el.addEventListener('change', changed); });
  clearBtn.addEventListener('click', function () { terms = []; changed(); });

  if (SEED.length) { addTerms(SEED.join(',')); } else { restore(); }
  recomputeText();
  renderChips();
  save();
  apply();
})();
"""

# Copying points to the clipboard. Works on whatever the filters currently leave in
# gd.data. customdata: [3] passage (HTML), [4] occurrence id, [5] membership,
# [6] numeric year, [7] index into DOCS, [8] hit_idx. Trace meta: {label, cluster, category}.
COPY_JS = r"""
(function () {
  var gd = document.getElementById('__DIV__');
  if (!gd) { return; }
  var RUN = __RUN__, DOCS = __DOCS__;
  var $ = function (id) { return document.getElementById(id); };
  var btnHover = $('copy-hover'), btnVisible = $('copy-visible'), btnOpt = $('opt-btn');
  var panel = $('opt-panel'), optMd = $('opt-md'), optCsv = $('opt-csv');
  var optLimit = $('opt-limit'), optClick = $('opt-click'), toast = $('toast');
  if (!btnHover || !btnVisible || !btnOpt || !panel || !toast) { return; }

  var OPT_KEY = 'cluster-copy-options';             // shared by all runs
  var COLS = ['occurrence_id', 'cluster', 'category', 'year', 'author', 'title', 'corpus',
              'doc_id', 'hit_idx', 'hit_word', 'membership', 'umap_x', 'umap_y', 'passage'];
  var opts = { format: 'markdown', limit: 20000, onClick: false };
  var hovered = null, last = null, toastTimer = null;

  /* ---------- options ---------- */
  function loadOpts() {
    try {
      var s = JSON.parse(localStorage.getItem(OPT_KEY) || 'null');
      if (!s) { return; }
      if (s.format === 'csv' || s.format === 'markdown') { opts.format = s.format; }
      var l = parseInt(s.limit, 10);
      if (!isNaN(l) && l >= 0) { opts.limit = l; }
      opts.onClick = !!s.onClick;
    } catch (e) { /* ignore corrupt saved options */ }
  }
  function saveOpts() { try { localStorage.setItem(OPT_KEY, JSON.stringify(opts)); } catch (e) {} }
  function syncOpts() {
    optMd.checked = opts.format === 'markdown';
    optCsv.checked = opts.format === 'csv';
    optLimit.value = opts.limit;
    optClick.checked = opts.onClick;
  }

  /* ---------- feedback and clipboard ---------- */
  function say(msg, bad) {
    toast.textContent = msg;
    toast.className = 'show' + (bad ? ' bad' : '');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.className = ''; }, 3400);
  }
  function legacyCopy(text) {
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      if (ok) { resolve(); } else { reject(new Error('copy blocked')); }
    });
  }
  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function () { return legacyCopy(text); });
    }
    return legacyCopy(text);
  }

  /* ---------- records ---------- */
  function plain(h) {
    return h.replace(/<br>/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
            .replace(/&quot;/g, '"').replace(/&#x27;/g, "'").replace(/&amp;/g, '&');
  }
  function record(t, i) {
    var cd = t.customdata[i], m = t.meta || {}, d = DOCS[cd[7]] || ['', '', '', ''];
    var p = plain(String(cd[3] || '')), a = p.indexOf('«'), b = p.indexOf('»');
    return {
      occurrence_id: cd[4],
      cluster: (m.cluster === undefined ? '' : m.cluster),
      category: m.category || '',
      year: (cd[6] === null || cd[6] === undefined) ? cd[0] : cd[6],
      author: d[2], title: d[3], corpus: d[0], doc_id: d[1],
      hit_idx: (cd[8] === null || cd[8] === undefined) ? '' : cd[8],
      hit_word: (a >= 0 && b > a) ? p.slice(a + 1, b) : '',
      membership: cd[5], umap_x: t.x[i], umap_y: t.y[i],
      passage: p
    };
  }

  /* ---------- formats ---------- */
  function csvCell(v) {
    if (v === null || v === undefined) { return ''; }
    var s = typeof v === 'number' && !Number.isInteger(v) ? String(Math.round(v * 1e4) / 1e4) : String(v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function toCSV(recs) {
    var lines = [COLS.join(',')];
    recs.forEach(function (r) { lines.push(COLS.map(function (c) { return csvCell(r[c]); }).join(',')); });
    return lines.join('\n') + '\n';
  }

  function mdEsc(s) { return String(s == null ? '' : s).replace(/([\\`*_\[\]<>])/g, '\\$1'); }
  function code(s) { return String(s == null ? '' : s).replace(/`/g, ''); }
  function mdPassage(p) {
    return mdEsc(p).replace(/«([^»]*)»/g, function (m, h) { return h ? '**' + h + '**' : ''; });
  }
  function mdEntry(r, n) {
    var who = (r.author ? mdEsc(r.author) : '') + (r.author && r.title ? ', ' : '') + mdEsc(r.title);
    var lines = [];
    lines.push('### ' + (n ? n + '. ' : '') + (who || '(untitled)') +
               (r.year !== '' && r.year != null ? ' (' + r.year + ')' : ''));
    lines.push('');
    var cl = r.cluster === -1 ? 'Noise'
           : 'Cluster ' + r.cluster + (r.category ? ' \u00b7 ' + mdEsc(r.category) : '');
    lines.push('- **Cluster:** ' + cl);
    lines.push('- **Source:** `' + code(r.corpus) + ' / ' + code(r.doc_id) + '`' +
               (r.hit_idx !== '' ? ', token ' + r.hit_idx : ''));
    lines.push('- **Occurrence:** `' + code(r.occurrence_id) + '`' +
               (isFinite(r.membership) ? ' \u00b7 membership ' + Number(r.membership).toFixed(2) : ''));
    lines.push('');
    lines.push('> ' + mdPassage(r.passage));
    return lines.join('\n');
  }

  function describeFilter() {
    var f = typeof gd.__filterInfo === 'function' ? gd.__filterInfo() : null, parts = [];
    if (f) {
      var inc = f.terms.filter(function (t) { return t.on && !t.neg; }).map(function (t) { return t.text; });
      var exc = f.terms.filter(function (t) { return t.on && t.neg; }).map(function (t) { return t.text; });
      if (inc.length) { parts.push('include ' + f.mode + ' of [' + inc.join(', ') + ']'); }
      if (exc.length) { parts.push('exclude [' + exc.join(', ') + ']'); }
      if (inc.length || exc.length) {
        parts.push('in ' + ({ passage: 'the passage', hit: 'the hit word', context: 'the context only' })[f.scope] +
                   (f.whole ? ', whole words' : ''));
      }
      if (f.years && (f.years[0] > f.yearBounds[0] || f.years[1] < f.yearBounds[1])) {
        parts.push('years ' + f.years[0] + '\u2013' + f.years[1]);
      }
    }
    var hidden = gd.data.filter(function (t) { return t.visible === 'legendonly' || t.visible === false; }).length;
    if (hidden) { parts.push(hidden + ' cluster' + (hidden === 1 ? '' : 's') + ' hidden in the legend'); }
    return parts.length ? parts.join('; ') : 'none';
  }

  function toMarkdown(recs, shown, total) {
    var head = ['# Occurrences', '',
                'Run `' + code(RUN) + '` \u00b7 ' + shown.toLocaleString() + ' point' + (shown === 1 ? '' : 's') +
                (shown < total ? ' (first ' + shown.toLocaleString() + ' of ' + total.toLocaleString() +
                                 ' visible, by year)' : '') + '.',
                'Filter: ' + describeFilter() + '.', ''];
    return head.join('\n') + '\n' + recs.map(function (r, i) { return mdEntry(r, i + 1); }).join('\n\n') + '\n';
  }

  /* ---------- copy actions ---------- */
  var FORMAT_NAME = { markdown: 'Markdown', csv: 'CSV' };
  function finish(text, n, total, what) {
    copyText(text).then(function () {
      var msg = 'Copied ' + what + ' as ' + FORMAT_NAME[opts.format];
      if (n < total) { msg += ' \u2014 first ' + n.toLocaleString() + ' of ' + total.toLocaleString() +
                              ' (raise the limit in Options)'; }
      say(msg);
    }, function () { say('The browser blocked copying. Try clicking the page first.', true); });
  }

  function copyPoint(ti, i) {
    var t = gd.data[ti];
    if (!t || !t.customdata || i == null || i >= t.customdata.length) { return false; }
    var r = record(t, i);
    finish(opts.format === 'csv' ? toCSV([r]) : mdEntry(r, 0) + '\n', 1, 1, '1 point');
    return true;
  }

  function copyVisible() {
    var refs = [];
    gd.data.forEach(function (t, ti) {
      if (t.visible === 'legendonly' || t.visible === false || !t.customdata) { return; }
      for (var i = 0; i < t.customdata.length; i++) { refs.push([ti, i]); }
    });
    if (!refs.length) { say('No points are visible', true); return; }
    var total = refs.length;

    function year(ref) {
      var y = gd.data[ref[0]].customdata[ref[1]][6];
      return (y === null || y === undefined) ? Infinity : y;
    }
    function cluster(ref) { var c = (gd.data[ref[0]].meta || {}).cluster; return c === undefined ? 0 : c; }
    refs.sort(function (a, b) {
      var ya = year(a), yb = year(b);
      if (ya !== yb) { return ya - yb; }
      var ca = cluster(a), cb = cluster(b);
      if (ca !== cb) { return ca - cb; }
      var ia = gd.data[a[0]].customdata[a[1]][4], ib = gd.data[b[0]].customdata[b[1]][4];
      return ia < ib ? -1 : (ia > ib ? 1 : 0);
    });
    if (opts.limit > 0 && refs.length > opts.limit) { refs = refs.slice(0, opts.limit); }

    var recs = refs.map(function (r) { return record(gd.data[r[0]], r[1]); });
    var text = opts.format === 'csv' ? toCSV(recs) : toMarkdown(recs, recs.length, total);
    finish(text, recs.length, total, recs.length.toLocaleString() + ' visible point' + (recs.length === 1 ? '' : 's'));
  }

  /* ---------- wiring ---------- */
  if (typeof gd.on === 'function') {
    gd.on('plotly_hover', function (ev) {
      var p = ev && ev.points && ev.points[0];
      if (p) { hovered = last = { ti: p.curveNumber, i: p.pointNumber }; }
    });
    gd.on('plotly_unhover', function () { hovered = null; });
    gd.on('plotly_click', function (ev) {
      var p = ev && ev.points && ev.points[0];
      if (opts.onClick && p) { copyPoint(p.curveNumber, p.pointNumber); }
    });
  }
  gd.__onApply = function () { hovered = last = null; };

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !panel.hidden) { panel.hidden = true; btnOpt.setAttribute('aria-expanded', 'false'); return; }
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) { return; }
    if (e.key !== 'c' && e.key !== 'C') { return; }
    var el = e.target, tag = el && el.tagName ? el.tagName.toLowerCase() : '';
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || (el && el.isContentEditable)) { return; }
    e.preventDefault();
    if (hovered) { copyPoint(hovered.ti, hovered.i); } else { say('Hover a point, then press C', true); }
  });

  btnHover.addEventListener('click', function () {
    if (last) { copyPoint(last.ti, last.i); } else { say('Hover a point first (then press C, or use this button)', true); }
  });
  btnVisible.addEventListener('click', copyVisible);

  btnOpt.addEventListener('click', function (e) {
    e.stopPropagation();
    panel.hidden = !panel.hidden;
    btnOpt.setAttribute('aria-expanded', String(!panel.hidden));
  });
  document.addEventListener('click', function (e) {
    if (!panel.hidden && !panel.contains(e.target) && e.target !== btnOpt) {
      panel.hidden = true; btnOpt.setAttribute('aria-expanded', 'false');
    }
  });
  [optMd, optCsv].forEach(function (el) {
    el.addEventListener('change', function () { opts.format = optCsv.checked ? 'csv' : 'markdown'; saveOpts(); });
  });
  optLimit.addEventListener('change', function () {
    var l = parseInt(optLimit.value, 10);
    opts.limit = (isNaN(l) || l < 0) ? opts.limit : l;
    optLimit.value = opts.limit; saveOpts();
  });
  optClick.addEventListener('change', function () { opts.onClick = optClick.checked; saveOpts(); });

  loadOpts();
  syncOpts();
})();
"""


def wrap_html(value: object, width: int = 60) -> str:
    """Wrap text for Plotly hover labels, escaping corpus text as HTML."""
    value = " ".join(str(value or "").split())
    escaped = html.escape(value)
    return "<br>".join(
        textwrap.wrap(escaped, width=width, break_long_words=True,
                      break_on_hyphens=False)
    )


def fetch_cluster_interpretations(conn, run_id: str) -> dict[int, dict]:
    """Fetch the LLM interpretation for each cluster in this run."""
    sql = """
        SELECT cluster, classification
        FROM target_cluster_interpretation
        WHERE run_id = %s
          AND prompt_version = %s
    """

    with conn.cursor() as cur:
        cur.execute(
            sql,
            (run_id, "cluster-interpretation-v1"),
        )

        rows = cur.fetchall()

    logger.info(
        "Loaded %d cluster interpretations for run %s",
        len(rows),
        run_id,
    )

    result = {}
    for cluster, classification in rows:
        if isinstance(classification, str):
            classification = json.loads(classification)

        if isinstance(classification, dict):
            result[int(cluster)] = classification

    return result


def fetch_occurrences(conn, occurrence_ids: list[str], words: int,
                      min_year: int | None = None,
                      max_year: int | None = None) -> dict:
    """
    Fetch metadata and a token-window passage for each occurrence.

    The lateral subquery uses the occurrence's own hit_idx, rather than searching
    the passage for the surface form (which may occur more than once).
    With min_year / max_year, out-of-range occurrences are not returned (and their
    passage text is never fetched).
    """
    sql = """
        SELECT
            o.occurrence_id, o.corpus, o.doc_id, o.pub_year, o.hit_idx,
            o.matched_token, d.author, d.title,
            COALESCE(passage.text, '') AS passage
        FROM target_occurrence o
        LEFT JOIN documents d
          ON d.corpus = o.corpus AND d.doc_id = o.doc_id
        LEFT JOIN LATERAL (
            SELECT string_agg(
                CASE WHEN t.token_idx = o.hit_idx
                     THEN '«' || t.token || '»'
                     ELSE t.token
                END,
                ' ' ORDER BY t.token_idx
            ) AS text
            FROM tokens t
            WHERE t.corpus = o.corpus
              AND t.doc_id = o.doc_id
              AND t.token_idx BETWEEN o.hit_idx - %s AND o.hit_idx + %s
        ) passage ON TRUE
        WHERE o.occurrence_id = ANY(%s)
          AND (%s::int IS NULL OR o.pub_year >= %s::int)
          AND (%s::int IS NULL OR o.pub_year <= %s::int)
    """
    result = {}
    # Keep parameter batches moderate for large runs.
    batch_size = 10_000
    with conn.cursor() as cur:
        for start in range(0, len(occurrence_ids), batch_size):
            batch = occurrence_ids[start:start + batch_size]
            cur.execute(sql, (words, words, batch,
                              min_year, min_year, max_year, max_year))
            for row in cur.fetchall():
                (oid, corpus, doc_id, year, hit_idx, token,
                 author, title, passage) = row
                result[oid] = {
                    "corpus": corpus,
                    "doc_id": doc_id,
                    "year": year,
                    "hit_idx": hit_idx,
                    "token": token or "",
                    "author": author or "Unknown author",
                    "title": title or doc_id,
                    "passage": passage or "",
                }
    return result


def _js_json(value) -> str:
    """JSON that is safe to embed inside an inline <script>."""
    return json.dumps(value).replace("</", "<\\/")


def build_page(fig, run_id: str, n_points: int, n_clusters: int,
               year_bounds: tuple[int, int] | None, use_cdn: bool,
               seed_terms: list[str] | None = None,
               docs: list[list[str]] | None = None) -> str:
    """Wrap the figure in a full-viewport page with the filters and copy controls."""
    year_controls = ""
    if year_bounds is not None:
        lo, hi = year_bounds
        year_controls = f"""
  <div class="years">
    <label>From
      <input id="yr-lo" type="range" min="{lo}" max="{hi}" step="1" value="{lo}">
      <input id="yr-lo-num" type="number" min="{lo}" max="{hi}" step="1" value="{lo}">
    </label>
    <label>To
      <input id="yr-hi" type="range" min="{lo}" max="{hi}" step="1" value="{hi}">
      <input id="yr-hi-num" type="number" min="{lo}" max="{hi}" step="1" value="{hi}">
    </label>
    <button id="yr-reset" type="button">Reset</button>
  </div>"""

    copy_controls = """
  <div class="copybar">
    <button id="copy-hover" type="button"
            title="Copy the point you last hovered (with the mouse over a point, press C)">Copy hovered point</button>
    <button id="copy-visible" type="button"
            title="Copy every point currently shown (year range, terms and legend apply)">Copy visible points</button>
    <span class="optwrap">
      <button id="opt-btn" type="button" aria-expanded="false" aria-controls="opt-panel">\u2699 Options</button>
      <div id="opt-panel" hidden>
        <div class="opt-title">Copy format</div>
        <div class="opt-formats">
          <label><input type="radio" name="copy-format" id="opt-md" value="markdown"> Markdown</label>
          <label><input type="radio" name="copy-format" id="opt-csv" value="csv"> CSV</label>
        </div>
        <label class="opt-row">Max points per copy
          <input type="number" id="opt-limit" min="0" step="1000"></label>
        <small>0 means no limit. Very large copies can hang the browser. Points are
          ordered by year, then cluster, so a limit keeps the earliest.</small>
        <label><input type="checkbox" id="opt-click"> Copy a point when I click it</label>
        <small>Shortcut: hover a point and press C.</small>
      </div>
    </span>
  </div>"""

    term_controls = """
  <div class="terms">
    <input id="term-in" type="text" autocomplete="off" spellcheck="false"
           placeholder="add term, press Enter  (comma = several, leading - = exclude)">
    <button id="term-add" type="button">Add</button>
    <span id="chips"></span>
    <label>match
      <select id="term-mode"><option value="any">any</option><option value="all">all</option></select>
    </label>
    <label>in
      <select id="term-scope">
        <option value="passage">passage</option>
        <option value="hit">hit word</option>
        <option value="context">context only</option>
      </select>
    </label>
    <label><input type="checkbox" id="term-whole"> whole words</label>
    <button id="term-clear" type="button">Clear terms</button>
  </div>"""

    run_json = _js_json(run_id)
    post_script = (
        FILTER_JS.replace("__DIV__", PLOT_DIV_ID)
        .replace("__RUN__", run_json)
        .replace("__SEED__", _js_json(seed_terms or []))
        + COPY_JS.replace("__DIV__", PLOT_DIV_ID)
        .replace("__RUN__", run_json)
        .replace("__DOCS__", _js_json(docs or []))
    )

    fragment = fig.to_html(
        full_html=False,
        include_plotlyjs="cdn" if use_cdn else True,
        default_width="100%",
        default_height="100%",
        div_id=PLOT_DIV_ID,
        post_script=post_script,
        config={
            "responsive": True,
            "scrollZoom": True,
            "displaylogo": False,
            "toImageButtonOptions": {"format": "png", "scale": 2},
        },
    )

    title = f"Target occurrence clusters · {run_id}"
    return (
        '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n<style>{PAGE_CSS}</style>\n</head>\n<body>\n"
        f'<div id="bar">\n  <span class="title">{html.escape(title)}</span>\n'
        f'  <span class="stat">{n_points:,} points · {n_clusters:,} clusters</span>'
        f'{year_controls}\n  <span class="stat" id="shown-count"></span>'
        f"{copy_controls}{term_controls}\n</div>\n"
        f'<div id="plotwrap">{fragment}</div>\n'
        '<div id="toast" role="status" aria-live="polite"></div>\n</body>\n</html>\n'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--words", type=int, default=20,
                        help="tokens of context on either side of the hit "
                             "(also the window the term filter searches)")
    parser.add_argument("--wrap", type=int, default=60,
                        help="hover-passage wrap width in characters")
    parser.add_argument("--out", default=None, help="output HTML path")
    parser.add_argument("--point-size", type=float, default=5.0)
    parser.add_argument("--min-year", type=int, default=None,
                        help="drop occurrences published before this year")
    parser.add_argument("--max-year", type=int, default=None,
                        help="drop occurrences published after this year")
    parser.add_argument("--term", action="append", default=[],
                        help="preload a term (repeatable). Replaces any list saved "
                             "in the browser.")
    parser.add_argument("--exclude", action="append", default=[],
                        help="preload an excluded term (repeatable)")
    parser.add_argument("--noise", action="store_true",
                        help="include HDBSCAN noise (shown in grey)")
    parser.add_argument("--cdn", action="store_true",
                        help="load Plotly from CDN instead of embedding it")
    args = parser.parse_args()

    npz_path = Path(OUT_DIR) / "target_runs" / f"{args.run_id}.npz"
    if not npz_path.exists():
        raise SystemExit(f"Cannot find clustering output: {npz_path}")

    data = np.load(npz_path, allow_pickle=False)
    ids = data["occurrence_id"].astype(str)
    xy = data["e2"]
    labels = data["labels"].astype(int)
    probs = data["probs"]

    if not (len(ids) == len(xy) == len(labels) == len(probs)):
        raise SystemExit("The .npz arrays have inconsistent lengths")

    print(f"Loading metadata and passages for {len(ids):,} occurrences...")
    conn = get_connection(application_name="visualise-target-clusters")

    try:
        metadata = fetch_occurrences(conn, ids.tolist(), args.words, args.min_year, args.max_year)
        interpretations = fetch_cluster_interpretations(conn, args.run_id)

        print(f"Loaded {len(interpretations)} cluster interpretations")
        for cluster, interpretation in sorted(interpretations.items()):
            print(
                f"  Cluster {cluster}: "
                f"{interpretation.get('category', '<no category>')}"
            )

    finally:
        conn.close()

    if args.min_year is not None or args.max_year is not None:
        keep = np.fromiter((oid in metadata for oid in ids), dtype=bool, count=len(ids))
        print(f"Year filter kept {int(keep.sum()):,} of {len(keep):,} occurrences")
        if not keep.any():
            raise SystemExit("No occurrences fall inside that year range")
        ids, xy, labels, probs = ids[keep], xy[keep], labels[keep], probs[keep]
    else:
        missing = len(ids) - len(metadata)
        if missing:
            print(f"Warning: {missing:,} occurrences had no matching metadata row")

    years = [m["year"] for m in metadata.values() if m["year"] is not None]
    year_bounds = (int(min(years)), int(max(years))) if years else None

    import plotly.graph_objects as go
    from plotly.colors import qualitative

    fig = go.Figure()
    palette = qualitative.Dark24
    cluster_ids = sorted(c for c in set(labels.tolist()) if c >= 0)
    if args.noise and np.any(labels == -1):
        cluster_ids = [-1] + cluster_ids

    # One entry per document, shared by all points (keeps the copy data compact):
    # [corpus, doc_id, author, full title].
    docs: list[list[str]] = []
    doc_index: dict[tuple[str, str], int] = {}

    def doc_slot(m: dict) -> int:
        key = (m["corpus"], m["doc_id"])
        if key not in doc_index:
            doc_index[key] = len(docs)
            docs.append([m["corpus"], m["doc_id"], m["author"], m["title"]])
        return doc_index[key]

    for cluster in cluster_ids:
        idx = np.flatnonzero(labels == cluster)
        if not len(idx):
            continue

        # customdata columns: 0 year text, 1 heading, 2 corpus/doc, 3 passage,
        # 4 occurrence id, 5 membership, 6 numeric year (used by the page's filters),
        # 7 index into docs, 8 hit_idx (7 and 8 are used when copying points)
        custom = []
        for i in idx:
            m = metadata.get(ids[i])
            if m is None:
                custom.append(["?", "Unknown", "No metadata", "", ids[i], 0.0, None, -1, None])
                continue

            heading = f"{m['author']}, {m['title'][:100]}"
            passage = wrap_html(m["passage"], args.wrap)
            custom.append([
                str(m["year"]),
                wrap_html(heading, args.wrap),
                wrap_html(f"{m['corpus']} / {m['doc_id']}", args.wrap),
                passage,
                ids[i],
                float(probs[i]),
                int(m["year"]) if m["year"] is not None else None,
                doc_slot(m),
                int(m["hit_idx"]) if m["hit_idx"] is not None else None,
            ])

        is_noise = cluster == -1

        # label = "Noise" if is_noise else f"Cluster {cluster}"
        # colour = "#777777" if is_noise else palette[(cluster if cluster >= 0 else 0) % len(palette)]

        category = ""
        if is_noise:
            label = "Noise"
        else:
            interpretation = interpretations.get(cluster, {})
            category = interpretation.get("category", "").strip()
            label = (
                f"Cluster {cluster} · {category}"
                if category
                else f"Cluster {cluster}"
            )

        colour = "#777777" if is_noise else palette[cluster % len(palette)]

        fig.add_trace(go.Scattergl(
            # Plain lists (not numpy) so the page's filters can read them back as given.
            x=np.round(xy[idx, 0], 4).tolist(),
            y=np.round(xy[idx, 1], 4).tolist(),
            mode="markers",
            name=f"{label} (n={len(idx):,})",
            meta=dict(label=label, cluster=int(cluster), category=category),
            marker=dict(
                size=3 if is_noise else args.point_size,
                color=colour,
                opacity=0.25 if is_noise else 0.78,
            ),
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>"
                "%{customdata[0]}<br>"
                "<span style='color:#aaaaaa'>%{customdata[2]}</span><br><br>"
                "%{customdata[3]}<br><br>"
                "<span style='color:#aaaaaa'>"
                "Membership: %{customdata[5]:.2f}<br>"
                "Occurrence: %{customdata[4]}"
                "</span><extra></extra>"
            ),
        ))

    fig.update_layout(
        template="plotly_dark",
        autosize=True,                      # fill the container; no fixed height
        paper_bgcolor="#111318",
        plot_bgcolor="#171a21",
        font=dict(family="Segoe UI, Arial, sans-serif", color="#e2e5eb", size=12),
        hoverlabel=dict(
            bgcolor="#252a34",
            bordercolor="#596273",
            font=dict(family="Segoe UI, Arial, sans-serif", size=16,
                      color="#f2f3f5"),
            align="left",
        ),
        xaxis=dict(title="UMAP 1", showgrid=True, gridcolor="#292e38",
                   zeroline=False),
        yaxis=dict(title="UMAP 2", showgrid=True, gridcolor="#292e38",
                   zeroline=False),
        legend=dict(
            title="Clusters · click to hide/show",
            bgcolor="rgba(20,23,30,0.85)",
            bordercolor="#343b48",
            borderwidth=1,
            itemsizing="constant",
            y=1,
            yanchor="top",
            x=1.01,
        ),
        margin=dict(l=55, r=230, t=20, b=50),
        hovermode="closest",
    )

    out_path = Path(args.out) if args.out else (
        Path(OUT_DIR) / "target_runs" / f"{args.run_id}.html"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        build_page(fig, args.run_id, len(ids), len(set(labels[labels >= 0].tolist())),
                   year_bounds, args.cdn,
                   list(args.term) + [f"-{t}" for t in args.exclude],
                   docs),
        encoding="utf-8",
    )

    print(f"Saved: {out_path}")
    print(f"Points: {len(ids):,} | clusters: {len(set(labels[labels >= 0])):,} "
          f"| noise: {(labels == -1).sum():,}")
    print(f"Open the HTML file in your browser. {out_path}")


if __name__ == "__main__":
    main()
