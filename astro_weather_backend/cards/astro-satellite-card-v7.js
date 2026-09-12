// astro-satellite-card v7 - ensure the live CLM age timer starts on existing Lovelace card instances.
import "/local/astro-satellite-card-v6.js";

const AstroSatelliteCardV7 = customElements.get("astro-satellite-card");

if (AstroSatelliteCardV7 && !AstroSatelliteCardV7.prototype._liveAgeTimerV7) {
  const proto = AstroSatelliteCardV7.prototype;
  const oldRender = proto._render;
  const hassDescriptor = Object.getOwnPropertyDescriptor(proto, "hass");
  const oldHassSetter = hassDescriptor?.set;

  proto._ensureLiveClmAgeTimerV7 = function() {
    // v5 already owns cleanup of _satAgeTimerV5 in disconnectedCallback.
    // Its connectedCallback can be missed when a newer module patches an
    // already-connected Lovelace element, so also start the timer from render
    // and from the HA state setter, both of which are guaranteed to run.
    if (!this._satAgeTimerV5) {
      this._satAgeTimerV5 = setInterval(() => this._updateLiveClmAgeV5(), 30000);
    }
  };

  proto._render = function() {
    oldRender.call(this);
    this._ensureLiveClmAgeTimerV7();
    this._updateLiveClmAgeV5();
  };

  if (oldHassSetter) {
    Object.defineProperty(proto, "hass", {
      ...hassDescriptor,
      set(hass) {
        oldHassSetter.call(this, hass);
        this._ensureLiveClmAgeTimerV7();
        this._updateLiveClmAgeV5();
      },
    });
  }

  proto._liveAgeTimerV7 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-satellite-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Satellite Nowcast Card v7",
    description: "CLM stáří se živě aktualizuje i na již připojené Lovelace kartě bez Ctrl+F5.",
  });
}
