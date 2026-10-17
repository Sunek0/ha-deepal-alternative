// Climate view, built from the shared design system: cabin climate (target
// temperature, on/off and inside temperature), seat heating and ventilation
// for the positions the vehicle exposes, steering wheel heating and the
// ambient readings when available. Every control hides itself when the
// vehicle does not expose its entity.

DeepalPanel.prototype._renderClimate = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  // --- Cabin climate ------------------------------------------------------

  const climateId = entity("climate", "cabin");
  const climateState = climateId ? stateFor(hass, climateId) : null;
  const climateOn = climateState ? climateState.state !== "off" : false;

  let climateSection = "";
  if (climateId) {
    const target = climateState?.attributes?.temperature;
    const inside = formatState(hass, entity("sensor", "inside_temperature"));
    const humidity = formatState(hass, entity("sensor", "cabin_humidity"));
    const layout = layoutFor(vehicle)?.climate;
    const stageHtml = layout
      ? `<div class="stage stage-climate">
          <img src="${assetUrl(layout.base)}" alt="">
          ${climateOn ? `<img src="${assetUrl(layout.layers.climate_on)}" alt="">` : ""}
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
        <div class="center">
          <div class="stepper large">
            <button data-action="temp-step" data-delta="-0.5" aria-label="-">&minus;</button>
            <span class="value">${escapeHtml(target != null ? `${target} °C` : "—")}</span>
            <button data-action="temp-step" data-delta="0.5" aria-label="+">+</button>
          </div>
        </div>
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
        ${
          inside || humidity
            ? `<div class="metrics">
                ${
                  inside
                    ? `<div class="metric">
                        <span class="label">${escapeHtml(t("inside_temperature"))}</span>
                        <span class="value">${escapeHtml(inside)}</span>
                      </div>`
                    : ""
                }
                ${
                  humidity
                    ? `<div class="metric">
                        <span class="label">${escapeHtml(t("cabin_humidity"))}</span>
                        <span class="value">${escapeHtml(humidity)}</span>
                      </div>`
                    : ""
                }
              </div>`
            : ""
        }
      </div>`;
  }

  // --- Seats (front always, rear when exposed) and steering wheel ---------

  const seatControl = (key, label) => {
    const id = entity("number", key);
    if (!id) return "";
    const state = stateFor(hass, id);
    return `
      <div class="control">
        <span class="label">${escapeHtml(label)}</span>
        <div class="stepper">
          <button data-action="number-step" data-key="${key}" data-delta="-1" aria-label="-">&minus;</button>
          <span class="value">${escapeHtml(state ? state.state : "—")}</span>
          <button data-action="number-step" data-key="${key}" data-delta="1" aria-label="+">+</button>
        </div>
      </div>`;
  };
  const seatControls = [
    seatControl(
      "seat_heating_front_left",
      `${t("seat_heating")} · ${t("front_left")}`,
    ),
    seatControl(
      "seat_heating_front_right",
      `${t("seat_heating")} · ${t("front_right")}`,
    ),
    seatControl(
      "seat_ventilation_front_left",
      `${t("seat_ventilation")} · ${t("front_left")}`,
    ),
    seatControl(
      "seat_ventilation_front_right",
      `${t("seat_ventilation")} · ${t("front_right")}`,
    ),
    seatControl(
      "seat_heating_rear_left",
      `${t("seat_heating")} · ${t("rear_left")}`,
    ),
    seatControl(
      "seat_heating_rear_right",
      `${t("seat_heating")} · ${t("rear_right")}`,
    ),
    seatControl(
      "seat_ventilation_rear_left",
      `${t("seat_ventilation")} · ${t("rear_left")}`,
    ),
    seatControl(
      "seat_ventilation_rear_right",
      `${t("seat_ventilation")} · ${t("rear_right")}`,
    ),
  ].join("");

  const steeringId = entity("switch", "steering_wheel_heating");
  const steeringOn = steeringId ? isOn(hass, steeringId) : false;
  const steeringTile = steeringId
    ? `<button class="tile ${steeringOn ? "on" : ""}" data-action="toggle-switch" data-key="steering_wheel_heating">
        <ha-icon icon="${PANEL_ICONS.steering}"></ha-icon>
        <span class="tile-body">
          <span class="tile-label">${escapeHtml(t("steering_wheel"))}</span>
          <span class="tile-value">${escapeHtml(steeringOn ? t("on") : t("off"))}</span>
        </span>
      </button>`
    : "";

  const seatsLayout = layoutFor(vehicle)?.seats;
  const seatsStage = seatsLayout
    ? `<div class="stage stage-seats">
        <img src="${assetUrl(seatsLayout.base)}" alt="">
        <span class="anim-slot" data-anim="seat_vent"></span>
      </div>`
    : "";

  const seatsSection =
    seatControls || steeringTile
      ? `<div class="section">
          <div class="section-head">
            <ha-icon icon="${PANEL_ICONS.seat_heating}"></ha-icon>
            <span class="section-title">${escapeHtml(t("seats"))}</span>
          </div>
          ${seatsStage}
          ${seatControls ? `<div class="steppers">${seatControls}</div>` : ""}
          ${steeringTile ? `<div class="tiles">${steeringTile}</div>` : ""}
        </div>`
      : "";

  // --- Ambience readings live inside the climate section (humidity next to
  // the inside temperature); no separate section.

  if (!climateSection && !seatsSection) {
    return `<div class="empty">${escapeHtml(t("unavailable"))}</div>`;
  }
  return `${climateSection}${seatsSection}`;
};
