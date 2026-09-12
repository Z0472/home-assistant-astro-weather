// astro-start-card v33 - compare current models with the CLM sample directly over the observatory.
import "/local/astro-start-card-v32.js";

const AstroStartCardV33 = customElements.get("astro-start-card");

if (AstroStartCardV33 && !AstroStartCardV33.prototype._localSatelliteComparisonV33) {
  const proto = AstroStartCardV33.prototype;

  proto._satelliteAgreementSummaryV30 = function() {
    const attrs = this._hass?.states?.[this._config?.decision_entity]?.attributes || {};
    const comparison = attrs.satelliteComparison;
    const satellite = attrs.satelliteNowcast;
    if (!comparison && !satellite) return "";

    if (comparison?.available && Number.isFinite(Number(comparison.agreement_pct))) {
      const agreement = Number(comparison.agreement_pct);
      const model = Number(comparison.model_cloud_pct);
      const localCloud = Number(comparison.satellite_local_cloud_pct ?? comparison.satellite_cloud_pct);
      const localLabel = Number.isFinite(localCloud) ? (localCloud >= 50 ? "mrak" : "jasno") : "bez dat";
      const tone = agreement >= 85
        ? "var(--success-color,#4caf50)"
        : agreement >= 70
          ? "var(--info-color,#2196f3)"
          : agreement >= 50
            ? "var(--warning-color,#ff9800)"
            : "var(--error-color,#f44336)";
      const title = this._escape(
        `Aktuální porovnání v čase CLM přímo nad observatoří: ` +
        `CLM ${localLabel} · modelový konsensus ${Number.isFinite(model) ? model.toFixed(0) + " %" : "—"} · ` +
        `absolutní rozdíl ${Number(comparison.absolute_error_pp ?? 0).toFixed(0)} p. b. Regionální 30km podíl oblačnosti se do této shody nezapočítává.`
      );
      return `<div class="night-satellite-v30" title="${title}" style="margin-top:5px;font-size:.72rem;line-height:1.25;color:var(--primary-text-color)"><span style="font-weight:700">🛰 Satelit vs aktuální modely:</span> <span style="font-weight:800;color:${tone}">${agreement.toFixed(0)} % shoda</span><span style="color:var(--secondary-text-color)"> · observatoř ${this._escape(localLabel)}</span></div>`;
    }

    const status = satellite?.credential_status;
    const text = status === "required"
      ? "čeká na EUMETSAT CLM přístup"
      : satellite?.reason || comparison?.reason || "bez kvantitativních dat";
    return `<div class="night-satellite-v30" style="margin-top:5px;font-size:.72rem;line-height:1.25;color:var(--secondary-text-color)"><span style="font-weight:700">🛰 Satelit:</span> ${this._escape(text)}</div>`;
  };

  proto._localSatelliteComparisonV33 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v33",
    description: "Aktuální shoda modelů se satelitem je vztažena ke CLM vzorku přímo nad observatoří, nikoli k regionálnímu 30km průměru.",
  });
}
