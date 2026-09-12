// astro-start-card v29 - compact live satellite/model agreement.
import "/local/astro-start-card-v28.js";

const AstroStartCardV29 = customElements.get("astro-start-card");

if (AstroStartCardV29 && !AstroStartCardV29.prototype._satelliteAgreementV29) {
  const proto = AstroStartCardV29.prototype;
  const oldDetail = proto._detailHtml;

  proto._satelliteAgreementLineV29 = function() {
    const attrs = this._hass?.states?.[this._config?.decision_entity]?.attributes || {};
    const comparison = attrs.satelliteComparison;
    const satellite = attrs.satelliteNowcast;
    if (!comparison && !satellite) return "";

    if (comparison?.available && Number.isFinite(Number(comparison.agreement_pct))) {
      const agreement = Number(comparison.agreement_pct);
      const model = Number(comparison.model_cloud_pct);
      const sat = Number(comparison.satellite_cloud_pct);
      const tone = agreement >= 85
        ? "var(--success-color,#4caf50)"
        : agreement >= 70
          ? "var(--info-color,#2196f3)"
          : agreement >= 50
            ? "var(--warning-color,#ff9800)"
            : "var(--error-color,#f44336)";
      const title = this._escape(
        `Satelit ${Number.isFinite(sat) ? sat.toFixed(0) + " %" : "—"} · ` +
        `konsensus ${Number.isFinite(model) ? model.toFixed(0) + " %" : "—"} · ` +
        `absolutní rozdíl ${Number(comparison.absolute_error_pp ?? 0).toFixed(0)} p. b. · ` +
        `modelů ${Number(comparison.model_count ?? 0)}`
      );
      return `<div class="satellite-agreement-v29" title="${title}" style="margin-top:7px;font-size:.79rem;line-height:1.35;color:var(--primary-text-color)"><span style="font-weight:700">🛰 Satelit vs modely:</span> <span style="font-weight:800;color:${tone}">${agreement.toFixed(0)} % shoda</span><span style="color:var(--secondary-text-color)"> · model ${Number.isFinite(model) ? model.toFixed(0) + " %" : "—"} / satelit ${Number.isFinite(sat) ? sat.toFixed(0) + " %" : "—"}</span></div>`;
    }

    const status = satellite?.credential_status;
    const text = status === "required"
      ? "čeká na EUMETSAT CLM přístup"
      : satellite?.reason || comparison?.reason || "bez kvantitativních dat";
    return `<div class="satellite-agreement-v29" style="margin-top:7px;font-size:.79rem;line-height:1.35;color:var(--secondary-text-color)"><span style="font-weight:700">🛰 Satelit vs modely:</span> ${this._escape(text)}</div>`;
  };

  proto._detailHtml = function(a) {
    let html = oldDetail.call(this, a);
    const line = this._satelliteAgreementLineV29();
    if (!line) return html;

    const marker = '<div class="current-spatial-panel';
    if (html.includes(marker)) {
      const end = html.indexOf("</div>", html.indexOf(marker));
      if (end >= 0) {
        html = html.slice(0, end + 6) + line + html.slice(end + 6);
        return html;
      }
    }
    const spatialMarker = '<div class="spatial-cloud-panel';
    if (html.includes(spatialMarker)) {
      return html.replace(spatialMarker, `${line}${spatialMarker}`);
    }
    return `${line}${html}`;
  };

  proto._satelliteAgreementV29 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v29",
    description: "Centrální rozhodnutí observatoře s kompaktní aktuální shodou modelového konsensu se satelitní realitou.",
  });
}
