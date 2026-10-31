// GENERATED FILE - do not edit; run scripts/build_panel.py after changing src/ or texts/.
const PANEL_VERSION = "1.7.0";

// ---- 10_constants.js ----
// Constants shared by the card modules. The build script prepends the
// PANEL_VERSION constant before this file.
const CARD_TAG = "deepal-card";
const PANEL_BASE_LANGUAGE = "en";
// Languages that borrow another language's texts verbatim.
const PANEL_BORROWED_LANGUAGES = { ca: "es", gl: "es", eu: "es" };
// Native names of the shipped card languages, shown in the settings selector.
const PANEL_LANGUAGE_NAMES = {
  en: "English",
  es: "Español",
  de: "Deutsch",
  fr: "Français",
  it: "Italiano",
  pt: "Português",
};
const PANEL_ASSETS_URL = "/deepal/frontend/assets";

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
// so the card only stacks them in order. `compact` is the state-aware 3/4
// artwork; `hero` is the static fallback when the vehicle image is missing;
// `animations` maps a transition key to the clip played when that transition
// happens, always over the matching static layer.
const PANEL_MODEL_LAYOUTS = {
  s05: {
    status: {
      // The base is the bare body: hood, trunk and doors are separate pieces
      // that must always be drawn, closed or open, like the original panel.
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

// Entity keys (translation_key) the card looks up, grouped by platform.
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
    license_plate: "license_plate",
    inside_pm25: "inside_pm25",
    air_quality_level: "air_quality_level",
    updated: "last_updated",
    fuel_level: "fuel_level",
    fuel_range: "fuel_range",
    fuel_volume: "fuel_volume",
    fuel_tank_capacity: "fuel_tank_capacity",
    climate_target_temperature: "climate_target_temperature",
    fan_level: "fan_level",
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
    warning_airbag: "warning_airbag",
    warning_coolant_temperature: "warning_coolant_temperature",
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

// Health warnings, in the order the card lists them, with their icons. The
// warnings section only renders while at least one of them is active.
const PANEL_WARNINGS = [
  ["warning_12v_battery", "mdi:car-battery"],
  ["warning_tpms", "mdi:car-tire-alert"],
  ["warning_airbag", "mdi:airbag"],
  ["warning_coolant_temperature", "mdi:coolant-temperature"],
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
  "de": {
    "actions": "Aktionen",
    "actions_hint": "Steuerungstasten anordnen, ausblenden und konfigurieren.",
    "air_quality_level": "Luftqualität",
    "alarm": "Alarm",
    "alerts_only": "Nur aktive Warnungen",
    "all_warnings": "Alle Warnungen",
    "ambience": "Ambiente",
    "appearance": "Darstellung",
    "auto": "Automatisch",
    "automatic": "Automatisch",
    "battery": "Batterie",
    "battery_low": "Batterie schwach",
    "bottom": "Unten",
    "button_labels": "Beschriftungen",
    "button_layout": "Anordnung",
    "button_primary": "Haupttasten",
    "button_size": "Größe",
    "cabin_humidity": "Luftfeuchtigkeit",
    "cable_idle": "Kabel angeschlossen, lädt nicht",
    "cancel": "Abbrechen",
    "card_description": "Konfigurierbare Deepal-Fahrzeugkarte: Hero-Bild, Steuerung, Klima, Laden, Diagnose und Einstellungen",
    "card_name": "Deepal-Fahrzeug",
    "card_padding": "Kartenränder",
    "central_lock": "Zentralverriegelung",
    "charge_current": "Ladestrom",
    "charge_limit": "Ladelimit",
    "charge_mode": "Ladeart",
    "charge_schedule": "Ladezeitplan",
    "charge_schedule_end": "Bis",
    "charge_schedule_start": "Von",
    "charge_session_current": "Aktueller Ladevorgang",
    "charge_session_last": "Letzter Ladevorgang",
    "charge_status": "Ladestatus",
    "charging": "Lädt",
    "climate": "Klima",
    "climate_off": "Ausschalten",
    "climate_on": "Einschalten",
    "close": "Schließen",
    "close_trunk": "Kofferraum schließen",
    "close_windows": "Fenster schließen",
    "closed": "Geschlossen",
    "cloud": "Verbindung",
    "command_failed": "Der Befehl ist fehlgeschlagen",
    "confirm": "Bestätigung anfordern",
    "confirm_climate_text": "Es wird ein Befehl an die Klimaanlage des Fahrzeugs gesendet.",
    "confirm_climate_title": "Klima ändern?",
    "confirm_find_text": "Die Lichter blinken und die Hupe ertönt.",
    "confirm_find_title": "Fahrzeug finden?",
    "confirm_flash_text": "Die Fahrzeuglichter blinken.",
    "confirm_flash_title": "Lichthupe?",
    "confirm_honk_text": "Die Hupe des Fahrzeugs ertönt.",
    "confirm_honk_title": "Hupen?",
    "confirm_lock_text": "Das Fahrzeug wird verriegelt.",
    "confirm_lock_title": "Fahrzeug verriegeln?",
    "confirm_refresh_text": "Es werden neue Daten vom Fahrzeug angefordert.",
    "confirm_refresh_title": "Daten aktualisieren?",
    "confirm_text": "Möchtest du den Befehl an das Fahrzeug senden?",
    "confirm_title": "Aktion bestätigen",
    "confirm_trunk_text": "Der Kofferraum wird geöffnet.",
    "confirm_trunk_title": "Kofferraum öffnen?",
    "confirm_unlock_text": "Das Fahrzeug wird entriegelt.",
    "confirm_unlock_title": "Fahrzeug entriegeln?",
    "confirm_windows_text": "Alle Fenster werden geöffnet.",
    "confirm_windows_title": "Fenster öffnen?",
    "controls": "Steuerung",
    "current_ac": "Strom (AC)",
    "current_dc": "Strom (DC)",
    "diag_mode": "Diagnosemodus",
    "diagnostics": "Diagnose",
    "disconnected": "Keine Verbindung zur Cloud",
    "doors": "Türen",
    "driving": "Fahrt",
    "energy": "Energie",
    "engine": "Motor",
    "epb": "Feststellbremse",
    "flash_and_honk": "Lichthupe und Hupe",
    "flash_lights": "Lichthupe",
    "front_left": "Vorne links",
    "front_right": "Vorne rechts",
    "fuel": "Kraftstoff",
    "fuel_range": "Kraftstoffreichweite",
    "fuel_tank_capacity": "Tankvolumen",
    "gear": "Gang",
    "half": "Halb",
    "hero": "Hero-Bild",
    "high_beam": "Fernlicht",
    "honk_horn": "Hupe",
    "hood": "Motorhaube",
    "image_aspect": "Seitenverhältnis",
    "image_entity": "Fahrzeugbild",
    "image_scale": "Zoom",
    "image_style": "Fahrzeugbild",
    "info": "Informationen",
    "inside_pm25": "PM2,5",
    "inside_temperature": "Innen",
    "isometric": "Isometrisch",
    "key_battery_low": "Schlüsselbatterie",
    "language": "Sprache",
    "level": "Stufe",
    "lights": "Lichter",
    "lock": "Verriegeln",
    "lock_doors": "Türen verriegeln",
    "locked": "Verriegelt",
    "low_beam": "Abblendlicht",
    "mileage_yesterday": "Gestern",
    "model": "Modell",
    "more": "Mehr",
    "move_down": "Nach unten",
    "move_up": "Nach oben",
    "name": "Name",
    "no_vehicle": "Noch kein Fahrzeug konfiguriert",
    "none": "Keine",
    "normal": "Normal",
    "not_plugged": "Kabel nicht angeschlossen",
    "odometer": "Kilometerstand",
    "off": "Aus",
    "offline": "Offline",
    "on": "Ein",
    "online": "Online",
    "open": "Offen",
    "open_trunk": "Kofferraum öffnen",
    "open_windows": "Fenster öffnen",
    "outside_temperature": "Außen",
    "photo": "Fotos",
    "planta": "Draufsicht",
    "plate": "Kennzeichen",
    "plugged": "Kabel angeschlossen",
    "position_lamp": "Standlicht",
    "range": "Reichweite",
    "rear_left": "Hinten links",
    "rear_right": "Hinten rechts",
    "refresh": "Aktualisieren",
    "refresh_hint": "Neue Daten vom Fahrzeug anfordern",
    "remaining_time": "Restzeit",
    "seat_heating": "Heizung",
    "seat_ventilation": "Belüftung",
    "seats": "Sitze",
    "section_actions": "Steuerung",
    "section_charging": "Laden",
    "section_climate": "Klima",
    "section_diagnostics": "Diagnose",
    "section_driving": "Fahrt",
    "section_energy": "Energie",
    "section_info": "Informationen",
    "section_status": "Status",
    "section_tires": "Reifen",
    "sections": "Bereiche",
    "sections_hint": "Bereiche anordnen und nicht benötigte ausblenden.",
    "sensors": "Sensoren",
    "session_end_level": "Endstand",
    "session_end_range": "Endreichweite",
    "session_ended": "Beendet",
    "session_start_level": "Startstand",
    "session_start_range": "Startreichweite",
    "session_started": "Gestartet",
    "settings": "Einstellungen",
    "settings_actions": "Aktionen",
    "settings_ambiguous": "Mehrere Karten nutzen dieses Fahrzeug; die Einstellungen wurden in deinem Konto gespeichert.",
    "settings_appearance": "Darstellung",
    "settings_hero": "Fahrzeug",
    "settings_local": "Einstellungen im Konto gespeichert; das Dashboard konnte nicht geschrieben werden.",
    "settings_saved": "Einstellungen im Dashboard gespeichert.",
    "settings_sections": "Bereiche",
    "settings_sensors": "Sensoren",
    "show": "Anzeigen",
    "show_on_hero": "Im Hero-Bild anzeigen",
    "show_settings": "Einstellungstaste anzeigen",
    "speed": "Geschwindigkeit",
    "status": "Status",
    "steering_wheel": "Lenkrad",
    "target_temperature": "Zieltemperatur",
    "tire_max": "Maximaldruck",
    "tire_min": "Minimaldruck",
    "tire_unit": "Druckeinheit",
    "tires": "Reifen",
    "title": "Deepal",
    "toast_position": "Position der Meldungen",
    "toasts": "Bildschirmmeldungen",
    "top": "Oben",
    "trip_mileage": "Fahrt",
    "trunk": "Kofferraum",
    "unavailable": "Nicht verfügbar",
    "unknown": "Unbekannt",
    "unlock": "Entriegeln",
    "unlock_doors": "Türen entriegeln",
    "unlocked": "Entriegelt",
    "updated": "Aktualisiert",
    "vehicle": "Fahrzeug",
    "vehicle_status": "Fahrzeugstatus",
    "warning_12v_battery": "12-V-Batterie",
    "warning_abs": "ABS",
    "warning_airbag": "Airbag",
    "warning_brake": "Bremsen",
    "warning_brake_fluid": "Bremsflüssigkeit",
    "warning_coolant_temperature": "Kühlmittel",
    "warning_eps": "Lenkung",
    "warning_power_limit": "Leistungslimit",
    "warning_power_system": "Antriebssystem",
    "warning_tpms": "Reifendruck",
    "warning_traction_battery_low": "Traktionsbatterie",
    "warnings": "Warnungen",
    "windows": "Fenster",
  },
  "en": {
    "actions": "Actions",
    "actions_hint": "Order, hide and configure the control buttons.",
    "air_quality_level": "Air quality",
    "alarm": "Alarm",
    "alerts_only": "Active warnings only",
    "all_warnings": "All warnings",
    "ambience": "Ambience",
    "appearance": "Appearance",
    "auto": "Automatic",
    "automatic": "Automatic",
    "battery": "Battery",
    "battery_low": "Battery low",
    "bottom": "Bottom",
    "button_labels": "Labels",
    "button_layout": "Layout",
    "button_primary": "Primary buttons",
    "button_size": "Size",
    "cabin_humidity": "Humidity",
    "cable_idle": "Cable connected, not charging",
    "cancel": "Cancel",
    "card_description": "Configurable Deepal vehicle card: hero, controls, climate, charging, diagnostics and settings",
    "card_name": "Deepal vehicle",
    "card_padding": "Card margins",
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
    "cloud": "Connection",
    "command_failed": "The command failed",
    "confirm": "Ask for confirmation",
    "confirm_climate_text": "A command will be sent to the vehicle climate.",
    "confirm_climate_title": "Change the climate?",
    "confirm_find_text": "The lights will flash and the horn will sound.",
    "confirm_find_title": "Find the vehicle?",
    "confirm_flash_text": "The vehicle lights will flash.",
    "confirm_flash_title": "Flash the lights?",
    "confirm_honk_text": "The vehicle horn will sound.",
    "confirm_honk_title": "Sound the horn?",
    "confirm_lock_text": "The vehicle will lock.",
    "confirm_lock_title": "Lock the vehicle?",
    "confirm_refresh_text": "Fresh data will be requested from the vehicle.",
    "confirm_refresh_title": "Refresh the data?",
    "confirm_text": "Do you want to send the command to the vehicle?",
    "confirm_title": "Confirm action",
    "confirm_trunk_text": "The trunk will open.",
    "confirm_trunk_title": "Open the trunk?",
    "confirm_unlock_text": "The vehicle will unlock.",
    "confirm_unlock_title": "Unlock the vehicle?",
    "confirm_windows_text": "All windows will open.",
    "confirm_windows_title": "Open the windows?",
    "controls": "Controls",
    "current_ac": "Current (AC)",
    "current_dc": "Current (DC)",
    "diag_mode": "Diagnostics mode",
    "diagnostics": "Diagnostics",
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
    "half": "Half",
    "hero": "Hero image",
    "high_beam": "High beam",
    "honk_horn": "Horn",
    "hood": "Hood",
    "image_aspect": "Aspect ratio",
    "image_entity": "Vehicle image",
    "image_scale": "Zoom",
    "image_style": "Vehicle image",
    "info": "Information",
    "inside_pm25": "PM2.5",
    "inside_temperature": "Inside",
    "isometric": "Isometric",
    "key_battery_low": "Key fob battery",
    "language": "Language",
    "level": "Level",
    "lights": "Lights",
    "lock": "Lock",
    "lock_doors": "Lock doors",
    "locked": "Locked",
    "low_beam": "Low beam",
    "mileage_yesterday": "Yesterday",
    "model": "Model",
    "more": "More",
    "move_down": "Move down",
    "move_up": "Move up",
    "name": "Name",
    "no_vehicle": "No vehicle configured yet",
    "none": "None",
    "normal": "Normal",
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
    "photo": "Photos",
    "planta": "Plant",
    "plate": "Plate",
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
    "section_actions": "Controls",
    "section_charging": "Charging",
    "section_climate": "Climate",
    "section_diagnostics": "Diagnostics",
    "section_driving": "Driving",
    "section_energy": "Energy",
    "section_info": "Information",
    "section_status": "Status",
    "section_tires": "Tyres",
    "sections": "Sections",
    "sections_hint": "Order the sections and hide the ones you do not need.",
    "sensors": "Sensors",
    "session_end_level": "End level",
    "session_end_range": "End range",
    "session_ended": "Ended",
    "session_start_level": "Start level",
    "session_start_range": "Start range",
    "session_started": "Started",
    "settings": "Settings",
    "settings_actions": "Actions",
    "settings_ambiguous": "More than one card uses this vehicle; the settings were saved to your account.",
    "settings_appearance": "Appearance",
    "settings_hero": "Vehicle",
    "settings_local": "Settings saved to your account; the dashboard could not be written.",
    "settings_saved": "Settings saved to the dashboard.",
    "settings_sections": "Sections",
    "settings_sensors": "Sensors",
    "show": "Show",
    "show_on_hero": "Show on the hero",
    "show_settings": "Show the settings button",
    "speed": "Speed",
    "status": "Status",
    "steering_wheel": "Steering wheel",
    "target_temperature": "Target temperature",
    "tire_max": "Maximum pressure",
    "tire_min": "Minimum pressure",
    "tire_unit": "Tyre unit",
    "tires": "Tires",
    "title": "Deepal",
    "toast_position": "Message position",
    "toasts": "On-screen messages",
    "top": "Top",
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
    "warning_airbag": "Airbag",
    "warning_brake": "Brakes",
    "warning_brake_fluid": "Brake fluid",
    "warning_coolant_temperature": "Coolant",
    "warning_eps": "Steering",
    "warning_power_limit": "Power limit",
    "warning_power_system": "Power system",
    "warning_tpms": "Tire pressure",
    "warning_traction_battery_low": "Traction battery",
    "warnings": "Warnings",
    "windows": "Windows",
  },
  "es": {
    "actions": "Acciones",
    "actions_hint": "Ordena, oculta y configura los botones de control.",
    "air_quality_level": "Calidad del aire",
    "alarm": "Alarma",
    "alerts_only": "Solo avisos activos",
    "all_warnings": "Todos los avisos",
    "ambience": "Ambiente",
    "appearance": "Apariencia",
    "auto": "Automático",
    "automatic": "Automático",
    "battery": "Batería",
    "battery_low": "Batería baja",
    "bottom": "Abajo",
    "button_labels": "Etiquetas",
    "button_layout": "Disposición",
    "button_primary": "Botones principales",
    "button_size": "Tamaño",
    "cabin_humidity": "Humedad",
    "cable_idle": "Cable conectado, sin cargar",
    "cancel": "Cancelar",
    "card_description": "Tarjeta configurable del vehículo Deepal: imagen, controles, clima, carga, diagnóstico y ajustes",
    "card_name": "Vehículo Deepal",
    "card_padding": "Márgenes de la tarjeta",
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
    "cloud": "Conexión",
    "command_failed": "El comando ha fallado",
    "confirm": "Pedir confirmación",
    "confirm_climate_text": "Se enviará una orden al clima del coche.",
    "confirm_climate_title": "¿Cambiar el clima?",
    "confirm_find_text": "Las luces parpadearán y sonará el claxon.",
    "confirm_find_title": "¿Localizar el coche?",
    "confirm_flash_text": "Las luces del coche parpadearán.",
    "confirm_flash_title": "¿Destello de luces?",
    "confirm_honk_text": "Sonará el claxon del coche.",
    "confirm_honk_title": "¿Claxon?",
    "confirm_lock_text": "El coche se bloqueará.",
    "confirm_lock_title": "¿Bloquear el coche?",
    "confirm_refresh_text": "Se pedirán datos nuevos al coche.",
    "confirm_refresh_title": "¿Actualizar los datos?",
    "confirm_text": "¿Quieres enviar la orden al coche?",
    "confirm_title": "Confirmar acción",
    "confirm_trunk_text": "El maletero se abrirá.",
    "confirm_trunk_title": "¿Abrir el maletero?",
    "confirm_unlock_text": "El coche se desbloqueará.",
    "confirm_unlock_title": "¿Desbloquear el coche?",
    "confirm_windows_text": "Todas las ventanillas se abrirán.",
    "confirm_windows_title": "¿Abrir las ventanillas?",
    "controls": "Controles",
    "current_ac": "Corriente (AC)",
    "current_dc": "Corriente (DC)",
    "diag_mode": "Modo de diagnóstico",
    "diagnostics": "Diagnóstico",
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
    "half": "Mitad",
    "hero": "Imagen",
    "high_beam": "Largas",
    "honk_horn": "Claxon",
    "hood": "Capó",
    "image_aspect": "Proporción",
    "image_entity": "Imagen del vehículo",
    "image_scale": "Zoom",
    "image_style": "Imagen del coche",
    "info": "Información",
    "inside_pm25": "PM2.5",
    "inside_temperature": "Interior",
    "isometric": "Isométrico",
    "key_battery_low": "Pila de la llave",
    "language": "Idioma",
    "level": "Nivel",
    "lights": "Luces",
    "lock": "Cerrar",
    "lock_doors": "Cerrar puertas",
    "locked": "Cerrado",
    "low_beam": "Cortas",
    "mileage_yesterday": "Ayer",
    "model": "Modelo",
    "more": "Más",
    "move_down": "Bajar",
    "move_up": "Subir",
    "name": "Nombre",
    "no_vehicle": "Aún no hay ningún vehículo configurado",
    "none": "Sin márgenes",
    "normal": "Normal",
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
    "photo": "Fotos",
    "planta": "Planta",
    "plate": "Matrícula",
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
    "section_actions": "Controles",
    "section_charging": "Carga",
    "section_climate": "Clima",
    "section_diagnostics": "Diagnóstico",
    "section_driving": "Conducción",
    "section_energy": "Energía",
    "section_info": "Información",
    "section_status": "Estado",
    "section_tires": "Neumáticos",
    "sections": "Secciones",
    "sections_hint": "Ordena las secciones y oculta las que no necesites.",
    "sensors": "Sensores",
    "session_end_level": "Nivel final",
    "session_end_range": "Autonomía final",
    "session_ended": "Fin",
    "session_start_level": "Nivel inicial",
    "session_start_range": "Autonomía inicial",
    "session_started": "Inicio",
    "settings": "Ajustes",
    "settings_actions": "Acciones",
    "settings_ambiguous": "Hay más de una tarjeta con este coche; los ajustes se guardaron en tu cuenta.",
    "settings_appearance": "Apariencia",
    "settings_hero": "Vehículo",
    "settings_local": "Ajustes guardados en tu cuenta; no se pudo escribir el dashboard.",
    "settings_saved": "Ajustes guardados en el dashboard.",
    "settings_sections": "Secciones",
    "settings_sensors": "Sensores",
    "show": "Mostrar",
    "show_on_hero": "Mostrar en la imagen",
    "show_settings": "Mostrar el botón de ajustes",
    "speed": "Velocidad",
    "status": "Estado",
    "steering_wheel": "Volante",
    "target_temperature": "Temperatura",
    "tire_max": "Presión máxima",
    "tire_min": "Presión mínima",
    "tire_unit": "Unidad de presión",
    "tires": "Neumáticos",
    "title": "Deepal",
    "toast_position": "Posición de los mensajes",
    "toasts": "Mensajes en pantalla",
    "top": "Arriba",
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
    "warning_airbag": "Airbag",
    "warning_brake": "Frenos",
    "warning_brake_fluid": "Líquido de frenos",
    "warning_coolant_temperature": "Refrigerante",
    "warning_eps": "Dirección",
    "warning_power_limit": "Límite de potencia",
    "warning_power_system": "Sistema de potencia",
    "warning_tpms": "Presión de neumáticos",
    "warning_traction_battery_low": "Batería de tracción",
    "warnings": "Avisos",
    "windows": "Ventanillas",
  },
  "fr": {
    "actions": "Actions",
    "actions_hint": "Ordonnez, masquez et configurez les boutons de commande.",
    "air_quality_level": "Qualité de l'air",
    "alarm": "Alarme",
    "alerts_only": "Alertes actives uniquement",
    "all_warnings": "Toutes les alertes",
    "ambience": "Ambiance",
    "appearance": "Apparence",
    "auto": "Automatique",
    "automatic": "Automatique",
    "battery": "Batterie",
    "battery_low": "Batterie faible",
    "bottom": "Bas",
    "button_labels": "Libellés",
    "button_layout": "Disposition",
    "button_primary": "Boutons principaux",
    "button_size": "Taille",
    "cabin_humidity": "Humidité",
    "cable_idle": "Câble branché, pas en charge",
    "cancel": "Annuler",
    "card_description": "Carte configurable du véhicule Deepal : image, commandes, climatisation, charge, diagnostic et réglages",
    "card_name": "Véhicule Deepal",
    "card_padding": "Marges de la carte",
    "central_lock": "Verrouillage centralisé",
    "charge_current": "Courant de charge",
    "charge_limit": "Limite de charge",
    "charge_mode": "Type de charge",
    "charge_schedule": "Plage de charge",
    "charge_schedule_end": "Jusqu'à",
    "charge_schedule_start": "Depuis",
    "charge_session_current": "Charge en cours",
    "charge_session_last": "Dernière charge",
    "charge_status": "État de charge",
    "charging": "En charge",
    "climate": "Climatisation",
    "climate_off": "Éteindre",
    "climate_on": "Allumer",
    "close": "Fermer",
    "close_trunk": "Fermer le coffre",
    "close_windows": "Fermer les vitres",
    "closed": "Fermé",
    "cloud": "Connexion",
    "command_failed": "La commande a échoué",
    "confirm": "Demander confirmation",
    "confirm_climate_text": "Une commande sera envoyée à la climatisation du véhicule.",
    "confirm_climate_title": "Changer la climatisation ?",
    "confirm_find_text": "Les phares clignoteront et le klaxon retentira.",
    "confirm_find_title": "Localiser le véhicule ?",
    "confirm_flash_text": "Les phares du véhicule clignoteront.",
    "confirm_flash_title": "Appels de phares ?",
    "confirm_honk_text": "Le klaxon du véhicule retentira.",
    "confirm_honk_title": "Klaxonner ?",
    "confirm_lock_text": "Le véhicule sera verrouillé.",
    "confirm_lock_title": "Verrouiller le véhicule ?",
    "confirm_refresh_text": "De nouvelles données seront demandées au véhicule.",
    "confirm_refresh_title": "Actualiser les données ?",
    "confirm_text": "Voulez-vous envoyer la commande au véhicule ?",
    "confirm_title": "Confirmer l'action",
    "confirm_trunk_text": "Le coffre s'ouvrira.",
    "confirm_trunk_title": "Ouvrir le coffre ?",
    "confirm_unlock_text": "Le véhicule sera déverrouillé.",
    "confirm_unlock_title": "Déverrouiller le véhicule ?",
    "confirm_windows_text": "Toutes les vitres s'ouvriront.",
    "confirm_windows_title": "Ouvrir les vitres ?",
    "controls": "Commandes",
    "current_ac": "Courant (CA)",
    "current_dc": "Courant (CC)",
    "diag_mode": "Mode diagnostic",
    "diagnostics": "Diagnostic",
    "disconnected": "Pas de connexion au cloud",
    "doors": "Portes",
    "driving": "Conduite",
    "energy": "Énergie",
    "engine": "Moteur",
    "epb": "Frein de stationnement",
    "flash_and_honk": "Phares et klaxon",
    "flash_lights": "Appels de phares",
    "front_left": "Avant gauche",
    "front_right": "Avant droit",
    "fuel": "Carburant",
    "fuel_range": "Autonomie carburant",
    "fuel_tank_capacity": "Capacité du réservoir",
    "gear": "Rapport",
    "half": "Moitié",
    "hero": "Image principale",
    "high_beam": "Feux de route",
    "honk_horn": "Klaxon",
    "hood": "Capot",
    "image_aspect": "Format",
    "image_entity": "Image du véhicule",
    "image_scale": "Zoom",
    "image_style": "Image du véhicule",
    "info": "Informations",
    "inside_pm25": "PM2,5",
    "inside_temperature": "Intérieur",
    "isometric": "Isométrique",
    "key_battery_low": "Pile de la clé",
    "language": "Langue",
    "level": "Niveau",
    "lights": "Feux",
    "lock": "Verrouiller",
    "lock_doors": "Verrouiller les portes",
    "locked": "Verrouillé",
    "low_beam": "Feux de croisement",
    "mileage_yesterday": "Hier",
    "model": "Modèle",
    "more": "Plus",
    "move_down": "Descendre",
    "move_up": "Monter",
    "name": "Nom",
    "no_vehicle": "Aucun véhicule configuré",
    "none": "Aucun",
    "normal": "Normal",
    "not_plugged": "Câble débranché",
    "odometer": "Kilométrage",
    "off": "Éteint",
    "offline": "Hors ligne",
    "on": "Allumé",
    "online": "En ligne",
    "open": "Ouvert",
    "open_trunk": "Ouvrir le coffre",
    "open_windows": "Ouvrir les vitres",
    "outside_temperature": "Extérieur",
    "photo": "Photos",
    "planta": "Vue du dessus",
    "plate": "Plaque",
    "plugged": "Câble branché",
    "position_lamp": "Veilleuses",
    "range": "Autonomie",
    "rear_left": "Arrière gauche",
    "rear_right": "Arrière droit",
    "refresh": "Actualiser",
    "refresh_hint": "Demander des données récentes au véhicule",
    "remaining_time": "Temps restant",
    "seat_heating": "Chauffage",
    "seat_ventilation": "Ventilation",
    "seats": "Sièges",
    "section_actions": "Commandes",
    "section_charging": "Charge",
    "section_climate": "Climatisation",
    "section_diagnostics": "Diagnostic",
    "section_driving": "Conduite",
    "section_energy": "Énergie",
    "section_info": "Informations",
    "section_status": "État",
    "section_tires": "Pneus",
    "sections": "Sections",
    "sections_hint": "Ordonnez les sections et masquez celles dont vous n'avez pas besoin.",
    "sensors": "Capteurs",
    "session_end_level": "Niveau final",
    "session_end_range": "Autonomie finale",
    "session_ended": "Terminée",
    "session_start_level": "Niveau initial",
    "session_start_range": "Autonomie initiale",
    "session_started": "Démarrée",
    "settings": "Réglages",
    "settings_actions": "Actions",
    "settings_ambiguous": "Plusieurs cartes utilisent ce véhicule ; les réglages ont été enregistrés dans votre compte.",
    "settings_appearance": "Apparence",
    "settings_hero": "Véhicule",
    "settings_local": "Réglages enregistrés dans votre compte ; le tableau de bord n'a pas pu être écrit.",
    "settings_saved": "Réglages enregistrés dans le tableau de bord.",
    "settings_sections": "Sections",
    "settings_sensors": "Capteurs",
    "show": "Afficher",
    "show_on_hero": "Afficher sur l'image",
    "show_settings": "Afficher le bouton de réglages",
    "speed": "Vitesse",
    "status": "État",
    "steering_wheel": "Volant",
    "target_temperature": "Température cible",
    "tire_max": "Pression maximale",
    "tire_min": "Pression minimale",
    "tire_unit": "Unité de pression",
    "tires": "Pneus",
    "title": "Deepal",
    "toast_position": "Position des messages",
    "toasts": "Messages à l'écran",
    "top": "Haut",
    "trip_mileage": "Trajet",
    "trunk": "Coffre",
    "unavailable": "Indisponible",
    "unknown": "Inconnu",
    "unlock": "Déverrouiller",
    "unlock_doors": "Déverrouiller les portes",
    "unlocked": "Déverrouillé",
    "updated": "Mis à jour",
    "vehicle": "Véhicule",
    "vehicle_status": "État du véhicule",
    "warning_12v_battery": "Batterie 12 V",
    "warning_abs": "ABS",
    "warning_airbag": "Airbag",
    "warning_brake": "Freins",
    "warning_brake_fluid": "Liquide de frein",
    "warning_coolant_temperature": "Liquide de refroidissement",
    "warning_eps": "Direction",
    "warning_power_limit": "Limite de puissance",
    "warning_power_system": "Système de propulsion",
    "warning_tpms": "Pression des pneus",
    "warning_traction_battery_low": "Batterie de traction",
    "warnings": "Alertes",
    "windows": "Vitres",
  },
  "it": {
    "actions": "Azioni",
    "actions_hint": "Ordina, nascondi e configura i pulsanti di comando.",
    "air_quality_level": "Qualità dell'aria",
    "alarm": "Allarme",
    "alerts_only": "Solo avvisi attivi",
    "all_warnings": "Tutti gli avvisi",
    "ambience": "Ambiente",
    "appearance": "Aspetto",
    "auto": "Automatico",
    "automatic": "Automatico",
    "battery": "Batteria",
    "battery_low": "Batteria scarica",
    "bottom": "In basso",
    "button_labels": "Etichette",
    "button_layout": "Disposizione",
    "button_primary": "Pulsanti principali",
    "button_size": "Dimensione",
    "cabin_humidity": "Umidità",
    "cable_idle": "Cavo collegato, in attesa di ricarica",
    "cancel": "Annulla",
    "card_description": "Scheda configurabile del veicolo Deepal: immagine, comandi, clima, ricarica, diagnostica e impostazioni",
    "card_name": "Veicolo Deepal",
    "card_padding": "Margini della scheda",
    "central_lock": "Chiusura centralizzata",
    "charge_current": "Corrente di ricarica",
    "charge_limit": "Limite di ricarica",
    "charge_mode": "Tipo di ricarica",
    "charge_schedule": "Programma di ricarica",
    "charge_schedule_end": "A",
    "charge_schedule_start": "Da",
    "charge_session_current": "Ricarica in corso",
    "charge_session_last": "Ultima ricarica",
    "charge_status": "Stato di ricarica",
    "charging": "In carica",
    "climate": "Clima",
    "climate_off": "Spegni",
    "climate_on": "Accendi",
    "close": "Chiudi",
    "close_trunk": "Chiudi bagagliaio",
    "close_windows": "Chiudi finestrini",
    "closed": "Chiuso",
    "cloud": "Connessione",
    "command_failed": "Il comando non è riuscito",
    "confirm": "Chiedi conferma",
    "confirm_climate_text": "Verrà inviato un comando al clima del veicolo.",
    "confirm_climate_title": "Cambiare il clima?",
    "confirm_find_text": "I fari lampeggeranno e il clacson suonerà.",
    "confirm_find_title": "Trovare il veicolo?",
    "confirm_flash_text": "I fari del veicolo lampeggeranno.",
    "confirm_flash_title": "Lampeggio dei fari?",
    "confirm_honk_text": "Il clacson del veicolo suonerà.",
    "confirm_honk_title": "Suonare il clacson?",
    "confirm_lock_text": "Il veicolo verrà bloccato.",
    "confirm_lock_title": "Bloccare il veicolo?",
    "confirm_refresh_text": "Verranno richiesti nuovi dati al veicolo.",
    "confirm_refresh_title": "Aggiornare i dati?",
    "confirm_text": "Vuoi inviare il comando al veicolo?",
    "confirm_title": "Conferma azione",
    "confirm_trunk_text": "Il bagagliaio si aprirà.",
    "confirm_trunk_title": "Aprire il bagagliaio?",
    "confirm_unlock_text": "Il veicolo verrà sbloccato.",
    "confirm_unlock_title": "Sbloccare il veicolo?",
    "confirm_windows_text": "Tutti i finestrini si apriranno.",
    "confirm_windows_title": "Aprire i finestrini?",
    "controls": "Comandi",
    "current_ac": "Corrente (CA)",
    "current_dc": "Corrente (CC)",
    "diag_mode": "Modalità diagnostica",
    "diagnostics": "Diagnostica",
    "disconnected": "Nessuna connessione al cloud",
    "doors": "Porte",
    "driving": "Guida",
    "energy": "Energia",
    "engine": "Motore",
    "epb": "Freno di stazionamento",
    "flash_and_honk": "Luci e clacson",
    "flash_lights": "Lampeggio fari",
    "front_left": "Anteriore sinistro",
    "front_right": "Anteriore destro",
    "fuel": "Carburante",
    "fuel_range": "Autonomia a carburante",
    "fuel_tank_capacity": "Capacità del serbatoio",
    "gear": "Marcia",
    "half": "Metà",
    "hero": "Immagine principale",
    "high_beam": "Abbaglianti",
    "honk_horn": "Clacson",
    "hood": "Cofano",
    "image_aspect": "Proporzioni",
    "image_entity": "Immagine del veicolo",
    "image_scale": "Zoom",
    "image_style": "Immagine del veicolo",
    "info": "Informazioni",
    "inside_pm25": "PM2,5",
    "inside_temperature": "Interno",
    "isometric": "Isometrico",
    "key_battery_low": "Batteria della chiave",
    "language": "Lingua",
    "level": "Livello",
    "lights": "Luci",
    "lock": "Blocca",
    "lock_doors": "Blocca le porte",
    "locked": "Bloccato",
    "low_beam": "Anabbaglianti",
    "mileage_yesterday": "Ieri",
    "model": "Modello",
    "more": "Altro",
    "move_down": "Sposta giù",
    "move_up": "Sposta su",
    "name": "Nome",
    "no_vehicle": "Nessun veicolo configurato",
    "none": "Nessuno",
    "normal": "Normale",
    "not_plugged": "Cavo scollegato",
    "odometer": "Contachilometri",
    "off": "Spento",
    "offline": "Non in linea",
    "on": "Acceso",
    "online": "In linea",
    "open": "Aperto",
    "open_trunk": "Apri bagagliaio",
    "open_windows": "Apri finestrini",
    "outside_temperature": "Esterno",
    "photo": "Foto",
    "planta": "Vista dall'alto",
    "plate": "Targa",
    "plugged": "Cavo collegato",
    "position_lamp": "Posizione",
    "range": "Autonomia",
    "rear_left": "Posteriore sinistro",
    "rear_right": "Posteriore destro",
    "refresh": "Aggiorna",
    "refresh_hint": "Richiedi dati aggiornati al veicolo",
    "remaining_time": "Tempo rimanente",
    "seat_heating": "Riscaldamento",
    "seat_ventilation": "Ventilazione",
    "seats": "Sedili",
    "section_actions": "Comandi",
    "section_charging": "Ricarica",
    "section_climate": "Clima",
    "section_diagnostics": "Diagnostica",
    "section_driving": "Guida",
    "section_energy": "Energia",
    "section_info": "Informazioni",
    "section_status": "Stato",
    "section_tires": "Pneumatici",
    "sections": "Sezioni",
    "sections_hint": "Ordina le sezioni e nascondi quelle che non ti servono.",
    "sensors": "Sensori",
    "session_end_level": "Livello finale",
    "session_end_range": "Autonomia finale",
    "session_ended": "Terminata",
    "session_start_level": "Livello iniziale",
    "session_start_range": "Autonomia iniziale",
    "session_started": "Avviata",
    "settings": "Impostazioni",
    "settings_actions": "Azioni",
    "settings_ambiguous": "Più schede usano questo veicolo; le impostazioni sono state salvate nel tuo account.",
    "settings_appearance": "Aspetto",
    "settings_hero": "Veicolo",
    "settings_local": "Impostazioni salvate nel tuo account; non è stato possibile scrivere la dashboard.",
    "settings_saved": "Impostazioni salvate nella dashboard.",
    "settings_sections": "Sezioni",
    "settings_sensors": "Sensori",
    "show": "Mostra",
    "show_on_hero": "Mostra sull'immagine",
    "show_settings": "Mostra il pulsante delle impostazioni",
    "speed": "Velocità",
    "status": "Stato",
    "steering_wheel": "Volante",
    "target_temperature": "Temperatura obiettivo",
    "tire_max": "Pressione massima",
    "tire_min": "Pressione minima",
    "tire_unit": "Unità di pressione",
    "tires": "Pneumatici",
    "title": "Deepal",
    "toast_position": "Posizione dei messaggi",
    "toasts": "Messaggi sullo schermo",
    "top": "In alto",
    "trip_mileage": "Viaggio",
    "trunk": "Bagagliaio",
    "unavailable": "Non disponibile",
    "unknown": "Sconosciuto",
    "unlock": "Sblocca",
    "unlock_doors": "Sblocca le porte",
    "unlocked": "Sbloccato",
    "updated": "Aggiornato",
    "vehicle": "Veicolo",
    "vehicle_status": "Stato del veicolo",
    "warning_12v_battery": "Batteria 12 V",
    "warning_abs": "ABS",
    "warning_airbag": "Airbag",
    "warning_brake": "Freni",
    "warning_brake_fluid": "Liquido dei freni",
    "warning_coolant_temperature": "Liquido refrigerante",
    "warning_eps": "Sterzo",
    "warning_power_limit": "Limite di potenza",
    "warning_power_system": "Sistema di propulsione",
    "warning_tpms": "Pressione degli pneumatici",
    "warning_traction_battery_low": "Batteria di trazione",
    "warnings": "Avvisi",
    "windows": "Finestrini",
  },
  "pt": {
    "actions": "Ações",
    "actions_hint": "Ordena, oculta e configura os botões de controlo.",
    "air_quality_level": "Qualidade do ar",
    "alarm": "Alarme",
    "alerts_only": "Apenas avisos ativos",
    "all_warnings": "Todos os avisos",
    "ambience": "Ambiente",
    "appearance": "Aspeto",
    "auto": "Automático",
    "automatic": "Automático",
    "battery": "Bateria",
    "battery_low": "Bateria fraca",
    "bottom": "Em baixo",
    "button_labels": "Etiquetas",
    "button_layout": "Disposição",
    "button_primary": "Botões principais",
    "button_size": "Tamanho",
    "cabin_humidity": "Humidade",
    "cable_idle": "Cabo ligado, sem carregar",
    "cancel": "Cancelar",
    "card_description": "Cartão configurável do veículo Deepal: imagem, controlos, climatização, carregamento, diagnóstico e definições",
    "card_name": "Veículo Deepal",
    "card_padding": "Margens do cartão",
    "central_lock": "Fecho centralizado",
    "charge_current": "Corrente de carga",
    "charge_limit": "Limite de carga",
    "charge_mode": "Tipo de carga",
    "charge_schedule": "Horário de carga",
    "charge_schedule_end": "Até",
    "charge_schedule_start": "Desde",
    "charge_session_current": "Carregamento em curso",
    "charge_session_last": "Último carregamento",
    "charge_status": "Estado de carga",
    "charging": "A carregar",
    "climate": "Climatização",
    "climate_off": "Desligar",
    "climate_on": "Ligar",
    "close": "Fechar",
    "close_trunk": "Fechar bagageira",
    "close_windows": "Fechar janelas",
    "closed": "Fechado",
    "cloud": "Ligação",
    "command_failed": "O comando falhou",
    "confirm": "Pedir confirmação",
    "confirm_climate_text": "Será enviado um comando à climatização do veículo.",
    "confirm_climate_title": "Alterar a climatização?",
    "confirm_find_text": "As luzes vão piscar e a buzina vai soar.",
    "confirm_find_title": "Localizar o veículo?",
    "confirm_flash_text": "As luzes do veículo vão piscar.",
    "confirm_flash_title": "Piscar as luzes?",
    "confirm_honk_text": "A buzina do veículo vai soar.",
    "confirm_honk_title": "Buzinar?",
    "confirm_lock_text": "O veículo será trancado.",
    "confirm_lock_title": "Trancar o veículo?",
    "confirm_refresh_text": "Serão pedidos dados novos ao veículo.",
    "confirm_refresh_title": "Atualizar os dados?",
    "confirm_text": "Queres enviar o comando ao veículo?",
    "confirm_title": "Confirmar ação",
    "confirm_trunk_text": "A bagageira vai abrir.",
    "confirm_trunk_title": "Abrir a bagageira?",
    "confirm_unlock_text": "O veículo será destrancado.",
    "confirm_unlock_title": "Destrancar o veículo?",
    "confirm_windows_text": "Todas as janelas vão abrir.",
    "confirm_windows_title": "Abrir as janelas?",
    "controls": "Controlos",
    "current_ac": "Corrente (CA)",
    "current_dc": "Corrente (CC)",
    "diag_mode": "Modo de diagnóstico",
    "diagnostics": "Diagnóstico",
    "disconnected": "Sem ligação à nuvem",
    "doors": "Portas",
    "driving": "Condução",
    "energy": "Energia",
    "engine": "Motor",
    "epb": "Travão de estacionamento",
    "flash_and_honk": "Luzes e buzina",
    "flash_lights": "Piscar luzes",
    "front_left": "Dianteiro esquerdo",
    "front_right": "Dianteiro direito",
    "fuel": "Combustível",
    "fuel_range": "Autonomia a combustível",
    "fuel_tank_capacity": "Capacidade do depósito",
    "gear": "Mudança",
    "half": "Metade",
    "hero": "Imagem principal",
    "high_beam": "Máximos",
    "honk_horn": "Buzina",
    "hood": "Capô",
    "image_aspect": "Proporção",
    "image_entity": "Imagem do veículo",
    "image_scale": "Zoom",
    "image_style": "Imagem do veículo",
    "info": "Informações",
    "inside_pm25": "PM2,5",
    "inside_temperature": "Interior",
    "isometric": "Isométrico",
    "key_battery_low": "Bateria da chave",
    "language": "Idioma",
    "level": "Nível",
    "lights": "Luzes",
    "lock": "Trancar",
    "lock_doors": "Trancar portas",
    "locked": "Trancado",
    "low_beam": "Médios",
    "mileage_yesterday": "Ontem",
    "model": "Modelo",
    "more": "Mais",
    "move_down": "Mover para baixo",
    "move_up": "Mover para cima",
    "name": "Nome",
    "no_vehicle": "Ainda não há nenhum veículo configurado",
    "none": "Nenhum",
    "normal": "Normal",
    "not_plugged": "Cabo desligado",
    "odometer": "Odómetro",
    "off": "Desligado",
    "offline": "Offline",
    "on": "Ligado",
    "online": "Online",
    "open": "Aberto",
    "open_trunk": "Abrir bagageira",
    "open_windows": "Abrir janelas",
    "outside_temperature": "Exterior",
    "photo": "Fotos",
    "planta": "Vista de cima",
    "plate": "Matrícula",
    "plugged": "Cabo ligado",
    "position_lamp": "Mínimos",
    "range": "Autonomia",
    "rear_left": "Traseiro esquerdo",
    "rear_right": "Traseiro direito",
    "refresh": "Atualizar",
    "refresh_hint": "Pedir dados novos ao veículo",
    "remaining_time": "Tempo restante",
    "seat_heating": "Aquecimento",
    "seat_ventilation": "Ventilação",
    "seats": "Assentos",
    "section_actions": "Controlos",
    "section_charging": "Carregamento",
    "section_climate": "Climatização",
    "section_diagnostics": "Diagnóstico",
    "section_driving": "Condução",
    "section_energy": "Energia",
    "section_info": "Informações",
    "section_status": "Estado",
    "section_tires": "Pneus",
    "sections": "Secções",
    "sections_hint": "Ordena as secções e oculta as que não precisares.",
    "sensors": "Sensores",
    "session_end_level": "Nível final",
    "session_end_range": "Autonomia final",
    "session_ended": "Terminado",
    "session_start_level": "Nível inicial",
    "session_start_range": "Autonomia inicial",
    "session_started": "Iniciado",
    "settings": "Definições",
    "settings_actions": "Ações",
    "settings_ambiguous": "Há mais do que um cartão com este veículo; as definições foram guardadas na tua conta.",
    "settings_appearance": "Aspeto",
    "settings_hero": "Veículo",
    "settings_local": "Definições guardadas na tua conta; não foi possível escrever o dashboard.",
    "settings_saved": "Definições guardadas no dashboard.",
    "settings_sections": "Secções",
    "settings_sensors": "Sensores",
    "show": "Mostrar",
    "show_on_hero": "Mostrar na imagem",
    "show_settings": "Mostrar o botão de definições",
    "speed": "Velocidade",
    "status": "Estado",
    "steering_wheel": "Volante",
    "target_temperature": "Temperatura definida",
    "tire_max": "Pressão máxima",
    "tire_min": "Pressão mínima",
    "tire_unit": "Unidade de pressão",
    "tires": "Pneus",
    "title": "Deepal",
    "toast_position": "Posição das mensagens",
    "toasts": "Mensagens no ecrã",
    "top": "Em cima",
    "trip_mileage": "Viagem",
    "trunk": "Bagageira",
    "unavailable": "Indisponível",
    "unknown": "Desconhecido",
    "unlock": "Destrancar",
    "unlock_doors": "Destrancar portas",
    "unlocked": "Destrancado",
    "updated": "Atualizado",
    "vehicle": "Veículo",
    "vehicle_status": "Estado do veículo",
    "warning_12v_battery": "Bateria de 12 V",
    "warning_abs": "ABS",
    "warning_airbag": "Airbag",
    "warning_brake": "Travões",
    "warning_brake_fluid": "Líquido dos travões",
    "warning_coolant_temperature": "Refrigerante",
    "warning_eps": "Direção",
    "warning_power_limit": "Limite de potência",
    "warning_power_system": "Sistema de propulsão",
    "warning_tpms": "Pressão dos pneus",
    "warning_traction_battery_low": "Bateria de tração",
    "warnings": "Avisos",
    "windows": "Janelas",
  },
};

// ---- 30_styles.js ----
// Card styles: one design-system layer shared by the hero, the sections,
// the settings panel and the editor. Everything is scoped to the shadow root and built on Home
// Assistant theme variables, so it follows light and dark themes.
//
// Views only compose these components; they must not add their own styles:
//   .hero      configurable vehicle image with its overlays
//   .segmented segmented control used by the climate content
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
  height: auto;
  background: transparent;
  color: var(--dp-text);
  font-family: var(--ha-font-family-body, Roboto, sans-serif);
}


:focus-visible {
  outline: 2px solid var(--dp-accent);
  outline-offset: 2px;
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

/* --- Dashboard card ---------------------------------------------------- */

.card-root {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  overflow: hidden;
  padding: var(--dp-space-md) var(--dp-space-lg) var(--dp-space-sm);
  border-radius: var(--dp-radius);
  background: var(--ha-card-background, var(--card-background-color, var(--dp-surface)));
  color: var(--dp-text);
}

.card-root[data-pad="half"] { padding: var(--dp-space-sm); gap: var(--dp-space-sm); }
.card-root[data-pad="none"] { padding: 0 0 var(--dp-space-sm); gap: var(--dp-space-sm); }
.card-root[data-pad="none"] .hero { border-radius: 0; }
.card-root[data-pad="none"] > .section { margin-inline: var(--dp-space-sm); }

.card-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  border: 0;
  border-radius: var(--dp-radius-sm);
  background: transparent;
  color: var(--dp-text-2);
  font-size: 13px;
  cursor: pointer;
}

.card-footer:hover { background: var(--dp-surface-2); color: var(--dp-text); }
.card-footer ha-icon { --mdc-icon-size: 18px; }

/* --- Hero -------------------------------------------------------------- */

.hero {
  position: relative;
  overflow: hidden;
  isolation: isolate;
  border-radius: var(--dp-radius);
  background: #000;
  aspect-ratio: var(--hero-aspect, 3 / 2);
  min-height: 180px;
}

.hero-stage,
.hero-stage .stage {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  aspect-ratio: auto;
  border-radius: 0;
}

.hero-stage .stage img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scale(var(--hero-scale, 1));
  transform-origin: center center;
}

.hero-stage .stage-status.stage-rotated {
  aspect-ratio: auto;
}

.hero-stage .stage-status.stage-rotated img {
  inset: auto 0;
  top: 50%;
  width: 100%;
  height: auto;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  transform: translateY(-50%) rotate(-90deg) scale(var(--hero-scale, 1));
  transform-origin: center center;
}

.hero-stage .vehicle-photo {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transform: scale(var(--hero-scale, 1));
  transform-origin: center center;
}

.hero-shade {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(180deg, rgba(0, 0, 0, 0.62), transparent 42%),
    linear-gradient(0deg, rgba(0, 0, 0, 0.58), transparent 38%);
}

.hero-top,
.hero-bottom {
  position: absolute;
  left: 0;
  right: 0;
  z-index: 2;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--dp-space-sm);
  padding: 12px 14px;
  color: #fff;
}

