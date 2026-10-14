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
 * Layered S05 picture, or the vehicle image entity for other models.
 *
 * Every piece is drawn, closed or open: the base image (Ocar1) is the bare
 * body and the doors, hood and trunk come as separate layers.
 */
function vehicleStageHtml(hass, vehicle) {
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const model = `${vehicle.model || ""} ${vehicle.name || ""}`;

  if (/s05/i.test(model)) {
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
    const layout = PANEL_S05_LAYOUT.status;
    return `<div class="stage stage-status">
      <img src="${assetUrl(layout.base)}" alt="">
      ${layers
        .map((name) => `<img src="${assetUrl(layout.layers[name])}" alt="">`)
        .join("")}
    </div>`;
  }

  const imageId = entity("image", "vehicle_image");
  const picture = imageId ? attributeFor(hass, imageId, "entity_picture") : null;
  if (!picture) return "";
  return `<div class="card"><img class="vehicle-photo" src="${escapeHtml(picture)}" alt=""></div>`;
}

/** State chips shared by the panel status view and the dashboard card. */
function vehicleChipsHtml(hass, vehicle, t) {
  const entity = (domain, key) => entityFor(vehicle, domain, key);
  const chips = [];
  const chip = (label, stateText, active, warn = false) =>
    `<span class="chip ${active ? (warn ? "warn" : "on") : ""}">${escapeHtml(label)}: ${escapeHtml(stateText)}</span>`;
  const chipFor = (labelKey, active) =>
    chip(t(labelKey), active ? t("open") : t("closed"), active, active);

  const lockId = entity("lock", "doors");
  const lockedBinary = entity("binary_sensor", "doors_locked");
  const lockState = lockId ? stateFor(hass, lockId) : null;
  const locked = lockState ? lockState.state === "locked" : null;
  if (lockId && locked !== null) {
    chips.push(
      `<span class="chip ${locked ? "" : "on"}">
        <ha-icon icon="${locked ? PANEL_ICONS.lock : PANEL_ICONS.unlock}"></ha-icon>
        ${escapeHtml(locked ? t("locked") : t("unlocked"))}
      </span>`,
    );
  } else if (lockedBinary) {
    const unlocked = isOn(hass, lockedBinary);
    chips.push(
      chip(t("doors"), unlocked ? t("unlocked") : t("locked"), unlocked, unlocked),
    );
  }

  const anyDoorOpen = [
    "door_front_left",
    "door_front_right",
    "door_rear_left",
    "door_rear_right",
  ].some((key) => isOn(hass, entity("binary_sensor", key)));
  chips.push(chipFor("doors", anyDoorOpen));

  const anyWindowOpen = [
    "window_front_left",
    "window_front_right",
    "window_rear_left",
    "window_rear_right",
  ].some((key) => isOn(hass, entity("binary_sensor", key)));
  chips.push(chipFor("windows", anyWindowOpen));

  chips.push(chipFor("trunk", isOn(hass, entity("binary_sensor", "trunk"))));
  chips.push(chipFor("hood", isOn(hass, entity("binary_sensor", "hood"))));

  const lightKeys = ["low_beam", "high_beam", "position_lamp"].filter((key) =>
    isOn(hass, entity("binary_sensor", key)),
  );
  chips.push(
    chip(
      t("lights"),
      lightKeys.length ? lightKeys.map((key) => t(key)).join(", ") : t("off"),
      lightKeys.length > 0,
    ),
  );

  const engineOn = isOn(hass, entity("binary_sensor", "engine"));
  chips.push(chip(t("engine"), engineOn ? t("on") : t("off"), engineOn));

  return chips.join("");
}
