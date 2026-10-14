// Climate view: cabin climate control, seat heating/ventilation and the
// steering wheel. Every control hides itself when the vehicle does not
// expose its entity.

DeepalPanel.prototype._renderClimate = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  const climateId = entity("climate", "cabin");
  const climateState = climateId ? stateFor(hass, climateId) : null;
  const climateOn = climateState ? climateState.state !== "off" : false;

  const layout = PANEL_S05_LAYOUT.climate;
  const stage = `<div class="stage stage-climate">
    <img src="${assetUrl(layout.base)}" alt="">
    ${climateOn ? `<img src="${assetUrl(layout.layers.climate_on)}" alt="">` : ""}
  </div>`;

  let climateCard = "";
  if (climateId) {
    const target = climateState?.attributes?.temperature;
    const inside = formatState(hass, entity("sensor", "inside_temperature"));
    climateCard = `<div class="card">
      <h2>${escapeHtml(t("climate"))}</h2>
      <div class="temperature stepper">
        <button data-action="temp-step" data-delta="-0.5">−</button>
        <span class="value">${escapeHtml(target != null ? `${target} °C` : "—")}</span>
        <button data-action="temp-step" data-delta="0.5">+</button>
      </div>
      <div class="row actions">
        <button class="action ${climateOn ? "secondary" : ""}" data-action="climate-mode" data-mode="heat_cool">
          ${escapeHtml(t("climate_on"))}
        </button>
        <button class="action ${climateOn ? "" : "secondary"}" data-action="climate-mode" data-mode="off">
          ${escapeHtml(t("climate_off"))}
        </button>
      </div>
      ${
        inside
          ? `<div class="metric"><span class="label">${escapeHtml(t("inside_temperature"))}</span><span class="value">${escapeHtml(inside)}</span></div>`
          : ""
      }
    </div>`;
  }

  const seatControl = (key, label) => {
    const id = entity("number", key);
    if (!id) return "";
    const state = stateFor(hass, id);
    return `<div class="control">
      <span class="label">${escapeHtml(label)}</span>
      <div class="stepper">
        <button data-action="number-step" data-key="${key}" data-delta="-1">−</button>
        <span class="value">${escapeHtml(state ? state.state : "—")}</span>
        <button data-action="number-step" data-key="${key}" data-delta="1">+</button>
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
  ].join("");

  const steeringId = entity("switch", "steering_wheel_heating");
  const steeringOn = steeringId ? isOn(hass, steeringId) : false;
  const steeringControl = steeringId
    ? `<button class="action ${steeringOn ? "" : "secondary"}" data-action="toggle-switch" data-key="steering_wheel_heating">
        <ha-icon icon="${PANEL_ICONS.steering}"></ha-icon>
        ${escapeHtml(t("steering_wheel"))}: ${escapeHtml(steeringOn ? t("on") : t("off"))}
      </button>`
    : "";

  const seatsCard =
    seatControls || steeringControl
      ? `<div class="card">
          <h2>${escapeHtml(t("seats"))}</h2>
          <div class="controls-grid">${seatControls}</div>
          ${steeringControl ? `<div class="row actions">${steeringControl}</div>` : ""}
        </div>`
      : "";

  if (!climateCard && !seatsCard) {
    return `<div class="empty">${escapeHtml(t("unavailable"))}</div>`;
  }
  return `${stage}${climateCard}${seatsCard}`;
};