.hero-top { top: 0; }
.hero-bottom { bottom: 0; align-items: flex-end; }

.hero-title {
  display: flex;
  flex-direction: column;
  min-width: 0;
  text-shadow: 0 1px 8px rgba(0, 0, 0, 0.55);
}

.hero-name {
  overflow: hidden;
  font-size: 18px;
  font-weight: 700;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hero-model,
.hero-plate {
  font-size: 12px;
  opacity: 0.82;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}

.hero-actions .icon-button {
  width: 36px;
  height: 36px;
  background: rgba(0, 0, 0, 0.38);
  color: #fff;
}

.hero-actions .hero-cloud {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  color: #fff;
  filter: drop-shadow(0 1px 4px rgba(0, 0, 0, 0.5));
}

.hero-actions .hero-cloud.ok { color: #6ee7b7; }
.hero-actions .hero-cloud.bad { color: #fca5a5; }

.hero-range {
  position: absolute;
  left: 14px;
  bottom: 48px;
  z-index: 2;
  display: flex;
  align-items: baseline;
  gap: 8px;
  color: #fff;
  text-shadow: 0 2px 12px rgba(0, 0, 0, 0.6);
}

.hero-range .big {
  font-size: 36px;
  font-weight: 300;
  letter-spacing: -0.03em;
  line-height: 1;
}

.hero-range .unit {
  font-size: 14px;
  opacity: 0.82;
}

.hero-range .split {
  display: flex;
  gap: 10px;
  font-size: 12px;
  opacity: 0.88;
}

.hero-range .split span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.hero-range ha-icon { --mdc-icon-size: 15px; }

.hero-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.hero-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 9px;
  border-radius: var(--dp-radius-pill);
  background: rgba(0, 0, 0, 0.46);
  color: #fff;
  font-size: 12px;
  white-space: nowrap;
  backdrop-filter: blur(4px);
}

.hero-chip ha-icon { --mdc-icon-size: 15px; }
.hero-chip.warn { background: rgba(185, 28, 28, 0.82); }
.hero-chip.on { background: rgba(5, 150, 105, 0.82); }

.hero-updated {
  font-size: 11px;
  opacity: 0.72;
  white-space: nowrap;
}

/* --- Actions ----------------------------------------------------------- */

.actions-grid,
.actions-fit {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(82px, 1fr));
  gap: var(--dp-space-sm);
}

.actions-scroll {
  display: flex;
  gap: var(--dp-space-sm);
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: thin;
}

.actions-scroll .action { flex: 0 0 86px; }

.actions-split .actions-main {
  display: grid;
  grid-template-columns: repeat(var(--primary, 4), minmax(0, 1fr));
  gap: var(--dp-space-sm);
}

.actions-split .actions-more {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(82px, 1fr));
  gap: var(--dp-space-sm);
  margin-top: var(--dp-space-sm);
}

