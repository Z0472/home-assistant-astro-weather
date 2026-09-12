// astro-satellite-card v8 - separate observatory CLM state from 30 km area cloud fraction.
import "/local/astro-satellite-card-v7.js";

const AstroSatelliteCardV8 = customElements.get("astro-satellite-card");

if (AstroSatelliteCardV8 && !AstroSatelliteCardV8.prototype._localVsAreaV8) {
  const proto = AstroSatelliteCardV8.prototype;
  const oldRender = proto._render;

  proto._localClmV8 = function(value) {
    const n = this._num(value);
    if (n === null) return { icon: "❔", label: "bez dat" };
    return n >= 50
      ? { icon: "☁️", label: "mrak" }
      : { icon: "🌙", label: "jasno" };
  };

  proto._areaTrendV8 = function(sat) {
    return ({
      incoming: "oblačnost v okolí přibývá",
      clearing: "oblačnost v okolí ubývá",
      steady: "bez výrazné změny",
    })[sat?.trend] || "trend neurčen";
  };

  proto._updateLocalVsAreaV8 = function() {
    if (!this.shadowRoot || !this._config || !this._hass) return;
    const satObj = this._hass.states?.[this._config.satellite_entity];
    if (!satObj || satObj.state === "unavailable") return;
    const sat = satObj.attributes || {};
    if (!sat.available) return;

    const radius = this._num(sat.radius_km) ?? 30;
    const areaCloud = this._num(sat.cloud_pct ?? satObj.state);
    const local = this._localClmV8(sat.center_cloud_pct);
    const current = this.shadowRoot.querySelector(".current");
    if (current) {
      const icon = current.querySelector(".icon");
      const cloud = current.querySelector(".cloud");
      const summary = current.querySelector(".summary");
      if (icon) icon.textContent = local.icon;
      if (cloud) cloud.textContent = `Observatoř: ${local.label}`;
      if (summary) {
        const bits = [
          `Okolí ${radius.toFixed(0)} km: ${areaCloud !== null ? areaCloud.toFixed(0) + " %" : "—"} oblačných CLM vzorků`,
          this._areaTrendV8(sat),
        ];
        const edge = sat.edge || {};
        if (edge?.stable && edge?.direction) {
          let edgeText = `hrana ${edge.direction}`;
          if (edge.approaching && Number.isFinite(Number(edge.eta_minutes))) {
            edgeText += ` · ETA ~${Number(edge.eta_minutes).toFixed(0)} min`;
          }
          bits.push(edgeText);
        }
        summary.textContent = bits.join(" · ");
        summary.title = "Stav observatoře je jediný středový CLM vzorek. Procento okolí je podíl oblačných vzorků z 17 bodů v kruhu, nikoli procento oblačnosti přímo nad dalekohledem.";
      }
    }

    const timeline = this.shadowRoot.querySelector(".timeline");
    if (timeline) {
      const title = document.createElement("div");
      title.className = "area-timeline-title-v8";
      title.textContent = `Vývoj oblačnosti v okolí ${radius.toFixed(0)} km`;
      title.style.cssText = "margin:2px 0 6px;font-size:.72rem;font-weight:700;color:var(--secondary-text-color)";
      timeline.before(title);
      timeline.querySelectorAll(".hour").forEach((node, index) => {
        node.title = index === 0
          ? `Skutečný podíl oblačných CLM vzorků v okolí ${radius.toFixed(0)} km.`
          : `Extrapolační nowcast podílu oblačných CLM vzorků v okolí ${radius.toFixed(0)} km; nejde o nový budoucí satelitní snímek.`;
      });
    }

    const cmpObj = this._hass.states?.[this._config.comparison_entity];
    const cmp = cmpObj?.attributes || {};
    const compareNode = this.shadowRoot.querySelector(".compare");
    if (compareNode && cmpObj && cmpObj.state !== "unavailable" && cmp.available) {
      const agreement = this._num(cmp.agreement_pct ?? cmpObj.state);
      const model = this._num(cmp.model_cloud_pct);
      const cmpLocal = this._localClmV8(cmp.satellite_local_cloud_pct ?? cmp.satellite_cloud_pct);
      if (agreement !== null) {
        compareNode.innerHTML = `<span>Aktuálně v čase CLM:</span> ` +
          `<b style="color:${this._agreementTone(agreement)}">${agreement.toFixed(0)} % shoda</b>` +
          `<span style="color:var(--secondary-text-color)"> · modelový konsensus ${model !== null ? model.toFixed(0) + " %" : "—"} · observatoř ${this._escape(cmpLocal.label)}</span>`;
        compareNode.title = "Modely jsou porovnávány se středovým CLM vzorkem nad observatoří. Regionální podíl oblačných vzorků do porovnání modelů nevstupuje.";
      }
    }
  };

  proto._render = function() {
    oldRender.call(this);
    this._updateLocalVsAreaV8();
  };

  proto._localVsAreaV8 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-satellite-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Satellite Nowcast Card v8",
    description: "Odděluje skutečný CLM stav přímo nad observatoří od regionálního podílu oblačných vzorků a jeho nowcastu.",
  });
}
