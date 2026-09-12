// astro-satellite-card v4 - cleaner, finer CLM overlay on a larger IR panel.
import "/local/astro-satellite-card-v3.js";

const AstroSatelliteCardV4 = customElements.get("astro-satellite-card");

if (AstroSatelliteCardV4 && !AstroSatelliteCardV4.prototype._fineOverlayV4) {
  const proto = AstroSatelliteCardV4.prototype;

  proto.getCardSize = function() {
    return this._config?.show_image === false ? 4 : 10;
  };

  proto._visualPanel = function(attrs, satObj) {
    if (this._config?.show_image === false) return "";
    const imageUrl = this._visualUrl(attrs, satObj);
    if (!imageUrl) return "";

    const size = this._num(attrs.visual_size_px) ?? 900;
    const center = size / 2;
    const visualRadius = this._num(attrs.visual_radius_km) ?? 150;
    const mapRadius = this._num(attrs.clm_map_radius_km ?? attrs.radius_km) ?? 30;
    const pxPerKm = center / visualRadius;
    const innerPx = mapRadius * 0.5 * pxPerKm;
    const outerPx = mapRadius * pxPerKm;
    const points = attrs?.clm_points;
    const showOverlay = this._config?.show_clm_map !== false && points && typeof points === "object" && !Array.isArray(points);

    const samples = [];
    if (showOverlay) {
      for (const [id, value] of Object.entries(points)) {
        const pos = this._samplePosition(id, mapRadius, visualRadius, size);
        if (!pos) continue;
        const cls = value === 0 || value === "0"
          ? "sample-clear-v4"
          : value === 1 || value === "1"
            ? "sample-cloud-v4"
            : "sample-nodata-v4";
        samples.push(`
          <circle class="sample-v4 ${cls}" cx="${pos.x.toFixed(1)}" cy="${pos.y.toFixed(1)}" r="${pos.center ? 6 : 5}">
            <title>${this._escape(`${id}: ${this._clmLabel(value)}`)}</title>
          </circle>`);
      }
    }

    const overlay = showOverlay ? `
      <svg class="visual-overlay visual-overlay-v4" viewBox="0 0 ${size} ${size}" role="img" aria-label="IR10.5 se skutečnými CLM vzorky kolem observatoře">
        <circle class="range-ring-v4 inner" cx="${center}" cy="${center}" r="${innerPx.toFixed(1)}"></circle>
        <circle class="range-ring-v4 outer" cx="${center}" cy="${center}" r="${outerPx.toFixed(1)}"></circle>
        ${samples.join("")}
        <circle class="observatory-ring-v4" cx="${center}" cy="${center}" r="9"></circle>
        <line class="observatory-cross-v4" x1="${center - 13}" y1="${center}" x2="${center + 13}" y2="${center}"></line>
        <line class="observatory-cross-v4" x1="${center}" y1="${center - 13}" x2="${center}" y2="${center + 13}"></line>
      </svg>` : "";

    const cycleTime = this._time(satObj?.last_updated);
    return `
      <style>
        .wrap { padding-left:8px !important; padding-right:8px !important; }
        .visual-section { margin-left:-1px; margin-right:-1px; }
        .visual-panel {
          width:calc(100% + 10px) !important;
          margin-left:-5px !important;
          border-radius:8px !important;
        }
        .visual-overlay-v4 { opacity:.92; }
        .range-ring-v4 {
          fill:none;
          stroke:rgba(255,255,255,.46);
          stroke-width:1.35;
        }
        .range-ring-v4.inner { stroke-dasharray:5 5; }
        .sample-v4 {
          stroke:rgba(255,255,255,.88);
          stroke-width:1.15;
          opacity:.88;
        }
        .sample-clear-v4 { fill:rgba(33,150,243,.92); }
        .sample-cloud-v4 { fill:rgba(158,158,158,.92); }
        .sample-nodata-v4 { fill:rgba(97,97,97,.80); }
        .observatory-ring-v4 {
          fill:none;
          stroke:rgba(255,202,40,.95);
          stroke-width:2.1;
        }
        .observatory-cross-v4 {
          stroke:rgba(255,202,40,.95);
          stroke-width:1.5;
        }
        .visual-note-v4 {
          margin-top:4px;
          color:var(--secondary-text-color);
          font-size:.61rem;
          line-height:1.25;
          text-align:center;
        }
      </style>
      <div class="visual-section">
        <div class="visual-head"><b>MTG/FCI IR10.5 + CLM vzorky</b><span>výřez ±${visualRadius.toFixed(0)} km · načteno ${cycleTime}</span></div>
        <div class="visual-panel">
          <img class="visual-image" src="${this._escape(imageUrl)}" alt="Aktuální EUMETSAT MTG IR10.5">
          ${overlay}
        </div>
        <div class="visual-note-v4">modrá jasno · šedá mrak · kruhy ${(mapRadius / 2).toFixed(0)} / ${mapRadius.toFixed(0)} km</div>
      </div>`;
  };

  proto._fineOverlayV4 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-satellite-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Satellite Nowcast Card v4",
    description: "Větší MTG/FCI IR snímek s jemným CLM overlayem bez textů uvnitř obrazu.",
  });
}
