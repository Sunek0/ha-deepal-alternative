// GENERATED FILE - do not edit; run scripts/build_panel.py after changing src/ or texts/.
const PANEL_VERSION = "1.5.0";

// ---- 10_constants.js ----
// Constants shared by the panel modules. The build script prepends the
// PANEL_VERSION constant before this file.
const PANEL_TAG = "deepal-panel";
const CARD_TAG = "deepal-card";
const CARD_COMPACT_TAG = "deepal-compact-card";
// Dashboard strategy types and the tags Home Assistant resolves for them.
const STRATEGY_DASHBOARD_TYPE = "deepal";
const STRATEGY_VIEW_TYPE = "deepal-vehicle";
const STRATEGY_DASHBOARD_TAG = "ll-strategy-dashboard-deepal";
const STRATEGY_VIEW_TAG = "ll-strategy-view-deepal-vehicle";
const PANEL_BASE_LANGUAGE = "en";
// Languages that borrow another language's texts verbatim.
const PANEL_BORROWED_LANGUAGES = { ca: "es", gl: "es", eu: "es" };
const PANEL_ASSETS_URL = "/deepal/frontend/assets";

// Tabs, in order: [key, icon]. The key is also the text key "tab_<key>".
// Models with their own layout can add a model-conditional tab (the S07
// Driving tab); the profile list lives in PANEL_MODEL_LAYOUTS.
const PANEL_TABS = [
  ["status", "mdi:car"],
  ["climate", "mdi:air-conditioner"],
  ["charging", "mdi:battery-charging"],
];

// Model profiles detected from the registry model plus the entities: the S05
// family splits into EV and PHEV, the S07 has its own artwork, and anything
// else keeps the generic rendering (the vehicle image entity).
const PANEL_PROFILE_S05_EV = "s05_ev";
const PANEL_PROFILE_S05_PHEV = "s05_phev";
const PANEL_PROFILE_S07 = "s07";
const PANEL_PROFILE_GENERIC = "generic";
const PANEL_S05_MODEL_TOKENS = ["S05", "C857"];
const PANEL_S07_MODEL_TOKENS = ["S07"];
// The integration creates the fuel sensors only for fuel vehicles (PHEV /
// range extender), so their presence is the EV/PHEV discriminator.
const PANEL_FUEL_ENTITY_KEYS = ["fuel_level", "fuel_range"];

// Per-model artwork, keyed by model family. Every file in `status`, `compact`,
// `climate`, `charging` and `seats` shares the canvas size of its base image,
// so the panel only stacks them in order. `tabs` is the model-conditional tab
// list; `compact` is the state-aware 3/4 artwork the compact card prefers;
// `hero` is its static fallback when the vehicle image is unavailable;
// `animations` maps a transition key to the clip played when that transition
// happens, always over the matching static layer.
const PANEL_MODEL_LAYOUTS = {
  s05: {
    tabs: PANEL_TABS,
    status: {
      // The base is the bare body: hood, trunk and doors are separate pieces
      // that must always be drawn, closed or open, like the hand-made panel.
      base: "s05/estado_planta/Ocar1.png",
      layers: {
        hood_closed: "s05/estado_planta/Ohood0.png",
        hood_open: "s05/estado_planta/Ohood1.png",
        trunk_closed: "s05/estado_planta/Otrunk0.png",
        trunk_open: "s05/estado_planta/Otrunk1.png",
        door_front_left_closed: "s05/estado_planta/OLF0.png",
        door_front_left_open: "s05/estado_planta/OLF1.png",
        door_front_right_closed: "s05/estado_planta/ORF0.png",
        door_front_right_open: "s05/estado_planta/ORF1.png",
        door_rear_left_closed: "s05/estado_planta/OLB0.png",
        door_rear_left_open: "s05/estado_planta/OLB1.png",
        door_rear_right_closed: "s05/estado_planta/ORB0.png",
        door_rear_right_open: "s05/estado_planta/ORB1.png",
        window_front_left_open: "s05/estado_planta/OwindowsLF1.png",
        window_front_right_open: "s05/estado_planta/OwindowsRF1.png",
        window_rear_left_open: "s05/estado_planta/OwindowsLB1.png",
        window_rear_right_open: "s05/estado_planta/OwindowsRB1.png",
        door_window_front_left_open: "s05/estado_planta/OopenDoor-windowsLF1.png",
        door_window_front_right_open: "s05/estado_planta/OopenDoor-windowsRF1.png",
        door_window_rear_left_open: "s05/estado_planta/OopenDoor-windowsLB1.png",
        door_window_rear_right_open: "s05/estado_planta/OopenDoor-windowsRB1.png",
        lights_on: "s05/estado_planta/OlowBeam1.png",
      },
    },
    // The compact card's 3/4 isometric view. The base is the bare body; the
    // doors, hood and trunk are separate pieces drawn in the order below.
    compact: {
      base: "s05/estado_isometrico/car1.png",
      layers: {
        hood_closed: "s05/estado_isometrico/hood0.png",
        hood_open: "s05/estado_isometrico/hood1.png",
        trunk_closed: "s05/estado_isometrico/trunk0.png",
        trunk_open: "s05/estado_isometrico/trunk1.png",
        door_front_left_closed: "s05/estado_isometrico/LF0.png",
        door_front_left_open: "s05/estado_isometrico/LF1.png",
        door_front_left_outline: "s05/estado_isometrico/LF0-outline.png",
        door_front_right_closed: "s05/estado_isometrico/RF0.png",
        door_front_right_open: "s05/estado_isometrico/RF1.png",
        door_front_right_outline: "s05/estado_isometrico/RF0-outline.png",
        door_rear_left_closed: "s05/estado_isometrico/LB0.png",
        door_rear_left_open: "s05/estado_isometrico/LB1.png",
        door_rear_left_outline: "s05/estado_isometrico/LB0-outline.png",
        door_rear_right_closed: "s05/estado_isometrico/RB0.png",
        door_rear_right_open: "s05/estado_isometrico/RB1.png",
        door_rear_right_outline: "s05/estado_isometrico/RB0-outline.png",
        window_front_left_closed: "s05/estado_isometrico/windowsLF0.png",
        window_front_left_closed_door_open:
          "s05/estado_isometrico/openDoor-windowsLF0.png",
        window_front_right_closed: "s05/estado_isometrico/windowsRF0.png",
        window_front_right_closed_door_open:
          "s05/estado_isometrico/openDoor-windowsRF0.png",
        window_rear_left_closed: "s05/estado_isometrico/windowsLB0.png",
        window_rear_left_closed_door_open:
          "s05/estado_isometrico/openDoor-windowsLB0.png",
        window_rear_right_closed: "s05/estado_isometrico/windowsRB0.png",
        window_rear_right_closed_door_open:
          "s05/estado_isometrico/openDoor-windowsRB0.png",
        lights_on: "s05/estado_isometrico/lowBeam1.png",
      },
    },
    climate: {
      base: "s05/aa/carAc.png",
      layers: { climate_on: "s05/aa/carAcOpen.png" },
    },
    charging: {
      base: "s05/bateria/carBattery.png",
      layers: {
        plugged: "s05/bateria/chargingLineOff.png",
        charging: "s05/bateria/chargingLineOn.png",
      },
    },
    seats: null,
    hero: null,
    animations: {},
  },
  s07: {
    tabs: [
      ["status", "mdi:car"],
      ["driving", "mdi:steering"],
      ["climate", "mdi:air-conditioner"],
      ["charging", "mdi:battery-charging"],
    ],
    status: {
      base: "s07/overlook/Ocar1.png",
      layers: {
        hood_closed: "s07/overlook/Ohood0.png",
        hood_open: "s07/overlook/Ohood1.png",
        trunk_closed: "s07/overlook/Otrunk0.png",
        trunk_open: "s07/overlook/Otrunk1.png",
        door_front_left_closed: "s07/overlook/OLF0.png",
        door_front_left_open: "s07/overlook/OLF1.png",
        door_front_right_closed: "s07/overlook/ORF0.png",
        door_front_right_open: "s07/overlook/ORF1.png",
        door_rear_left_closed: "s07/overlook/OLB0.png",
        door_rear_left_open: "s07/overlook/OLB1.png",
        door_rear_right_closed: "s07/overlook/ORB0.png",
        door_rear_right_open: "s07/overlook/ORB1.png",
        window_front_left_open: "s07/overlook/OwindowsLF1.png",
        window_front_right_open: "s07/overlook/OwindowsRF1.png",
        window_rear_left_open: "s07/overlook/OwindowsLB1.png",
        window_rear_right_open: "s07/overlook/OwindowsRB1.png",
        door_window_front_left_open: "s07/overlook/OopenDoor-windowsLF1.png",
        door_window_front_right_open: "s07/overlook/OopenDoor-windowsRF1.png",
        door_window_rear_left_open: "s07/overlook/OopenDoor-windowsLB1.png",
        door_window_rear_right_open: "s07/overlook/OopenDoor-windowsRB1.png",
        lights_on: "s07/overlook/OlowBeam1.png",
      },
    },
    climate: {
      base: "s07/aa/carAc.png",
      layers: { climate_on: "s07/aa/carAcOpen.png" },
    },
    charging: {
      base: "s07/bateria/carBattery.png",
      layers: {
        plugged: "s07/bateria/chargingLineOff.png",
        charging: "s07/bateria/chargingLineOn.png",
      },
    },
    seats: { base: "s07/asientos/carSeat.png" },
    hero: "s07/side/carDefault.png",
    animations: {
      climate_on: "s07/anim/anim_air_start_left.webm",
      seat_vent: "s07/anim/anim_seat_wind_left.webm",
      charging_on: "s07/anim/anim_battery_capacity.webm",
    },
  },
};

