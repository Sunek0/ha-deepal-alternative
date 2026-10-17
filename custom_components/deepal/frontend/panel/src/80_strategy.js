// Dashboard strategy: `custom:deepal` generates one view per Deepal vehicle
// and each view delegates to `custom:deepal-vehicle`, which builds its cards
// lazily when the view opens. The view composes the bundled complete card
// plus the sections the vehicle's model profile defines (energy readings on
// fuel vehicles, driving and ambience on models that report them), all
// resolved through the frontend registries so no entity id is hardcoded.
// Both strategies declare the device and entity registries as regeneration
// dependencies and offer no editor; generation never throws: a missing
// vehicle becomes an explanatory card.

/** Localized panel text for a strategy-generated string. */
function strategyText(hass, key) {
  return translate(panelLanguage(hass || {}), key);
}

/** Stable unique view path for a vehicle. */
function strategyViewPath(vehicle) {
  const slug = String(vehicle.name || "deepal")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 24);
  return `${slug || "deepal"}-${String(vehicle.deviceId).slice(-6)}`;
}

/** A tile for an entity that may not exist; null lets the caller filter. */
function strategyTile(t, vehicle, domain, key, nameKey, icon, options = {}) {
  const id = entityFor(vehicle, domain, key);
  if (!id) return null;
  return { type: "tile", entity: id, name: t(nameKey), icon, ...options };
}

/** A tile that presses one of the integration's buttons. */
function strategyButtonTile(t, vehicle, key, nameKey, icon, color) {
  const id = entityFor(vehicle, "button", key);
  if (!id) return null;
  return {
    type: "tile",
    entity: id,
    name: t(nameKey),
    icon,
    color,
    tap_action: {
      action: "perform-action",
      perform_action: "button.press",
      target: { entity_id: id },
    },
    grid_options: { columns: 6 },
  };
}

/** A 24 h history graph for one sensor metric. */
function strategyGraph(t, vehicle, key, nameKey, color) {
  const id = entityFor(vehicle, "sensor", key);
  if (!id) return null;
  return {
    type: "history-graph",
    entities: [{ entity: id, name: t(nameKey), color }],
    hours_to_show: 24,
  };
}

/**
 * Templated alerts card for the vehicle it is generated for: every clause
 * uses the entity ids discovered at generation time and the whole card hides
 * itself when nothing is wrong.
 */
function strategyAlertsTemplate(t, vehicle) {
  const checks = [];
  const quote = (value) => `'${value}'`;
  const line = (condition, text) =>
    `{% if ${condition} %}{% set ns.items = ns.items + ['- ${text}'] %}{% endif %}`;

  const doors = [
    "door_front_left",
    "door_front_right",
    "door_rear_left",
    "door_rear_right",
  ]
    .map((key) => entityFor(vehicle, "binary_sensor", key))
    .filter(Boolean);
  if (doors.length) {
    const condition = doors
      .map((id) => `is_state(${quote(id)}, 'on')`)
      .join(" or ");
    checks.push(line(condition, `${t("doors")}: ${t("open")}`));
  }

  const windowsId = entityFor(vehicle, "cover", "windows");
  if (windowsId) {
    checks.push(
      line(
        `is_state(${quote(windowsId)}, 'open')`,
        `${t("windows")}: ${t("open")}`,
      ),
    );
  }
  const trunkId = entityFor(vehicle, "binary_sensor", "trunk");
  if (trunkId) {
    checks.push(line(`is_state(${quote(trunkId)}, 'on')`, t("trunk")));
  }
  const hoodId = entityFor(vehicle, "binary_sensor", "hood");
  if (hoodId) {
    checks.push(line(`is_state(${quote(hoodId)}, 'on')`, t("hood")));
  }
  const lockId = entityFor(vehicle, "lock", "doors");
  if (lockId) {
    checks.push(line(`is_state(${quote(lockId)}, 'unlocked')`, t("unlocked")));
  }

  for (const [key, labelKey] of [
    ["tire_alarm_front_left", "front_left"],
    ["tire_alarm_front_right", "front_right"],
    ["tire_alarm_rear_left", "rear_left"],
    ["tire_alarm_rear_right", "rear_right"],
  ]) {
    const id = entityFor(vehicle, "binary_sensor", key);
    if (id) {
      checks.push(
        line(
          `is_state(${quote(id)}, 'on')`,
          `${t("warning_tpms")}: ${t(labelKey)}`,
        ),
      );
    }
  }

  const pluggedId = entityFor(vehicle, "binary_sensor", "charger_plugged");
  const chargingId = entityFor(vehicle, "binary_sensor", "charging");
  if (pluggedId && chargingId) {
    checks.push(
      line(
        `is_state(${quote(pluggedId)}, 'on') and is_state(${quote(chargingId)}, 'off')`,
        t("cable_idle"),
      ),
    );
  }
  const batteryId = entityFor(vehicle, "sensor", "battery");
  if (batteryId) {
    checks.push(
      `{% set battery = states(${quote(batteryId)}) | float(100) %}` +
        `{% if battery < 20 %}{% set ns.items = ns.items + ['- ${t("battery_low")}'] %}{% endif %}`,
    );
  }
  const connectedId = entityFor(vehicle, "binary_sensor", "connected");
  if (connectedId) {
    checks.push(
      line(`is_state(${quote(connectedId)}, 'off')`, t("disconnected")),
    );
  }

  if (!checks.length) return null;
  return [
    "{% set ns = namespace(items=[]) %}",
    ...checks,
    `{% if ns.items %}{{ ns.items | join('\\n') }}{% else %}- ${t("strategy_no_alerts")}{% endif %}`,
  ].join("\n");
}

