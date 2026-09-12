// astro-satellite-card v5 - explicit live CLM age and IR refresh timestamps.
import "/local/astro-satellite-card-v4.js";

const AstroSatelliteCardV5 = customElements.get("astro-satellite-card");

if (AstroSatelliteCardV5 && !AstroSatelliteCardV5.prototype._logicalTimeLabelsV5) {
  const proto = AstroSatelliteCardV5.prototype;
  const oldRender = proto._render;
  const oldVisualPanel = proto._visualPanel;
  const oldConnected = proto.connectedCallback;
  const oldDisconnected = proto.disconnectedCallback;

  proto._liveClmAgeV5 = function(asOf) {
    const d = asOf ? new Date(asOf) : null;
    if (!(d instanceof Date) || Number.isNaN(d.getTime())) return null;
    return Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
  };

  proto._updateLiveClmAgeV5 = function() {
    if (!this.shadowRoot || !this._config || !this._hass) return;
    const satObj = this._hass.states?.[this._config.satellite_entity];
    const asOf = satObj?.attributes?.as_of;
    const age = this._liveClmAgeV5(asOf);
    const node = this.shadowRoot.querySelector(".age");
    if (!node) return;

    if (age === null) {
      node.textContent = "CLM —";
      node.style.color = "var(--secondary-text-color)";
      return;
    }

    node.textContent = `CLM ${this._time(asOf)} · před ${age} min`;
    node.title = "Čas CLM je čas měření; stáří se přepočítává živě v prohlížeči.";
    node.style.color = age >= 45
      ? "var(--error-color,#f44336)"
      : age >= 30
        ? "var(--warning-color,#ff9800)"
        : "var(--secondary-text-color)";
  };

  proto._visualPanel = function(attrs, satObj) {
    const html = oldVisualPanel.call(this, attrs, satObj);
    if (!html) return html;
    const visualRadius = this._num(attrs?.visual_radius_km) ?? 150;
    const refreshed = this._time(satObj?.last_updated);
    const replacement = `<div class="visual-head"><b>MTG/FCI IR10.5 + CLM vzorky</b><span>IR obnoveno ${refreshed} · výřez ±${visualRadius.toFixed(0)} km</span></div>`;
    return html.replace(
      /<div class="visual-head"><b>MTG\/FCI IR10\.5 \+ CLM vzorky<\/b><span>[\s\S]*?<\/span><\/div>/,
      replacement,
    );
  };

  proto._render = function() {
    oldRender.call(this);
    this._updateLiveClmAgeV5();
  };

  proto.connectedCallback = function() {
    if (oldConnected) oldConnected.call(this);
    if (!this._satAgeTimerV5) {
      this._satAgeTimerV5 = setInterval(() => this._updateLiveClmAgeV5(), 30000);
    }
    this._updateLiveClmAgeV5();
  };

  proto.disconnectedCallback = function() {
    if (this._satAgeTimerV5) {
      clearInterval(this._satAgeTimerV5);
      this._satAgeTimerV5 = null;
    }
    if (oldDisconnected) oldDisconnected.call(this);
  };

  proto._logicalTimeLabelsV5 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-satellite-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Satellite Nowcast Card v5",
    description: "Satelitní karta s živým stářím CLM dat a jednoznačně odděleným časem obnovení IR obrazu.",
  });
}