.action {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 76px;
  padding: 8px 6px;
  border: 0;
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-family: inherit;
  cursor: pointer;
  touch-action: manipulation;
}

.action:hover { filter: brightness(1.07); }
.action ha-icon { --mdc-icon-size: 24px; }
.action.on { background: var(--dp-accent); color: var(--dp-on-text); }
.action.warn { background: var(--dp-warn); color: var(--dp-on-text); }
.action:disabled { opacity: 0.45; cursor: default; }
.action .action-label { font-size: 11px; font-weight: 600; text-align: center; }
.action .action-value { font-size: 10px; color: var(--dp-text-2); text-align: center; }
.action.on .action-value, .action.warn .action-value { color: var(--dp-on-text); }
.action.size-s { min-height: 60px; }
.action.size-s ha-icon { --mdc-icon-size: 20px; }
.action.size-l { min-height: 92px; }
.action.size-l ha-icon { --mdc-icon-size: 30px; }

.actions-more-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin: var(--dp-space-sm) auto 0;
  padding: 4px 12px;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-pill);
  background: var(--dp-surface);
  color: var(--dp-text-2);
  font-size: 12px;
  cursor: pointer;
}

/* --- Info tiles -------------------------------------------------------- */

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: var(--dp-space-sm);
}

.info-tile {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  min-height: 58px;
  padding: 8px 10px;
  border: 0;
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
}