/** Sections of one vehicle's generated view. */
function strategyVehicleSections(hass, vehicle) {
  const t = (key) => strategyText(hass, key);
  const sections = [];

  sections.push({
    type: "grid",
    column_span: 2,
    cards: [
      {
        type: "custom:deepal-card",
        device_id: vehicle.deviceId,
        grid_options: { columns: "full" },
      },
    ],
  });

  const controls = [
    strategyTile(t, vehicle, "lock", "doors", "central_lock", "mdi:car-door-lock", {
      color: "red",
      features: [{ type: "lock-commands" }],
      grid_options: { columns: 6 },
    }),
    strategyTile(t, vehicle, "cover", "windows", "windows", "mdi:window-closed-variant", {
      color: "cyan",
      tap_action: { action: "toggle" },
      grid_options: { columns: 6 },
    }),
    strategyTile(t, vehicle, "cover", "trunk", "trunk", "mdi:car-back", {
      color: "blue",
      tap_action: { action: "toggle" },
      grid_options: { columns: 6 },
    }),
    strategyButtonTile(t, vehicle, "flash_lights", "flash_lights", "mdi:car-light-alert", "amber"),
    strategyButtonTile(t, vehicle, "honk_horn", "honk_horn", "mdi:bullhorn", "red"),
    strategyButtonTile(t, vehicle, "flash_and_honk", "flash_and_honk", "mdi:car-light-alert", "orange"),
    strategyButtonTile(t, vehicle, "refresh", "refresh", "mdi:refresh", "blue"),
  ].filter(Boolean);
  if (controls.length) {
    sections.push({
      type: "grid",
      column_span: 1,
      cards: [
        { type: "heading", heading: t("controls"), icon: "mdi:car-cog" },
        ...controls,
      ],
    });
  }

  const trends = [
    strategyGraph(t, vehicle, "battery", "battery", "green"),
    strategyGraph(t, vehicle, "range", "range", "teal"),
    strategyGraph(t, vehicle, "fuel_level", "fuel", "amber"),
    strategyGraph(t, vehicle, "fuel_range", "fuel_range", "orange"),
  ].filter(Boolean);
  if (trends.length) {
    sections.push({
      type: "grid",
      column_span: 1,
      cards: [
        { type: "heading", heading: t("energy"), icon: "mdi:chart-line" },
        ...trends,
      ],
    });
  }

  const tires = [
    ["tire_front_left", "front_left"],
    ["tire_front_right", "front_right"],
    ["tire_rear_left", "rear_left"],
    ["tire_rear_right", "rear_right"],
  ]
    .map(([key, labelKey]) =>
      strategyTile(t, vehicle, "sensor", key, labelKey, "mdi:tire", {
        tap_action: { action: "more-info" },
        grid_options: { columns: 6 },
      }),
    )
    .filter(Boolean);
  if (tires.length) {
    sections.push({
      type: "grid",
      column_span: 1,
      cards: [{ type: "heading", heading: t("tires"), icon: "mdi:tire" }, ...tires],
    });
  }

  const driving = [
    ["speed", "speed", "mdi:speedometer"],
    ["gear", "gear", "mdi:car-shift-pattern"],
    ["epb_status", "epb", "mdi:parking"],
    ["vehicle_status", "vehicle_status", "mdi:car-info"],
    ["mileage_yesterday", "mileage_yesterday", "mdi:counter"],
    ["trip_mileage", "trip_mileage", "mdi:map-marker-distance"],
  ]
    .map(([key, labelKey, icon]) =>
      strategyTile(t, vehicle, "sensor", key, labelKey, icon, {
        grid_options: { columns: 6 },
      }),
    )
    .filter(Boolean);
  if (driving.length) {
    sections.push({
      type: "grid",
      column_span: 1,
      cards: [
        { type: "heading", heading: t("driving"), icon: "mdi:steering" },
        ...driving,
      ],
    });
  }

  const ambience = [
    ["outside_temperature", "outside_temperature", "mdi:thermometer"],
    ["inside_pm25", "inside_pm25", "mdi:blur"],
    ["air_quality_level", "air_quality_level", "mdi:air-filter"],
  ]
    .map(([key, labelKey, icon]) =>
      strategyTile(t, vehicle, "sensor", key, labelKey, icon, {
        grid_options: { columns: 6 },
      }),
    )
    .filter(Boolean);
  if (ambience.length) {
    sections.push({
      type: "grid",
      column_span: 1,
      cards: [
        { type: "heading", heading: t("ambience"), icon: "mdi:air-filter" },
        ...ambience,
      ],
    });
  }

  const alerts = strategyAlertsTemplate(t, vehicle);
  if (alerts) {
    sections.push({
      type: "grid",
      column_span: 1,
      cards: [
        { type: "heading", heading: t("warnings"), icon: "mdi:alert-circle-outline" },
        { type: "markdown", content: alerts },
      ],
    });
  }

  return sections;
}

