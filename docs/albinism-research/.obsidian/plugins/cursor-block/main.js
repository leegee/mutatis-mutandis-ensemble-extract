"use strict";
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
  default: () => CursorBlockPlugin
});
module.exports = __toCommonJS(main_exports);
var import_obsidian = require("obsidian");
var import_state = require("@codemirror/state");
var import_view = require("@codemirror/view");
var blockCursorLayer = (0, import_view.layer)({
  above: true,
  class: "cm-block-cursor-layer",
  markers(view) {
    const markers = [];
    for (const range of view.state.selection.ranges) {
      if (!range.empty)
        continue;
      const head = range.head;
      const line = view.state.doc.lineAt(head);
      if (head < line.to) {
        markers.push(
          ...import_view.RectangleMarker.forRange(
            view,
            "cm-block-cursor",
            import_state.EditorSelection.range(head, head + 1)
          )
        );
      } else {
        const coords = view.coordsAtPos(head);
        if (!coords)
          continue;
        const base = view.scrollDOM.getBoundingClientRect();
        const left = coords.left - base.left + view.scrollDOM.scrollLeft;
        const top = coords.top - base.top + view.scrollDOM.scrollTop;
        markers.push(
          new import_view.RectangleMarker(
            "cm-block-cursor",
            left,
            top,
            view.defaultCharacterWidth,
            coords.bottom - coords.top
          )
        );
      }
    }
    return markers;
  },
  update(update) {
    return update.docChanged || update.selectionSet || update.viewportChanged || update.geometryChanged;
  }
});
var DEFAULT_SETTINGS = {
  useAccentColor: true,
  color: "#7f6df2",
  opacity: 0.6,
  invertText: false,
  blink: true,
  blinkSpeed: 1.2
};
var restartBlink = import_view.ViewPlugin.fromClass(
  class {
    constructor() {
      this.phase = false;
    }
    update(update) {
      if (!update.docChanged && !update.selectionSet)
        return;
      this.phase = !this.phase;
      update.view.dom.classList.toggle("cursor-block-phase-b", this.phase);
    }
  }
);
var CursorBlockPlugin = class extends import_obsidian.Plugin {
  constructor() {
    super(...arguments);
    this.settings = DEFAULT_SETTINGS;
  }
  async onload() {
    await this.loadSettings();
    this.applyStyles();
    this.addSettingTab(new CursorBlockSettingTab(this.app, this));
    this.registerEditorExtension([
      blockCursorLayer,
      restartBlink,
      import_view.EditorView.editorAttributes.of({ class: "cursor-block-enabled" })
    ]);
  }
  onunload() {
    const style = document.body.style;
    style.removeProperty("--cursor-block-color");
    style.removeProperty("--cursor-block-opacity");
    style.removeProperty("--cursor-block-blend");
    style.removeProperty("--cursor-block-blink-duration");
    document.body.classList.remove("cursor-block-no-blink");
  }
  async loadSettings() {
    const data = await this.loadData();
    this.settings = Object.assign({}, DEFAULT_SETTINGS, data);
  }
  // Settings are passed to the CSS through variables on the body
  applyStyles() {
    const s = this.settings;
    const style = document.body.style;
    style.setProperty("--cursor-block-color", s.useAccentColor ? "var(--text-accent)" : s.color);
    style.setProperty("--cursor-block-opacity", String(s.invertText ? 1 : s.opacity));
    style.setProperty("--cursor-block-blend", s.invertText ? "difference" : "normal");
    style.setProperty("--cursor-block-blink-duration", `${s.blinkSpeed}s`);
    document.body.classList.toggle("cursor-block-no-blink", !s.blink);
  }
};
var CursorBlockSettingTab = class extends import_obsidian.PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }
  getSettingDefinitions() {
    const settings = this.plugin.settings;
    return [
      {
        name: "Use accent color",
        desc: "Use the theme's accent color instead of a custom color.",
        control: { type: "toggle", key: "useAccentColor", defaultValue: DEFAULT_SETTINGS.useAccentColor }
      },
      {
        name: "Cursor color",
        visible: () => !settings.useAccentColor,
        control: { type: "color", key: "color", defaultValue: DEFAULT_SETTINGS.color }
      },
      {
        name: "Invert text under cursor",
        desc: "Solid block with the character underneath shown in inverted color (ignores opacity).",
        control: { type: "toggle", key: "invertText", defaultValue: DEFAULT_SETTINGS.invertText }
      },
      {
        name: "Opacity",
        visible: () => !settings.invertText,
        control: {
          type: "slider",
          key: "opacity",
          min: 0.1,
          max: 1,
          step: 0.05,
          defaultValue: DEFAULT_SETTINGS.opacity,
          displayFormat: (v) => `${Math.round(v * 100)}%`
        }
      },
      {
        name: "Blink",
        control: { type: "toggle", key: "blink", defaultValue: DEFAULT_SETTINGS.blink }
      },
      {
        name: "Blink duration",
        desc: "Lower values make the cursor blink faster.",
        visible: () => settings.blink,
        control: {
          type: "slider",
          key: "blinkSpeed",
          min: 0.4,
          max: 3,
          step: 0.1,
          defaultValue: DEFAULT_SETTINGS.blinkSpeed,
          displayFormat: (v) => `${v.toFixed(1)}s`
        }
      }
    ];
  }
  // Saves through the default implementation, then applies the new look and
  // shows or hides the settings that depend on the toggles
  async setControlValue(key, value) {
    await super.setControlValue(key, value);
    this.plugin.applyStyles();
    this.refreshDomState();
  }
};

/* nosourcemap */