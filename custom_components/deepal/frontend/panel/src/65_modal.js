// The vehicle dialog: one sheet with the climate, seats and tyres tabs. The
// card opens it from the climate, seats and tyres actions; the tab order is
// fixed and only tabs whose data or artwork exists are offered.

const VEHICLE_MODAL_TABS = ["climate", "seats", "tyres"];
const VEHICLE_SEAT_KEYS = [
  "seat_heating_front_left",
  "seat_ventilation_front_left",
  "seat_heating_front_right",
  "seat_ventilation_front_right",
];
const VEHICLE_TIRE_KEYS = [
  "tire_front_left",
  "tire_front_right",
  "tire_rear_left",
  "tire_rear_right",
];
const VEHICLE_TAB_ICONS = {
  climate: "climate",
  seats: "seat",
  tyres: "tire",
};
const VEHICLE_TAB_LABELS = {
  climate: "climate",
  seats: "seats",
  tyres: "tires",
};

function seatControlsAvailable(card, vehicle) {
  return (
    VEHICLE_SEAT_KEYS.some((key) => entityFor(vehicle, "number", key)) ||
    Boolean(entityFor(vehicle, "switch", "steering_wheel_heating"))
  );
}

function vehicleTabAvailable(card, vehicle, tab) {
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  if (tab === "climate") return Boolean(entity("climate", "cabin"));
  if (tab === "seats") return seatControlsAvailable(card, vehicle);
  if (tab === "tyres") {
    return VEHICLE_TIRE_KEYS.some((key) => entity("sensor", key));
  }
  return false;
}

function vehicleTabs(card, vehicle) {
  return VEHICLE_MODAL_TABS.filter((tab) =>
    vehicleTabAvailable(card, vehicle, tab),
  );
}

function vehicleTabsHtml(card, vehicle, active) {
  return `<div class="segmented modal-tabs" role="tablist">${vehicleTabs(
    card,
    vehicle,
  )
    .map(
      (tab) => `<button class="segment" role="tab" aria-selected="${
        tab === active
      }" data-action="modal-tab" data-tab="${tab}">
        <ha-icon icon="${PANEL_ICONS[VEHICLE_TAB_ICONS[tab]]}"></ha-icon>
        <span>${escapeHtml(card._t(VEHICLE_TAB_LABELS[tab]))}</span>
      </button>`,
    )
    .join("")}</div>`;
}

function climateStageHtml(card, vehicle) {
  const layout = layoutFor(vehicle)?.climate;
  if (!layout) return "";
  const climateId = entityFor(vehicle, "climate", "cabin");
  const climateState = stateFor(card._hass, climateId);
  const on = Boolean(climateState && climateState.state !== "off");
  const air = layout.layers && layout.layers.climate_on;
  return `<div class="stage stage-climate">
    <img src="${assetUrl(layout.base, vehicle)}" alt="">
    ${on && air ? `<img class="air" src="${assetUrl(air, vehicle)}" alt="">` : ""}
    <span class="anim-slot" data-anim="climate_on"></span>
  </div>`;
}

function climateTabHtml(card, vehicle) {
  const hass = card._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const climateId = entity("climate", "cabin");
  const climateState = stateFor(hass, climateId);
  const on = Boolean(climateState && climateState.state !== "off");
  const humidity = formatState(hass, entity("sensor", "cabin_humidity"));
  const metrics = [
    humidity ? card._metric(card._t("cabin_humidity"), humidity) : "",
  ].filter(Boolean);
  return `${climateStageHtml(card, vehicle)}
    <div class="modal-section">
      ${
        metrics.length
          ? `<div class="metrics climate-metrics">${metrics.join("")}</div>`
          : ""
      }
      ${climateWheelHtml(card, vehicle)}
      <div class="segmented">
        <button class="segment" aria-pressed="${on}" data-action="climate-mode" data-mode="heat_cool">
          <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon>
          <span>${escapeHtml(card._t("climate_on"))}</span>
        </button>
        <button class="segment" aria-pressed="${!on}" data-action="climate-mode" data-mode="off">
          <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon>
          <span>${escapeHtml(card._t("climate_off"))}</span>
        </button>
      </div>
    </div>`;
}

function seatLevel(card, vehicle, key) {
  const id = entityFor(vehicle, "number", key);
  if (!id) return 0;
  const state = stateFor(card._hass, id);
  const value = state ? Number(state.state) : 0;
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(3, Math.round(value)));
}