.info-tile.static { cursor: default; }
.info-tile ha-icon { --mdc-icon-size: 20px; color: var(--dp-text-2); }
.info-tile .info-value { font-size: 15px; font-weight: 600; }
.info-tile .info-label { font-size: 11px; color: var(--dp-text-2); }

/* --- Settings ---------------------------------------------------------- */

deepal-card-settings { display: block; width: 100%; }

.settings-sheet {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: var(--dp-space-md);
  background: rgba(0, 0, 0, 0.58);
}

.settings-panel {
  display: flex;
  flex-direction: column;
  width: min(680px, 100%);
  max-height: 88vh;
  overflow: hidden;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius);
  background: var(--dp-surface);
  color: var(--dp-text);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
}

.settings-panel.embedded {
  position: static;
  width: 100%;
  max-height: none;
  box-shadow: none;
}

.settings-head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  padding: var(--dp-space-md) var(--dp-space-lg);
  border-bottom: 1px solid var(--dp-line);
}

.settings-head h3 {
  flex: 1;
  margin: 0;
  font-size: 17px;
}

.settings-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 50%;
  background: var(--dp-surface-2);
  color: var(--dp-text);
  cursor: pointer;
}

.settings-tabs {
  display: flex;
  gap: 4px;
  padding: 8px var(--dp-space-md);
  overflow-x: auto;
  border-bottom: 1px solid var(--dp-line);
  scrollbar-width: thin;
}

.settings-tab {
  flex: none;
  padding: 7px 11px;
  border: 0;
  border-radius: var(--dp-radius-pill);
  background: transparent;
  color: var(--dp-text-2);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.settings-tab.on { background: var(--dp-accent); color: var(--dp-on-text); }

.settings-body {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  padding: var(--dp-space-md) var(--dp-space-lg) var(--dp-space-xl);
  overflow-y: auto;
}

.settings-group {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-sm);
  padding: var(--dp-space-md);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
}

.settings-group h4 {
  margin: 0;
  font-size: 13px;
  color: var(--dp-text-2);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.setting-row {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  min-height: 38px;
  font-size: 13px;
}

.setting-row > span { flex: 1; min-width: 0; }
.setting-row small { display: block; color: var(--dp-text-2); font-size: 11px; }
.setting-row select,
.setting-row input[type="text"],
.setting-row input[type="number"] {
  min-width: 120px;
  max-width: 190px;
  padding: 7px 8px;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-family: inherit;
  font-size: 13px;
}
.setting-row input[type="checkbox"] { width: 18px; height: 18px; accent-color: var(--dp-accent); }
.setting-row .move { display: inline-flex; gap: 4px; }
.setting-row .move button {
  width: 30px;
  height: 30px;
  border: 1px solid var(--dp-line);
  border-radius: 8px;
  background: var(--dp-surface-2);
  color: var(--dp-text);
  cursor: pointer;
}
.setting-row.off > span { opacity: 0.55; }
.settings-hint { margin: 0; color: var(--dp-text-2); font-size: 12px; }

/* --- Confirm sheet ----------------------------------------------------- */

.confirm-sheet {
  position: fixed;
  inset: 0;
  z-index: 21;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--dp-space-md);
  background: rgba(0, 0, 0, 0.58);
}

.confirm-box {
  width: min(420px, 100%);
  padding: var(--dp-space-lg);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius);
  background: var(--dp-surface);
  color: var(--dp-text);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
}

.confirm-box h3 { margin: 0 0 6px; font-size: 17px; }
.confirm-box p { margin: 0 0 var(--dp-space-md); color: var(--dp-text-2); font-size: 13px; }
.confirm-actions { display: flex; gap: var(--dp-space-sm); }
.confirm-actions button {
  flex: 1;
  min-height: 42px;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
}
.confirm-actions .go { border-color: var(--dp-warn); background: var(--dp-warn); color: var(--dp-on-text); }

.card-toast {
  padding: 8px 12px;
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
  color: var(--dp-text);
  font-size: 12px;
}

.card-toast.pos-top { order: -1; }
.card-toast.ok { background: rgba(5, 150, 105, 0.18); }
.card-toast.warn { background: rgba(185, 28, 28, 0.18); }

.hero-empty {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  min-height: 180px;
  color: rgba(255, 255, 255, 0.55);
}

.hero-empty ha-icon { --mdc-icon-size: 52px; }

/* --- Modal dialogs ----------------------------------------------------- */

.modal-sheet {
  position: fixed;
  inset: 0;
  z-index: 22;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--dp-space-md);
  background: rgba(0, 0, 0, 0.6);
}

.modal-panel {
  display: flex;
  flex-direction: column;
  width: min(820px, 100%);
  max-height: 88vh;
  overflow: hidden;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius);
  background: var(--ha-card-background, var(--card-background-color, var(--dp-surface)));
  color: var(--dp-text);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.45);
}

.modal-head {
  display: flex;
  align-items: center;
  gap: var(--dp-space-sm);
  padding: var(--dp-space-md) var(--dp-space-lg);
  border-bottom: 1px solid var(--dp-line);
}

.modal-head h3 {
  flex: 1;
  margin: 0;
  font-size: 17px;
}

.modal-body {
  padding: var(--dp-space-md) var(--dp-space-lg) var(--dp-space-xl);
  overflow-y: auto;
}

.modal-columns {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--dp-space-lg);
}

.modal-col {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  min-width: 0;
}

.modal-section {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  padding: var(--dp-space-md);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
}

.modal-section h4 {
  margin: 0;
  font-size: 13px;
  color: var(--dp-text-2);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.tire-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--dp-space-sm);
}

.tire-card {
  display: flex;
  align-items: center;
  gap: var(--dp-space-md);
  min-height: 72px;
  padding: var(--dp-space-md);
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface-2);
}

.tire-card ha-icon {
  --mdc-icon-size: 28px;
  color: var(--dp-text-2);
}

.tire-card.warn {
  border-color: var(--dp-warn);
  background: color-mix(in srgb, var(--dp-warn) 16%, var(--dp-surface-2));
}

.tire-card.warn ha-icon { color: var(--dp-warn); }
.tire-label { font-size: 12px; color: var(--dp-text-2); }
.tire-value { font-size: 18px; font-weight: 700; }

/* --- Editor ------------------------------------------------------------ */

.card-editor {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-md);
  padding: var(--dp-space-sm);
}

.card-editor .editor-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.card-editor select {
  min-height: 40px;
  padding: 8px 10px;
  border: 1px solid var(--dp-line);
  border-radius: var(--dp-radius-sm);
  background: var(--dp-surface);
  color: var(--dp-text);
  font-family: inherit;
}

/* --- Narrow layouts ---------------------------------------------------- */

@media (max-width: 600px) {
  .vitals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .steppers { grid-template-columns: 1fr; }
  .card-root { padding: var(--dp-space-md); }
  .card-root[data-pad="none"] { padding: 0 0 var(--dp-space-sm); }
  .hero { aspect-ratio: var(--hero-aspect, 4 / 3); }
  .hero-range .big { font-size: 30px; }
  deepal-card-settings { display: block; width: 100%; }

.settings-sheet { padding: 0; align-items: stretch; }
  .settings-panel { width: 100%; max-height: 100vh; border-radius: 0; }
  .settings-body { padding-bottom: 48px; }
}

