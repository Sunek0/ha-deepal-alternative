// Driving view, only for the model profiles that define it (the S07): the
// driving readings the vehicle reports and the ambience block. Every metric
// hides itself when its entity is missing or unknown, so a vehicle that
// reports only part of them still renders correctly.

DeepalPanel.prototype._renderDriving = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  const metric = (labelKey, key) => {
    const id = entity("sensor", key);
    if (!id) return "";
    const value = formatState(hass, id);
    if (value === null) return "";
    return `
      <div class="metric">
        <span class="label">${escapeHtml(t(labelKey))}</span>
        <span class="value">${escapeHtml(value)}</span>
      </div>`;
  };

  const drivingMetrics = [
    metric("speed", "speed"),
    metric("gear", "gear"),
    metric("epb", "epb_status"),
    metric("vehicle_status", "vehicle_status"),
    metric("mileage_yesterday", "mileage_yesterday"),
    metric("trip_mileage", "trip_mileage"),
  ].join("");

  const ambienceMetrics = [
    metric("outside_temperature", "outside_temperature"),
    metric("inside_pm25", "inside_pm25"),
    metric("air_quality_level", "air_quality_level"),
  ].join("");

  const section = (icon, titleKey, metrics) =>
    metrics
      ? `<div class="section">
          <div class="section-head">
            <ha-icon icon="${icon}"></ha-icon>
            <span class="section-title">${escapeHtml(t(titleKey))}</span>
          </div>
          <div class="metrics">${metrics}</div>
        </div>`
      : "";

  const driving = section(PANEL_ICONS.driving, "driving", drivingMetrics);
  const ambience = section(PANEL_ICONS.ambience, "ambience", ambienceMetrics);

  if (!driving && !ambience) {
    return `<div class="empty">${escapeHtml(t("unavailable"))}</div>`;
  }
  return `${driving}${ambience}`;
};
