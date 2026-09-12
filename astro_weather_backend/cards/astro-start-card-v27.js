// astro-start-card v27 - current spatial trend plus hour-by-hour cloud trend arrows.
import "/local/astro-start-card-v26.js";

const AstroStartCardV27 = customElements.get("astro-start-card");

if (AstroStartCardV27 && !AstroStartCardV27.prototype._spatialTimelineV27) {
  const proto = AstroStartCardV27.prototype;
  const oldDetail = proto._detailHtml;

  const trendTone = (state) => ({
    incoming: "var(--warning-color,#ff9800)",
    clearing: "var(--success-color,#4caf50)",
    steady: "var(--secondary-text-color)",
    boundary: "var(--secondary-text-color)",
    stable_clear: "var(--success-color,#4caf50)",
    stable_cloudy: "var(--secondary-text-color)",
  })[state] || "var(--secondary-text-color)";

  proto._spatialTrendTooltipV27 = function(spatial) {
    if (!spatial) return "";
    const bits = [
      spatial.shortText || null,
      Number.isFinite(Number(spatial.centerCloud))
        ? `střed ${Number(spatial.centerCloud).toFixed(0)} %`
        : null,
      Number.isFinite(Number(spatial.edgeDistanceKm)) && spatial.edgeDirection
        ? `hrana ~${Number(spatial.edgeDistanceKm).toFixed(0)} km ${spatial.edgeDirection}`
        : null,
      Number.isFinite(Number(spatial.spatialStability))
        ? `prostorová stabilita ${Number(spatial.spatialStability).toFixed(0)} %`
        : null,
      Array.isArray(spatial.sources) && spatial.sources.length
        ? `zdroje ${spatial.sources.join(" + ")}`
        : null,
    ].filter(Boolean);
    return bits.join(" · ");
  };

  proto._detailHtml = function(a) {
    let html = oldDetail.call(this, a);
    if (!a) return html;

    const current = a.currentSpatialCloud;
    const night = a.spatialCloud;

    if (night?.shortText) {
      html = html.replace(
        "<b>Vývoj oblačnosti:</b>",
        "<b>Předpověď noci:</b>",
      );
    }

    if (current?.shortText) {
      const asOf = current.asOf ? this._formatTime(current.asOf) : "teď";
      const title = this._escape(this._spatialTrendTooltipV27(current));
      const panel = `<div class="current-spatial-panel" title="${title}" style="margin-top:10px;padding:8px 10px;border:1px solid var(--divider-color);border-left:4px solid ${trendTone(current.state)};border-radius:8px;background:color-mix(in srgb,var(--secondary-background-color) 72%,transparent);font-size:.80rem"><b>Aktuální trend ${this._escape(asOf)}:</b> ${this._escape(current.shortText)} <span style="color:var(--secondary-text-color)">· podle modelů</span></div>`;
      const spatialMarker = '<div class="spatial-cloud-panel';
      if (html.includes(spatialMarker)) {
        html = html.replace(spatialMarker, `${panel}${spatialMarker}`);
      } else {
        html = html.replace('<div class="aerosol-panel', `${panel}<div class="aerosol-panel`);
      }
    }

    const rows = Array.isArray(a.displayHours) && a.displayHours.length
      ? a.displayHours
      : a.hours;

    if (Array.isArray(rows)) {
      rows.forEach((hour) => {
        const arrow = hour?.spatialArrow;
        if (!arrow || !hour?.start) return;
        const trend = hour.spatialTrend || "steady";
        const label = hour.spatialTrendLabel || "setrvalý stav";
        const edge = Number.isFinite(Number(hour.spatialEdgeDistanceKm)) && hour.spatialEdgeDirection
          ? ` · hrana ~${Number(hour.spatialEdgeDistanceKm).toFixed(0)} km ${hour.spatialEdgeDirection}`
          : "";
        const marker = `<div class="t">${this._formatTime(hour.start)}</div><div class="s">`;
        const injected = `<div class="t">${this._formatTime(hour.start)}</div><div class="hour-spatial-trend" title="${this._escape(`${label}${edge}`)}" style="margin-top:1px;font-size:.76rem;line-height:1;font-weight:800;color:${trendTone(trend)}">${this._escape(arrow)}</div><div class="s">`;
        html = html.replace(marker, injected);
      });
    }

    return html;
  };

  proto._spatialTimelineV27 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v27",
    description: "Jednoduchý verdikt, aktuální trend oblačnosti a hodinové šipky zatahování/vyjasňování.",
  });
}
