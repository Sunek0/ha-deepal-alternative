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