function seatSpotHtml(card, vehicle, spot) {
  const steering = spot.key === "steering_wheel_heating";
  const entityId = steering
    ? entityFor(vehicle, "switch", "steering_wheel_heating")
    : entityFor(vehicle, "number", spot.key);
  if (!entityId) return "";
  const level = steering
    ? isOn(card._hass, entityId)
      ? 1
      : 0
    : seatLevel(card, vehicle, spot.key);
  const active = level > 0;
  const position = spot.key.includes("front_left")
    ? "front_left"
    : spot.key.includes("front_right")
      ? "front_right"
      : "";
  const label = steering
    ? card._t("steering_wheel")
    : `${card._t(
        spot.key.includes("heating") ? "seat_heating" : "seat_ventilation",
      )} · ${card._t(position)}`;
  const bars = steering
    ? ""
    : `<span class="seat-level" aria-hidden="true">${[1, 2, 3]
        .map((index) => `<i class="${index <= level ? "on" : ""}"></i>`)
        .join("")}</span>`;
  const className = steering
    ? "steer"
    : spot.key.includes("heating")
      ? "hot"
      : "cool";
  return `<button class="seat-spot ${className} ${active ? "on" : ""}"
    style="left:${spot.x}%;top:${spot.y}%"
    data-action="${steering ? "toggle-switch" : "seat-cycle"}"
    data-key="${escapeHtml(spot.key)}"
    aria-label="${escapeHtml(label)}"
    aria-pressed="${active}"
    title="${escapeHtml(label)}">
    <ha-icon icon="${PANEL_ICONS[spot.icon]}"></ha-icon>
    ${bars}
  </button>`;
}

function seatFallbackBodyHtml(card, vehicle) {
  const controls = [
    ["seat_heating_front_left", `${card._t("seat_heating")} · ${card._t("front_left")}`],
    ["seat_heating_front_right", `${card._t("seat_heating")} · ${card._t("front_right")}`],
    ["seat_ventilation_front_left", `${card._t("seat_ventilation")} · ${card._t("front_left")}`],
    ["seat_ventilation_front_right", `${card._t("seat_ventilation")} · ${card._t("front_right")}`],
  ]
    .map(([key, label]) => card._seatControlHtml(vehicle, key, label))
    .filter(Boolean);
  const steeringId = entityFor(vehicle, "switch", "steering_wheel_heating");
  const steeringOn = isOn(card._hass, steeringId);
  const steering = steeringId
    ? `<button class="tile ${steeringOn ? "on" : ""}" data-action="toggle-switch" data-key="steering_wheel_heating">
        <ha-icon icon="${PANEL_ICONS.steering}"></ha-icon>
        <span class="tile-body">
          <span class="tile-label">${escapeHtml(card._t("steering_wheel"))}</span>
          <span class="tile-value">${escapeHtml(
            card._t(steeringOn ? "on" : "off"),
          )}</span>
        </span>
      </button>`
    : "";
  return `${
    controls.length ? `<div class="steppers">${controls.join("")}</div>` : ""
  }${steering ? `<div class="tiles">${steering}</div>` : ""}`;
}

function seatMapLayout(vehicle) {
  const layout = layoutFor(vehicle)?.seats;
  if (
    !layout ||
    !layout.base ||
    !layout.crop ||
    !Array.isArray(layout.spots) ||
    !layout.spots.length
  ) {
    return null;
  }
  return layout;
}

function seatMapStageHtml(card, vehicle, layout) {
  const crop = layout.crop;
  const width = (1125 / crop.w) * 100;
  const left = (-crop.x / crop.w) * 100;
  const top = (-crop.y / crop.h) * 100;
  const spots = (layout.spots || [])
    .map((spot) => seatSpotHtml(card, vehicle, spot))
    .join("");
  return `<div class="stage stage-seat-map"
    style="aspect-ratio:${crop.w} / ${crop.h};--seat-img-width:${width.toFixed(
      3,
    )}%;--seat-img-left:${left.toFixed(3)}%;--seat-img-top:${top.toFixed(3)}%">
    <img class="seats-base" src="${assetUrl(layout.base, vehicle)}" alt="">
    ${spots}
  </div>`;
}

function seatControlsHtml(card, vehicle) {
  const layout = seatMapLayout(vehicle);
  if (layout) return seatMapStageHtml(card, vehicle, layout);
  return seatFallbackBodyHtml(card, vehicle);
}

