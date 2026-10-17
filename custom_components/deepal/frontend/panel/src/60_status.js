// Status view, built from the shared design system: the layered vehicle
// picture with its state chips and summary metrics, the control tiles, the
// tire pressures, the active health warnings and the fuel data when the
// vehicle exposes it.

DeepalPanel.prototype._renderStatus = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  const metric = (label, value, cls = "") => `
    <div class="metric ${cls}">
      <span class="label">${escapeHtml(label)}</span>
      <span class="value">${escapeHtml(value ?? "—")}</span>
    </div>`;

  // --- Vehicle: layered picture, state chips and summary metrics ---------

  const chargeStatusId = entity("sensor", "charge_status");
  const metrics = [
    metric(t("odometer"), formatState(hass, entity("sensor", "odometer"))),
    chargeStatusId
      ? metric(t("charge_status"), chargeStatusText(hass, vehicle, t))
      : metric(
          t("vehicle_status"),
          formatState(hass, entity("sensor", "vehicle_status")),
        ),
  ];

  const vehicleSection = `
    <div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.car}"></ha-icon>
        <span class="section-title">${escapeHtml(t("vehicle"))}</span>
      </div>
      ${vehicleStageHtml(hass, vehicle)}
      <div class="chips">${vehicleChipsHtml(hass, vehicle, t, { lock: this._chipsShowLock })}</div>
      <div class="metrics">${metrics.join("")}</div>
    </div>`;

  // --- Controls: one tile per available action ---------------------------

  const tile = (icon, label, value, action, key, cls = "") => `
    <button class="tile ${cls}" data-action="${action}" ${key ? `data-key="${key}"` : ""}>
      <ha-icon icon="${icon}"></ha-icon>
      <span class="tile-body">
        <span class="tile-label">${escapeHtml(label)}</span>
        ${value ? `<span class="tile-value">${escapeHtml(value)}</span>` : ""}
      </span>
    </button>`;

  const tiles = [];
  const locked = lockStateFor(hass, vehicle);
  if (locked !== null) {
    tiles.push(
      tile(
        locked ? PANEL_ICONS.unlock : PANEL_ICONS.lock,
        locked ? t("unlock_doors") : t("lock_doors"),
        locked ? t("locked") : t("unlocked"),
        "lock-toggle",
        null,
        locked ? "" : "warn",
      ),
    );
  }
  const windowsId = entity("cover", "windows");
  if (windowsId) {
    const open = stateFor(hass, windowsId)?.state === "open";
    tiles.push(
      tile(
        PANEL_ICONS.window,
        open ? t("close_windows") : t("open_windows"),
        open ? t("open") : t("closed"),
        "cover-toggle",
        "windows",
      ),
    );
  }
  const trunkId = entity("cover", "trunk");
  if (trunkId) {
    const open = stateFor(hass, trunkId)?.state === "open";
    tiles.push(
      tile(
        PANEL_ICONS.trunk,
        open ? t("close_trunk") : t("open_trunk"),
        open ? t("open") : t("closed"),
        "cover-toggle",
        "trunk",
      ),
    );
  }
  if (entity("button", "flash_lights")) {
    tiles.push(
      tile(PANEL_ICONS.flash, t("flash_lights"), null, "press", "flash_lights"),
    );
  }
  if (entity("button", "honk_horn")) {
    tiles.push(
      tile(PANEL_ICONS.horn, t("honk_horn"), null, "press", "honk_horn"),
    );
  }
  if (this._showsFlashAndHonk && entity("button", "flash_and_honk")) {
    tiles.push(
      tile(
        PANEL_ICONS.flash_and_honk,
        t("flash_and_honk"),
        null,
        "press",
        "flash_and_honk",
      ),
    );
  }

  const controlsSection = tiles.length
    ? `<div class="section">
        <div class="section-head">
          <ha-icon icon="mdi:gesture-tap-button"></ha-icon>
          <span class="section-title">${escapeHtml(t("controls"))}</span>
        </div>
        <div class="tiles">${tiles.join("")}</div>
      </div>`
    : "";

  // --- Tires: pressure tiles, highlighted while the alarm is on ----------

  const tire = (key, alarmKey, labelKey) => {
    const id = entity("sensor", key);
    if (!id) return "";
    const alarm = isOn(hass, entity("binary_sensor", alarmKey));
    const value = formatState(hass, id) || "—";
    return `
      <div class="tile static ${alarm ? "warn" : ""}">
        <ha-icon icon="${PANEL_ICONS.tire}"></ha-icon>
        <span class="tile-body">
          <span class="tile-label">${escapeHtml(t(labelKey))}</span>
          <span class="tile-value">${escapeHtml(value)}</span>
        </span>
      </div>`;
  };
  const tires = [
    tire("tire_front_left", "tire_alarm_front_left", "front_left"),
    tire("tire_front_right", "tire_alarm_front_right", "front_right"),
    tire("tire_rear_left", "tire_alarm_rear_left", "rear_left"),
    tire("tire_rear_right", "tire_alarm_rear_right", "rear_right"),
  ].join("");
  const tiresSection = tires
    ? `<div class="section">
        <div class="section-head">
          <ha-icon icon="${PANEL_ICONS.tire}"></ha-icon>
          <span class="section-title">${escapeHtml(t("tires"))}</span>
        </div>
        <div class="tiles">${tires}</div>
      </div>`
    : "";

  // --- Energy: the profile defines the block (the S05 PHEV); the vehicle
  // fills it and every metric hides itself when its entity is missing ------

  const energyMetric = (labelKey, key) => {
    const id = entity("sensor", key);
    return id ? metric(t(labelKey), formatState(hass, id)) : "";
  };
  const energyMetrics =
    vehicle.profile === PANEL_PROFILE_S05_PHEV
      ? [
          energyMetric("battery", "battery"),
          energyMetric("range", "range"),
          energyMetric("fuel", "fuel_level"),
          energyMetric("fuel_range", "fuel_range"),
          energyMetric("fuel_tank_capacity", "fuel_tank_capacity"),
        ].join("")
      : "";
  const energySection = energyMetrics
    ? `<div class="section">
        <div class="section-head">
          <ha-icon icon="${PANEL_ICONS.fuel}"></ha-icon>
          <span class="section-title">${escapeHtml(t("energy"))}</span>
        </div>
        <div class="metrics">${energyMetrics}</div>
      </div>`
    : "";

  return `${vehicleSection}${energySection}${controlsSection}${tiresSection}${warningsHtml(hass, vehicle, t)}`;
};
