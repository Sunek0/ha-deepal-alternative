// Dashboard card: the sidebar panel inside a card. It is configured with one
// vehicle (device selector) and inherits the three views, the action handling
// and the update guards from the panel element.

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

  _renderHtml() {
    const vehicle = this._vehicle;
    const refresh = vehicle
      ? entityFor(vehicle, "button", "refresh")
      : undefined;
    return `
      <style>${PANEL_CSS}</style>
      <div class="card-root">
        <div class="card-title">
          <ha-icon icon="mdi:car-electric"></ha-icon>
          ${escapeHtml(vehicle ? vehicle.name : this._t("title"))}
          <div class="spacer"></div>
          ${
            refresh
              ? `<button class="icon-button" title="${escapeHtml(this._t("refresh_hint"))}" data-action="refresh"><ha-icon icon="mdi:refresh"></ha-icon></button>`
              : ""
          }
        </div>
        ${this._error ? `<div class="error">${escapeHtml(this._error)}</div>` : ""}
        ${
          vehicle
            ? `<nav class="tabs" role="tablist">${this._tabsHtml()}</nav>
               <div class="view">${this._renderView(vehicle)}</div>`
            : `<div class="empty">${escapeHtml(this._t("no_vehicle"))}</div>`
        }
      </div>`;
  }
}
