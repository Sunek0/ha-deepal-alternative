// Climate view, built from the shared design system: cabin climate (target
// temperature and on/off) and the cabin humidity when available. Seat and
// steering-wheel controls live in the seats section. Every control hides
// itself when the vehicle does not expose its entity.

DeepalCardBase.prototype._renderClimate = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  // --- Cabin climate ------------------------------------------------------

  const climateId = entity("climate", "cabin");
  const climateState = climateId ? stateFor(hass, climateId) : null;
  const climateOn = climateState ? climateState.state !== "off" : false;

  let climateSection = "";
  if (climateId) {
    const humidity = formatState(hass, entity("sensor", "cabin_humidity"));
    const layout = layoutFor(vehicle)?.climate;
    const stageHtml = layout
      ? `<div class="stage stage-climate">
          <img src="${assetUrl(layout.base, vehicle)}" alt="">
          ${climateOn ? `<img src="${assetUrl(layout.layers.climate_on, vehicle)}" alt="">` : ""}
          <span class="anim-slot" data-anim="climate_on"></span>
        </div>`
      : "";
    climateSection = `
      <div class="section">
        <div class="section-head">
          <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon>
          <span class="section-title">${escapeHtml(t("climate"))}</span>
        </div>
        ${stageHtml}
        ${
          humidity
            ? `<div class="metrics climate-metrics">
                <div class="metric">
                  <span class="label">${escapeHtml(t("cabin_humidity"))}</span>
                  <span class="value">${escapeHtml(humidity)}</span>
                </div>
              </div>`
            : ""
        }
        ${climateWheelHtml(this, vehicle)}
        <div class="segmented">
          <button class="segment" aria-pressed="${climateOn}" data-action="climate-mode" data-mode="heat_cool">
            <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon>
            <span>${escapeHtml(t("climate_on"))}</span>
          </button>
          <button class="segment" aria-pressed="${!climateOn}" data-action="climate-mode" data-mode="off">
            <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon>
            <span>${escapeHtml(t("climate_off"))}</span>
          </button>
        </div>
      </div>`;
  }

  return climateSection;
};

function climateWheelHtml(card, vehicle) {
  const climateId = entityFor(vehicle, "climate", "cabin");
  const state = stateFor(card._hass, climateId);
  if (!state) return "";
  const attributes = state.attributes || {};
  const current = Number(attributes.temperature);
  if (!Number.isFinite(current)) return "";
  const step =
    Number(attributes.target_temp_step ?? attributes.step ?? 0.5) || 0.5;
  const min = Number(attributes.min_temp ?? 16);
  const max = Number(attributes.max_temp ?? 32);
  const values = [
    current - step * 2,
    current - step,
    current,
    current + step,
    current + step * 2,
  ];
  const cells = values.map((value, index) => {
    const rounded = Math.round(value * 10) / 10;
    if (index === 2) {
      return `<div class="temp-wheel-current" aria-live="polite"><span class="value">${rounded.toFixed(
        1,
      )}<small>°C</small></span></div>`;
    }
    if (value < min - 0.001 || value > max + 0.001) {
      return `<span class="temp-wheel-slot" aria-hidden="true"></span>`;
    }
    const distance = index === 1 || index === 3 ? "near" : "far";
    return `<button class="temp-wheel-step ${distance}" data-action="temp-set" data-temp="${rounded}" aria-label="${escapeHtml(
      rounded.toFixed(1),
    )} °C">${rounded.toFixed(1)}</button>`;
  });
  return `<div class="temp-wheel" role="group" aria-label="${escapeHtml(
    card._t("target_temperature"),
  )}">${cells.join("")}</div>`;
}
