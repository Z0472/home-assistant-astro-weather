// astro-start-card v26 - compact spatial cloud trend around the observatory.
import "/local/astro-start-card-v25.js";

const AstroStartCardV26 = customElements.get("astro-start-card");

if (AstroStartCardV26 && !AstroStartCardV26.prototype._spatialCloudV26) {
  const proto = AstroStartCardV26.prototype;
  const oldNightSummary = proto._nightSummaryHtml;
  const oldDetail = proto._detailHtml;

  const tone = (state) => ({
    stable_clear: "good",
    clearing: "good",
    boundary: "warning",
    incoming: "warning",
    stable_cloudy: "bad",
  })[state] || "neutral";

  proto._spatialCloudTooltipV26 = function(spatial) {
    if (!spatial) return "";
    const bits = [
      `Okolí ${Number(spatial.radiusKm || 0).toFixed(0)} km`,
      Number.isFinite(Number(spatial.centerCloud)) ? `střed ${Number(spatial.centerCloud).toFixed(0)} %` : null,
      Number.isFinite(Number(spatial.minCloud)) && Number.isFinite(Number(spatial.maxCloud))
        ? `rozsah ${Number(spatial.minCloud).toFixed(0)}–${Number(spatial.maxCloud).toFixed(0)} %`
        : null,
      Number.isFinite(Number(spatial.spatialStability))
        ? `prostorová stabilita ${Number(spatial.spatialStability).toFixed(0)} %`
        : null,
      Array.isArray(spatial.sources) && spatial.sources.length
        ? `zdroje ${spatial.sources.join(" + ")}`
        : null,
      spatial.dominantLayer ? `dominantní vrstva ${spatial.dominantLayer}` : null,
      Number.isFinite(Number(spatial.windSpeedMs)) && Number.isFinite(Number(spatial.windFromDeg))
        ? `proudění ${Number(spatial.windSpeedMs).toFixed(1)} m/s z ${Number(spatial.windFromDeg).toFixed(0)}°`
        : null,
    ].filter(Boolean);
    return bits.join(" · ");
  };

  proto._nightSummaryHtml = function(a, idx) {
    let html = oldNightSummary.call(this, a, idx);
    const spatial = a?.spatialCloud;
    if (!spatial?.shortText) return html;
    const cls = tone(spatial.state);
    const title = this._escape(this._spatialCloudTooltipV26(spatial));
    const row = `<div class="night-spatial ${cls}" title="${title}" style="margin-top:6px;font-size:.72rem;font-weight:700;color:${cls === "good" ? "var(--success-color,#4caf50)" : cls === "bad" ? "var(--error-color,#f44336)" : "var(--warning-color,#ff9800)"}">${this._escape(spatial.shortText)}</div>`;
    return html.replace('<div class="night-aerosols', `${row}<div class="night-aerosols`);
  };

  proto._detailHtml = function(a) {
    let html = oldDetail.call(this, a);
    const spatial = a?.spatialCloud;
    if (!spatial?.shortText) return html;
    const cls = tone(spatial.state);
    const title = this._escape(this._spatialCloudTooltipV26(spatial));
    const accent = cls === "good"
      ? "var(--success-color,#4caf50)"
      : cls === "bad"
        ? "var(--error-color,#f44336)"
        : "var(--warning-color,#ff9800)";
    const panel = `<div class="spatial-cloud-panel ${cls}" title="${title}" style="margin-top:10px;padding:8px 10px;border:1px solid var(--divider-color);border-left:4px solid ${accent};border-radius:8px;background:color-mix(in srgb,var(--secondary-background-color) 72%,transparent);font-size:.80rem"><b>Vývoj oblačnosti:</b> ${this._escape(spatial.shortText)} <span style="color:var(--secondary-text-color)">· okolí ${this._escape(spatial.radiusKm)} km</span></div>`;
    return html.replace('<div class="aerosol-panel', `${panel}<div class="aerosol-panel`);
  };

  proto._spatialCloudV26 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v26",
    description: "Jednoduchý verdikt s prostorovým trendem oblačnosti v okolí observatoře.",
  });
}