// Entity keys (translation_key) the panel looks up, grouped by platform.
// Optional keys are skipped when the vehicle does not expose them.
const PANEL_KEYS = {
  sensor: {
    battery: "battery_level",
    range: "remaining_range",
    odometer: "total_odometer",
    speed: "speed",
    gear: "gear",
    epb_status: "epb_status",
    vehicle_status: "vehicle_status",
    mileage_yesterday: "mileage_yesterday",
    trip_mileage: "trip_mileage",
    charge_status: "charge_status",
    charge_mode: "charge_mode",
    charge_current: "charge_current",
    ac_charge_current: "ac_charge_current",
    dc_charge_current: "dc_charge_current",
    remaining_time: "remaining_charge_time",
    remaining_time_formatted: "remaining_charge_time_formatted",
    charge_limit_sensor: "charge_limit",
    inside_temperature: "inside_temperature",
    outside_temperature: "outside_temperature",
    cabin_humidity: "cabin_humidity",
    inside_pm25: "inside_pm25",
    air_quality_level: "air_quality_level",
    updated: "last_updated",
    fuel_level: "fuel_level",
    fuel_range: "fuel_range",
    fuel_tank_capacity: "fuel_tank_capacity",
    tire_front_left: "tire_pressure_front_left",
    tire_front_right: "tire_pressure_front_right",
    tire_rear_left: "tire_pressure_rear_left",
    tire_rear_right: "tire_pressure_rear_right",
  },
  binary_sensor: {
    charging: "charging",
    charger_plugged: "charger_plugged",
    connected: "connected",
    engine: "engine",
    doors_locked: "doors_lock_state",
    door_front_left: "door_front_left",
    door_front_right: "door_front_right",
    door_rear_left: "door_rear_left",
    door_rear_right: "door_rear_right",
    window_front_left: "window_open_front_left",
    window_front_right: "window_open_front_right",
    window_rear_left: "window_open_rear_left",
    window_rear_right: "window_open_rear_right",
    trunk: "trunk",
    hood: "hood",
    low_beam: "low_beam",
    high_beam: "high_beam",
    position_lamp: "position_lamp",
    rear_fog_lamp: "rear_fog_lamp",
    tire_alarm_front_left: "tire_alarm_front_left",
    tire_alarm_front_right: "tire_alarm_front_right",
    tire_alarm_rear_left: "tire_alarm_rear_left",
    tire_alarm_rear_right: "tire_alarm_rear_right",
    warning_12v_battery: "warning_12v_battery",
    warning_tpms: "warning_tpms",
    warning_abs: "warning_abs",
    warning_brake_fluid: "warning_brake_fluid",
    warning_brake: "warning_brake",
    warning_eps: "warning_eps",
    warning_power_limit: "warning_power_limit",
    warning_power_system: "warning_power_system",
    warning_traction_battery_low: "warning_traction_battery_low",
    key_battery_low: "key_battery_low",
  },
  lock: { doors: "doors" },
  cover: { windows: "windows", trunk: "trunk" },
  climate: { cabin: "cabin_climate" },
  number: {
    charge_limit: "charge_limit",
    seat_heating_front_left: "seat_heating_level_front_left",
    seat_heating_front_right: "seat_heating_level_front_right",
    seat_ventilation_front_left: "seat_ventilation_level_front_left",
    seat_ventilation_front_right: "seat_ventilation_level_front_right",
    seat_heating_rear_left: "seat_heating_level_rear_left",
    seat_heating_rear_right: "seat_heating_level_rear_right",
    seat_ventilation_rear_left: "seat_ventilation_level_rear_left",
    seat_ventilation_rear_right: "seat_ventilation_level_rear_right",
  },
  switch: {
    steering_wheel_heating: "steering_wheel_heating",
    charge_schedule: "charge_schedule",
  },
  time: {
    schedule_start: "charge_schedule_start",
    schedule_end: "charge_schedule_end",
  },
  button: {
    refresh: "refresh_vehicle_data",
    flash_lights: "flash_lights",
    honk_horn: "honk_horn",
    flash_and_honk: "flash_and_honk",
  },
  image: { vehicle_image: "vehicle_image" },
};

// Health warnings, in the order the panel lists them, with their icons. The
// warnings section only renders while at least one of them is active.
const PANEL_WARNINGS = [
  ["warning_12v_battery", "mdi:car-battery"],
  ["warning_tpms", "mdi:car-tire-alert"],
  ["warning_abs", "mdi:car-brake-abs"],
  ["warning_brake_fluid", "mdi:car-brake-fluid-level"],
  ["warning_brake", "mdi:car-brake-alert"],
  ["warning_eps", "mdi:steering"],
  ["warning_power_limit", "mdi:speedometer-slow"],
  ["warning_power_system", "mdi:engine"],
  ["warning_traction_battery_low", "mdi:battery-alert"],
  ["key_battery_low", "mdi:key-alert"],
];

// ---- 20_texts.js ----
// GENERATED FILE - do not edit; run scripts/build_panel.py after changing src/ or texts/.

// UI strings, embedded from frontend/panel/texts/*.json.
const PANEL_TEXTS = {
  "en": {
    "air_quality_level": "Air quality",
    "alarm": "Alarm",
    "ambience": "Ambience",
    "battery": "Battery",
    "battery_low": "Battery low",
    "cabin_humidity": "Humidity",
    "cable_idle": "Cable connected, not charging",
    "card_description": "Vehicle status, picture and essential controls for a Deepal car",
    "card_name": "Deepal vehicle",
    "central_lock": "Central locking",
    "charge_current": "Current",
    "charge_limit": "Charge limit",
    "charge_mode": "Charging type",
    "charge_schedule": "Charge schedule",
    "charge_schedule_end": "To",
    "charge_schedule_start": "From",
    "charge_session_current": "Current session",
    "charge_session_last": "Last session",
    "charge_status": "Charge status",
    "charging": "Charging",
    "climate": "Climate",
    "climate_off": "Turn off",
    "climate_on": "Turn on",
    "close": "Close",
    "close_trunk": "Close trunk",
    "close_windows": "Close windows",
    "closed": "Closed",
    "command_failed": "The command failed",
    "compact_card_description": "Compact status, picture and quick controls of a Deepal car",
    "compact_card_name": "Deepal vehicle (compact)",
    "controls": "Controls",
    "current_ac": "Current (AC)",
    "current_dc": "Current (DC)",
    "disconnected": "No connection to the cloud",
    "doors": "Doors",
    "driving": "Driving",
    "energy": "Energy",
    "engine": "Engine",
    "epb": "Parking brake",
    "flash_and_honk": "Flash and horn",
    "flash_lights": "Flash",
    "front_left": "Front left",
    "front_right": "Front right",
    "fuel": "Fuel",
    "fuel_range": "Fuel range",
    "fuel_tank_capacity": "Tank capacity",
    "gear": "Gear",
    "high_beam": "High beam",
    "honk_horn": "Horn",
    "hood": "Hood",
    "inside_pm25": "PM2.5",
    "inside_temperature": "Inside",
    "key_battery_low": "Key fob battery",
    "level": "Level",
    "lights": "Lights",
    "lock": "Lock",
    "lock_doors": "Lock doors",
    "locked": "Locked",
    "low_beam": "Low beam",
    "mileage_yesterday": "Yesterday",
    "no_vehicle": "No vehicle configured yet",
    "not_plugged": "Cable unplugged",
    "odometer": "Odometer",
    "off": "Off",
    "offline": "Offline",
    "on": "On",
    "online": "Online",
    "open": "Open",
    "open_trunk": "Open trunk",
    "open_windows": "Open windows",
    "outside_temperature": "Outside",
    "plugged": "Cable plugged",
    "position_lamp": "Position",
    "range": "Range",
    "rear_left": "Rear left",
    "rear_right": "Rear right",
    "refresh": "Refresh",
    "refresh_hint": "Request fresh data from the vehicle",
    "remaining_time": "Time left",
    "seat_heating": "Heating",
    "seat_ventilation": "Ventilation",
    "seats": "Seats",
    "session_end_level": "End level",
    "session_end_range": "End range",
    "session_ended": "Ended",
    "session_start_level": "Start level",
    "session_start_range": "Start range",
    "session_started": "Started",
    "speed": "Speed",
    "steering_wheel": "Steering wheel",
    "strategy_description": "One dashboard view per car, generated from your Deepal entities",
    "strategy_name": "Deepal",
    "strategy_no_alerts": "Everything is in order.",
    "strategy_no_vehicle": "This vehicle is no longer available. Edit the dashboard and pick another one.",
    "strategy_no_vehicles": "No Deepal vehicle is configured yet. Add the Deepal integration first.",
    "tab_charging": "Charging",
    "tab_climate": "Climate",
    "tab_driving": "Driving",
    "tab_status": "Status",
    "target_temperature": "Target temperature",
    "tires": "Tires",
    "title": "Deepal",
    "trip_mileage": "Trip",
    "trunk": "Trunk",
    "unavailable": "Unavailable",
    "unknown": "Unknown",
    "unlock": "Unlock",
    "unlock_doors": "Unlock doors",
    "unlocked": "Unlocked",
    "updated": "Updated",
    "vehicle": "Vehicle",
    "vehicle_status": "Vehicle status",
    "warning_12v_battery": "12 V battery",
    "warning_abs": "ABS",
    "warning_brake": "Brakes",
    "warning_brake_fluid": "Brake fluid",
    "warning_eps": "Steering",
    "warning_power_limit": "Power limit",
    "warning_power_system": "Power system",
    "warning_tpms": "Tire pressure",
    "warning_traction_battery_low": "Traction battery",
    "warnings": "Warnings",
    "windows": "Windows",
  },
  "es": {
    "air_quality_level": "Calidad del aire",
    "alarm": "Alarma",
    "ambience": "Ambiente",
    "battery": "Batería",
    "battery_low": "Batería baja",
    "cabin_humidity": "Humedad",
    "cable_idle": "Cable conectado, sin cargar",
    "card_description": "Estado, imagen y controles esenciales de un coche Deepal",
    "card_name": "Vehículo Deepal",
    "central_lock": "Cierre centralizado",
    "charge_current": "Corriente",
    "charge_limit": "Límite de carga",
    "charge_mode": "Tipo de carga",
    "charge_schedule": "Programación de carga",
    "charge_schedule_end": "Hasta",
    "charge_schedule_start": "Desde",
    "charge_session_current": "Carga en curso",
    "charge_session_last": "Última carga",
    "charge_status": "Estado de carga",
    "charging": "Cargando",
    "climate": "Climatización",
    "climate_off": "Apagar",
    "climate_on": "Encender",
    "close": "Cerrar",
    "close_trunk": "Cerrar maletero",
    "close_windows": "Subir ventanillas",
    "closed": "Cerrado",
    "command_failed": "El comando ha fallado",
    "compact_card_description": "Estado compacto, imagen y controles rápidos de un coche Deepal",
    "compact_card_name": "Vehículo Deepal (compacta)",
    "controls": "Controles",
    "current_ac": "Corriente (AC)",
    "current_dc": "Corriente (DC)",
    "disconnected": "Sin conexión con la nube",
    "doors": "Puertas",
    "driving": "Conducción",
    "energy": "Energía",
    "engine": "Motor",
    "epb": "Freno de mano",
    "flash_and_honk": "Destello y claxon",
    "flash_lights": "Destello",
    "front_left": "Del. izq.",
    "front_right": "Del. der.",
    "fuel": "Combustible",
    "fuel_range": "Autonomía (combustible)",
    "fuel_tank_capacity": "Capacidad del depósito",
    "gear": "Marcha",
    "high_beam": "Largas",
    "honk_horn": "Claxon",
    "hood": "Capó",
    "inside_pm25": "PM2.5",
    "inside_temperature": "Interior",
    "key_battery_low": "Pila de la llave",
    "level": "Nivel",
    "lights": "Luces",
    "lock": "Cerrar",
    "lock_doors": "Cerrar puertas",
    "locked": "Cerrado",
    "low_beam": "Cortas",
    "mileage_yesterday": "Ayer",
    "no_vehicle": "Aún no hay ningún vehículo configurado",
    "not_plugged": "Cable desconectado",
    "odometer": "Kilómetros",
    "off": "Apagado",
    "offline": "Sin conexión",
    "on": "Encendido",
    "online": "En línea",
    "open": "Abrir",
    "open_trunk": "Abrir maletero",
    "open_windows": "Bajar ventanillas",
    "outside_temperature": "Exterior",
    "plugged": "Cable conectado",
    "position_lamp": "Posición",
    "range": "Autonomía",
    "rear_left": "Tras. izq.",
    "rear_right": "Tras. der.",
    "refresh": "Actualizar",
    "refresh_hint": "Pide datos nuevos al coche",
    "remaining_time": "Tiempo restante",
    "seat_heating": "Calefacción",
    "seat_ventilation": "Ventilación",
    "seats": "Asientos",
    "session_end_level": "Nivel final",
    "session_end_range": "Autonomía final",
    "session_ended": "Fin",
    "session_start_level": "Nivel inicial",
    "session_start_range": "Autonomía inicial",
    "session_started": "Inicio",
    "speed": "Velocidad",
    "steering_wheel": "Volante",
    "strategy_description": "Una vista de dashboard por coche, generada desde tus entidades Deepal",
    "strategy_name": "Deepal",
    "strategy_no_alerts": "Todo en orden.",
    "strategy_no_vehicle": "Este vehículo ya no está disponible. Edita el dashboard y elige otro.",
    "strategy_no_vehicles": "Todavía no hay ningún vehículo Deepal configurado. Añade primero la integración Deepal.",
    "tab_charging": "Carga",
    "tab_climate": "Clima",
    "tab_driving": "Conducción",
    "tab_status": "Estado",
    "target_temperature": "Temperatura",
    "tires": "Neumáticos",
    "title": "Deepal",
    "trip_mileage": "Trayecto",
    "trunk": "Maletero",
    "unavailable": "No disponible",
    "unknown": "Desconocido",
    "unlock": "Abrir",
    "unlock_doors": "Abrir puertas",
    "unlocked": "Abierto",
    "updated": "Actualizado",
    "vehicle": "Vehículo",
    "vehicle_status": "Estado del vehículo",
    "warning_12v_battery": "Batería de 12 V",
    "warning_abs": "ABS",
    "warning_brake": "Frenos",
    "warning_brake_fluid": "Líquido de frenos",
    "warning_eps": "Dirección",
    "warning_power_limit": "Límite de potencia",
    "warning_power_system": "Sistema de potencia",
    "warning_tpms": "Presión de neumáticos",
    "warning_traction_battery_low": "Batería de tracción",
    "warnings": "Avisos",
    "windows": "Ventanillas",
  },
};

