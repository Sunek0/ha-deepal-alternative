// Status view: the layered S05 picture (or the vehicle image fallback), the
// state chips, the tire pressures and the essential controls.

DeepalPanel.prototype._renderStatus = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  const metric = (labelKey, value) => `
    <div class="card"><div class="metric">
      <span class="label">${escapeHtml(t(labelKey))}</span>
      <span class="value">${escapeHtml(value ?? "—")}</span>
    </div></div>`;

  const metrics = [
    metric("battery", formatState(hass, entity("sensor", "battery"))),
    metric("range", formatState(hass, entity("sensor", "range"))),
    metric("odometer", formatState(hass, entity("sensor", "odometer"))),
    metric(
      "charging",
      isOn(hass, entity("binary_sensor", "charging")) ? t("on") : t("off"),
    ),
    metric(
      "plugged",
      isOn(hass, entity("binary_sensor", "charger_plugged"))
        ? t("plugged")
        : t("not_plugged"),
    ),
  ];

  const chips = vehicleChipsHtml(hass, vehicle, t);

  const tire = (key, alarmKey, labelKey) => {
    const id = entity("sensor", key);
    if (!id) return "";
    const alarm = isOn(hass, entity("binary_sensor", alarmKey));
    const value = formatState(hass, id) || "—";
    return `<div class="tire ${alarm ? "alarm" : ""}">
      <span>${escapeHtml(t(labelKey))}</span>
      <span><ha-icon icon="${PANEL_ICONS.tire}"></ha-icon> ${escapeHtml(value)}</span>
    </div>`;
  };
  const tires = [
    tire("tire_front_left", "tire_alarm_front_left", "front_left"),
    tire("tire_front_right", "tire_alarm_front_right", "front_right"),
    tire("tire_rear_left", "tire_alarm_rear_left", "rear_left"),
    tire("tire_rear_right", "tire_alarm_rear_right", "rear_right"),
  ].join("");

  const actions = [];
  const lockId = entity("lock", "doors");
  const lockState = lockId ? stateFor(hass, lockId) : null;
  const locked = lockState ? lockState.state === "locked" : null;
  if (lockId && locked !== null) {
    actions.push(
      `<button class="action secondary" data-action="lock-toggle">
        <ha-icon icon="${locked ? PANEL_ICONS.unlock : PANEL_ICONS.lock}"></ha-icon>
        ${escapeHtml(locked ? t("unlock_doors") : t("lock_doors"))}
      </button>`,
    );
  }
  const windowsId = entity("cover", "windows");
  if (windowsId) {
    const open = stateFor(hass, windowsId)?.state === "open";
    actions.push(
      `<button class="action secondary" data-action="cover-toggle" data-key="windows">
        <ha-icon icon="${PANEL_ICONS.window}"></ha-icon>
        ${escapeHtml(open ? t("close_windows") : t("open_windows"))}
      </button>`,
    );
  }
  const trunkId = entity("cover", "trunk");
  if (trunkId) {
    const open = stateFor(hass, trunkId)?.state === "open";
    actions.push(
      `<button class="action secondary" data-action="cover-toggle" data-key="trunk">
        <ha-icon icon="${PANEL_ICONS.trunk}"></ha-icon>
        ${escapeHtml(open ? t("close_trunk") : t("open_trunk"))}
      </button>`,
    );
  }
  if (entity("button", "flash_lights")) {
    actions.push(
      `<button class="action secondary" data-action="press" data-key="flash_lights">
        <ha-icon icon="${PANEL_ICONS.flash}"></ha-icon>${escapeHtml(t("flash_lights"))}
      </button>`,
    );
  }
  if (entity("button", "honk_horn")) {
    actions.push(
      `<button class="action secondary" data-action="press" data-key="honk_horn">
        <ha-icon icon="${PANEL_ICONS.horn}"></ha-icon>${escapeHtml(t("honk_horn"))}
      </button>`,
    );
  }

  return `
    ${vehicleStageHtml(hass, vehicle)}
    <div class="chips">${chips}</div>
    <div class="grid">${metrics.join("")}</div>
    ${
      tires
        ? `<div class="card"><h2>${escapeHtml(t("tires"))}</h2><div class="tires">${tires}</div></div>`
        : ""
    }
    ${actions.length ? `<div class="actions">${actions.join("")}</div>` : ""}`;
};

