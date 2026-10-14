// Constants shared by the panel modules. The build script prepends the
// PANEL_VERSION constant before this file.
const PANEL_TAG = "deepal-panel";
const CARD_TAG = "deepal-card";
const PANEL_BASE_LANGUAGE = "en";
// Languages that borrow another language's texts verbatim.
const PANEL_BORROWED_LANGUAGES = { ca: "es", gl: "es", eu: "es" };
const PANEL_ASSETS_URL = "/deepal/frontend/assets";

// Tabs, in order: [key, icon]. The key is also the text key "tab_<key>".
const PANEL_TABS = [
  ["status", "mdi:car"],
  ["climate", "mdi:air-conditioner"],
  ["charging", "mdi:battery-charging"],
];

// Layered S05 views. Every file shares the canvas size of its base image,
// so the panel only stacks them in order. Paths are relative to the assets
// URL. Models without a layout fall back to the vehicle image entity.
const PANEL_S05_LAYOUT = {
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
};

// Entity keys (translation_key) the panel looks up, grouped by platform.
// Optional keys are skipped when the vehicle does not expose them.
const PANEL_KEYS = {
  sensor: {
    battery: "battery_level",
    range: "remaining_range",
    odometer: "total_odometer",
    charge_current: "charge_current",
    remaining_time: "remaining_charge_time",
    inside_temperature: "inside_temperature",
    tire_front_left: "tire_pressure_front_left",
    tire_front_right: "tire_pressure_front_right",
    tire_rear_left: "tire_pressure_rear_left",
    tire_rear_right: "tire_pressure_rear_right",
  },
  binary_sensor: {
    charging: "charging",
    charger_plugged: "charger_plugged",
    engine: "engine",
    doors_locked: "doors_lock_state",
    any_door_open: "any_door_open",
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
    tire_alarm_front_left: "tire_alarm_front_left",
    tire_alarm_front_right: "tire_alarm_front_right",
    tire_alarm_rear_left: "tire_alarm_rear_left",
    tire_alarm_rear_right: "tire_alarm_rear_right",
    rear_fog_lamp: "rear_fog_lamp",
  },
  lock: { doors: "doors" },
  cover: { windows: "windows", trunk: "trunk" },
  climate: { cabin: "cabin_climate" },
  number: {
    seat_heating_front_left: "seat_heating_level_front_left",
    seat_heating_front_right: "seat_heating_level_front_right",
    seat_ventilation_front_left: "seat_ventilation_level_front_left",
    seat_ventilation_front_right: "seat_ventilation_level_front_right",
  },
  switch: { steering_wheel_heating: "steering_wheel_heating" },
  button: {
    refresh: "refresh_vehicle_data",
    flash_lights: "flash_lights",
    honk_horn: "honk_horn",
  },
  image: { vehicle_image: "vehicle_image" },
};