// ---- 30_styles.js ----
// Panel styles: one design-system layer shared by the sidebar panel and both
// dashboard cards. Everything is scoped to the shadow root and built on Home
// Assistant theme variables, so it follows light and dark themes.
//
// Views only compose these components; they must not add their own styles:
//   .app-bar   application bar (title, vehicle selector, actions)
//   .vitals    persistent glance strip (battery, range, lock, freshness)
//   .segmented tab control (status / climate / charging)
//   .section   titled card group
//   .chip      state pill (neutral, on / warn for active or alert)
//   .tile      touch target for controls and compact readouts
//   .metric    label + value readout
//   .stepper   minus / value / plus control
//   .stage     layered vehicle picture

const PANEL_CSS = `
:host {
  /* Spacing, radii and type tokens: the single source for the whole UI. */
  --dp-space-xs: 4px;
  --dp-space-sm: 8px;
  --dp-space-md: 12px;
  --dp-space-lg: 16px;
  --dp-space-xl: 24px;
  --dp-radius: var(--ha-card-border-radius, 16px);
  --dp-radius-sm: 12px;
  --dp-radius-pill: 999px;
  --dp-surface: var(--card-background-color);
  --dp-surface-2: var(--secondary-background-color);
  --dp-line: var(--divider-color);
  --dp-text: var(--primary-text-color);
  --dp-text-2: var(--secondary-text-color);
  --dp-accent: var(--primary-color);
  --dp-warn: var(--error-color);
  --dp-on-text: var(--text-primary-color, white);
  --dp-touch: 44px;

  display: block;
  height: 100%;
  background: var(--primary-background-color);
  color: var(--dp-text);
  font-family: var(--ha-font-family-body, Roboto, sans-serif);
}

.panel {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  height: 100%;
  max-width: 900px;
  margin: 0 auto;
  padding: var(--dp-space-md) var(--dp-space-lg) 32px;
  overflow-y: auto;
}

:focus-visible {
  outline: 2px solid var(--dp-accent);
  outline-offset: 2px;
}

/* --- App bar ----------------------------------------------------------- */

.app-bar {
  position: sticky;
  top: calc(var(--dp-space-md) * -1);
  z-index: 2;
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  flex-wrap: wrap;
  padding: var(--dp-space-sm) 0;
  background: var(--primary-background-color);
}

.app-title {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  font-size: 20px;
  font-weight: 600;
  margin: 0;
}

.app-title .model {
  font-size: 13px;
  font-weight: 400;
  color: var(--dp-text-2);
}

.spacer { flex: 1; }

.vehicle-select {
  display: flex;
  align-items: center;
  gap: 6px;
}

.vehicle-select select {
  background: var(--dp-surface);
  color: var(--dp-text);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  padding: 6px 8px;
  font-size: 14px;
}

.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: var(--dp-touch);
  height: var(--dp-touch);
  border: none;
  border-radius: 50%;
  background: var(--dp-surface);
  color: var(--dp-text);
  cursor: pointer;
  touch-action: manipulation;
}

.icon-button:hover { background: var(--dp-surface-2); }

/* --- Vitals strip ------------------------------------------------------ */

.vitals {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(104px, 1fr));
  gap: var(--dp-space-sm);
}

.vital {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  min-height: var(--dp-touch);
  padding: var(--dp-space-sm) 10px;
  background: var(--dp-surface);
  border-radius: var(--dp-radius-sm);
  overflow: hidden;
}

.vital ha-icon { color: var(--dp-text-2); --mdc-icon-size: 20px; }
.vital.on ha-icon { color: var(--dp-accent); }
.vital.warn { background: var(--dp-warn); color: var(--dp-on-text); }
.vital.warn ha-icon { color: var(--dp-on-text); }

.vital-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.vital-label {
  font-size: 11px;
  color: var(--dp-text-2);
  white-space: nowrap;
}

.vital.warn .vital-label { color: var(--dp-on-text); }

.vital-value {
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* --- Segmented tabs ---------------------------------------------------- */

.segmented {
  display: flex;
  gap: var(--dp-space-xs);
  padding: var(--dp-space-xs);
  background: var(--dp-surface);
  border-radius: var(--dp-radius-pill);
}

.segment {
  flex: 1 1 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  padding: var(--dp-space-sm);
  border: none;
  border-radius: var(--dp-radius-pill);
  background: none;
  color: var(--dp-text-2);
  font-size: 14px;
  cursor: pointer;
  touch-action: manipulation;
}

.segment:hover { color: var(--dp-text); }

.segment[aria-selected="true"],
.segment[aria-pressed="true"] {
  background: var(--dp-accent);
  color: var(--dp-on-text);
}

.segment ha-icon { --mdc-icon-size: 18px; }

.center { display: flex; justify-content: center; }

/* --- Sections ---------------------------------------------------------- */

.view {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
}

.section {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  padding: var(--dp-space-md) 14px;
  background: var(--dp-surface);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius);
}

.section-head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
}

.section-head ha-icon { color: var(--dp-text-2); --mdc-icon-size: 18px; }

.section-title {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--dp-text-2);
  text-transform: uppercase;
}

.section-note {
  margin-left: auto;
  font-size: 12px;
  color: var(--dp-text-2);
}

/* --- Chips ------------------------------------------------------------- */

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: var(--dp-radius-pill);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-size: 13px;
  white-space: nowrap;
}

.chip ha-icon { --mdc-icon-size: 16px; }
.chip.on { background: var(--dp-accent); color: var(--dp-on-text); }
.chip.warn { background: var(--dp-warn); color: var(--dp-on-text); }

/* --- Tiles ------------------------------------------------------------- */

.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: var(--dp-space-sm);
}

.tile {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  min-height: var(--dp-touch);
  padding: 10px var(--dp-space-md);
  border: none;
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-family: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  touch-action: manipulation;
}

.tile:hover { filter: brightness(1.06); }
.tile.static { cursor: default; }
.tile.static:hover { filter: none; }
.tile ha-icon { --mdc-icon-size: 20px; }
.tile.on { background: var(--dp-accent); color: var(--dp-on-text); }
.tile.warn { background: var(--dp-warn); color: var(--dp-on-text); }
.tile:disabled { opacity: 0.5; cursor: default; }

.tile-body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.tile-label { font-size: 12px; color: var(--dp-text-2); }
.tile-value { font-size: 15px; font-weight: 600; }
.tile.on .tile-label, .tile.warn .tile-label { color: var(--dp-on-text); }

/* --- Metrics ----------------------------------------------------------- */

.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: var(--dp-space-sm);
}

.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px var(--dp-space-md);
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
}

.metric .label { font-size: 12px; color: var(--dp-text-2); }
.metric .value { font-size: 17px; font-weight: 600; }
.metric.warn .value { color: var(--dp-warn); }

/* --- Steppers ---------------------------------------------------------- */

.steppers {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
  gap: var(--dp-space-sm);
}

.stepper {
  display: inline-flex;
  align-items: center;
  gap: var(--dp-space-sm);
}

.stepper button {
  width: 32px;
  height: 32px;
  border: 1px solid var(--dp-line);
  border-radius: 50%;
  background: var(--dp-surface);
  color: var(--dp-text);
  font-size: 16px;
  cursor: pointer;
  touch-action: manipulation;
}

.stepper button:hover { background: var(--dp-surface-2); }
.stepper .value {
  min-width: 44px;
  text-align: center;
  font-size: 16px;
  font-weight: 600;
}

.stepper.large button { width: var(--dp-touch); height: var(--dp-touch); }
.stepper.large .value { font-size: 28px; min-width: 84px; }

.control {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.control .label { font-size: 12px; color: var(--dp-text-2); }

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field label { font-size: 12px; color: var(--dp-text-2); }

.field input[type="time"] {
  min-height: 40px;
  padding: 8px 10px;
  background: var(--dp-surface-2);
  color: var(--dp-text);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  font-family: inherit;
  font-size: 14px;
}

/* --- Vehicle stage ----------------------------------------------------- */

.stage {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: var(--dp-radius);
}

.stage-status { aspect-ratio: 1 / 1; }
/* The rotated status picture is cropped top and bottom to a 750:550 frame;
   the square source stays centred and is not scaled down. */
.stage-status.stage-rotated { aspect-ratio: 750 / 550; }
.stage-status.stage-rotated img {
  inset: auto 0;
  top: 50%;
  height: auto;
  aspect-ratio: 1 / 1;
  transform: translateY(-50%) rotate(-90deg);
}
.stage-compact { aspect-ratio: 3 / 2; }
.stage-climate { aspect-ratio: 1125 / 642; }
.stage-charging { aspect-ratio: 3 / 2; }
.stage-seats {
  aspect-ratio: 3 / 4;
  max-width: 460px;
  margin: 0 auto;
}

/* --- Animation layer --------------------------------------------------- */

.anim-host {
  display: none;
}

.anim-slot {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
}

.anim-slot video.anim {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

/* The seat wind clip is a partial overlay: its placement over the seats
   picture is approximate and tuned here. */
.stage-seats .anim-slot {
  inset: auto;
  left: 18%;
  top: 20%;
  width: 62%;
  height: 58%;
}

.stage img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}

/* The isometric angle can hide an open front door behind its own panel; the
   pre-rendered outline piece is stacked on top of the open door. */
.stage .open-door-outline {
  opacity: 0.92;
}

.vehicle-photo {
  display: block;
  width: 100%;
  border-radius: var(--dp-radius);
}

/* --- Sessions and feedback -------------------------------------------- */

.session {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: var(--dp-space-sm);
}

.alert {
  background: color-mix(in srgb, var(--dp-warn) 12%, transparent);
  border: 1px solid var(--dp-warn);
  border-radius: var(--dp-radius-sm);
  padding: var(--dp-space-sm) var(--dp-space-md);
  font-size: 14px;
}

.empty {
  padding: var(--dp-space-xl);
  text-align: center;
  color: var(--dp-text-2);
}

/* --- Dashboard cards --------------------------------------------------- */

.card-root {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  padding: var(--dp-space-md) var(--dp-space-lg);
  background: var(--dp-surface);
  border-radius: var(--dp-radius);
  color: var(--dp-text);
}

.card-title {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  font-size: 16px;
  font-weight: 600;
}

.card-title .model {
  font-size: 13px;
  font-weight: 400;
  color: var(--dp-text-2);
}

/* --- Narrow layouts ---------------------------------------------------- */

@media (max-width: 600px) {
  .panel { padding: var(--dp-space-sm) var(--dp-space-sm) var(--dp-space-xl); }
  .app-title { font-size: 18px; }
  .vitals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .steppers { grid-template-columns: 1fr; }
  .segment span { display: none; }
  .segment ha-icon { --mdc-icon-size: 22px; }
  .card-root { padding: var(--dp-space-md); }
}

:host([narrow]) .panel { padding: var(--dp-space-sm) var(--dp-space-sm) var(--dp-space-xl); }
:host([narrow]) .vitals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .steppers { grid-template-columns: 1fr; }
:host([narrow]) .segment span { display: none; }
:host([narrow]) .segment ha-icon { --mdc-icon-size: 22px; }
`;