:host([narrow]) .vitals { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
:host([narrow]) .steppers { grid-template-columns: 1fr; }
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
  settings: "mdi:tune-variant",
  info: "mdi:information-outline",
  close: "mdi:close",
  up: "mdi:chevron-up",
  down: "mdi:chevron-down",
  more: "mdi:chevron-down",
  speed: "mdi:speedometer",
  gear: "mdi:car-shift-pattern",
  battery_level: "mdi:battery",
  lock_state: "mdi:lock-check",
  power: "mdi:power",
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
 * names. No entity id is assumed, so the card works on any installation.
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

/** Localized whole-number state, or null when there is nothing to show. */
function formatIntegerState(hass, entityId) {
  const state = stateFor(hass, entityId);
  if (!state) return null;
  const value = Number.parseFloat(state.state);
  if (!Number.isFinite(value)) {
    return hass.formatEntityState ? hass.formatEntityState(state) : state.state;
  }
  const text = new Intl.NumberFormat(panelLanguage(hass), {
    maximumFractionDigits: 0,
  }).format(Math.round(value));
  const unit = state.attributes.unit_of_measurement;
  return unit ? `${text} ${unit}` : text;
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
// Shared vehicle rendering used by the dashboard card:
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

/** Locked state used by the hero chip and the lock control. */
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

// ---- 50_card.js ----
// Shared card base: vehicle discovery, service dispatch, state guards and
// render-key handling. The single dashboard card (70_card.js) provides the
// hero, the configurable sections and the settings panel.

class DeepalCardBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._deviceId = null;
    this._error = "";
    this._vehicles = [];
    this._settingsOpen = false;
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
    // Rebuilding the card on every global state change would replace the
    // buttons under the pointer and swallow clicks.
    if (
      this.shadowRoot.innerHTML &&
      this._renderKey() === this._renderKeyCache
    ) {
      return;
    }
    if (this._pointerDown) {
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

  /** The card offers the combined flash-and-horn action. */
  get _showsFlashAndHonk() {
    return true;
  }

  _syncVehicles() {
    this._vehicles = discoverVehicles(this._hass || {});
    const configured = this._config && this._config.device_id;
    if (
      configured &&
      this._vehicles.some((vehicle) => vehicle.deviceId === configured)
    ) {
      this._deviceId = configured;
      return;
    }
    if (!this._vehicles.some((vehicle) => vehicle.deviceId === this._deviceId)) {
      this._deviceId = this._vehicles.length
        ? this._vehicles[0].deviceId
        : null;
    }
  }

  get _vehicle() {
    return (
      this._vehicles.find((vehicle) => vehicle.deviceId === this._deviceId) ||
      null
    );
  }

  get _language() {
    const configured = this._config && this._config.language;
    if (configured && configured !== "auto") {
      return panelLanguage({ locale: { language: configured } });
    }
    return panelLanguage(this._hass || {});
  }

  _t(key, values) {
    return translate(this._language, key, values);
  }

  async _callService(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data);
      this._error = "";
      this._render();
      return true;
    } catch (error) {
      const message = error && (error.message || error.error || String(error));
      this._error = message || this._t("command_failed");
      this._render();
      return false;
    }
  }

  _handleCustomClick() {
    return false;
  }

  _onClick(event) {
    const target = event.target.closest("[data-action]");
    if (!target || target.disabled) return;
    if (this._handleCustomClick(target)) return;
    this._executeAction(target.dataset.action, target.dataset);
  }

  _executeAction(action, data = {}) {
    const target = { dataset: data };
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
    if (this._handleCustomChange && this._handleCustomChange(event)) return;
    const target = event.target.closest("[data-action]");
    if (!target) return;
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

  /** Cheap signature of everything the card currently shows. */
  _renderKey() {
    const hass = this._hass || {};
    const vehicle = this._vehicle;
    const parts = [
      this._deviceId || "",
      this._error,
      this._narrow ? "1" : "0",
      this._settingsOpen ? "settings" : "",
      panelLanguage(hass),
      this._language,
      JSON.stringify(this._config || {}),
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
      for (const entry of [
        ...(this._config.info_custom || []),
        ...(this._config.diag_custom || []),
      ]) {
        const state = hass.states[entry.entity];
        parts.push(
          state
            ? `${entry.entity}=${state.state};${JSON.stringify(state.attributes)}`
            : `${entry.entity}=missing`,
        );
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
      // A render error must never leave the card stuck on the old view.
      console.error("Deepal card render failed", error);
      this.shadowRoot.innerHTML = `
        <style>${PANEL_CSS}</style>
        <div class="card-root">
          <div class="alert">${escapeHtml(
            String((error && error.message) || error),
          )}</div>
        </div>`;
    }
    this._renderKeyCache = this._renderKey();
  }

  _renderHtml() {
    return `<style>${PANEL_CSS}</style><div class="card-root"><div class="empty">${escapeHtml(this._t("no_vehicle"))}</div></div>`;
  }
}

// ---- 55_animations.js ----
// Shared animation layer: the profile clips (air start, seat ventilation and
// battery capacity) rendered as progressive enhancement over the matching
// static layers. The card re-renders by replacing its shadow HTML, so every
// <video> lives in a persistent host node that is re-appended after each
// render and moved into the current stage slot; a clip only plays when its
// transition becomes true (never on page loads or tab changes) and it never
// loops. When the browser cannot render the format (VP9 alpha) or the user
// prefers reduced motion, the static layers stay visible and nothing else
// changes.

DeepalCardBase.prototype._animationsEnabled = function () {
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
DeepalCardBase.prototype._animationHost = function () {
  if (!this._animHost) {
    this._animHost = document.createElement("div");
    this._animHost.className = "anim-host";
    this._animHost.setAttribute("aria-hidden", "true");
  }
  return this._animHost;
};

/** Cached <video> of one clip for one vehicle. */
DeepalCardBase.prototype._animationVideo = function (vehicle, key, source) {
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
DeepalCardBase.prototype._transitionStates = function (vehicle) {
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
DeepalCardBase.prototype._playAnimation = function (vehicle, key) {
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
DeepalCardBase.prototype._syncAnimations = function () {
  const vehicle = this._vehicle;
  if (!vehicle) return;
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
DeepalCardBase.prototype._startAnimationProbe = function (source) {
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

// ---- 61_climate.js ----
// Climate view, built from the shared design system: cabin climate (target
// temperature, on/off and inside temperature), seat heating and ventilation
// for the positions the vehicle exposes, steering wheel heating and the
// ambient readings when available. Every control hides itself when the
// vehicle does not expose its entity.

DeepalCardBase.prototype._renderClimate = function (vehicle) {
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

  if (!climateSection && !seatsSection) return "";
  return `${climateSection}${seatsSection}`;
};

// ---- 62_charging.js ----
// Charging view, built from the shared design system: battery and session
// state, the charge status (enum when the vehicle reports it), current and
// remaining time, the charge schedule, the charge limit when exposed, and the
// session summaries the charging sensor exposes as attributes.

DeepalCardBase.prototype._renderCharging = function (vehicle) {
  const hass = this._hass;
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const t = (key) => this._t(key);

  // --- Charging state ------------------------------------------------------

  const plugged = isOn(hass, entity("binary_sensor", "charger_plugged"));
  const hasChargingData =
    entity("sensor", "battery") ||
    entity("sensor", "charge_status") ||
    entity("binary_sensor", "charging") ||
    entity("binary_sensor", "charger_plugged") ||
    entity("sensor", "ac_charge_current") ||
    entity("sensor", "dc_charge_current") ||
    entity("sensor", "charge_current") ||
    entity("sensor", "remaining_time_formatted") ||
    entity("sensor", "remaining_time") ||
    entity("sensor", "charge_mode") ||
    entity("switch", "charge_schedule") ||
    entity("time", "schedule_start") ||
    entity("time", "schedule_end") ||
    entity("number", "charge_limit") ||
    entity("sensor", "charge_limit_sensor");
  if (!hasChargingData) return "";
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
        <span class="section-title">${escapeHtml(t("charging"))}</span>
      </div>
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

DeepalCardBase.prototype._renderDriving = function (vehicle) {
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

  if (!driving && !ambience) return "";
  return `${driving}${ambience}`;
};

// ---- 70_card.js ----
// The single Deepal dashboard card: a configurable hero, configurable
// sections, an action layout, a visual editor and in-card settings. It uses
// the integration's registry-based discovery and model profiles; 61_climate.js,
// 62_charging.js and 63_driving.js provide the section content.

const CARD_SECTIONS = [
  "actions",
  "status",
  "climate",
  "charging",
  "driving",
  "energy",
  "info",
  "diagnostics",
  "tires",
];
const CARD_BUTTONS = [
  "lock",
  "windows",
  "trunk",
  "climate",
  "tires",
  "flash",
  "honk",
  "find",
];
const CARD_HERO_ITEMS = ["name", "model", "plate", "range", "lock", "cloud", "updated"];
const CARD_CONFIRM_ITEMS = ["unlock", "lock", "trunk", "windows", "climate", "flash", "honk", "find"];
const CARD_INFO_ITEMS = {
  odometer: ["sensor", "odometer", "odometer", "odometer"],
  battery: ["sensor", "battery", "battery", "battery"],
  range: ["sensor", "range", "range", "range"],
  outside_temperature: ["sensor", "outside_temperature", "outside_temperature", "temperature"],
  inside_temperature: ["sensor", "inside_temperature", "inside_temperature", "temperature"],
  cabin_humidity: ["sensor", "cabin_humidity", "cabin_humidity", "humidity"],
  fuel_level: ["sensor", "fuel_level", "fuel", "fuel"],
  fuel_range: ["sensor", "fuel_range", "fuel_range", "fuel"],
  charge_status: ["sensor", "charge_status", "charge_status", "charging"],
  vehicle_status: ["sensor", "vehicle_status", "vehicle_status", "car"],
  speed: ["sensor", "speed", "speed", "speed"],
  gear: ["sensor", "gear", "gear", "gear"],
  trip_mileage: ["sensor", "trip_mileage", "trip_mileage", "odometer"],
  mileage_yesterday: ["sensor", "mileage_yesterday", "mileage_yesterday", "odometer"],
};
const CARD_INFO_IDS = Object.keys(CARD_INFO_ITEMS);

const CARD_DEFAULTS = {
  hero_style: "auto",
  hero_show: ["name", "model", "plate", "range", "lock", "cloud", "updated"],
  order: ["actions", "status", "charging", "info", "climate", "tires", "driving", "energy", "diagnostics"],
  hidden: ["status", "climate", "tires", "driving", "energy"],
  buttons: CARD_BUTTONS.slice(),
  buttons_hidden: [],
  button_layout: "grid",
  button_primary: 4,
  button_size: "m",
  button_labels: "both",
  confirm: ["unlock", "trunk", "windows"],
  info: ["odometer", "battery", "outside_temperature", "inside_temperature", "cabin_humidity", "fuel_level", "charge_status"],
  info_custom: [],
  diag: null,
  diag_mode: "alerts",
  diag_custom: [],
  diag_ignore: [],
  show_settings: true,
  language: "auto",
  toasts: true,
  toast_position: "bottom",
  card_padding: "normal",
  image_scale: 1,
  image_aspect: null,
  tire_unit: "bar",
  tire_min: 2.0,
  tire_max: 3.5,
};
const CARD_SETTING_KEYS = Object.keys(CARD_DEFAULTS);

const cardUniq = (values) => [...new Set(values)];
const cardClone = (value) => JSON.parse(JSON.stringify(value));

function cardFixOrder(values, all) {
  const list = cardUniq((Array.isArray(values) ? values : []).filter((value) => all.includes(value)));
  return [...list, ...all.filter((value) => !list.includes(value))];
}

function mergeCardConfig(yaml, local) {
  const c = { ...cardClone(CARD_DEFAULTS), ...(yaml || {}), ...(local || {}) };
  if (c.hero_style === "carview") c.hero_style = "iso";
  c.hero_show = cardUniq((Array.isArray(c.hero_show) ? c.hero_show : []).filter((value) => CARD_HERO_ITEMS.includes(value)));
  c.order = cardFixOrder(c.order, CARD_SECTIONS);
  c.hidden = cardUniq((Array.isArray(c.hidden) ? c.hidden : []).filter((value) => CARD_SECTIONS.includes(value)));
  c.buttons = cardFixOrder(c.buttons, CARD_BUTTONS);
  c.buttons_hidden = cardUniq((Array.isArray(c.buttons_hidden) ? c.buttons_hidden : []).filter((value) => CARD_BUTTONS.includes(value)));
  c.confirm = cardUniq((Array.isArray(c.confirm) ? c.confirm : []).filter((value) => CARD_CONFIRM_ITEMS.includes(value)));
  c.info = cardUniq((Array.isArray(c.info) ? c.info : []).filter((value) => CARD_INFO_IDS.includes(value)));
  c.info_custom = Array.isArray(c.info_custom) ? c.info_custom.filter((item) => item && item.entity) : [];
  c.diag_custom = Array.isArray(c.diag_custom) ? c.diag_custom.filter((item) => item && item.entity) : [];
  c.diag_ignore = Array.isArray(c.diag_ignore) ? c.diag_ignore : [];
  c.button_primary = Math.max(1, Math.min(6, Number(c.button_primary) || 4));
  c.image_scale = Number(c.image_scale) > 0 ? Number(c.image_scale) : 1;
  c.tire_unit = ["bar", "kPa", "psi"].includes(c.tire_unit) ? c.tire_unit : "bar";
  return c;
}

function cardSettingsOnly(values) {
  const out = {};
  if (values && typeof values === "object" && !Array.isArray(values)) {
    for (const key of CARD_SETTING_KEYS) {
      if (Object.prototype.hasOwnProperty.call(values, key)) out[key] = values[key];
    }
  }
  return out;
}

const CARD_CONFIRM_TEXT = {
  unlock: ["confirm_unlock_title", "confirm_unlock_text"],
  lock: ["confirm_lock_title", "confirm_lock_text"],
  trunk: ["confirm_trunk_title", "confirm_trunk_text"],
  windows: ["confirm_windows_title", "confirm_windows_text"],
  climate: ["confirm_climate_title", "confirm_climate_text"],
  flash: ["confirm_flash_title", "confirm_flash_text"],
  honk: ["confirm_honk_title", "confirm_honk_text"],
  find: ["confirm_find_title", "confirm_find_text"],
};

class DeepalCard extends DeepalCardBase {
  constructor() {
    super();
    this._yaml = {};
    this._local = {};
    this._remoteLoaded = false;
    this._settingsTab = "hero";
    this._settingsScroll = 0;
    this._settingsDirty = false;
    this._uiRestored = false;
    this._modal = null;
    this._confirm = null;
    this._moreOpen = false;
    this._toast = null;
    this._saveTimer = null;
    this.shadowRoot.addEventListener("settings-change", (event) => this._patch(event.detail || {}));
    this.shadowRoot.addEventListener("settings-close", () => {
      this._settingsOpen = false;
      this._settingsScroll = 0;
      this._saveUiState();
      this._render();
      this._commitSettings();
    });
  }

  static getStubConfig(hass) {
    const vehicles = discoverVehicles(hass || {});
    return vehicles.length ? { device_id: vehicles[0].deviceId } : {};
  }

  static getConfigElement() {
    return document.createElement("deepal-card-editor");
  }

  setConfig(config) {
    if (!config) throw new Error("Deepal card: missing configuration");
    this._yaml = { ...config };
    this._config = mergeCardConfig(config, this._local);
    if (config.device_id) this._deviceId = config.device_id;
    if (!this._uiRestored) {
      this._uiRestored = true;
      this._restoreUiState();
    }
    if (this._hass) this._render();
  }

  set hass(hass) {
    if (this._settingsOpen && this._hass) {
      // Keep the settings sheet and its scroll position stable while the
      // vehicle telemetry updates behind it.
      this._hass = hass;
      this._syncVehicles();
      return;
    }
    super.hass = hass;
    if (!this._remoteLoaded && this._config) {
      this._remoteLoaded = true;
      this._loadUserData();
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this._settingsDirty) this._commitSettings();
  }

  getCardSize() {
    return 10;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _userDataKey() {
    const device = (this._config && this._config.device_id) || this._deviceId || "default";
    return `deepal_card_${device}`;
  }

  async _loadUserData() {
    if (!this._hass || typeof this._hass.callWS !== "function") return;
    try {
      const result = await this._hass.callWS({
        type: "frontend/get_user_data",
        key: this._userDataKey(),
      });
      const value = cardSettingsOnly(result && result.value);
      if (Object.keys(value).length) {
        this._local = { ...value, ...this._local };
        this._config = mergeCardConfig(this._yaml, this._local);
        this._render();
      }
    } catch (error) {
      // User data is optional; the YAML configuration is the source of truth.
    }
  }

  _uiKey() {
    return `deepal_card_ui_${(this._config && this._config.device_id) || this._deviceId || "default"}`;
  }

  _saveUiState() {
    try {
      if (!this._settingsOpen) {
        sessionStorage.removeItem(this._uiKey());
        return;
      }
      sessionStorage.setItem(this._uiKey(), JSON.stringify({
        t: Date.now(),
        tab: this._settingsTab,
        scroll: this._settingsScroll || 0,
      }));
    } catch (error) {
      // Private browsing can disable sessionStorage; the dialog still works.
    }
  }

  _restoreUiState() {
    try {
      const value = JSON.parse(sessionStorage.getItem(this._uiKey()) || "null");
      if (value && Date.now() - value.t < 30000) {
        this._settingsOpen = true;
        this._settingsTab = value.tab || "hero";
        this._settingsScroll = value.scroll || 0;
      }
    } catch (error) {
      // Ignore a malformed or unavailable sessionStorage.
    }
  }

  _patch(patch) {
    if (!patch || !Object.keys(patch).length) return;
    this._local = { ...this._local, ...cardSettingsOnly(patch) };
    this._config = mergeCardConfig(this._yaml, this._local);
    this._settingsDirty = true;
    this._render();
  }

  _commitSettings() {
    if (!this._settingsDirty) return;
    this._settingsDirty = false;
    clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._persist(), 0);
  }

  async _persist() {
    try {
      await this._saveYaml();
      this._toast = { type: "ok", text: this._t("settings_saved") };
    } catch (error) {
      await this._saveRemote();
      this._toast = {
        type: "warn",
        text: this._t(error && error.message === "ambiguous" ? "settings_ambiguous" : "settings_local"),
      };
    }
    if (this._toast) {
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => {
        this._toast = null;
        this._render();
      }, 5000);
      this._render();
    }
  }

  async _saveRemote() {
    if (!this._hass || typeof this._hass.callWS !== "function") return;
    try {
      await this._hass.callWS({
        type: "frontend/set_user_data",
        key: this._userDataKey(),
        value: this._local,
      });
    } catch (error) {
      // A read-only user still gets the in-memory configuration for this view.
    }
  }

  async _saveYaml() {
    const hass = this._hass;
    if (!hass || typeof hass.callWS !== "function" || !this._config.device_id) {
      throw new Error("local");
    }
    if (hass.user && hass.user.is_admin === false) throw new Error("local");
    if (typeof location === "undefined") throw new Error("local");
    const segment = String(location.pathname || "").split("/")[1] || "lovelace";
    const urlPath = segment === "lovelace" ? null : segment;
    const config = await hass.callWS({
      type: "lovelace/config",
      url_path: urlPath,
      force: true,
    });
    const found = [];
    const visit = (node) => {
      if (Array.isArray(node)) {
        node.forEach(visit);
        return;
      }
      if (node && typeof node === "object") {
        if (node.type === `custom:${CARD_TAG}` && node.device_id === this._config.device_id) {
          found.push(node);
        }
        Object.values(node).forEach(visit);
      }
    };
    visit(config);
    if (found.length !== 1) throw new Error("ambiguous");
    Object.assign(found[0], cardSettingsOnly(this._local));
    await hass.callWS({
      type: "lovelace/config/save",
      url_path: urlPath,
      config,
    });
    this._yaml = { ...found[0] };
    this._local = {};
    this._config = mergeCardConfig(this._yaml, {});
  }

  _heroStyle(vehicle) {
    const style = this._config.hero_style || "auto";
    if (style !== "auto") return style;
    if (vehicle.profile === "s07") return "photo";
    if (vehicle.profile === "generic") return "image";
    return "iso";
  }

  _heroAspect(style, vehicle) {
    if (this._config.image_aspect) return this._config.image_aspect;
    if (style === "planta") {
      return vehicle &&
        (vehicle.profile === PANEL_PROFILE_S05_EV ||
          vehicle.profile === PANEL_PROFILE_S05_PHEV ||
          vehicle.profile === PANEL_PROFILE_S07)
        ? "750 / 550"
        : "16 / 9";
    }
    if (style === "iso") return "3 / 2";
    return "16 / 9";
  }

  _heroStageHtml(vehicle, style) {
    const hass = this._hass;
    let html = "";
    const charging = isOn(hass, entityFor(vehicle, "binary_sensor", "charging"));
    const plugged = isOn(hass, entityFor(vehicle, "binary_sensor", "charger_plugged"));
    const chargingLayout = layoutFor(vehicle)?.charging;
    const isS05 =
      vehicle.profile === PANEL_PROFILE_S05_EV ||
      vehicle.profile === PANEL_PROFILE_S05_PHEV;
    if (style === "iso" && isS05 && chargingLayout && (charging || plugged)) {
      return `<div class="stage stage-charging">
        <img src="${assetUrl(chargingLayout.base, vehicle)}" alt="">
        <img src="${assetUrl(
          charging ? chargingLayout.layers.charging : chargingLayout.layers.plugged,
          vehicle,
        )}" alt="">
      </div>`;
    }
    if (style === "iso") {
      html = vehicleCompactStageHtml(hass, vehicle);
      if (!html) html = vehicleHeroHtml(vehicle);
      if (!html) html = vehiclePhotoHtml(hass, vehicle);
      if (!html) html = vehicleStageHtml(hass, vehicle);
    } else if (style === "planta") {
      html = vehicleStageHtml(hass, vehicle, { rotate: true });
      if (!html) html = vehiclePhotoHtml(hass, vehicle);
      if (!html) html = vehicleHeroHtml(vehicle);
    } else if (style === "photo") {
      html = vehiclePhotoHtml(hass, vehicle);
      if (!html) html = vehicleHeroHtml(vehicle);
      if (!html) html = vehicleCompactStageHtml(hass, vehicle);
      if (!html) html = vehicleStageHtml(hass, vehicle);
    } else {
      html = vehiclePhotoHtml(hass, vehicle);
      if (!html) html = vehicleHeroHtml(vehicle);
      if (!html) html = vehicleStageHtml(hass, vehicle);
    }
    return html || `<div class="hero-empty"><ha-icon icon="${PANEL_ICONS.car_electric}"></ha-icon></div>`;
  }

  _heroChips(vehicle, show = null) {
    const hass = this._hass;
    const chips = [];
    const locked = lockStateFor(hass, vehicle);
    if (locked !== null && (!show || show.has("lock"))) {
      chips.push(
        `<span class="hero-chip ${locked ? "" : "warn"}">
          <ha-icon icon="${locked ? PANEL_ICONS.lock : PANEL_ICONS.unlock}"></ha-icon>
          ${escapeHtml(locked ? this._t("locked") : this._t("unlocked"))}
        </span>`,
      );
    }
    const charging = isOn(hass, entityFor(vehicle, "binary_sensor", "charging"));
    const plugged = isOn(hass, entityFor(vehicle, "binary_sensor", "charger_plugged"));
    if (charging || plugged) {
      chips.push(
        `<span class="hero-chip on">
          <ha-icon icon="${PANEL_ICONS.charging}"></ha-icon>
          ${escapeHtml(charging ? this._t("charging") : this._t("plugged"))}
        </span>`,
      );
    }
    return chips.join("");
  }

  _renderHero(vehicle) {
    const hass = this._hass;
    const show = new Set(this._config.hero_show || []);
    const style = this._heroStyle(vehicle);
    const name = vehicle.name || this._t("title");
    const model = vehicle.model || "";
    const plate = formatState(hass, entityFor(vehicle, "sensor", "license_plate"));
    const range = formatIntegerState(hass, entityFor(vehicle, "sensor", "range"));
    const fuelRange = formatIntegerState(hass, entityFor(vehicle, "sensor", "fuel_range"));
    const connectedId = entityFor(vehicle, "binary_sensor", "connected");
    const connected = stateFor(hass, connectedId);
    const updatedId = entityFor(vehicle, "sensor", "updated");
    const updatedState = stateFor(hass, updatedId);
    const updated = updatedState
      ? formatRelativeTime(this._language, updatedState.state)
      : null;
    const title = [
      show.has("name") ? `<span class="hero-name">${escapeHtml(name)}</span>` : "",
      show.has("model") && model && !name.toUpperCase().includes(model.toUpperCase())
        ? `<span class="hero-model">${escapeHtml(model)}</span>`
        : "",
      show.has("plate") && plate ? `<span class="hero-plate">${escapeHtml(plate)}</span>` : "",
    ].join("");
    const rangeParts = [
      range ? `<span class="big">${escapeHtml(range)}</span>` : "",
      range ? `<span class="unit">${escapeHtml(this._t("range"))}</span>` : "",
    ].join("");
    const split = [];
    if (fuelRange) {
      split.push(
        `<span><ha-icon icon="${PANEL_ICONS.fuel}"></ha-icon>${escapeHtml(fuelRange)}</span>`,
      );
    }
    const meta = [
      show.has("cloud") && connected
        ? `<span class="hero-cloud ${connected.state === "on" ? "ok" : "bad"}" title="${escapeHtml(connected.state === "on" ? this._t("online") : this._t("offline"))}">
            <ha-icon icon="${connected.state === "on" ? PANEL_ICONS.cloud : PANEL_ICONS.cloud_off}"></ha-icon>
          </span>`
        : "",
    ].join("");
    const chips = this._heroChips(vehicle, show);
    return `
      <div class="hero" style="--hero-aspect:${escapeHtml(this._heroAspect(style, vehicle))};--hero-scale:${this._config.image_scale || 1}">
        <div class="hero-stage" data-style="${escapeHtml(style)}">${this._heroStageHtml(vehicle, style)}</div>
        <div class="hero-shade"></div>
        <div class="hero-top">
          <div class="hero-title">${title}</div>
          <div class="hero-actions">${meta}</div>
        </div>
        ${show.has("range") && rangeParts ? `<div class="hero-range">${rangeParts}${split.length ? `<span class="split">${split.join("")}</span>` : ""}</div>` : ""}
        <div class="hero-bottom">
          <div class="hero-chips">${chips}</div>
          ${show.has("updated") && updated ? `<span class="hero-updated">${escapeHtml(updated)}</span>` : ""}
        </div>
      </div>`;
  }

  _tone(value) {
    if (value === null || value === undefined || value === "unavailable" || value === "unknown") return "warn";
    return "";
  }

  _actionDefs(vehicle) {
    const hass = this._hass;
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const defs = [];
    const locked = lockStateFor(hass, vehicle);
    if (locked !== null) {
      defs.push({
        id: "lock",
        icon: locked ? PANEL_ICONS.unlock : PANEL_ICONS.lock,
        label: locked ? this._t("unlock_doors") : this._t("lock_doors"),
        value: locked ? this._t("locked") : this._t("unlocked"),
        tone: locked ? "" : "warn",
        confirm: locked ? "unlock" : "lock",
        execute: () => this._executeAction("lock-toggle"),
      });
    }
    const coverDef = (id, icon, openLabel, closedLabel, confirmKey) => {
      const state = stateFor(hass, entity("cover", id));
      if (!state) return;
      const open = state.state === "open";
      defs.push({
        id,
        icon,
        label: open ? closedLabel : openLabel,
        value: open ? this._t("open") : this._t("closed"),
        tone: open ? "warn" : "",
        confirm: open ? null : confirmKey,
        execute: () => this._executeAction("cover-toggle", { key: id }),
      });
    };
    coverDef("windows", PANEL_ICONS.window, this._t("open_windows"), this._t("close_windows"), "windows");
    coverDef("trunk", PANEL_ICONS.trunk, this._t("open_trunk"), this._t("close_trunk"), "trunk");

    const climateId = entity("climate", "cabin");
    const climateState = stateFor(hass, climateId);
    if (climateId && climateState) {
      const on = climateState.state !== "off";
      defs.push({
        id: "climate",
        icon: PANEL_ICONS.climate,
        label: this._t("climate"),
        value: on ? this._t("on") : this._t("off"),
        tone: on ? "on" : "",
        modal: "climate",
      });
    }

    const tireValues = [
      ["tire_front_left", "tire_alarm_front_left"],
      ["tire_front_right", "tire_alarm_front_right"],
      ["tire_rear_left", "tire_alarm_rear_left"],
      ["tire_rear_right", "tire_alarm_rear_right"],
    ]
      .map(([key, alarmKey]) => this._tireDisplay(vehicle, key, alarmKey))
      .filter(Boolean);
    if (tireValues.length) {
      defs.push({
        id: "tires",
        icon: PANEL_ICONS.tire,
        label: this._t("tires"),
        value: tireValues[0].text,
        tone: tireValues.some((item) => item.warn) ? "warn" : "",
        modal: "tires",
      });
    }

    for (const [id, icon, label, key, confirmKey] of [
      ["flash", PANEL_ICONS.flash, this._t("flash_lights"), "flash_lights", "flash"],
      ["honk", PANEL_ICONS.horn, this._t("honk_horn"), "honk_horn", "honk"],
      ["find", PANEL_ICONS.flash_and_honk, this._t("flash_and_honk"), "flash_and_honk", "find"],
    ]) {
      if (!entity("button", key)) continue;
      defs.push({
        id,
        icon,
        label,
        value: "",
        confirm: confirmKey,
        execute: () => this._executeAction("press", { key }),
      });
    }
    const hidden = new Set(this._config.buttons_hidden || []);
    const order = this._config.buttons || CARD_BUTTONS;
    return order
      .filter((id) => !hidden.has(id))
      .map((id) => defs.find((def) => def.id === id))
      .filter(Boolean);
  }

  _needsConfirm(def) {
    return Boolean(def && def.confirm && (this._config.confirm || []).includes(def.confirm));
  }

  _runAction(id) {
    const def = this._actionDefs(this._vehicle).find((item) => item.id === id);
    if (!def) return;
    if (def.modal) {
      this._modal = def.modal;
      this._render();
      return;
    }
    if (def.static || !def.execute) return;
    if (this._needsConfirm(def)) {
      this._confirm = def;
      this._render();
      return;
    }
    this._confirm = null;
    def.execute();
  }

  _actionHtml(def) {
    const labels = this._config.button_labels || "both";
    const showTitle = labels === "title" || labels === "both";
    const showValue = labels === "status" || labels === "both";
    const tag = def.static ? "div" : "button";
    const size = ["s", "m", "l"].includes(this._config.button_size)
      ? this._config.button_size
      : "m";
    const attrs = def.static
      ? `class="action static ${def.tone || ""} size-${size}"`
      : `class="action ${def.tone || ""} size-${size}" data-action="card-action" data-id="${escapeHtml(def.id)}" title="${escapeHtml(def.label)}" aria-label="${escapeHtml(def.label)}"`;
    return `<${tag} ${attrs}>
      <ha-icon icon="${def.icon}"></ha-icon>
      ${showTitle ? `<span class="action-label">${escapeHtml(def.label)}</span>` : ""}
      ${showValue && def.value ? `<span class="action-value">${escapeHtml(def.value)}</span>` : ""}
    </${tag}>`;
  }

  _sectionActions(vehicle) {
    const defs = this._actionDefs(vehicle);
    if (!defs.length) return "";
    const size = ["s", "m", "l"].includes(this._config.button_size)
      ? this._config.button_size
      : "m";
    const layout = ["grid", "scroll", "split", "fit"].includes(this._config.button_layout)
      ? this._config.button_layout
      : "grid";
    let body = "";
    if (layout === "scroll") {
      body = `<div class="actions-scroll">${defs.map((def) => this._actionHtml(def)).join("")}</div>`;
    } else if (layout === "split") {
      const primary = Math.max(1, Math.min(defs.length, Number(this._config.button_primary) || 4));
      const main = defs.slice(0, primary);
      const more = defs.slice(primary);
      body = `<div class="actions-split">
        <div class="actions-main" style="--primary:${main.length}">${main.map((def) => this._actionHtml(def)).join("")}</div>
        ${more.length && this._moreOpen ? `<div class="actions-more">${more.map((def) => this._actionHtml(def)).join("")}</div>` : ""}
        ${more.length ? `<button class="actions-more-toggle" data-action="more-actions"><ha-icon icon="${PANEL_ICONS.more}"></ha-icon><span>${escapeHtml(this._t("more"))}</span></button>` : ""}
      </div>`;
    } else {
      body = `<div class="actions-${layout}">${defs.map((def) => this._actionHtml(def)).join("")}</div>`;
    }
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="mdi:gesture-tap-button"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("controls"))}</span>
      </div>
      <div class="actions size-${size}">${body}</div>
    </div>`;
  }

  _metric(label, value, cls = "") {
    return `<div class="metric ${cls}">
      <span class="label">${escapeHtml(label)}</span>
      <span class="value">${escapeHtml(value ?? "—")}</span>
    </div>`;
  }

  _sectionStatus(vehicle) {
    const hass = this._hass;
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const metrics = [];
    const add = (labelKey, entityId, formatter = null) => {
      if (!entityId) return;
      const value = formatter ? formatter() : formatState(hass, entityId);
      if (value === null) return;
      metrics.push(this._metric(this._t(labelKey), value));
    };
    add("odometer", entity("sensor", "odometer"), () =>
      formatIntegerState(hass, entity("sensor", "odometer")),
    );
    if (entity("sensor", "charge_status")) {
      add("charge_status", entity("sensor", "charge_status"), () =>
        chargeStatusText(hass, vehicle, (key) => this._t(key)),
      );
    } else {
      add("vehicle_status", entity("sensor", "vehicle_status"));
    }
    add("battery", entity("sensor", "battery"), () =>
      formatIntegerState(hass, entity("sensor", "battery")),
    );
    add("range", entity("sensor", "range"), () =>
      formatIntegerState(hass, entity("sensor", "range")),
    );
    if (!metrics.length) return "";
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.car}"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("status"))}</span>
      </div>
      <div class="metrics">${metrics.join("")}</div>
    </div>`;
  }

  _sectionEnergy(vehicle) {
    if (!hasFuelEntities(vehicle)) return "";
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const values = [
      ["battery", "battery"],
      ["range", "range"],
      ["fuel", "fuel_level"],
      ["fuel_range", "fuel_range"],
      ["fuel_tank_capacity", "fuel_tank_capacity"],
    ]
      .map(([labelKey, key]) => {
        const id = entity("sensor", key);
        return id
          ? this._metric(
              this._t(labelKey),
              formatIntegerState(this._hass, id),
            )
          : "";
      })
      .filter(Boolean);
    if (!values.length) return "";
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.fuel}"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("energy"))}</span>
      </div>
      <div class="metrics">${values.join("")}</div>
    </div>`;
  }

  _tireDisplay(vehicle, key, alarmKey) {
    const hass = this._hass;
    const id = entityFor(vehicle, "sensor", key);
    if (!id) return null;
    const state = stateFor(hass, id);
    if (!state) return null;
    const raw = Number.parseFloat(state.state);
    if (!Number.isFinite(raw)) return null;
    const sourceUnit = String(state.attributes.unit_of_measurement || "bar").toLowerCase();
    let bar = raw;
    if (sourceUnit === "kpa") bar = raw / 100;
    else if (sourceUnit === "psi") bar = raw * 0.0689476;
    else if (raw > 50) bar = raw / 100;
    const unit = this._config.tire_unit || "bar";
    const value =
      unit === "kPa" ? Math.round(bar * 100) : unit === "psi" ? (bar / 0.0689476).toFixed(1) : bar.toFixed(2);
    const alarm = isOn(hass, entityFor(vehicle, "binary_sensor", alarmKey));
    const low = Number(this._config.tire_min) > 0 && bar < Number(this._config.tire_min);
    const high = Number(this._config.tire_max) > 0 && bar > Number(this._config.tire_max);
    return { text: `${value} ${unit}`, warn: alarm || low || high };
  }

  _sectionTires(vehicle) {
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const tire = (key, alarmKey, labelKey) => {
      if (!entity("sensor", key)) return "";
      const display = this._tireDisplay(vehicle, key, alarmKey);
      if (!display) return "";
      return `<div class="tile static ${display.warn ? "warn" : ""}">
        <ha-icon icon="${PANEL_ICONS.tire}"></ha-icon>
        <span class="tile-body">
          <span class="tile-label">${escapeHtml(this._t(labelKey))}</span>
          <span class="tile-value">${escapeHtml(display.text)}</span>
        </span>
      </div>`;
    };
    const tires = [
      tire("tire_front_left", "tire_alarm_front_left", "front_left"),
      tire("tire_front_right", "tire_alarm_front_right", "front_right"),
      tire("tire_rear_left", "tire_alarm_rear_left", "rear_left"),
      tire("tire_rear_right", "tire_alarm_rear_right", "rear_right"),
    ].filter(Boolean);
    if (!tires.length) return "";
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.tire}"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("tires"))}</span>
      </div>
      <div class="tiles">${tires.join("")}</div>
    </div>`;
  }

  _sectionInfo(vehicle) {
    const hass = this._hass;
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const tiles = [];
    const integerInfo = new Set([
      "odometer",
      "range",
      "battery",
      "fuel_level",
      "fuel_range",
      "trip_mileage",
      "mileage_yesterday",
    ]);
    for (const id of this._config.info || []) {
      const spec = CARD_INFO_ITEMS[id];
      if (!spec) continue;
      const [domain, key, labelKey, iconKey] = spec;
      const entityId = entity(domain, key);
      const value = integerInfo.has(id)
        ? formatIntegerState(hass, entityId)
        : formatState(hass, entityId);
      if (value === null) continue;
      tiles.push(`<div class="info-tile static">
        <ha-icon icon="${PANEL_ICONS[iconKey] || PANEL_ICONS.info}"></ha-icon>
        <div><div class="info-value">${escapeHtml(value)}</div><div class="info-label">${escapeHtml(this._t(labelKey))}</div></div>
      </div>`);
    }
    for (const item of this._config.info_custom || []) {
      const value = formatState(hass, item.entity);
      if (value === null) continue;
      const label = item.label || item.entity;
      tiles.push(`<button class="info-tile" data-action="more-info" data-entity="${escapeHtml(item.entity)}">
        <ha-icon icon="${escapeHtml(item.icon || "mdi:information-outline")}"></ha-icon>
        <div><div class="info-value">${escapeHtml(value)}</div><div class="info-label">${escapeHtml(label)}</div></div>
      </button>`);
    }
    if (!tiles.length) return "";
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.car}"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("info"))}</span>
      </div>
      <div class="info-grid">${tiles.join("")}</div>
    </div>`;
  }

  _sectionDiagnostics(vehicle) {
    const hass = this._hass;
    const mode = this._config.diag_mode === "all" ? "all" : "alerts";
    const selected = Array.isArray(this._config.diag) ? new Set(this._config.diag) : null;
    const ignored = new Set(this._config.diag_ignore || []);
    const items = [];
    for (const [key, icon] of PANEL_WARNINGS) {
      if (selected && !selected.has(key)) continue;
      const id = entityFor(vehicle, "binary_sensor", key);
      if (!id || ignored.has(id)) continue;
      const state = stateFor(hass, id);
      if (!state) continue;
      const on = state.state === "on";
      if (mode === "alerts" && !on) continue;
      items.push(`<span class="chip ${on ? "warn" : ""}">
        <ha-icon icon="${icon}"></ha-icon>
        ${escapeHtml(this._t(key))}${mode === "all" ? `: ${escapeHtml(this._t(on ? "on" : "off"))}` : ""}
      </span>`);
    }
    for (const item of this._config.diag_custom || []) {
      if (ignored.has(item.entity)) continue;
      const state = stateFor(hass, item.entity);
      if (!state) continue;
      const on = ["on", "true", "problem", "alarm", "low"].includes(String(state.state).toLowerCase());
      if (mode === "alerts" && !on) continue;
      items.push(`<span class="chip ${on ? "warn" : ""}">
        <ha-icon icon="${escapeHtml(item.icon || PANEL_ICONS.alert)}"></ha-icon>
        ${escapeHtml(item.label || item.entity)}${mode === "all" ? `: ${escapeHtml(this._t(on ? "on" : "off"))}` : ""}
      </span>`);
    }
    if (!items.length) return "";
    return `<div class="section">
      <div class="section-head">
        <ha-icon icon="${PANEL_ICONS.alert}"></ha-icon>
        <span class="section-title">${escapeHtml(this._t("diagnostics"))}</span>
      </div>
      <div class="chips">${items.join("")}</div>
    </div>`;
  }

  _chargingConnected(vehicle) {
    return (
      isOn(this._hass, entityFor(vehicle, "binary_sensor", "charger_plugged")) ||
      isOn(this._hass, entityFor(vehicle, "binary_sensor", "charging"))
    );
  }

  _sectionHtml(key, vehicle) {
    switch (key) {
      case "actions":
        return this._sectionActions(vehicle);
      case "status":
        return this._sectionStatus(vehicle);
      case "climate":
        return this._renderClimate(vehicle);
      case "charging":
        return this._chargingConnected(vehicle) ? this._renderCharging(vehicle) : "";
      case "driving":
        return vehicle.profile === PANEL_PROFILE_S07 ? this._renderDriving(vehicle) : "";
      case "energy":
        return this._sectionEnergy(vehicle);
      case "info":
        return this._sectionInfo(vehicle);
      case "diagnostics":
        return this._sectionDiagnostics(vehicle);
      case "tires":
        return this._sectionTires(vehicle);
      default:
        return "";
    }
  }

  _renderSections(vehicle) {
    const hidden = new Set(this._config.hidden || []);
    return (this._config.order || CARD_SECTIONS)
      .filter((key) => !hidden.has(key))
      .map((key) => this._sectionHtml(key, vehicle))
      .filter(Boolean)
      .join("");
  }

  _seatControlHtml(vehicle, key, label) {
    const id = entityFor(vehicle, "number", key);
    if (!id) return "";
    const state = stateFor(this._hass, id);
    return `<div class="control">
      <span class="label">${escapeHtml(label)}</span>
      <div class="stepper">
        <button data-action="number-step" data-key="${key}" data-delta="-1" aria-label="-">&minus;</button>
        <span class="value">${escapeHtml(state ? state.state : "—")}</span>
        <button data-action="number-step" data-key="${key}" data-delta="1" aria-label="+">+</button>
      </div>
    </div>`;
  }

  _climateModalHtml(vehicle) {
    const entity = (domain, key) => entityFor(vehicle, domain, key);
    const climateId = entity("climate", "cabin");
    const climateState = stateFor(this._hass, climateId);
    const on = Boolean(climateState && climateState.state !== "off");
    const target = climateState?.attributes?.temperature;
    const inside = formatState(this._hass, entity("sensor", "inside_temperature"));
    const humidity = formatState(this._hass, entity("sensor", "cabin_humidity"));
    const seats = [
      ["seat_heating_front_left", `${this._t("seat_heating")} · ${this._t("front_left")}`],
      ["seat_heating_front_right", `${this._t("seat_heating")} · ${this._t("front_right")}`],
      ["seat_ventilation_front_left", `${this._t("seat_ventilation")} · ${this._t("front_left")}`],
      ["seat_ventilation_front_right", `${this._t("seat_ventilation")} · ${this._t("front_right")}`],
      ["seat_heating_rear_left", `${this._t("seat_heating")} · ${this._t("rear_left")}`],
      ["seat_heating_rear_right", `${this._t("seat_heating")} · ${this._t("rear_right")}`],
      ["seat_ventilation_rear_left", `${this._t("seat_ventilation")} · ${this._t("rear_left")}`],
      ["seat_ventilation_rear_right", `${this._t("seat_ventilation")} · ${this._t("rear_right")}`],
    ]
      .map(([key, label]) => this._seatControlHtml(vehicle, key, label))
      .filter(Boolean);
    const steeringId = entity("switch", "steering_wheel_heating");
    const steeringOn = isOn(this._hass, steeringId);
    const steering = steeringId
      ? `<button class="tile ${steeringOn ? "on" : ""}" data-action="toggle-switch" data-key="steering_wheel_heating">
          <ha-icon icon="${PANEL_ICONS.steering}"></ha-icon>
          <span class="tile-body">
            <span class="tile-label">${escapeHtml(this._t("steering_wheel"))}</span>
            <span class="tile-value">${escapeHtml(this._t(steeringOn ? "on" : "off"))}</span>
          </span>
        </button>`
      : "";
    const metrics = [
      inside ? this._metric(this._t("inside_temperature"), inside) : "",
      humidity ? this._metric(this._t("cabin_humidity"), humidity) : "",
    ].filter(Boolean);
    return `<div class="modal-columns">
      <div class="modal-col">
        <div class="modal-section">
          <h4>${escapeHtml(this._t("climate"))}</h4>
          ${metrics.length ? `<div class="metrics">${metrics.join("")}</div>` : ""}
          <div class="center">
            <div class="stepper large">
              <button data-action="temp-step" data-delta="-0.5" aria-label="-">&minus;</button>
              <span class="value">${escapeHtml(target != null ? `${target} °C` : "—")}</span>
              <button data-action="temp-step" data-delta="0.5" aria-label="+">+</button>
            </div>
          </div>
          <div class="segmented">
            <button class="segment" aria-pressed="${on}" data-action="climate-mode" data-mode="heat_cool">
              <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon><span>${escapeHtml(this._t("climate_on"))}</span>
            </button>
            <button class="segment" aria-pressed="${!on}" data-action="climate-mode" data-mode="off">
              <ha-icon icon="${PANEL_ICONS.climate}"></ha-icon><span>${escapeHtml(this._t("climate_off"))}</span>
            </button>
          </div>
        </div>
      </div>
      <div class="modal-col">
        <div class="modal-section">
          <h4>${escapeHtml(this._t("seats"))}</h4>
          ${seats.length ? `<div class="steppers">${seats.join("")}</div>` : ""}
          ${steering ? `<div class="tiles">${steering}</div>` : ""}
        </div>
      </div>
    </div>`;
  }

  _tiresModalHtml(vehicle) {
    const tires = [
      ["tire_front_left", "tire_alarm_front_left", "front_left"],
      ["tire_front_right", "tire_alarm_front_right", "front_right"],
      ["tire_rear_left", "tire_alarm_rear_left", "rear_left"],
      ["tire_rear_right", "tire_alarm_rear_right", "rear_right"],
    ]
      .map(([key, alarmKey, labelKey]) => {
        const display = this._tireDisplay(vehicle, key, alarmKey);
        if (!display) return "";
        return `<div class="tire-card ${display.warn ? "warn" : ""}">
          <ha-icon icon="${PANEL_ICONS.tire}"></ha-icon>
          <div>
            <div class="tire-label">${escapeHtml(this._t(labelKey))}</div>
            <div class="tire-value">${escapeHtml(display.text)}</div>
          </div>
        </div>`;
      })
      .filter(Boolean);
    return tires.length
      ? `<div class="tire-grid">${tires.join("")}</div>`
      : `<div class="empty">${escapeHtml(this._t("unavailable"))}</div>`;
  }

  _renderModal() {
    if (!this._modal || !this._vehicle) return "";
    const title = this._t(this._modal === "tires" ? "tires" : "climate");
    const body = this._modal === "tires"
      ? this._tiresModalHtml(this._vehicle)
      : this._climateModalHtml(this._vehicle);
    return `<div class="modal-sheet">
      <div class="modal-panel" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
        <div class="modal-head">
          <h3>${escapeHtml(title)}</h3>
          <button class="settings-close" data-action="close-modal" aria-label="${escapeHtml(this._t("close"))}">
            <ha-icon icon="${PANEL_ICONS.close}"></ha-icon>
          </button>
        </div>
        <div class="modal-body">${body}</div>
      </div>
    </div>`;
  }

  _renderConfirm() {
    if (!this._confirm) return "";
    const [titleKey, textKey] = CARD_CONFIRM_TEXT[this._confirm.confirm] || ["confirm_title", "confirm_text"];
    return `<div class="confirm-sheet">
      <div class="confirm-box" role="dialog" aria-modal="true">
        <h3>${escapeHtml(this._t(titleKey))}</h3>
        <p>${escapeHtml(this._t(textKey))}</p>
        <div class="confirm-actions">
          <button data-action="confirm-no">${escapeHtml(this._t("cancel"))}</button>
          <button class="go" data-action="confirm-yes">${escapeHtml(this._t("confirm"))}</button>
        </div>
      </div>
    </div>`;
  }

  _renderToast() {
    if (!this._toast || this._config.toasts === false) return "";
    return `<div class="card-toast pos-${this._config.toast_position === "top" ? "top" : "bottom"} ${this._toast.type || ""}">${escapeHtml(this._toast.text)}</div>`;
  }

  _renderSettings() {
    return `<div class="settings-sheet"><deepal-card-settings></deepal-card-settings></div>`;
  }

  _renderHtml() {
    const vehicle = this._vehicle;
    return `<style>${PANEL_CSS}</style>
      <div class="card-root" data-pad="${escapeHtml(this._config.card_padding || "normal")}">
        ${vehicle ? this._renderHero(vehicle) : ""}
        ${this._error ? `<div class="alert">${escapeHtml(this._error)}</div>` : ""}
        ${this._renderToast()}
        ${vehicle ? this._renderSections(vehicle) : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`}
        ${vehicle && this._config.show_settings !== false ? `<button class="card-footer" data-action="open-settings"><ha-icon icon="${PANEL_ICONS.settings}"></ha-icon><span>${escapeHtml(this._t("settings"))}</span></button>` : ""}
        ${this._renderModal()}
        ${this._settingsOpen ? this._renderSettings() : ""}
        ${this._renderConfirm()}
      </div>`;
  }

  _render() {
    const previous = this.shadowRoot.querySelector("deepal-card-settings");
    if (previous && previous._tab) this._settingsTab = previous._tab;
    if (previous && previous.shadowRoot) {
      const body = previous.shadowRoot.querySelector(".settings-body");
      if (body) this._settingsScroll = body.scrollTop;
    }
    super._render();
    const settings = this.shadowRoot.querySelector("deepal-card-settings");
    if (settings) {
      settings.hass = this._hass;
      settings.tab = this._settingsTab;
      settings.config = this._config;
      if (this._settingsScroll) {
        requestAnimationFrame(() => {
          const body = settings.shadowRoot && settings.shadowRoot.querySelector(".settings-body");
          if (body) body.scrollTop = this._settingsScroll;
        });
      }
    }
    this._saveUiState();
  }

  _renderKey() {
    return [
      super._renderKey(),
      this._modal || "",
      this._confirm ? this._confirm.id : "",
      this._moreOpen ? "more" : "",
      this._toast ? `${this._toast.type}:${this._toast.text}` : "",
    ].join("|");
  }

  _handleCustomClick(target) {
    const action = target.dataset.action;
    if (action === "open-settings") {
      this._settingsOpen = true;
      this._settingsTab = "hero";
      this._settingsScroll = 0;
      this._modal = null;
      this._saveUiState();
      this._render();
      return true;
    }
    if (action === "close-modal") {
      this._modal = null;
      this._render();
      return true;
    }
    if (action === "card-action") {
      this._runAction(target.dataset.id);
      return true;
    }
    if (action === "more-actions") {
      this._moreOpen = !this._moreOpen;
      this._render();
      return true;
    }
    if (action === "more-info") {
      const entityId = target.dataset.entity;
      if (entityId) {
        this.dispatchEvent(new CustomEvent("hass-more-info", {
          bubbles: true,
          composed: true,
          detail: { entityId },
        }));
      }
      return true;
    }
    if (action === "confirm-yes") {
      const def = this._confirm;
      this._confirm = null;
      this._render();
      if (def && def.execute) def.execute();
      return true;
    }
    if (action === "confirm-no") {
      this._confirm = null;
      this._render();
      return true;
    }
    return false;
  }
}

class DeepalCardSettings extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "hero";
    this._config = null;
    this._hass = null;
    this.shadowRoot.addEventListener("click", (event) => this._onClick(event));
    this.shadowRoot.addEventListener("change", (event) => this._onChange(event));
  }

  set hass(value) {
    this._hass = value;
  }

  set config(value) {
    this._config = value;
    this._render();
  }

  set tab(value) {
    this._tab = ["hero", "sections", "actions", "sensors", "appearance"].includes(value) ? value : "hero";
    if (this._config) this._render();
  }

  get embedded() {
    return this.hasAttribute("embedded");
  }

  _t(key, values) {
    const language =
      this._config && this._config.language && this._config.language !== "auto"
        ? this._config.language
        : panelLanguage(this._hass || {});
    return translate(panelLanguage({ locale: { language } }), key, values);
  }

  _emit(patch) {
    this.dispatchEvent(new CustomEvent("settings-change", {
      detail: patch,
      bubbles: true,
      composed: true,
    }));
  }

  _tabs() {
    const tabs = [
      ["hero", "settings_hero"],
      ["sections", "settings_sections"],
      ["actions", "settings_actions"],
      ["sensors", "settings_sensors"],
      ["appearance", "settings_appearance"],
    ];
    return `<div class="settings-tabs">${tabs.map(([id, label]) =>
      `<button class="settings-tab ${this._tab === id ? "on" : ""}" data-settings-tab="${id}">${escapeHtml(this._t(label))}</button>`
    ).join("")}</div>`;
  }

  _select(key, value, options) {
    return `<select data-setting="${key}">${options.map(([id, label]) =>
      `<option value="${escapeHtml(id)}" ${String(id) === String(value) ? "selected" : ""}>${escapeHtml(this._t(label))}</option>`
    ).join("")}</select>`;
  }

  _check(key, value, label) {
    return `<label class="setting-row"><span>${escapeHtml(this._t(label))}</span><input type="checkbox" data-setting="${key}" ${value ? "checked" : ""}></label>`;
  }

  _arrayCheck(key, item, values, label) {
    return `<label class="setting-row"><span>${escapeHtml(this._t(label))}</span><input type="checkbox" data-array="${key}" data-value="${item}" ${(values || []).includes(item) ? "checked" : ""}></label>`;
  }

  _orderList(key, values, all, labelOf, hiddenKey) {
    const hidden = new Set((hiddenKey && this._config[hiddenKey]) || []);
    return `<div class="settings-group">${(values || all).map((id, index) => {
      const isHidden = hidden.has(id);
      return `<div class="setting-row ${isHidden ? "off" : ""}">
        <span>${escapeHtml(this._t(labelOf(id)))}</span>
        <span class="move">
          <button data-order="${key}" data-id="${id}" data-dir="-1" ${index === 0 ? "disabled" : ""} aria-label="${escapeHtml(this._t("move_up"))}"><ha-icon icon="${PANEL_ICONS.up}"></ha-icon></button>
          <button data-order="${key}" data-id="${id}" data-dir="1" ${index === (values || all).length - 1 ? "disabled" : ""} aria-label="${escapeHtml(this._t("move_down"))}"><ha-icon icon="${PANEL_ICONS.down}"></ha-icon></button>
          ${hiddenKey ? `<input type="checkbox" data-hide="${hiddenKey}" data-value="${id}" ${isHidden ? "" : "checked"} aria-label="${escapeHtml(this._t("show"))}">` : ""}
        </span>
      </div>`;
    }).join("")}</div>`;
  }

  _tabHero() {
    const c = this._config;
    return `<div class="settings-group">
      <h4>${escapeHtml(this._t("settings_hero"))}</h4>
      <label class="setting-row"><span>${escapeHtml(this._t("image_style"))}</span>${this._select("hero_style", c.hero_style, [
        ["auto", "auto"], ["planta", "planta"], ["iso", "isometric"], ["photo", "photo"], ["image", "image_entity"],
      ])}</label>
      <label class="setting-row"><span>${escapeHtml(this._t("image_scale"))}</span><input type="number" step="0.05" min="0.5" max="2" data-setting="image_scale" value="${escapeHtml(c.image_scale)}"></label>
      <label class="setting-row"><span>${escapeHtml(this._t("image_aspect"))}</span><input type="text" data-setting="image_aspect" value="${escapeHtml(c.image_aspect || "")}" placeholder="3 / 2"></label>
      <label class="setting-row"><span>${escapeHtml(this._t("card_padding"))}</span>${this._select("card_padding", c.card_padding, [["normal", "normal"], ["half", "half"], ["none", "none"]])}</label>
    </div>
    <div class="settings-group">
      <h4>${escapeHtml(this._t("show_on_hero"))}</h4>
      ${CARD_HERO_ITEMS.map((item) => this._arrayCheck("hero_show", item, c.hero_show, item === "model" ? "model" : item === "plate" ? "plate" : item)).join("")}
    </div>`;
  }

  _tabSections() {
    return `<p class="settings-hint">${escapeHtml(this._t("sections_hint"))}</p>
      ${this._orderList("order", this._config.order, CARD_SECTIONS, (id) => `section_${id}`, "hidden")}`;
  }

  _tabActions() {
    const c = this._config;
    return `<p class="settings-hint">${escapeHtml(this._t("actions_hint"))}</p>
      ${this._orderList("buttons", c.buttons, CARD_BUTTONS, (id) => (id === "find" ? "flash_and_honk" : id), "buttons_hidden")}
      <div class="settings-group">
        <h4>${escapeHtml(this._t("settings_actions"))}</h4>
        <label class="setting-row"><span>${escapeHtml(this._t("button_layout"))}</span>${this._select("button_layout", c.button_layout, [["grid", "grid"], ["scroll", "scroll"], ["split", "split"], ["fit", "fit"]])}</label>
        <label class="setting-row"><span>${escapeHtml(this._t("button_primary"))}</span><input type="number" min="1" max="6" data-setting="button_primary" value="${escapeHtml(c.button_primary)}"></label>
        <label class="setting-row"><span>${escapeHtml(this._t("button_size"))}</span>${this._select("button_size", c.button_size, [["s", "s"], ["m", "m"], ["l", "l"]])}</label>
        <label class="setting-row"><span>${escapeHtml(this._t("button_labels"))}</span>${this._select("button_labels", c.button_labels, [["none", "none"], ["status", "status"], ["title", "title"], ["both", "both"]])}</label>
      </div>
      <div class="settings-group">
        <h4>${escapeHtml(this._t("confirm"))}</h4>
        ${CARD_CONFIRM_ITEMS.map((item) => this._arrayCheck("confirm", item, c.confirm, item === "find" ? "flash_and_honk" : item === "flash" ? "flash_lights" : item === "honk" ? "honk_horn" : item)).join("")}
      </div>`;
  }

  _tabSensors() {
    const c = this._config;
    return `<div class="settings-group">
      <h4>${escapeHtml(this._t("info"))}</h4>
      ${CARD_INFO_IDS.map((item) => this._arrayCheck("info", item, c.info, CARD_INFO_ITEMS[item][2])).join("")}
    </div>
    <div class="settings-group">
      <h4>${escapeHtml(this._t("diagnostics"))}</h4>
      <label class="setting-row"><span>${escapeHtml(this._t("diag_mode"))}</span>${this._select("diag_mode", c.diag_mode, [["alerts", "alerts_only"], ["all", "all_warnings"]])}</label>
    </div>
    <div class="settings-group">
      <h4>${escapeHtml(this._t("tires"))}</h4>
      <label class="setting-row"><span>${escapeHtml(this._t("tire_unit"))}</span>${this._select("tire_unit", c.tire_unit, [["bar", "bar"], ["kPa", "kPa"], ["psi", "psi"]])}</label>
      <label class="setting-row"><span>${escapeHtml(this._t("tire_min"))}</span><input type="number" step="0.1" data-setting="tire_min" value="${escapeHtml(c.tire_min)}"></label>
      <label class="setting-row"><span>${escapeHtml(this._t("tire_max"))}</span><input type="number" step="0.1" data-setting="tire_max" value="${escapeHtml(c.tire_max)}"></label>
    </div>`;
  }

  _tabAppearance() {
    const c = this._config;
    const languages = [
      ["auto", "automatic"],
      ...Object.keys(PANEL_TEXTS).map((code) => [
        code,
        PANEL_LANGUAGE_NAMES[code] || code.toUpperCase(),
      ]),
    ];
    return `<div class="settings-group">
      <h4>${escapeHtml(this._t("appearance"))}</h4>
      <label class="setting-row"><span>${escapeHtml(this._t("language"))}</span>${this._select("language", c.language, languages)}</label>
      ${this._check("toasts", c.toasts !== false, "toasts")}
      <label class="setting-row"><span>${escapeHtml(this._t("toast_position"))}</span>${this._select("toast_position", c.toast_position, [["bottom", "bottom"], ["top", "top"]])}</label>
      ${this._check("show_settings", c.show_settings !== false, "show_settings")}
    </div>`;
  }

  _body() {
    if (!this._config) return "";
    if (this._tab === "sections") return this._tabSections();
    if (this._tab === "actions") return this._tabActions();
    if (this._tab === "sensors") return this._tabSensors();
    if (this._tab === "appearance") return this._tabAppearance();
    return this._tabHero();
  }

  _render() {
    if (!this._config) return;
    this.shadowRoot.innerHTML = `<style>${PANEL_CSS}</style>
      <div class="settings-panel ${this.embedded ? "embedded" : ""}">
        <div class="settings-head">
          <h3>${escapeHtml(this._t("settings"))}</h3>
          ${this.embedded ? "" : `<button class="settings-close" data-settings-close aria-label="${escapeHtml(this._t("close"))}"><ha-icon icon="${PANEL_ICONS.close}"></ha-icon></button>`}
        </div>
        ${this._tabs()}
        <div class="settings-body">${this._body()}</div>
      </div>`;
  }

  _onClick(event) {
    const tab = event.target.closest("[data-settings-tab]");
    if (tab) {
      this._tab = tab.dataset.settingsTab;
      this._render();
      return;
    }
    if (event.target.closest("[data-settings-close]")) {
      this.dispatchEvent(new CustomEvent("settings-close", { bubbles: true, composed: true }));
      return;
    }
    const order = event.target.closest("[data-order]");
    if (order) {
      const key = order.dataset.order;
      const list = [...(this._config[key] || [])];
      const index = list.indexOf(order.dataset.id);
      const next = index + Number(order.dataset.dir);
      if (index < 0 || next < 0 || next >= list.length) return;
      [list[index], list[next]] = [list[next], list[index]];
      this._emit({ [key]: list });
    }
  }

  _onChange(event) {
    const input = event.target;
    if (input.dataset.setting) {
      let value = input.type === "checkbox" ? input.checked : input.value;
      if (input.type === "number") value = Number(value);
      if (["image_aspect"].includes(input.dataset.setting) && !value) value = null;
      this._emit({ [input.dataset.setting]: value });
      return;
    }
    if (input.dataset.array) {
      const key = input.dataset.array;
      const set = new Set(this._config[key] || []);
      if (input.checked) set.add(input.dataset.value);
      else set.delete(input.dataset.value);
      this._emit({ [key]: [...set] });
      return;
    }
    if (input.dataset.hide) {
      const key = input.dataset.hide;
      const set = new Set(this._config[key] || []);
      if (input.checked) set.delete(input.dataset.value);
      else set.add(input.dataset.value);
      this._emit({ [key]: [...set] });
    }
  }
}

class DeepalCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._settings = null;
  }

  setConfig(config) {
    this._config = { ...(config || {}) };
    this._draw();
  }

  set hass(value) {
    const first = !this._hass;
    this._hass = value;
    if (this._settings) {
      this._settings.hass = value;
      if (first) this._draw();
      return;
    }
    this._draw();
  }

  _draw() {
    const vehicles = discoverVehicles(this._hass || {});
    const selected = this._config.device_id || (vehicles[0] && vehicles[0].deviceId) || "";
    this.shadowRoot.innerHTML = `<style>${PANEL_CSS}</style>
      <div class="card-editor">
        <label class="editor-field"><span>${escapeHtml(translate(panelLanguage(this._hass || {}), "vehicle"))}</span>
          <select data-device>
            ${vehicles.length ? "" : `<option value="">${escapeHtml(translate(panelLanguage(this._hass || {}), "no_vehicle"))}</option>`}
            ${vehicles.map((vehicle) => `<option value="${escapeHtml(vehicle.deviceId)}" ${vehicle.deviceId === selected ? "selected" : ""}>${escapeHtml(vehicle.name)}${vehicle.model ? ` · ${escapeHtml(vehicle.model)}` : ""}</option>`).join("")}
          </select>
        </label>
        <deepal-card-settings embedded></deepal-card-settings>
      </div>`;
    const settings = this.shadowRoot.querySelector("deepal-card-settings");
    settings.hass = this._hass;
    settings.tab = "hero";
    settings.config = mergeCardConfig(this._config, null);
    settings.addEventListener("settings-change", (event) => {
      this._config = { ...this._config, ...event.detail };
      settings.config = mergeCardConfig(this._config, null);
      this._emit();
    });
    this.shadowRoot.querySelector("[data-device]").addEventListener("change", (event) => {
      this._config = { ...this._config, device_id: event.target.value };
      this._emit();
      this._draw();
    });
    this._settings = settings;
  }

  _emit() {
    const { type, device_id, ...rest } = this._config;
    const config = { type: `custom:${CARD_TAG}`, ...rest };
    if (device_id) config.device_id = device_id;
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config },
      bubbles: true,
      composed: true,
    }));
  }
}

