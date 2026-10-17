// Charging view, built from the shared design system: battery and session
// state, the charging picture, the charge status (enum when the vehicle
// reports it), current and remaining time, the charge schedule, the charge
// limit when exposed, and the session summaries the charging sensor exposes
// as attributes.

DeepalPanel.prototype._renderCharging = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  // --- Charging state ------------------------------------------------------

  const charging = isOn(hass, entity("binary_sensor", "charging"));
  const plugged = isOn(hass, entity("binary_sensor", "charger_plugged"));
  const layout = layoutFor(vehicle)?.charging;
  const stageHtml = layout
    ? `<div class="stage stage-charging">
        <img src="${assetUrl(layout.base)}" alt="">
        ${
          plugged
            ? `<img src="${assetUrl(charging ? layout.layers.charging : layout.layers.plugged)}" alt="">`
            : ""
        }
        <span class="anim-slot" data-anim="charging_on"></span>
      </div>`
    : "";

  const metric = (label, value) => `
    <div class="metric">
      <span class="label">${escapeHtml(label)}</span>
      <span class="value">${escapeHtml(value ?? "—")}</span>
    </div>`;

  const acCurrent = entity("sensor", "ac_charge_current");
  const dcCurrent = entity("sensor", "dc_charge_current");
  const currentMetric =
    acCurrent || dcCurrent
      ? `${acCurrent ? metric(t("current_ac"), formatState(hass, acCurrent)) : ""}${
          dcCurrent ? metric(t("current_dc"), formatState(hass, dcCurrent)) : ""
        }`
      : metric(
          t("charge_current"),
          formatState(hass, entity("sensor", "charge_current")),
        );

  const remaining =
    formatState(hass, entity("sensor", "remaining_time_formatted")) ||
    formatState(hass, entity("sensor", "remaining_time"));

  const mode = formatState(hass, entity("sensor", "charge_mode"));

  const metrics = [
    metric(t("battery"), formatState(hass, entity("sensor", "battery"))),
    metric(t("plugged"), plugged ? t("plugged") : t("not_plugged")),
    mode ? metric(t("charge_mode"), mode) : "",
    currentMetric,
    metric(t("remaining_time"), remaining),
  ].join("");

  const chargingSection = `
    <div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.charging}"></ha-icon>
        <span class="section-title">${escapeHtml(t("tab_charging"))}</span>
      </div>
      ${stageHtml}
      <div class="metrics">${metrics}</div>
    </div>`;

  // --- Charge schedule (switch and start/end times) ------------------------

  const scheduleId = entity("switch", "charge_schedule");
  const scheduleStartId = entity("time", "schedule_start");
  const scheduleEndId = entity("time", "schedule_end");
  const scheduleOn = scheduleId ? isOn(hass, scheduleId) : false;
  const scheduleTile = scheduleId
    ? `<button class="tile ${scheduleOn ? "on" : ""}" data-action="toggle-switch" data-key="charge_schedule">
        <ha-icon icon="${PANEL_ICONS.schedule}"></ha-icon>
        <span class="tile-body">
          <span class="tile-label">${escapeHtml(t("charge_schedule"))}</span>
          <span class="tile-value">${escapeHtml(scheduleOn ? t("on") : t("off"))}</span>
        </span>
      </button>`
    : "";
  const timeField = (id, key, labelKey) => {
    const value = formatTime(hass, id);
    if (value === null) return "";
    return `
      <div class="field">
        <label for="deepal-${key}">${escapeHtml(t(labelKey))}</label>
        <input id="deepal-${key}" type="time" value="${escapeHtml(value)}"
               data-action="time-set" data-key="${key}">
      </div>`;
  };
  const scheduleFields = `${timeField(scheduleStartId, "schedule_start", "charge_schedule_start")}${timeField(scheduleEndId, "schedule_end", "charge_schedule_end")}`;
  const scheduleSection =
    scheduleTile || scheduleFields
      ? `<div class="section">
          <div class="section-head">
            <ha-icon icon="${PANEL_ICONS.schedule}"></ha-icon>
            <span class="section-title">${escapeHtml(t("charge_schedule"))}</span>
          </div>
          ${scheduleFields ? `<div class="tiles">${scheduleFields}</div>` : ""}
          ${scheduleTile ? `<div class="tiles">${scheduleTile}</div>` : ""}
        </div>`
      : "";

  // --- Charge limit (only on vehicles that expose it) ----------------------

  const limitId = entity("number", "charge_limit");
  const limitState = limitId ? stateFor(hass, limitId) : null;
  const limitSection = limitState
    ? `<div class="section">
        <div class="section-head">
          <ha-icon icon="${PANEL_ICONS.charge_limit}"></ha-icon>
          <span class="section-title">${escapeHtml(t("charge_limit"))}</span>
        </div>
        <div class="control">
          <div class="stepper large">
            <button data-action="number-step" data-key="charge_limit" data-delta="-1" aria-label="-">&minus;</button>
            <span class="value">${escapeHtml(`${limitState.state} %`)}</span>
            <button data-action="number-step" data-key="charge_limit" data-delta="1" aria-label="+">+</button>
          </div>
        </div>
      </div>`
    : "";

  // --- Tracked sessions (current and last) ---------------------------------

  const chargingId = entity("binary_sensor", "charging");
  const current = chargingId
    ? attributeFor(hass, chargingId, "current_charge")
    : null;
  const last = chargingId ? attributeFor(hass, chargingId, "last_charge") : null;
  const session = (labelKey, data) => {
    if (!data) return "";
    const level = (value) => (value == null ? null : `${value} %`);
    const range = (value) => (value == null ? null : `${value} km`);
    const rows = [
      data.start ? [t("session_started"), formatDateTime(this._language, data.start)] : null,
      data.end ? [t("session_ended"), formatDateTime(this._language, data.end)] : null,
      data.start_level != null ? [t("session_start_level"), level(data.start_level)] : null,
      data.end_level != null ? [t("session_end_level"), level(data.end_level)] : null,
      data.start_range != null ? [t("session_start_range"), range(data.start_range)] : null,
      data.end_range != null ? [t("session_end_range"), range(data.end_range)] : null,
    ].filter(Boolean);
    if (!rows.length) return "";
    return `
      <div class="section">
        <div class="section-head">
          <ha-icon icon="${PANEL_ICONS.clock}"></ha-icon>
          <span class="section-title">${escapeHtml(t(labelKey))}</span>
        </div>
        <div class="session">
          ${rows
            .map(
              ([label, value]) =>
                `<div class="metric"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(value)}</span></div>`,
            )
            .join("")}
        </div>
      </div>`;
  };

  return `${chargingSection}${session("charge_session_last", last)}${scheduleSection}${limitSection}${session("charge_session_current", current)}`;
};