const PANEL_ICONS = {
  car: "mdi:car",
  car_electric: "mdi:car-electric",
  refresh: "mdi:refresh",
  lock: "mdi:lock",
  unlock: "mdi:lock-open-variant",
  flash: "mdi:car-light-alert",
  horn: "mdi:bullhorn",
  flash_and_honk: "mdi:car-light-alert",
  window: "mdi:window-closed-variant",
  trunk: "mdi:car-back",
  hood: "mdi:car",
  doors: "mdi:car-door",
  climate: "mdi:air-conditioner",
  charging: "mdi:battery-charging",
  battery: "mdi:car-battery",
  bolt: "mdi:lightning-bolt",
  tire: "mdi:tire",
  odometer: "mdi:counter",
  range: "mdi:map-marker-distance",
  seat_heating: "mdi:car-seat-heater",
  seat_ventilation: "mdi:car-seat-cooler",
  steering: "mdi:steering",
  cloud: "mdi:cloud-check",
  cloud_off: "mdi:cloud-off-outline",
  clock: "mdi:clock-outline",
  alert: "mdi:alert",
  fuel: "mdi:gas-station",
  schedule: "mdi:calendar-clock",
  charge_limit: "mdi:battery-lock",
  plug_ac: "mdi:ev-plug-type2",
  plug_dc: "mdi:ev-plug-ccs2",
  current_ac: "mdi:current-ac",
  current_dc: "mdi:current-dc",
  mode: "mdi:lightning-bolt",
  temperature: "mdi:thermometer",
  humidity: "mdi:water-percent",
  pm25: "mdi:blur",
  driving: "mdi:steering",
  ambience: "mdi:air-filter",
};

// ---- 40_helpers.js ----
// Shared helpers: language, texts, entity discovery and formatting.

const PANEL_DOMAINS = Object.keys(PANEL_KEYS);

/** Resolve the Home Assistant UI language to one of the shipped texts. */
function panelLanguage(hass) {
  const raw =
    (hass && hass.locale && hass.locale.language) ||
    (hass && hass.language) ||
    PANEL_BASE_LANGUAGE;
  const base = String(raw).toLowerCase().split("-")[0];
  return PANEL_BORROWED_LANGUAGES[base] || base;
}

/** Translate a key for the given language, with English fallback. */
function translate(language, key, values) {
  const texts = PANEL_TEXTS[language] || PANEL_TEXTS[PANEL_BASE_LANGUAGE];
  let text = key in texts ? texts[key] : key;
  if (values) {
    for (const [name, value] of Object.entries(values)) {
      text = text.split(`{${name}}`).join(value);
    }
  }
  return text;
}

// Panel paths mapped to the directory names used by the official model ZIP.
const DYNAMIC_ASSET_DIRS = {
  estado_planta: "overlook",
  overlook: "overlook",
  side: "side",
  aa: "ac",
  bateria: "battery",
  asientos: "seat",
};
const DYNAMIC_ASSET_CATEGORIES = {
  estado_planta: "status",
  overlook: "status",
  side: "hero",
  aa: "climate",
  bateria: "charging",
  asientos: "seats",
};

/** Absolute URL of an asset, preferring the vehicle's official pack. */
function assetUrl(path, vehicle) {
  const parts = String(path).split("/");
  const directory = parts[1];
  const category = DYNAMIC_ASSET_CATEGORIES[directory];
  const assets = vehicle && vehicle.modelAssets;
  if (assets && category && assets.categories.includes(category)) {
    const mapped = DYNAMIC_ASSET_DIRS[directory];
    const relative = parts.slice(2).join("/");
    return `${assets.base}/${mapped}/${relative}?v=${assets.md5 || PANEL_VERSION}`;
  }
  return `${PANEL_ASSETS_URL}/${path}?v=${PANEL_VERSION}`;
}

/** Escape a value before inserting it into generated HTML. */
function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

/** Upper-case alphanumerics of the vehicle model, for containment checks. */
function normalizeModelText(value) {
  return String(value || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "");
}

/** Whether the vehicle exposes the integration's fuel sensors. */
function hasFuelEntities(vehicle) {
  return PANEL_FUEL_ENTITY_KEYS.some((key) =>
    Boolean(entityFor(vehicle, "sensor", key)),
  );
}

/**
 * Model profile of a vehicle: S05 EV, S05 PHEV, S07 or generic.
 *
 * The registry model carries the integration's series name; inside the S05
 * family the fuel sensors (created only for fuel vehicles) split EV and PHEV,
 * the same discriminator the integration uses.
 */
function detectProfile(vehicle) {
  const model = normalizeModelText(vehicle && vehicle.model);
  if (PANEL_S05_MODEL_TOKENS.some((token) => model.includes(token))) {
    return hasFuelEntities(vehicle)
      ? PANEL_PROFILE_S05_PHEV
      : PANEL_PROFILE_S05_EV;
  }
  if (PANEL_S07_MODEL_TOKENS.some((token) => model.includes(token))) {
    return PANEL_PROFILE_S07;
  }
  return PANEL_PROFILE_GENERIC;
}

/**
 * Artwork and layout of a vehicle's model, or null when the model has none:
 * the vehicle image entity and the entity-driven sections are the fallback.
 */
function layoutFor(vehicle) {
  if (!vehicle) return null;
  if (vehicle.profile === PANEL_PROFILE_S07) return PANEL_MODEL_LAYOUTS.s07;
  if (
    vehicle.profile === PANEL_PROFILE_S05_EV ||
    vehicle.profile === PANEL_PROFILE_S05_PHEV
  ) {
    return PANEL_MODEL_LAYOUTS.s05;
  }
  return null;
}

/**
 * Group the integration entities into vehicles by device id.
 *
 * Reads the frontend registries only: `hass.entities` carries the platform,
 * device and translation key of every entity, and `hass.devices` the vehicle
 * names. No entity id is assumed, so the panel works on any installation.
 * Every vehicle also carries its detected model profile.
 */
function discoverVehicles(hass) {
  const vehicles = new Map();
  const entities = (hass && hass.entities) || {};
  for (const entry of Object.values(entities)) {
    if (entry.platform !== "deepal") continue;
    if (!entry.device_id || !entry.translation_key) continue;
    if (entry.disabled_by || entry.hidden_by) continue;
    const domain = String(entry.entity_id).split(".")[0];
    if (!PANEL_DOMAINS.includes(domain)) continue;
    let vehicle = vehicles.get(entry.device_id);
    if (!vehicle) {
      const device = ((hass && hass.devices) || {})[entry.device_id] || {};
      vehicle = {
        deviceId: entry.device_id,
        name: device.name_by_user || device.name || "Deepal",
        model: device.model || "",
        profile: null,
        entities: {},
      };
      vehicles.set(entry.device_id, vehicle);
    }
    vehicle.entities[domain] = vehicle.entities[domain] || {};
    vehicle.entities[domain][entry.translation_key] = entry.entity_id;
  }
  for (const vehicle of vehicles.values()) {
    vehicle.profile = detectProfile(vehicle);
    const imageId = vehicle.entities.image?.vehicle_image;
    const imageState = imageId && hass.states ? hass.states[imageId] : null;
    const attributes = (imageState && imageState.attributes) || {};
    const base = attributes.model_assets_base;
    const categories = attributes.model_assets_categories;
    vehicle.modelAssets =
      base && Array.isArray(categories)
        ? {
            base,
            categories,
            md5: attributes.model_assets_md5 || "",
          }
        : null;
  }
  return [...vehicles.values()].sort((left, right) =>
    left.name.localeCompare(right.name),
  );
}

