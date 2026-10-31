// Card styles: one design-system layer shared by the hero, the sections,
// the settings panel and the editor. Everything is scoped to the shadow root and built on Home
// Assistant theme variables, so it follows light and dark themes.
//
// Views only compose these components; they must not add their own styles:
//   .hero      configurable vehicle image with its overlays
//   .segmented segmented control used by the climate content
//   .section   titled card group
//   .chip      state pill (neutral, on / warn for active or alert)
//   .tile      touch target for controls and compact readouts
//   .metric    label + value readout
//   .stepper   minus / value / plus control
//   .stage     layered vehicle picture

const PANEL_CSS = `
:host {
  /* Spacing, radii and type tokens: the single source for the whole UI. */
  --dp-space-xs: 4px;
  --dp-space-sm: 8px;
  --dp-space-md: 12px;
  --dp-space-lg: 16px;
  --dp-space-xl: 24px;
  --dp-radius: var(--ha-card-border-radius, 16px);
  --dp-radius-sm: 12px;
  --dp-radius-pill: 999px;
  --dp-surface: var(--card-background-color);
  --dp-surface-2: var(--secondary-background-color);
  --dp-line: var(--divider-color);
  --dp-text: var(--primary-text-color);
  --dp-text-2: var(--secondary-text-color);
  --dp-accent: var(--primary-color);
  --dp-warn: var(--error-color);
  --dp-on-text: var(--text-primary-color, white);
  --dp-touch: 44px;

  display: block;
  height: auto;
  background: transparent;
  color: var(--dp-text);
  font-family: var(--ha-font-family-body, Roboto, sans-serif);
}


:focus-visible {
  outline: 2px solid var(--dp-accent);
  outline-offset: 2px;
}

/* --- Segmented tabs ---------------------------------------------------- */

.segmented {
  display: flex;
  gap: var(--dp-space-xs);
  padding: var(--dp-space-xs);
  background: var(--dp-surface);
  border-radius: var(--dp-radius-pill);
}

.segment {
  flex: 1 1 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  padding: var(--dp-space-sm);
  border: none;
  border-radius: var(--dp-radius-pill);
  background: none;
  color: var(--dp-text-2);
  font-size: 14px;
  cursor: pointer;
  touch-action: manipulation;
}

.segment:hover { color: var(--dp-text); }

.segment[aria-selected="true"],
.segment[aria-pressed="true"] {
  background: var(--dp-accent);
  color: var(--dp-on-text);
}

.segment ha-icon { --mdc-icon-size: 18px; }

.center { display: flex; justify-content: center; }

/* --- Sections ---------------------------------------------------------- */


.section {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  padding: var(--dp-space-md) 14px;
  background: var(--dp-surface);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius);
}

.section-head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
}

.section-head ha-icon { color: var(--dp-text-2); --mdc-icon-size: 18px; }

.section-title {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--dp-text-2);
  text-transform: uppercase;
}

.section-note {
  margin-left: auto;
  font-size: 12px;
  color: var(--dp-text-2);
}

/* --- Chips ------------------------------------------------------------- */

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: var(--dp-radius-pill);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-size: 13px;
  white-space: nowrap;
}

.chip ha-icon { --mdc-icon-size: 16px; }
.chip.on { background: var(--dp-accent); color: var(--dp-on-text); }
.chip.warn { background: var(--dp-warn); color: var(--dp-on-text); }

/* --- Tiles ------------------------------------------------------------- */

.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: var(--dp-space-sm);
}

.tile {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  min-height: var(--dp-touch);
  padding: 10px var(--dp-space-md);
  border: none;
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-family: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  touch-action: manipulation;
}

.tile:hover { filter: brightness(1.06); }
.tile.static { cursor: default; }
.tile.static:hover { filter: none; }
.tile ha-icon { --mdc-icon-size: 20px; }
.tile.on { background: var(--dp-accent); color: var(--dp-on-text); }
.tile.warn { background: var(--dp-warn); color: var(--dp-on-text); }
.tile:disabled { opacity: 0.5; cursor: default; }

.tile-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.tile-label { font-size: 12px; color: var(--dp-text-2); }
.tile-value { font-size: 15px; font-weight: 600; }
.tile.on .tile-label, .tile.warn .tile-label { color: var(--dp-on-text); }

/* --- Metrics ----------------------------------------------------------- */

.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: var(--dp-space-sm);
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px var(--dp-space-md);
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
}

.metric .label { font-size: 12px; color: var(--dp-text-2); }
.metric .value { font-size: 17px; font-weight: 600; }
.metric.warn .value { color: var(--dp-warn); }

/* --- Steppers ---------------------------------------------------------- */

.steppers {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: var(--dp-space-sm);
}

.stepper {
  display: inline-flex;
  align-items: center;
  gap: var(--dp-space-sm);
}

.stepper button {
  width: 32px;
  height: 32px;
  border: 1px solid var(--dp-line);
  border-radius: 50%;
  background: var(--dp-surface);
  color: var(--dp-text);
  font-size: 16px;
  cursor: pointer;
  touch-action: manipulation;
}

.stepper button:hover { background: var(--dp-surface-2); }
.stepper .value {
  min-width: 44px;
  text-align: center;
  font-size: 16px;
  font-weight: 600;
}

.stepper.large button { width: var(--dp-touch); height: var(--dp-touch); }
.stepper.large .value { font-size: 28px; min-width: 84px; }

.control {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.control .label { font-size: 12px; color: var(--dp-text-2); }

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field label { font-size: 12px; color: var(--dp-text-2); }

.field input[type="time"] {
  min-height: 40px;
  padding: 8px 10px;
  background: var(--dp-surface-2);
  color: var(--dp-text);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  font-family: inherit;
  font-size: 14px;
}

/* --- Vehicle stage ----------------------------------------------------- */

.stage {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: var(--dp-radius);
}

.stage-status { aspect-ratio: 1 / 1; }
/* The rotated status picture is cropped top and bottom to a 750:550 frame;
   the square source stays centred and is not scaled down. */
.stage-status.stage-rotated { aspect-ratio: 750 / 550; }
.stage-status.stage-rotated img {
  inset: auto 0;
  top: 50%;
  height: auto;
  aspect-ratio: 1 / 1;
  transform: translateY(-50%) rotate(-90deg);
}
.stage-compact { aspect-ratio: 3 / 2; }
.stage-climate { aspect-ratio: 1125 / 642; }
.stage-charging { aspect-ratio: 3 / 2; }
.stage-seats {
  aspect-ratio: 3 / 4;
  max-width: 460px;
  margin: 0 auto;
}

/* --- Animation layer --------------------------------------------------- */

.anim-host {
  display: none;
}

.anim-slot {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
}

.anim-slot video.anim {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

/* The seat wind clip is a partial overlay: its placement over the seats
   picture is approximate and tuned here. */
.stage-seats .anim-slot {
  inset: auto;
  left: 18%;
  top: 20%;
  width: 62%;
  height: 58%;
}

.stage img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

/* The isometric angle can hide an open front door behind its own panel; the
   pre-rendered outline piece is stacked on top of the open door. */
.stage .open-door-outline {
  opacity: 0.92;
}

.vehicle-photo {
  display: block;
  width: 100%;
  border-radius: var(--dp-radius);
}

/* --- Sessions and feedback -------------------------------------------- */

.session {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: var(--dp-space-sm);
}

.alert {
  background: color-mix(in srgb, var(--dp-warn) 12%, transparent);
  border: 1px solid var(--dp-warn);
  border-radius: var(--dp-radius-sm);
  padding: var(--dp-space-sm) var(--dp-space-md);
  font-size: 14px;
}

.empty {
  padding: var(--dp-space-xl);
  text-align: center;
  color: var(--dp-text-2);
}

/* --- Dashboard card ---------------------------------------------------- */

.card-root {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  overflow: hidden;
  padding: var(--dp-space-md) var(--dp-space-lg) var(--dp-space-sm);
  border-radius: var(--dp-radius);
  background: var(--ha-card-background, var(--card-background-color, var(--dp-surface)));
  color: var(--dp-text);
}

.card-root[data-pad="half"] { padding: var(--dp-space-sm); gap: var(--dp-space-sm); }
.card-root[data-pad="none"] { padding: 0 0 var(--dp-space-sm); gap: var(--dp-space-sm); }
.card-root[data-pad="none"] .hero { border-radius: 0; }
.card-root[data-pad="none"] > .section { margin-inline: var(--dp-space-sm); }

.card-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  border: 0;
  border-radius: var(--dp-radius-sm);
  background: transparent;
  color: var(--dp-text-2);
  font-size: 13px;
  cursor: pointer;
}

.card-footer:hover { background: var(--dp-surface-2); color: var(--dp-text); }
.card-footer ha-icon { --mdc-icon-size: 18px; }

/* --- Hero -------------------------------------------------------------- */

.hero {
  position: relative;
  overflow: hidden;
  isolation: isolate;
  border-radius: var(--dp-radius);
  background: #000;
  aspect-ratio: var(--hero-aspect, 3 / 2);
  min-height: 180px;
}

.hero-stage,
.hero-stage .stage {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  aspect-ratio: auto;
  border-radius: 0;
}

.hero-stage .stage img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scale(var(--hero-scale, 1));
  transform-origin: center center;
}

.hero-stage .stage-status.stage-rotated {
  aspect-ratio: auto;
}

.hero-stage .stage-status.stage-rotated img {
  inset: auto 0;
  top: 50%;
  width: 100%;
  height: auto;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  transform: translateY(-50%) rotate(-90deg) scale(var(--hero-scale, 1));
  transform-origin: center center;
}

.hero-stage .vehicle-photo {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scale(var(--hero-scale, 1));
  transform-origin: center center;
}

.hero-shade {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(180deg, rgba(0, 0, 0, 0.62), transparent 42%),
    linear-gradient(0deg, rgba(0, 0, 0, 0.58), transparent 38%);
}

.hero-top,
.hero-bottom {
  position: absolute;
  left: 0;
  right: 0;
  z-index: 2;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--dp-space-sm);
  padding: 12px 14px;
  color: #fff;
}

.hero-top { top: 0; }
.hero-bottom { bottom: 0; align-items: flex-end; }

.hero-title {
  display: flex;
  flex-direction: column;
  min-width: 0;
  text-shadow: 0 1px 8px rgba(0, 0, 0, 0.55);
}

.hero-name {
  overflow: hidden;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hero-model,
.hero-plate {
  font-size: 12px;
  opacity: 0.82;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}

.hero-actions .icon-button {
  width: 36px;
  height: 36px;
  background: rgba(0, 0, 0, 0.38);
  color: #fff;
}

.hero-actions .hero-cloud {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  color: #fff;
  filter: drop-shadow(0 1px 4px rgba(0, 0, 0, 0.5));
}

.hero-actions .hero-cloud.ok { color: #6ee7b7; }
.hero-actions .hero-cloud.bad { color: #fca5a5; }

.hero-range {
  position: absolute;
  left: 14px;
  bottom: 48px;
  z-index: 2;
  display: flex;
  align-items: baseline;
  gap: 8px;
  color: #fff;
  text-shadow: 0 2px 12px rgba(0, 0, 0, 0.6);
}

.hero-range .big {
  font-size: 36px;
  font-weight: 300;
  letter-spacing: -0.03em;
  line-height: 1;
}

.hero-range .unit {
  font-size: 14px;
  opacity: 0.82;
}

.hero-range .split {
  display: flex;
  gap: 10px;
  font-size: 12px;
  opacity: 0.88;
}

.hero-range .split span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.hero-range ha-icon { --mdc-icon-size: 15px; }

.hero-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.hero-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 9px;
  border-radius: var(--dp-radius-pill);
  background: rgba(0, 0, 0, 0.46);
  color: #fff;
  font-size: 12px;
  white-space: nowrap;
  backdrop-filter: blur(4px);
}

.hero-chip ha-icon { --mdc-icon-size: 15px; }
.hero-chip.warn { background: rgba(185, 28, 28, 0.82); }
.hero-chip.on { background: rgba(5, 150, 105, 0.82); }

.hero-updated {
  font-size: 11px;
  opacity: 0.72;
  white-space: nowrap;
}

/* --- Actions ----------------------------------------------------------- */

.actions-grid,
.actions-fit {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(82px, 1fr));
  gap: var(--dp-space-sm);
}

.actions-scroll {
  display: flex;
  gap: var(--dp-space-sm);
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: thin;
}

.actions-scroll .action { flex: 0 0 86px; }

.actions-split .actions-main {
  display: grid;
  grid-template-columns: repeat(var(--primary, 4), minmax(0, 1fr));
  gap: var(--dp-space-sm);
}

.actions-split .actions-more {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(82px, 1fr));
  gap: var(--dp-space-sm);
  margin-top: var(--dp-space-sm);
}

.action {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 76px;
  padding: 8px 6px;
  border: 0;
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-family: inherit;
  cursor: pointer;
  touch-action: manipulation;
}

.action:hover { filter: brightness(1.07); }
.action ha-icon { --mdc-icon-size: 24px; }
.action.on { background: var(--dp-accent); color: var(--dp-on-text); }
.action.warn { background: var(--dp-warn); color: var(--dp-on-text); }
.action:disabled { opacity: 0.45; cursor: default; }
.action .action-label { font-size: 11px; font-weight: 600; text-align: center; }
.action .action-value { font-size: 10px; color: var(--dp-text-2); text-align: center; }
.action.on .action-value, .action.warn .action-value { color: var(--dp-on-text); }
.action.size-s { min-height: 60px; }
.action.size-s ha-icon { --mdc-icon-size: 20px; }
.action.size-l { min-height: 92px; }
.action.size-l ha-icon { --mdc-icon-size: 30px; }

.actions-more-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin: var(--dp-space-sm) auto 0;
  padding: 4px 12px;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-pill);
  background: var(--dp-surface);
  color: var(--dp-text-2);
  font-size: 12px;
  cursor: pointer;
}

/* --- Info tiles -------------------------------------------------------- */

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: var(--dp-space-sm);
}

.info-tile {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  min-height: 58px;
  padding: 8px 10px;
  border: 0;
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
}

.info-tile.static { cursor: default; }
.info-tile ha-icon { --mdc-icon-size: 20px; color: var(--dp-text-2); }
.info-tile .info-value { font-size: 15px; font-weight: 600; }
.info-tile .info-label { font-size: 11px; color: var(--dp-text-2); }

/* --- Settings ---------------------------------------------------------- */

deepal-card-settings { display: block; width: 100%; }

.settings-sheet {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: var(--dp-space-md);
  background: rgba(0, 0, 0, 0.58);
}

.settings-panel {
  display: flex;
  flex-direction: column;
  width: min(680px, 100%);
  max-height: 88vh;
  overflow: hidden;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius);
  background: var(--dp-surface);
  color: var(--dp-text);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
}

.settings-panel.embedded {
  position: static;
  width: 100%;
  max-height: none;
  box-shadow: none;
}

.settings-head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  padding: var(--dp-space-md) var(--dp-space-lg);
  border-bottom: 1px solid var(--dp-line);
}

.settings-head h3 {
  flex: 1;
  margin: 0;
  font-size: 17px;
}

.settings-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: var(--dp-surface-2);
  color: var(--dp-text);
  cursor: pointer;
}

.settings-tabs {
  display: flex;
  gap: 4px;
  padding: 8px var(--dp-space-md);
  overflow-x: auto;
  border-bottom: 1px solid var(--dp-line);
  scrollbar-width: thin;
}

.settings-tab {
  flex: none;
  padding: 7px 11px;
  border: 0;
  border-radius: var(--dp-radius-pill);
  background: transparent;
  color: var(--dp-text-2);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.settings-tab.on { background: var(--dp-accent); color: var(--dp-on-text); }

.settings-body {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  padding: var(--dp-space-md) var(--dp-space-lg) var(--dp-space-xl);
  overflow-y: auto;
}

.settings-group {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-sm);
  padding: var(--dp-space-md);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
}

.settings-group h4 {
  margin: 0;
  font-size: 13px;
  color: var(--dp-text-2);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.setting-row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  min-height: 38px;
  font-size: 13px;
}

.setting-row > span { flex: 1; min-width: 0; }
.setting-row small { display: block; color: var(--dp-text-2); font-size: 11px; }
.setting-row select,
.setting-row input[type="text"],
.setting-row input[type="number"] {
  min-width: 120px;
  max-width: 190px;
  padding: 7px 8px;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-family: inherit;
  font-size: 13px;
}
.setting-row input[type="checkbox"] { width: 18px; height: 18px; accent-color: var(--dp-accent); }
.setting-row .move { display: inline-flex; gap: 4px; }
.setting-row .move button {
  width: 30px;
  height: 30px;
  border: 1px solid var(--dp-line);
  border-radius: 8px;
  background: var(--dp-surface-2);
  color: var(--dp-text);
  cursor: pointer;
}
.setting-row.off > span { opacity: 0.55; }
.settings-hint { margin: 0; color: var(--dp-text-2); font-size: 12px; }

/* --- Confirm sheet ----------------------------------------------------- */

.confirm-sheet {
  position: fixed;
  inset: 0;
  z-index: 21;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--dp-space-md);
  background: rgba(0, 0, 0, 0.58);
}

.confirm-box {
  width: min(420px, 100%);
  padding: var(--dp-space-lg);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius);
  background: var(--dp-surface);
  color: var(--dp-text);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
}

.confirm-box h3 { margin: 0 0 6px; font-size: 17px; }
.confirm-box p { margin: 0 0 var(--dp-space-md); color: var(--dp-text-2); font-size: 13px; }
.confirm-actions { display: flex; gap: var(--dp-space-sm); }
.confirm-actions button {
  flex: 1;
  min-height: 42px;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
}
.confirm-actions .go { border-color: var(--dp-warn); background: var(--dp-warn); color: var(--dp-on-text); }

.card-toast {
  padding: 8px 12px;
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-size: 12px;
}

.card-toast.pos-top { order: -1; }
.card-toast.ok { background: rgba(5, 150, 105, 0.18); }
.card-toast.warn { background: rgba(185, 28, 28, 0.18); }

.hero-empty {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  min-height: 180px;
  color: rgba(255, 255, 255, 0.55);
}

.hero-empty ha-icon { --mdc-icon-size: 52px; }

/* --- Modal dialogs ----------------------------------------------------- */

.modal-sheet {
  position: fixed;
  inset: 0;
  z-index: 22;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--dp-space-md);
  background: rgba(0, 0, 0, 0.6);
}

.modal-panel {
  display: flex;
  flex-direction: column;
  width: min(820px, 100%);
  max-height: 88vh;
  overflow: hidden;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius);
  background: var(--ha-card-background, var(--card-background-color, var(--dp-surface)));
  color: var(--dp-text);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
}

.modal-head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  padding: var(--dp-space-md) var(--dp-space-lg);
  border-bottom: 1px solid var(--dp-line);
}

.modal-head h3 {
  flex: 1;
  margin: 0;
  font-size: 17px;
}

.modal-body {
  padding: var(--dp-space-md) var(--dp-space-lg) var(--dp-space-xl);
  overflow-y: auto;
}

.modal-columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--dp-space-lg);
}

.modal-col {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  min-width: 0;
}

.modal-section {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  padding: var(--dp-space-md);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
}

.modal-section h4 {
  margin: 0;
  font-size: 13px;
  color: var(--dp-text-2);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.tire-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--dp-space-sm);
}

.tire-card {
  display: flex;
  align-items: center;
  gap: var(--dp-space-md);
  min-height: 72px;
  padding: var(--dp-space-md);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
}

.tire-card ha-icon {
  --mdc-icon-size: 28px;
  color: var(--dp-text-2);
}

.tire-card.warn {
  border-color: var(--dp-warn);
  background: color-mix(in srgb, var(--dp-warn) 16%, var(--dp-surface-2));
}

.tire-card.warn ha-icon { color: var(--dp-warn); }
.tire-label { font-size: 12px; color: var(--dp-text-2); }
.tire-value { font-size: 18px; font-weight: 700; }

/* --- Editor ------------------------------------------------------------ */

.card-editor {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  padding: var(--dp-space-sm);
}

.card-editor .editor-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.card-editor select {
  min-height: 40px;
  padding: 8px 10px;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface);
  color: var(--dp-text);
  font-family: inherit;
}

/* --- Narrow layouts ---------------------------------------------------- */

@media (max-width: 600px) {
  .vitals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .steppers { grid-template-columns: 1fr; }
  .card-root { padding: var(--dp-space-md); }
  .card-root[data-pad="none"] { padding: 0 0 var(--dp-space-sm); }
  .hero { aspect-ratio: var(--hero-aspect, 4 / 3); }
  .hero-range .big { font-size: 30px; }
  deepal-card-settings { display: block; width: 100%; }

.settings-sheet { padding: 0; align-items: stretch; }
  .settings-panel { width: 100%; max-height: 100vh; border-radius: 0; }
  .settings-body { padding-bottom: 48px; }
}

:host([narrow]) .vitals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .steppers { grid-template-columns: 1fr; }
`;

