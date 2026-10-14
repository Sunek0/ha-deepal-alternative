// Charging view: battery and session state, the charging picture and the
// session summaries the charging sensor exposes as attributes.

DeepalPanel.prototype._renderCharging = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  const charging = isOn(hass, entity("binary_sensor", "charging"));
  const plugged = isOn(hass, entity("binary_sensor", "charger_plugged"));
  const layout = PANEL_S05_LAYOUT.charging;
  const stage = `<div class="stage stage-charging">
    <img src="${assetUrl(layout.base)}" alt="">
    ${
      plugged
        ? `<img src="${assetUrl(charging ? layout.layers.charging : layout.layers.plugged)}" alt="">`
        : ""
    }
  </div>`;

  const metric = (labelKey, value) => `
    <div class="card"><div class="metric">
      <span class="label">${escapeHtml(t(labelKey))}</span>
      <span class="value">${escapeHtml(value ?? "—")}</span>
    </div></div>`;
  const metrics = [
    metric("battery", formatState(hass, entity("sensor", "battery"))),
    metric("charging", charging ? t("on") : t("off")),
    metric("plugged", plugged ? t("plugged") : t("not_plugged")),
    metric(
      "charge_current",
      formatState(hass, entity("sensor", "charge_current")),
    ),
    metric(
      "remaining_time",
      formatState(hass, entity("sensor", "remaining_time")),
    ),
  ];

  const chargingId = entity("binary_sensor", "charging");
  const current = chargingId
    ? attributeFor(hass, chargingId, "current_charge")
    : null;
  const last = chargingId ? attributeFor(hass, chargingId, "last_charge") : null;
  const session = (labelKey, data) => {
    if (!data) return "";
    const level = (value) => (value == null ? "—" : `${value} %`);
    const rows = [];
    if (data.start) {
      rows.push([
        t("session_started"),
        formatDateTime(this._language, data.start),
      ]);
    }
    if (data.end) {
      rows.push([t("session_ended"), formatDateTime(this._language, data.end)]);
    }
    if (data.start_level != null) {
      rows.push([t("session_start_level"), level(data.start_level)]);
    }
    if (data.end_level != null) {
      rows.push([t("session_end_level"), level(data.end_level)]);
    }
    if (!rows.length) return "";
    return `<div class="card"><h2>${escapeHtml(t(labelKey))}</h2><div class="session">
      ${rows
        .map(
          ([label, value]) =>
            `<div class="metric"><span class="label">${escapeHtml(label)}</span><span class="value">${escapeHtml(value)}</span></div>`,
        )
        .join("")}
    </div></div>`;
  };

  return `${stage}
    <div class="grid">${metrics.join("")}</div>
    ${session("charge_session_current", current)}
    ${session("charge_session_last", last)}`;
};