/**
 * Entity id of a vehicle key, or undefined when the vehicle lacks it.
 *
 * Views use the friendly keys of PANEL_KEYS; a raw translation key also
 * resolves because the lookup falls back to the given name.
 */
function entityFor(vehicle, domain, key) {
  const ids = vehicle.entities[domain];
  if (!ids) return undefined;
  const translationKey =
    (PANEL_KEYS[domain] && PANEL_KEYS[domain][key]) || key;
  return ids[translationKey];
}

/** Entity state, or null for unknown/unavailable/missing states. */
function stateFor(hass, entityId) {
  if (!entityId) return null;
  const state = hass.states[entityId];
  if (!state || state.state === "unknown" || state.state === "unavailable") {
    return null;
  }
  return state;
}

/** True when the entity exists and reports "on". */
function isOn(hass, entityId) {
  const state = stateFor(hass, entityId);
  return state !== null && state.state === "on";
}

/** Localized entity value, or null when there is nothing to show. */
function formatState(hass, entityId) {
  const state = stateFor(hass, entityId);
  if (!state) return null;
  if (hass.formatEntityState) {
    return hass.formatEntityState(state);
  }
  const unit = state.attributes.unit_of_measurement;
  return unit ? `${state.state} ${unit}` : state.state;
}

/** Numeric attribute of an entity, or null. */
function attributeFor(hass, entityId, name) {
  const state = stateFor(hass, entityId);
  if (!state) return null;
  const value = state.attributes[name];
  return value === undefined ? null : value;
}

/** Localized date and time for an ISO timestamp, falling back to the raw value. */
function formatDateTime(language, value) {
  if (!value) return "—";
  try {
    return new Intl.DateTimeFormat(language, {
      dateStyle: "short",
      timeStyle: "short",
    }).format(new Date(value));
  } catch (error) {
    return String(value);
  }
}

/** Relative age of an ISO timestamp ("3 min ago"), or null when unreadable. */
function formatRelativeTime(language, value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  const steps = [
    { limit: 60, unit: "second" },
    { limit: 3600, unit: "minute", div: 60 },
    { limit: 86400, unit: "hour", div: 3600 },
    { limit: 2592000, unit: "day", div: 86400 },
    { limit: Infinity, unit: "month", div: 2592000 },
  ];
  for (const step of steps) {
    if (Math.abs(seconds) < step.limit) {
      const amount = step.div ? Math.round(seconds / step.div) : seconds;
      try {
        return new Intl.RelativeTimeFormat(language, {
          numeric: "auto",
          style: "short",
        }).format(-amount, step.unit);
      } catch (error) {
        return null;
      }
    }
  }
  return null;
}

/** Value of a time entity as HH:MM, or null when it has no usable state. */
function formatTime(hass, entityId) {
  const state = stateFor(hass, entityId);
  if (!state) return null;
  const raw = String(state.state);
  return /^\d{1,2}:\d{2}/.test(raw) ? raw.slice(0, 5).padStart(5, "0") : raw;
}

// ---- 45_vehicle.js ----
// Shared vehicle rendering used by the sidebar panel and the dashboard card:
// the layered status picture, the state chips and the pointer-freeze helper
// that keeps clicks reliable while states update.

/**
 * Never replace the DOM while a pointer is pressed inside the element: a
 * state update between pointerdown and pointerup would detach the button
 * under the finger and swallow the click. Updates are deferred to release.
 */
function installPointerFreeze(element) {
  element._pointerDown = false;
  element._renderPending = false;
  element.shadowRoot.addEventListener("pointerdown", () => {
    element._pointerDown = true;
  });
  element._releasePointer = () => {
    if (!element._pointerDown) return;
    element._pointerDown = false;
    if (element._renderPending) {
      element._renderPending = false;
      element._render();
    }
  };
  window.addEventListener("pointerup", element._releasePointer, true);
  window.addEventListener("pointercancel", element._releasePointer, true);
  element._removePointerFreeze = () => {
    window.removeEventListener("pointerup", element._releasePointer, true);
    window.removeEventListener("pointercancel", element._releasePointer, true);
  };
}

/** Language of a standalone element (no hass yet), for the card picker. */
function browserLanguage() {
  const raw =
    (typeof document !== "undefined" &&
      document.documentElement &&
      document.documentElement.lang) ||
    (typeof navigator !== "undefined" && navigator.language) ||
    PANEL_BASE_LANGUAGE;
  return panelLanguage({ locale: { language: raw } });
}

/**
 * Layered picture of the vehicle's model profile, or the vehicle image entity
 * when the model has no artwork.
 *
 * Every piece is drawn, closed or open: the base image (Ocar1) is the bare
 * body and the doors, hood and trunk come as separate layers.
 */
function vehicleStageHtml(hass, vehicle, options = {}) {
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const layout = layoutFor(vehicle);

  if (layout && layout.status) {
    const layers = [
      isOn(hass, entity("binary_sensor", "hood"))
        ? "hood_open"
        : "hood_closed",
      isOn(hass, entity("binary_sensor", "trunk"))
        ? "trunk_open"
        : "trunk_closed",
    ];
    const part = (doorKey, windowKey, position) => {
      const doorOpen = isOn(hass, entity("binary_sensor", doorKey));
      const windowOpen = isOn(hass, entity("binary_sensor", windowKey));
      if (doorOpen && windowOpen) layers.push(`door_window_${position}_open`);
      else if (doorOpen) layers.push(`door_${position}_open`);
      else if (windowOpen) layers.push(`window_${position}_open`);
      else layers.push(`door_${position}_closed`);
    };
    part("door_front_left", "window_front_left", "front_left");
    part("door_front_right", "window_front_right", "front_right");
    part("door_rear_left", "window_rear_left", "rear_left");
    part("door_rear_right", "window_rear_right", "rear_right");
    if (
      ["low_beam", "high_beam", "position_lamp"].some((key) =>
        isOn(hass, entity("binary_sensor", key)),
      )
    ) {
      layers.push("lights_on");
    }
    const stage = layout.status;
    const stageClass = `stage stage-status${options.rotate ? " stage-rotated" : ""}`;
    return `<div class="${stageClass}">
      <img src="${assetUrl(stage.base, vehicle)}" alt="">
      ${layers
        .map((name) => `<img src="${assetUrl(stage.layers[name], vehicle)}" alt="">`)
        .join("")}
    </div>`;
  }

  const imageId = entity("image", "vehicle_image");
  const picture = imageId ? attributeFor(hass, imageId, "entity_picture") : null;
  if (!picture) return "";
  return vehiclePhotoHtml(hass, vehicle);
}

/**
 * State-aware 3/4 picture for the compact card, or "" when the model has no
 * compact artwork.
 *
 * The staged isometric pack is drawn in its documented order: the far-side
 * doors and the closed trunk stay behind the bare body, then the open trunk,
 * hood and near-side doors go in front. Window glass is drawn only while the
 * window is up, with a variant for an open door. Open doors get their outline
 * piece on top, which is what makes the state readable at this angle.
 */
function vehicleCompactStageHtml(hass, vehicle) {
  const layout = layoutFor(vehicle)?.compact;
  if (!layout) return "";
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const on = (key) => isOn(hass, entity("binary_sensor", key));
  const layers = layout.layers;
  const images = [];
  const outlines = [];

  const add = (name) => {
    if (name) images.push(`<img src="${assetUrl(name)}" alt="">`);
  };
  const side = (position) => {
    const doorOpen = on(`door_${position}`);
    const windowOpen = on(`window_${position}`);
    if (!windowOpen) {
      add(
        layers[
          doorOpen
            ? `window_${position}_closed_door_open`
            : `window_${position}_closed`
        ],
      );
    }
    add(layers[doorOpen ? `door_${position}_open` : `door_${position}_closed`]);
    if (doorOpen) outlines.push(layers[`door_${position}_outline`]);
  };

  side("rear_right");
  side("front_right");
  if (!on("trunk")) add(layers.trunk_closed);
  add(layout.base);
  if (on("trunk")) add(layers.trunk_open);
  add(on("hood") ? layers.hood_open : layers.hood_closed);
  side("rear_left");
  side("front_left");
  if (["low_beam", "high_beam", "position_lamp"].some((key) => on(key))) {
    add(layers.lights_on);
  }
  for (const name of outlines) {
    if (!name) continue;
    images.push(
      `<img class="open-door-outline" src="${assetUrl(name)}" alt="">`,
    );
  }
  return `<div class="stage stage-compact">${images.join("")}</div>`;
}

/** Vehicle image entity as a picture ("" when the image is unavailable). */
function vehiclePhotoHtml(hass, vehicle) {
  const imageId = entityFor(vehicle, "image", "vehicle_image");
  const picture = imageId
    ? attributeFor(hass, imageId, "entity_picture")
    : null;
  if (!picture) return "";
  return `<img class="vehicle-photo" src="${escapeHtml(picture)}" alt="">`;
}

/** Official hero picture (3/4 view), or "" when the model has none. */
function vehicleHeroHtml(vehicle) {
  const hero = layoutFor(vehicle)?.hero;
  if (hero) {
    return `<img class="vehicle-photo" src="${assetUrl(hero, vehicle)}" alt="">`;
  }
  // S05 has no bundled hero, but the official pack may provide one.
  if (
    vehicle.modelAssets &&
    vehicle.modelAssets.categories.includes("hero")
  ) {
    return `<img class="vehicle-photo" src="${assetUrl("s05/side/carDefault.png", vehicle)}" alt="">`;
  }
  return "";
}

/**
 * Central-locking chip displayed below the status picture, or "" when the
 * vehicle has no lock entity or its state is unknown.
 */