function seatsTabHtml(card, vehicle) {
  const layout = seatMapLayout(vehicle);
  if (layout) return seatMapStageHtml(card, vehicle, layout);
  return `<div class="modal-section">
    <h4>${escapeHtml(card._t("seats"))}</h4>
    ${seatFallbackBodyHtml(card, vehicle)}
  </div>`;
}

function tireReading(card, vehicle, key, alarmKey, labelKey) {
  const display = card._tireDisplay(vehicle, key, alarmKey);
  if (!display) return null;
  const parts = String(display.text).split(" ");
  return {
    label: card._t(labelKey),
    value: parts.shift(),
    unit: parts.join(" "),
    warn: display.warn,
  };
}

function tireReadingHtml(reading) {
  return `<span class="tire-label">${escapeHtml(reading.label)}</span>
    <span class="tire-value">${escapeHtml(reading.value)}${
      reading.unit ? ` <small>${escapeHtml(reading.unit)}</small>` : ""
    }</span>`;
}

function tireAnnotationHtml(reading, x, y) {
  if (!reading) return "";
  return `<div class="tire-annotation ${reading.warn ? "warn" : ""}" style="left:${x}%;top:${y}%">
    ${tireReadingHtml(reading)}
  </div>`;
}

function tireTextHtml(reading) {
  if (!reading) return "";
  return `<div class="tire-text ${reading.warn ? "warn" : ""}">${tireReadingHtml(reading)}</div>`;
}

function tyresTabHtml(card, vehicle) {
  const readings = {
    frontLeft: tireReading(
      card,
      vehicle,
      "tire_front_left",
      "tire_alarm_front_left",
      "front_left",
    ),
    frontRight: tireReading(
      card,
      vehicle,
      "tire_front_right",
      "tire_alarm_front_right",
      "front_right",
    ),
    rearLeft: tireReading(
      card,
      vehicle,
      "tire_rear_left",
      "tire_alarm_rear_left",
      "rear_left",
    ),
    rearRight: tireReading(
      card,
      vehicle,
      "tire_rear_right",
      "tire_alarm_rear_right",
      "rear_right",
    ),
  };
  const topView = layoutFor(vehicle)?.status
    ? vehicleStageHtml(card._hass, vehicle, { rotate: true })
    : "";
  if (!topView) {
    const tiles = [
      readings.frontLeft,
      readings.frontRight,
      readings.rearLeft,
      readings.rearRight,
    ]
      .map(tireTextHtml)
      .filter(Boolean);
    return `<div class="tire-text-grid">${
      tiles.length
        ? tiles.join("")
        : `<div class="empty">${escapeHtml(card._t("unavailable"))}</div>`
    }</div>`;
  }
  return `<div class="tire-stage-overlay">
    ${topView}
    <div class="tire-annotations">
      ${tireAnnotationHtml(readings.frontRight, 28, 17)}
      ${tireAnnotationHtml(readings.rearRight, 73, 17)}
      ${tireAnnotationHtml(readings.frontLeft, 28, 83)}
      ${tireAnnotationHtml(readings.rearLeft, 73, 83)}
    </div>
  </div>`;
}

function vehicleTabHtml(card, vehicle, tab) {
  if (tab === "seats") return seatsTabHtml(card, vehicle);
  if (tab === "tyres") return tyresTabHtml(card, vehicle);
  return climateTabHtml(card, vehicle);
}

function vehicleModalHtml(card) {
  if (card._modal !== "vehicle" || !card._vehicle) return "";
  const vehicle = card._vehicle;
  const tabs = vehicleTabs(card, vehicle);
  if (!tabs.length) return "";
  const active = tabs.includes(card._modalTab) ? card._modalTab : tabs[0];
  const title = card._t("vehicle");
  return `<div class="modal-sheet">
    <div class="modal-panel" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
      <div class="modal-head">
        <h3>${escapeHtml(title)}</h3>
        <button class="settings-close" data-action="close-modal" aria-label="${escapeHtml(card._t("close"))}">
          <ha-icon icon="${PANEL_ICONS.close}"></ha-icon>
        </button>
      </div>
      ${vehicleTabsHtml(card, vehicle, active)}
      <div class="modal-body" role="tabpanel" id="vehicle-pane-${active}">
        ${vehicleTabHtml(card, vehicle, active)}
      </div>
    </div>
  </div>`;
}
