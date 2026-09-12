// astro-satellite-card v6 - explicitly scope model percentages to the current CLM time.
import "/local/astro-satellite-card-v5.js";

const AstroSatelliteCardV6 = customElements.get("astro-satellite-card");

if (AstroSatelliteCardV6 && !AstroSatelliteCardV6.prototype._currentComparisonScopeV6) {
  const proto = AstroSatelliteCardV6.prototype;
  const oldRender = proto._render;

  proto._updateCurrentComparisonV6 = function() {
    if (!this.shadowRoot || !this._config || !this._hass) return;
    const cmpObj = this._hass.states?.[this._config.comparison_entity];
    const cmp = cmpObj?.attributes || {};
    const node = this.shadowRoot.querySelector(".compare");
    if (!node || !cmpObj || cmpObj.state === "unavailable" || !cmp.available) return;

    const agreement = this._num(cmp.agreement_pct ?? cmpObj.state);
    const model = this._num(cmp.model_cloud_pct);
    const sat = this._num(cmp.satellite_cloud_pct);
    if (agreement === null) return;

    node.innerHTML = `<span>Aktuálně v čase CLM:</span> ` +
      `<b style="color:${this._agreementTone(agreement)}">${agreement.toFixed(0)} % shoda</b>` +
      `<span style="color:var(--secondary-text-color)"> · modelový konsensus ${model !== null ? model.toFixed(0) + " %" : "—"} · satelit ${sat !== null ? sat.toFixed(0) + " %" : "—"}</span>`;
    node.title = "Tato procenta jsou okamžitý modelový konsensus ve stejném čase jako CLM snímek; nejsou to průměry za celou noc.";
  };

  proto._render = function() {
    oldRender.call(this);
    this._updateCurrentComparisonV6();
  };

  proto._currentComparisonScopeV6 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-satellite-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Satellite Nowcast Card v6",
    description: "Aktuální modelový konsensus je jednoznačně označen jako hodnota v čase CLM, nikoli průměr za noc.",
  });
}