function vehicleLockChipHtml(hass, vehicle, t) {
  const locked = lockStateFor(hass, vehicle);
  if (locked === null) return "";
  return `<span class="chip ${locked ? "" : "warn"}">
    <ha-icon icon="${locked ? PANEL_ICONS.lock : PANEL_ICONS.unlock}"></ha-icon>
    ${escapeHtml(locked ? t("locked") : t("unlocked"))}
  </span>`;
}

/** Locked state shared by the vitals strip and the lock control. */
function lockStateFor(hass, vehicle) {
  const lockId = entityFor(vehicle, "lock", "doors");
  const lockState = lockId ? stateFor(hass, lockId) : null;
  if (lockState) return lockState.state === "locked";
  const binaryId = entityFor(vehicle, "binary_sensor", "doors_locked");
  const binary = stateFor(hass, binaryId);
  if (binary) return binary.state !== "on";
  return null;
}

/** Translated charge status, falling back to the charging and plug flags. */
function chargeStatusText(hass, vehicle, t) {
  const statusId = entityFor(vehicle, "sensor", "charge_status");
  const status = stateFor(hass, statusId);
  if (status) return formatState(hass, statusId);
  if (isOn(hass, entityFor(vehicle, "binary_sensor", "charging"))) {
    return t("charging");
  }
  if (isOn(hass, entityFor(vehicle, "binary_sensor", "charger_plugged"))) {
    return t("plugged");
  }
  return t("not_plugged");
}

/**
 * Persistent vitals: battery (with a charging bolt), range, lock state and
 * data freshness. Rendered on every tab, above the segmented control. The
 * dashboard cards pass `{ lock: false }` to leave the lock state to their
 * own state chips.
 */
function vitalsHtml(hass, vehicle, t, options = {}) {
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const vital = (label, value, icon, cls = "", title = "") => `
    <div class="vital ${cls}" title="${escapeHtml(title)}">
      <ha-icon icon="${icon}"></ha-icon>
      <div class="vital-body">
        <span class="vital-label">${escapeHtml(label)}</span>
        <span class="vital-value">${escapeHtml(value ?? "—")}</span>
      </div>
    </div>`;
  const items = [];

  const charging = isOn(hass, entity("binary_sensor", "charging"));
  items.push(
    vital(
      t("battery"),
      formatState(hass, entity("sensor", "battery")),
      charging ? PANEL_ICONS.bolt : PANEL_ICONS.battery,
      charging ? "on" : "",
    ),
  );

  items.push(
    vital(
      t("range"),
      formatState(hass, entity("sensor", "range")),
      PANEL_ICONS.range,
    ),
  );

  const locked =
    options.lock === false ? null : lockStateFor(hass, vehicle);
  if (locked !== null) {
    items.push(
      vital(
        t("central_lock"),
        locked ? t("locked") : t("unlocked"),
        locked ? PANEL_ICONS.lock : PANEL_ICONS.unlock,
        locked ? "" : "warn",
      ),
    );
  }

  const connectedId = entity("binary_sensor", "connected");
  const connectedState = stateFor(hass, connectedId);
  const connected = connectedState ? connectedState.state === "on" : null;
  const updatedId = entity("sensor", "updated");
  const updatedState = stateFor(hass, updatedId);
  const relative = updatedState
    ? formatRelativeTime(
        panelLanguage(hass),
        updatedState.state,
      )
    : null;
  const absolute = updatedState
    ? formatDateTime(panelLanguage(hass), updatedState.state)
    : "";
  items.push(
    vital(
      t("updated"),
      relative || (connected === true ? t("online") : null),
      connected === false ? PANEL_ICONS.cloud_off : PANEL_ICONS.cloud,
      connected === false ? "warn" : "",
      absolute,
    ),
  );

  return `<div class="vitals">${items.join("")}</div>`;
}

/** Active health warnings, in the panel's stable order. */
function activeWarnings(hass, vehicle) {
  return PANEL_WARNINGS.filter(([key]) =>
    isOn(hass, entityFor(vehicle, "binary_sensor", key)),
  );
}

/** Warnings section: rendered only while at least one warning is active. */
function warningsHtml(hass, vehicle, t) {
  const active = activeWarnings(hass, vehicle);
  if (!active.length) return "";
  return `<div class="section">
    <div class="section-head">
      <ha-icon icon="${PANEL_ICONS.alert}"></ha-icon>
      <span class="section-title">${escapeHtml(t("warnings"))}</span>
    </div>
    <div class="chips">${active
      .map(
        ([key, icon]) =>
          `<span class="chip warn"><ha-icon icon="${icon}"></ha-icon>${escapeHtml(t(key))}</span>`,
      )
      .join("")}</div>
  </div>`;
}

// ---- 50_panel.js ----
// Panel shell: app bar, persistent vitals, segmented tabs, action dispatch
// and error feedback. The views live in 60_status.js, 61_climate.js,
// 62_charging.js and 63_driving.js and hang off the prototype.

class DeepalPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "status";
    this._deviceId = null;
    this._error = "";
    this._vehicles = [];
    this._animHost = null;
    this._animVideos = {};
    this._animStates = {};
    this._animSupported = null;
    this._animProbeStarted = false;
    installPointerFreeze(this);
    this.shadowRoot.addEventListener("click", (event) => this._onClick(event));
    this.shadowRoot.addEventListener("change", (event) => this._onChange(event));
  }

  disconnectedCallback() {
    this._removePointerFreeze();
  }

  set hass(hass) {
    this._hass = hass;
    this._syncVehicles();
    // Rebuilding the whole panel on every global state change would replace
    // the buttons under the pointer and swallow clicks.
    if (
      this.shadowRoot.innerHTML &&
      this._renderKey() === this._renderKeyCache
    ) {
      return;
    }
    if (this._pointerDown) {
      // A finger or the mouse button is down: never swap the DOM under it.
      this._renderPending = true;
      return;
    }
    this._render();
  }

  set narrow(narrow) {
    this._narrow = Boolean(narrow);
    this.toggleAttribute("narrow", this._narrow);
    if (this._hass) this._render();
  }

  /** Whether the combined flash-and-horn control is offered (panel only). */
  get _showsFlashAndHonk() {
    return true;
  }

  _syncVehicles() {
    this._vehicles = discoverVehicles(this._hass || {});
    if (!this._vehicles.some((vehicle) => vehicle.deviceId === this._deviceId)) {
      this._deviceId = this._vehicles.length
        ? this._vehicles[0].deviceId
        : null;
    }
    // A model change can drop the selected tab (the Driving tab only exists
    // on the profiles that define it): fall back to the status tab.
    const vehicle = this._vehicle;
    if (
      vehicle &&
      !this._profileTabs(vehicle).some(([key]) => key === this._tab)
    ) {
      this._tab = "status";
    }
  }

  get _vehicle() {
    return (
      this._vehicles.find((vehicle) => vehicle.deviceId === this._deviceId) ||
      null
    );
  }

  get _language() {
    return panelLanguage(this._hass || {});
  }

  _t(key, values) {
    return translate(this._language, key, values);
  }

  async _callService(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data);
      this._error = "";
    } catch (error) {
      const message = error && (error.message || error.error || String(error));
      this._error = message || this._t("command_failed");
    }
    this._render();
  }

  _onClick(event) {
    const target = event.target.closest("[data-action]");
    if (!target || target.disabled) return;
    const action = target.dataset.action;
    if (action === "tab") {
      this._tab = target.dataset.tab;
      this._render();
      return;
    }
    const vehicle = this._vehicle;
    if (!vehicle) return;
    const hass = this._hass;
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    switch (action) {
      case "refresh": {
        const id = entity("button", "refresh");
        if (id) this._callService("button", "press", { entity_id: id });
        return;
      }
      case "press": {
        const id = entity("button", target.dataset.key);
        if (id) this._callService("button", "press", { entity_id: id });
        return;
      }
      case "lock-toggle": {
        const id = entity("lock", "doors");
        if (!id) return;
        const locked = stateFor(hass, id)?.state === "locked";
        this._callService("lock", locked ? "unlock" : "lock", {
          entity_id: id,
        });
        return;
      }
      case "cover-toggle": {
        const id = entity("cover", target.dataset.key);
        if (!id) return;
        const open = stateFor(hass, id)?.state === "open";
        this._callService("cover", open ? "close_cover" : "open_cover", {
          entity_id: id,
        });
        return;
      }
      case "climate-mode": {
        const id = entity("climate", "cabin");
        if (id) {
          this._callService("climate", "set_hvac_mode", {
            entity_id: id,
            hvac_mode: target.dataset.mode,
          });
        }
        return;
      }
      case "temp-step": {
        const id = entity("climate", "cabin");
        if (!id) return;
        const state = stateFor(hass, id);
        const current = Number(
          state?.attributes?.temperature ??
            state?.attributes?.current_temperature ??
            22,
        );
        const min = Number(state?.attributes?.min_temp ?? 16);
        const max = Number(state?.attributes?.max_temp ?? 32);
        const delta = Number(target.dataset.delta || 0);
        const value = Math.min(
          max,
          Math.max(min, Math.round((current + delta) * 2) / 2),
        );
        this._callService("climate", "set_temperature", {
          entity_id: id,
          temperature: value,
        });
        return;
      }
      case "number-step": {
        const id = entity("number", target.dataset.key);
        if (!id) return;
        const state = stateFor(hass, id);
        if (!state) return;
        const min = Number(state.attributes.min ?? 0);
        const max = Number(state.attributes.max ?? 3);
        const step = Number(state.attributes.step ?? 1) || 1;
        const delta = Number(target.dataset.delta || 0) * step;
        const value = Math.min(
          max,
          Math.max(min, Number(state.state) + delta),
        );
        this._callService("number", "set_value", { entity_id: id, value });
        return;
      }
      case "toggle-switch": {
        const id = entity("switch", target.dataset.key);
        if (!id) return;
        this._callService("switch", isOn(hass, id) ? "turn_off" : "turn_on", {
          entity_id: id,
        });
        return;
      }
    }
  }

  _onChange(event) {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    if (target.dataset.action === "select-vehicle") {
      this._deviceId = target.value;
      this._render();
      return;
    }
    if (target.dataset.action === "time-set") {
      const vehicle = this._vehicle;
      if (!vehicle) return;
      const id = entityFor(vehicle, "time", target.dataset.key);
      if (id && target.value) {
        this._callService("time", "set_value", {
          entity_id: id,
          time: target.value,
        });
      }
    }
  }

  /** Cheap signature of everything the panel currently shows. */
  _renderKey() {
    const hass = this._hass || {};
    const vehicle = this._vehicle;
    const parts = [
      this._tab,
      this._deviceId || "",
      this._error,
      this._narrow ? "1" : "0",
      panelLanguage(hass),
      this._vehicles
        .map((candidate) => `${candidate.deviceId}:${candidate.name}`)
        .join("|"),
    ];
    if (vehicle && hass.states) {
      for (const [domain, keys] of Object.entries(PANEL_KEYS)) {
        const ids = vehicle.entities[domain];
        if (!ids) continue;
        for (const key of Object.values(keys)) {
          const entityId = ids[key];
          if (!entityId) continue;
          const state = hass.states[entityId];
          parts.push(
            state
              ? `${entityId}=${state.state};${JSON.stringify(state.attributes)}`
              : `${entityId}=missing`,
          );
        }
      }
    }
    return parts.join("\n");
  }

  _render() {
    if (!this._hass) return;
    try {
      this.shadowRoot.innerHTML = this._renderHtml();
      this._syncAnimations();
    } catch (error) {
      // A render error must never leave the panel stuck on the old view.
      console.error("Deepal panel render failed", error);
      this.shadowRoot.innerHTML = `
        <style>${PANEL_CSS}</style>
        <div class="panel">
          <div class="alert">${escapeHtml(
            String((error && error.message) || error),
          )}</div>
        </div>`;
    }
    this._renderKeyCache = this._renderKey();
  }

  _renderHtml() {
    const vehicle = this._vehicle;
    const vehicles = this._vehicles;
    const refresh = vehicle
      ? entityFor(vehicle, "button", "refresh")
      : undefined;
    const name = vehicle ? vehicle.name : this._t("title");
    const model = vehicle && vehicle.model ? vehicle.model : "";
    const selector =
      vehicles.length > 1
        ? `
      <div class="vehicle-select">
        <ha-icon icon="mdi:car-multiple"></ha-icon>
        <select data-action="select-vehicle" aria-label="${escapeHtml(this._t("vehicle"))}">
          ${vehicles
            .map(
              (candidate) =>
                `<option value="${escapeHtml(candidate.deviceId)}" ${
                  candidate.deviceId === this._deviceId ? "selected" : ""
                }>${escapeHtml(candidate.name)}</option>`,
            )
            .join("")}
        </select>
      </div>`
        : "";
    return `
      <style>${PANEL_CSS}</style>
      <div class="panel">
        <header class="app-bar">
          <h1 class="app-title">
            <ha-icon icon="${PANEL_ICONS.car_electric}"></ha-icon>
            <span>${escapeHtml(name)}</span>
            ${model ? `<span class="model">${escapeHtml(model)}</span>` : ""}
          </h1>
          <div class="spacer"></div>
          ${selector}
          ${
            refresh
              ? `<button class="icon-button" title="${escapeHtml(this._t("refresh_hint"))}" aria-label="${escapeHtml(this._t("refresh_hint"))}" data-action="refresh"><ha-icon icon="${PANEL_ICONS.refresh}"></ha-icon></button>`
              : ""
          }
        </header>
        ${this._error ? `<div class="alert">${escapeHtml(this._error)}</div>` : ""}
        ${
          vehicle
            ? `${vitalsHtml(this._hass, vehicle, (key) => this._t(key))}
               <nav class="segmented" role="tablist">${this._tabsHtml()}</nav>
               <div class="view">${this._renderView(vehicle)}</div>`
            : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`
        }
      </div>`;
  }

  _renderView(vehicle) {
    if (this._tab === "driving") return this._renderDriving(vehicle);
    if (this._tab === "climate") return this._renderClimate(vehicle);
    if (this._tab === "charging") return this._renderCharging(vehicle);
    return this._renderStatus(vehicle);
  }

  /** Tabs of the vehicle's model profile, or the default list. */
  _profileTabs(vehicle) {
    const layout = layoutFor(vehicle);
    return (layout && layout.tabs) || PANEL_TABS;
  }

  _tabsHtml() {
    return this._profileTabs(this._vehicle).map(
      ([key, icon]) => `
      <button class="segment" role="tab" aria-selected="${this._tab === key}" data-action="tab" data-tab="${key}">
        <ha-icon icon="${icon}"></ha-icon>
        <span>${escapeHtml(this._t(`tab_${key}`))}</span>
      </button>`,
    ).join("");
  }
}

// ---- 55_animations.js ----
// Shared animation layer: the profile clips (air start, seat ventilation and
// battery capacity) rendered as progressive enhancement over the matching
// static layers. The panel re-renders by replacing its shadow HTML, so every
// <video> lives in a persistent host node that is re-appended after each
// render and moved into the current stage slot; a clip only plays when its
// transition becomes true (never on page loads or tab changes) and it never
// loops. When the browser cannot render the format (VP9 alpha) or the user
// prefers reduced motion, the static layers stay visible and nothing else
// changes.

DeepalPanel.prototype._animationsEnabled = function () {
  if (typeof window === "undefined") return false;
  if (window.DEEPAL_DISABLE_ANIMATIONS) return false;
  try {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return false;
    }
  } catch (error) {
    // No matchMedia: keep the animations.
  }
  return this._animSupported === true;
};

/** Persistent node that parks the <video> elements between re-renders. */
DeepalPanel.prototype._animationHost = function () {
  if (!this._animHost) {
    this._animHost = document.createElement("div");
    this._animHost.className = "anim-host";
    this._animHost.setAttribute("aria-hidden", "true");
  }
  return this._animHost;
};

/** Cached <video> of one clip for one vehicle. */
DeepalPanel.prototype._animationVideo = function (vehicle, key, source) {
  const cacheKey = `${vehicle.deviceId}:${key}`;
  let video = this._animVideos[cacheKey];
  if (!video) {
    video = document.createElement("video");
    video.className = "anim";
    video.muted = true;
    video.playsInline = true;
    video.preload = "auto";
    video.setAttribute("aria-hidden", "true");
    video.addEventListener("ended", () => {
      video.hidden = true;
    });
    this._animVideos[cacheKey] = video;
  }
  const url = assetUrl(source);
  if (video.dataset.source !== url) {
    video.dataset.source = url;
    video.src = url;
    video.hidden = true;
  }
  return video;
};

/** Transition-relevant state of one vehicle. */
DeepalPanel.prototype._transitionStates = function (vehicle) {
  const hass = this._hass || {};
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const climateId = entity("climate", "cabin");
  const climateState = climateId ? stateFor(hass, climateId) : null;
  const seatOn = [
    "seat_ventilation_front_left",
    "seat_ventilation_front_right",
    "seat_ventilation_rear_left",
    "seat_ventilation_rear_right",
  ].some((key) => {
    const id = entity("number", key);
    const state = id ? stateFor(hass, id) : null;
    return state ? Number(state.state) > 0 : false;
  });
  return {
    climate_on: Boolean(climateState && climateState.state !== "off"),
    charging_on: isOn(hass, entity("binary_sensor", "charging")),
    seat_vent: seatOn,
  };
};

/** Place a clip and play it once (used for a transition that just happened). */
DeepalPanel.prototype._playAnimation = function (vehicle, key) {
  const video = this._animVideos[`${vehicle.deviceId}:${key}`];
  if (!video || !video.closest || !video.closest(".anim-slot")) return;
  video.hidden = false;
  try {
    video.currentTime = 0;
  } catch (error) {
    // Seeking before metadata is loaded: the clip starts from the beginning.
  }
  const started = video.play();
  if (started && typeof started.catch === "function") {
    started.catch(() => {
      video.hidden = true;
    });
  }
};

/**
 * Move every clip of the current model into its stage slot (or park it) and
 * play the clips whose transition just became true.
 */
DeepalPanel.prototype._syncAnimations = function () {
  const vehicle = this._vehicle;
  const layout = layoutFor(vehicle);
  const animations = (layout && layout.animations) || {};
  const host = this._animationHost();
  if (!this.shadowRoot.contains(host)) {
    this.shadowRoot.append(host);
  }

  for (const [key, source] of Object.entries(animations)) {
    const video = this._animationVideo(vehicle, key, source);
    const slot = this.shadowRoot.querySelector(
      `.anim-slot[data-anim="${key}"]`,
    );
    if (slot && this._animationsEnabled()) {
      if (video.parentElement !== slot) slot.appendChild(video);
    } else if (video.parentElement !== host) {
      video.pause();
      video.hidden = true;
      host.appendChild(video);
    }
  }

  if (Object.keys(animations).length && this._animSupported === null) {
    this._startAnimationProbe(Object.values(animations)[0]);
  }

  const states = this._transitionStates(vehicle);
  const previous = this._animStates[vehicle.deviceId];
  this._animStates[vehicle.deviceId] = states;
  if (!previous || !this._animationsEnabled()) return;
  for (const key of Object.keys(states)) {
    if (states[key] && !previous[key] && animations[key]) {
      this._playAnimation(vehicle, key);
    }
  }
};

/**
 * One-time alpha probe: draw a clip frame to a canvas and check that its
 * transparency survives (browsers that ignore VP9 alpha return opaque pixels
 * and fall back to the static layers).
 */
DeepalPanel.prototype._startAnimationProbe = function (source) {
  if (this._animProbeStarted) return;
  this._animProbeStarted = true;
  const probe = document.createElement("video");
  probe.muted = true;
  probe.playsInline = true;
  probe.preload = "auto";
  probe.src = assetUrl(source);
  const finish = (supported) => {
    this._animSupported = supported;
    try {
      this._syncAnimations();
    } catch (error) {
      // A probe failure must never break the render.
    }
  };
  probe.addEventListener(
    "loadeddata",
    () => {
      try {
        const canvas = document.createElement("canvas");
        canvas.width = probe.videoWidth || 2;
        canvas.height = probe.videoHeight || 2;
        const context = canvas.getContext("2d");
        context.drawImage(probe, 0, 0, canvas.width, canvas.height);
        const data = context.getImageData(
          0,
          0,
          canvas.width,
          canvas.height,
        ).data;
        let transparent = false;
        for (let index = 3; index < data.length; index += 4) {
          if (data[index] < 255) {
            transparent = true;
            break;
          }
        }
        finish(transparent);
      } catch (error) {
        finish(false);
      }
    },
    { once: true },
  );
  probe.addEventListener("error", () => finish(false), { once: true });
  window.setTimeout(() => {
    if (this._animSupported === null) finish(false);
  }, 4000);
};

// ---- 60_status.js ----
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
      ${vehicleStageHtml(hass, vehicle, { rotate: true })}
      <div class="chips">${vehicleLockChipHtml(hass, vehicle, t)}</div>
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

// ---- 61_climate.js ----
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
        <img src="${assetUrl(seatsLayout.base, vehicle)}" alt="">
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

// ---- 62_charging.js ----
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
        <img src="${assetUrl(layout.base, vehicle)}" alt="">
        ${
          plugged
            ? `<img src="${assetUrl(charging ? layout.layers.charging : layout.layers.plugged, vehicle)}" alt="">`
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

// ---- 63_driving.js ----
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

// ---- 70_card.js ----
// Dashboard cards. The complete card (`deepal-card`) is the sidebar panel
// inside a card: same vitals, views, actions and update guards. The compact
// card (`deepal-compact-card`) is a glance composition of the same parts:
// title, vitals, the layered picture with its state chips, quick actions and
// a charging strip while the cable is connected.

class DeepalCard extends DeepalPanel {
  constructor() {
    super();
    this._config = {};
  }

  static getStubConfig(hass) {
    const vehicles = discoverVehicles(hass || {});
    return vehicles.length ? { device_id: vehicles[0].deviceId } : {};
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "device_id",
          required: true,
          selector: { device: { filter: [{ integration: "deepal" }] } },
        },
      ],
      computeLabel: () => translate(PANEL_BASE_LANGUAGE, "vehicle"),
    };
  }

  setConfig(config) {
    this._config = config || {};
    if (this._config.device_id) {
      this._deviceId = this._config.device_id;
    }
  }

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, min_rows: 4 };
  }

  get _showsFlashAndHonk() {
    return false;
  }

  _titleHtml() {
    const vehicle = this._vehicle;
    const refresh = vehicle
      ? entityFor(vehicle, "button", "refresh")
      : undefined;
    const name = vehicle ? vehicle.name : this._t("title");
    const model = vehicle && vehicle.model ? vehicle.model : "";
    return `
      <div class="card-title">
        <ha-icon icon="${PANEL_ICONS.car_electric}"></ha-icon>
        <span>${escapeHtml(name)}</span>
        ${model ? `<span class="model">${escapeHtml(model)}</span>` : ""}
        <div class="spacer"></div>
        ${
          refresh
            ? `<button class="icon-button" title="${escapeHtml(this._t("refresh_hint"))}" aria-label="${escapeHtml(this._t("refresh_hint"))}" data-action="refresh"><ha-icon icon="${PANEL_ICONS.refresh}"></ha-icon></button>`
            : ""
        }
      </div>`;
  }

  _renderHtml() {
    const vehicle = this._vehicle;
    return `
      <style>${PANEL_CSS}</style>
      <div class="card-root">
        ${this._titleHtml()}
        ${this._error ? `<div class="alert">${escapeHtml(this._error)}</div>` : ""}
        ${
          vehicle
            ? `${vitalsHtml(this._hass, vehicle, (key) => this._t(key), { lock: false })}
               <nav class="segmented" role="tablist">${this._tabsHtml()}</nav>
               <div class="view">${this._renderView(vehicle)}</div>`
            : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`
        }
      </div>`;
  }
}

