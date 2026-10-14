// Panel styles. Everything is scoped to the shadow root and built on Home
// Assistant theme variables so the panel follows light and dark themes.

const PANEL_CSS = `
:host {
  display: block;
  height: 100%;
  background: var(--primary-background-color);
  color: var(--primary-text-color);
  font-family: var(--ha-font-family-body, Roboto, sans-serif);
}
.panel {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  max-width: 900px;
  margin: 0 auto;
  padding: 12px 16px 32px;
  overflow-y: auto;
}
.header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.header h1 {
  font-size: 20px;
  font-weight: 600;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.spacer { flex: 1; }
.vehicle-select {
  display: flex;
  align-items: center;
  gap: 6px;
}
.vehicle-select select {
  background: var(--card-background-color);
  color: var(--primary-text-color);
  border: 1px solid var(--divider-color);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 14px;
}
.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: var(--card-background-color);
  color: var(--primary-text-color);
  cursor: pointer;
  touch-action: manipulation;
}
.icon-button:hover { background: var(--secondary-background-color); }
.tabs {
  display: flex;
  border-bottom: 1px solid var(--divider-color);
}
.tab {
  flex: 1 1 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: none;
  background: none;
  color: var(--secondary-text-color);
  font-size: 14px;
  padding: 10px 8px;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  touch-action: manipulation;
}
.tab[aria-selected="true"] {
  color: var(--primary-color);
  border-bottom-color: var(--primary-color);
}
.view { display: flex; flex-direction: column; gap: 12px; }
.card {
  background: var(--card-background-color);
  border-radius: var(--ha-card-border-radius, 12px);
  box-shadow: var(--ha-card-box-shadow, none);
  border: 1px solid var(--divider-color);
  padding: 12px 16px;
}
.card h2 {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
  color: var(--secondary-text-color);
}
.card-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 16px;
  background: var(--card-background-color);
  border-radius: var(--ha-card-border-radius, 12px);
  color: var(--primary-text-color);
}
.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
}
.stage {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: var(--ha-card-border-radius, 12px);
}
.stage-status { aspect-ratio: 1 / 1; }
.stage-climate { aspect-ratio: 1125 / 642; }
.stage-charging { aspect-ratio: 3 / 2; }
.stage img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 13px;
  background: var(--secondary-background-color);
  color: var(--primary-text-color);
}
.chip.on { background: var(--primary-color); color: var(--text-primary-color, white); }
.chip.warn { background: var(--error-color); color: var(--text-primary-color, white); }
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.metric .label { font-size: 12px; color: var(--secondary-text-color); }
.metric .value { font-size: 18px; font-weight: 600; }
.tires {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.tire {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--secondary-background-color);
}
.tire.alarm { background: var(--error-color); color: var(--text-primary-color, white); }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  border-radius: 10px;
  background: var(--primary-color);
  color: var(--text-primary-color, white);
  padding: 8px 12px;
  font-size: 14px;
  cursor: pointer;
  touch-action: manipulation;
}
.action.secondary {
  background: var(--secondary-background-color);
  color: var(--primary-text-color);
}
.action:disabled { opacity: 0.5; cursor: default; }
.stepper {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.stepper button {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 1px solid var(--divider-color);
  background: var(--card-background-color);
  color: var(--primary-text-color);
  cursor: pointer;
}
.controls-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.control {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.control .row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.temperature {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: center;
}
.temperature .value { font-size: 28px; font-weight: 600; }
.empty {
  padding: 24px;
  text-align: center;
  color: var(--secondary-text-color);
}
.error {
  background: var(--error-color);
  color: var(--text-primary-color, white);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 14px;
}
.session {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.session .metric .value { font-size: 15px; }
.row { display: flex; align-items: center; gap: 8px; }
.row.actions { justify-content: center; flex-wrap: wrap; }
.action-chip { border: none; cursor: pointer; }
.vehicle-photo {
  display: block;
  width: 100%;
  border-radius: var(--ha-card-border-radius, 12px);
}
.stepper .value { min-width: 28px; text-align: center; font-weight: 600; }
@media (max-width: 600px) {
  .panel { padding: 8px 8px 24px; }
  .grid, .controls-grid { grid-template-columns: 1fr; }
  .tab { padding: 8px; font-size: 13px; }
}
:host([narrow]) .grid,
:host([narrow]) .controls-grid {
  grid-template-columns: 1fr;
}
`;

const PANEL_ICONS = {
  refresh: "mdi:refresh",
  lock: "mdi:lock",
  unlock: "mdi:lock-open-variant",
  flash: "mdi:car-light-alert",
  horn: "mdi:bullhorn",
  window: "mdi:window-closed-variant",
  trunk: "mdi:car-back",
  car: "mdi:car",
  climate: "mdi:air-conditioner",
  charging: "mdi:battery-charging",
  battery: "mdi:car-battery",
  tire: "mdi:tire",
  seat_heating: "mdi:car-seat-heater",
  seat_ventilation: "mdi:car-seat-cooler",
  steering: "mdi:steering",
};
