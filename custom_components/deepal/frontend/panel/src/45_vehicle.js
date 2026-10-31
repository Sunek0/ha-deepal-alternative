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
