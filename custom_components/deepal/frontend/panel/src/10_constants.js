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

// Per-model artwork, keyed by model family. Every file in `status`, `climate`,
// `charging` and `seats` shares the canvas size of its base image, so the
// panel only stacks them in order. `tabs` is the model-conditional tab list;
// `hero` is the 3/4 picture the compact card falls back to when the vehicle
// image is unavailable; `animations` maps a transition key to the clip played
// when that transition happens, always over the matching static layer.
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
