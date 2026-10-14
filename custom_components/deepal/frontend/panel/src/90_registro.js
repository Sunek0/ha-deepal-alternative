// Register the frontend elements with Home Assistant.

if (!customElements.get(PANEL_TAG)) {
  customElements.define(PANEL_TAG, DeepalPanel);
}

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, DeepalCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: CARD_TAG,
    name: translate(browserLanguage(), "card_name"),
    description: translate(browserLanguage(), "card_description"),
    // No live preview in the picker: the card renders the full panel, and a
    // preview can race the module load and fail with "custom element not
    // found". The card is added from the list and configured afterwards.
    preview: false,
    documentationURL: "https://github.com/Sunek0/ha-deepal-alternative",
  });
}
