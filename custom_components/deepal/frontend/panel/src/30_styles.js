// Panel styles: one design-system layer shared by the sidebar panel and both
// dashboard cards. Everything is scoped to the shadow root and built on Home
// Assistant theme variables, so it follows light and dark themes.
//
// Views only compose these components; they must not add their own styles:
//   .app-bar   application bar (title, vehicle selector, actions)
//   .vitals    persistent glance strip (battery, range, lock, freshness)
//   .segmented tab control (status / climate / charging)
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
  height: 100%;
  background: var(--primary-background-color);
  color: var(--dp-text);
  font-family: var(--ha-font-family-body, Roboto, sans-serif);
}

.panel {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  height: 100%;
  max-width: 900px;
  margin: 0 auto;
  padding: var(--dp-space-md) var(--dp-space-lg) 32px;
  overflow-y: auto;
}

:focus-visible {
  outline: 2px solid var(--dp-accent);
  outline-offset: 2px;
}

/* --- App bar ----------------------------------------------------------- */

.app-bar {
  position: sticky;
  top: calc(var(--dp-space-md) * -1);
  z-index: 2;
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  flex-wrap: wrap;
  padding: var(--dp-space-sm) 0;
  background: var(--primary-background-color);
}

.app-title {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  font-size: 20px;
  font-weight: 600;
  margin: 0;
}

.app-title .model {
  font-size: 13px;
  font-weight: 400;
  color: var(--dp-text-2);
}

.spacer { flex: 1; }

.vehicle-select {
  display: flex;
  align-items: center;
  gap: 6px;
}

.vehicle-select select {
  background: var(--dp-surface);
  color: var(--dp-text);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  padding: 6px 8px;
  font-size: 14px;
}

.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--dp-touch);
  height: var(--dp-touch);
  border: none;
  border-radius: 50%;
  background: var(--dp-surface);
  color: var(--dp-text);
  cursor: pointer;
  touch-action: manipulation;
}

.icon-button:hover { background: var(--dp-surface-2); }

/* --- Vitals strip ------------------------------------------------------ */

.vitals {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(104px, 1fr));
  gap: var(--dp-space-sm);
}

.vital {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  min-height: var(--dp-touch);
  padding: var(--dp-space-sm) 10px;
  background: var(--dp-surface);
  border-radius: var(--dp-radius-sm);
  overflow: hidden;
}

.vital ha-icon { color: var(--dp-text-2); --mdc-icon-size: 20px; }
.vital.on ha-icon { color: var(--dp-accent); }
.vital.warn { background: var(--dp-warn); color: var(--dp-on-text); }
.vital.warn ha-icon { color: var(--dp-on-text); }

.vital-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.vital-label {
  font-size: 11px;
  color: var(--dp-text-2);
  white-space: nowrap;
}

.vital.warn .vital-label { color: var(--dp-on-text); }

.vital-value {
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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

.view {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
}

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

/* --- Dashboard cards --------------------------------------------------- */

.card-root {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  padding: var(--dp-space-md) var(--dp-space-lg);
  background: var(--dp-surface);
  border-radius: var(--dp-radius);
  color: var(--dp-text);
}

.card-title {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  font-size: 16px;
  font-weight: 600;
}

.card-title .model {
  font-size: 13px;
  font-weight: 400;
  color: var(--dp-text-2);
}

/* --- Narrow layouts ---------------------------------------------------- */

@media (max-width: 600px) {
  .panel { padding: var(--dp-space-sm) var(--dp-space-sm) var(--dp-space-xl); }
  .app-title { font-size: 18px; }
  .vitals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .steppers { grid-template-columns: 1fr; }
  .segment span { display: none; }
  .segment ha-icon { --mdc-icon-size: 22px; }
  .card-root { padding: var(--dp-space-md); }
}

:host([narrow]) .panel { padding: var(--dp-space-sm) var(--dp-space-sm) var(--dp-space-xl); }
:host([narrow]) .vitals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .steppers { grid-template-columns: 1fr; }
:host([narrow]) .segment span { display: none; }
:host([narrow]) .segment ha-icon { --mdc-icon-size: 22px; }
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
};
