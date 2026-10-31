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