class DeepalDashboardStrategy extends HTMLElement {
  static registryDependencies = ["entities", "devices"];

  static noEditor = true;

  static getCreateSuggestions(hass) {
    return {
      title: strategyText(hass, "strategy_name"),
      icon: "mdi:car-electric",
    };
  }

  static async generate(config, hass) {
    const vehicles = discoverVehicles(hass || {});
    if (!vehicles.length) {
      return {
        views: [
          {
            title: strategyText(hass, "title"),
            cards: [
              {
                type: "markdown",
                content: strategyText(hass, "strategy_no_vehicles"),
              },
            ],
          },
        ],
      };
    }
    return {
      views: vehicles.map((vehicle) => ({
        title: vehicle.name,
        path: strategyViewPath(vehicle),
        icon: "mdi:car-electric",
        strategy: {
          type: `custom:${STRATEGY_VIEW_TYPE}`,
          device_id: vehicle.deviceId,
        },
      })),
    };
  }
}

class DeepalVehicleViewStrategy extends HTMLElement {
  static registryDependencies = ["entities", "devices"];

  static noEditor = true;

  static async generate(config, hass) {
    const deviceId = config && config.device_id;
    const vehicle = discoverVehicles(hass || {}).find(
      (candidate) => candidate.deviceId === deviceId,
    );
    if (!vehicle) {
      return {
        type: "sections",
        max_columns: 2,
        sections: [
          {
            type: "grid",
            cards: [
              {
                type: "markdown",
                content: strategyText(hass, "strategy_no_vehicle"),
              },
            ],
          },
        ],
      };
    }
    return {
      type: "sections",
      max_columns: 2,
      sections: strategyVehicleSections(hass, vehicle),
    };
  }
}