// ---- 90_registration.js ----
// Register the dashboard card and its editor with Home Assistant.
//
// The frontend swaps window.customElements for its polyfilled registry while
// it boots. A module injected early can therefore define the elements on a
// registry that is thrown away later. Define, verify and keep re-registering
// for a while so the definitions end up in the registry Home Assistant uses.

const CARD_ELEMENTS = [
  [CARD_TAG, DeepalCard],
  ["deepal-card-settings", DeepalCardSettings],
  ["deepal-card-editor", DeepalCardEditor],
];

/** Define the elements missing from the current registry, once. */
function registerCardElements() {
  let registered = true;
  for (const [tag, elementClass] of CARD_ELEMENTS) {
    if (customElements.get(tag)) continue;
    try {
      customElements.define(tag, elementClass);
    } catch (error) {
      // Another copy of the bundle may be defining it right now; the check
      // below decides whether the element is resolvable.
    }
    registered = registered && Boolean(customElements.get(tag));
  }
  if (registered) registerCustomCards();
  return registered;
}

/** Add the card picker entry once, even when the module loads twice. */
function registerCustomCards() {
  window.customCards = window.customCards || [];
  if (window.customCards.some((entry) => entry.type === CARD_TAG)) return;
  window.customCards.push({
    type: CARD_TAG,
    name: translate(browserLanguage(), "card_name"),
    description: translate(browserLanguage(), "card_description"),
    preview: false,
    documentationURL: "https://github.com/Sunek0/ha-deepal-alternative",
  });
}

// Verify for a while: the registry can be replaced right after this module
// runs, so re-register whenever a definition is missing, and stop once the
// definitions have stayed put (or after the ceiling).
const CARD_REGISTRATION_STARTED = Date.now();
const CARD_REGISTRATION_GRACE_MS = 5000;
const CARD_REGISTRATION_CEILING_MS = 30000;
registerCardElements();
const CARD_REGISTRATION_TIMER = window.setInterval(() => {
  const elapsed = Date.now() - CARD_REGISTRATION_STARTED;
  const settled = registerCardElements() && elapsed > CARD_REGISTRATION_GRACE_MS;
  if (settled || elapsed > CARD_REGISTRATION_CEILING_MS) {
    window.clearInterval(CARD_REGISTRATION_TIMER);
  }
}, 250);
window.addEventListener("load", registerCardElements, { once: true });