const PANEL_ICONS = {
  car: "mdi:car",
  car_electric: "mdi:car-electric",
  refresh: "mdi:refresh",
  lock: "mdi:lock",
  unlock: "mdi:lock-open-variant",
  flash: "mdi:car-light-alert",
  horn: "mdi:bullhorn",
  flash_and_honk: "mdi:car-light-alert",
  window: "mdi:window-closed-variant",
  trunk: "mdi:car-back",
  hood: "mdi:car",
  doors: "mdi:car-door",
  climate: "mdi:air-conditioner",
  charging: "mdi:battery-charging",
  battery: "mdi:car-battery",
  bolt: "mdi:lightning-bolt",
  tire: "mdi:tire",
  odometer: "mdi:counter",
  range: "mdi:map-marker-distance",
  seat_heating: "mdi:car-seat-heater",
  seat_ventilation: "mdi:car-seat-cooler",
  steering: "mdi:steering",
  cloud: "mdi:cloud-check",
  cloud_off: "mdi:cloud-off-outline",
  clock: "mdi:clock-outline",
  alert: "mdi:alert",
  fuel: "mdi:gas-station",
  schedule: "mdi:calendar-clock",
  charge_limit: "mdi:battery-lock",
  plug_ac: "mdi:ev-plug-type2",
  plug_dc: "mdi:ev-plug-ccs2",
  current_ac: "mdi:current-ac",
  current_dc: "mdi:current-dc",
  mode: "mdi:lightning-bolt",
  temperature: "mdi:thermometer",
  humidity: "mdi:water-percent",
  pm25: "mdi:blur",
  driving: "mdi:steering",
  ambience: "mdi:air-filter",
  settings: "mdi:tune-variant",
  info: "mdi:information-outline",
  close: "mdi:close",
  up: "mdi:chevron-up",
  down: "mdi:chevron-down",
  more: "mdi:chevron-down",
  speed: "mdi:speedometer",
  gear: "mdi:car-shift-pattern",
  battery_level: "mdi:battery",
  lock_state: "mdi:lock-check",
  power: "mdi:power",
};
