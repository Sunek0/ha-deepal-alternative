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