class DeepalCompactCard extends DeepalCard {
  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, min_rows: 3 };
  }

  _actionsHtml(vehicle) {
    const hass = this._hass;
    const t = (key) => this._t(key);
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
    const windowsId = entityFor(vehicle, "cover", "windows");
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
    if (entityFor(vehicle, "button", "flash_lights")) {
      tiles.push(
        tile(PANEL_ICONS.flash, t("flash_lights"), null, "press", "flash_lights"),
      );
    }
    if (entityFor(vehicle, "button", "honk_horn")) {
      tiles.push(
        tile(PANEL_ICONS.horn, t("honk_horn"), null, "press", "honk_horn"),
      );
    }
    return tiles.length ? `<div class="tiles">${tiles.join("")}</div>` : "";
  }

  _chargingStripHtml(vehicle) {
    const hass = this._hass;
    const t = (key) => this._t(key);
    const plugged = isOn(hass, entityFor(vehicle, "binary_sensor", "charger_plugged"));
    if (!plugged) return "";
    const metric = (label, value) => `
      <div class="metric">
        <span class="label">${escapeHtml(label)}</span>
        <span class="value">${escapeHtml(value ?? "—")}</span>
      </div>`;
    const current =
      formatState(hass, entityFor(vehicle, "sensor", "ac_charge_current")) ||
      formatState(hass, entityFor(vehicle, "sensor", "dc_charge_current")) ||
      formatState(hass, entityFor(vehicle, "sensor", "charge_current"));
    const remaining =
      formatState(hass, entityFor(vehicle, "sensor", "remaining_time_formatted")) ||
      formatState(hass, entityFor(vehicle, "sensor", "remaining_time"));
    return `
      <div class="section">
        <div class="section-head">
          <ha-icon icon="${PANEL_ICONS.charging}"></ha-icon>
          <span class="section-title">${escapeHtml(t("charging"))}</span>
        </div>
        <div class="metrics">
          ${metric(t("charge_status"), chargeStatusText(hass, vehicle, t))}
          ${current ? metric(t("charge_current"), current) : ""}
          ${remaining ? metric(t("remaining_time"), remaining) : ""}
        </div>
      </div>`;
  }

  _climateHtml(vehicle) {
    const hass = this._hass;
    const t = (key) => this._t(key);
    const climateId = entityFor(vehicle, "climate", "cabin");
    if (!climateId) return "";
    const climateState = stateFor(hass, climateId);
    const climateOn = climateState ? climateState.state !== "off" : false;
    const target = climateState?.attributes?.temperature;
    return `
      <div class="section">
        <div class="section-head">
          <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon>
          <span class="section-title">${escapeHtml(t("climate"))}</span>
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
        <div class="center">
          <div class="stepper">
            <button data-action="temp-step" data-delta="-0.5" aria-label="-">&minus;</button>
            <span class="value">${escapeHtml(target != null ? `${target} °C` : "—")}</span>
            <button data-action="temp-step" data-delta="0.5" aria-label="+">+</button>
          </div>
        </div>
      </div>`;
  }

  _renderHtml() {
    const vehicle = this._vehicle;
    return `
      <style>${PANEL_CSS}</style>
      <div class="card-root">
        ${this._titleHtml()}
        ${this._error ? `<div class="alert">${escapeHtml(this._error)}</div>` : ""}
        ${
          vehicle
            ? `${vitalsHtml(this._hass, vehicle, (key) => this._t(key))}
               <div class="section">
                 ${vehicleCompactStageHtml(this._hass, vehicle) || vehiclePhotoHtml(this._hass, vehicle) || vehicleHeroHtml(vehicle) || vehicleStageHtml(this._hass, vehicle)}
               </div>
               ${this._climateHtml(vehicle)}
               ${this._actionsHtml(vehicle)}
               ${this._chargingStripHtml(vehicle)}`
            : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`
        }
      </div>`;
  }
}

// ---- 80_strategy.js ----
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

// ---- 90_registration.js ----
// Register the frontend elements with Home Assistant.
//
// The frontend swaps window.customElements for its polyfilled registry (the
// scoped custom element registry) while it boots. A module Assistant injects
// early — the integration's extra module URL and the Lovelace resource are
// loaded before the frontend is ready — can therefore define the elements on
// a registry that is thrown away later, and the picker then reports "Custom
// element not found". Define, verify and keep re-registering for a while so
// the definitions always end up in the registry Home Assistant is using.

const PANEL_ELEMENTS = [
  [PANEL_TAG, DeepalPanel],
  [CARD_TAG, DeepalCard],
  [CARD_COMPACT_TAG, DeepalCompactCard],
  [STRATEGY_DASHBOARD_TAG, DeepalDashboardStrategy],
  [STRATEGY_VIEW_TAG, DeepalVehicleViewStrategy],
];

// Picker entries: [tag, name text key, description text key].
const PANEL_CARD_ENTRIES = [
  [CARD_TAG, "card_name", "card_description"],
  [CARD_COMPACT_TAG, "compact_card_name", "compact_card_description"],
];

/** Define the elements missing from the current registry, once. */
function registerPanelElements() {
  let registered = true;
  for (const [tag, elementClass] of PANEL_ELEMENTS) {
    // Truthiness, not class identity: a second copy of the bundle defines
    // its own classes, and either copy is fine.
    if (customElements.get(tag)) continue;
    try {
      customElements.define(tag, elementClass);
    } catch (error) {
      // Another copy of the bundle may be defining it right now; the check
      // below decides whether the element is resolvable.
    }
    registered = registered && Boolean(customElements.get(tag));
  }
  if (registered) {
    registerCustomCards();
    registerCustomStrategies();
  }
  return registered;
}

/** Add the dashboard strategy entry once, even when the module loads twice. */
function registerCustomStrategies() {
  window.customStrategies = window.customStrategies || [];
  if (
    window.customStrategies.some(
      (entry) => entry.type === STRATEGY_DASHBOARD_TYPE,
    )
  ) {
    return;
  }
  window.customStrategies.push({
    type: STRATEGY_DASHBOARD_TYPE,
    strategyType: "dashboard",
    name: translate(browserLanguage(), "strategy_name"),
    description: translate(browserLanguage(), "strategy_description"),
    documentationURL: "https://github.com/Sunek0/ha-deepal-alternative",
  });
}

/** Add the card picker entries once, even when the module loads twice. */
function registerCustomCards() {
  window.customCards = window.customCards || [];
  for (const [type, nameKey, descriptionKey] of PANEL_CARD_ENTRIES) {
    if (window.customCards.some((entry) => entry.type === type)) continue;
    window.customCards.push({
      type,
      name: translate(browserLanguage(), nameKey),
      description: translate(browserLanguage(), descriptionKey),
      // No live preview in the picker: a preview can race the module load
      // and fail with "custom element not found"; the card is added from the
      // list and configured afterwards.
      preview: false,
      documentationURL: "https://github.com/Sunek0/ha-deepal-alternative",
    });
  }
}

// Verify for a while: the registry can be replaced right after this module
// runs, so re-register whenever a definition is missing, and stop once the
// definitions have stayed put (or after the ceiling).
const PANEL_REGISTRATION_STARTED = Date.now();
const PANEL_REGISTRATION_GRACE_MS = 5000;
const PANEL_REGISTRATION_CEILING_MS = 30000;
registerPanelElements();
const PANEL_REGISTRATION_TIMER = window.setInterval(() => {
  const elapsed = Date.now() - PANEL_REGISTRATION_STARTED;
  const settled = registerPanelElements() && elapsed > PANEL_REGISTRATION_GRACE_MS;
  if (settled || elapsed > PANEL_REGISTRATION_CEILING_MS) {
    window.clearInterval(PANEL_REGISTRATION_TIMER);
  }
}, 250);
window.addEventListener("load", registerPanelElements, { once: true });
