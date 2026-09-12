// astro-start-card v32 - keep nightly model averages in one place and clarify live satellite comparison.
import "/local/astro-start-card-v31.js";

const AstroStartCardV32 = customElements.get("astro-start-card");

if (AstroStartCardV32 && !AstroStartCardV32.prototype._modelPercentCleanupV32) {
  const proto = AstroStartCardV32.prototype;
  const oldNightSummary = proto._nightSummaryHtml;
  const oldDetail = proto._detailHtml;

  // The satellite comparison is an instantaneous comparison at the CLM time,
  // not the average model cloud cover for the whole astronomical night.  Keep
  // the current model percentage on the dedicated satellite card only.
  proto._satelliteAgreementSummaryV30 = function() {
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
        `Aktuální porovnání v čase CLM: satelit ${Number.isFinite(sat) ? sat.toFixed(0) + " %" : "—"} · ` +
        `modelový konsensus ${Number.isFinite(model) ? model.toFixed(0) + " %" : "—"} · ` +
        `absolutní rozdíl ${Number(comparison.absolute_error_pp ?? 0).toFixed(0)} p. b.`
      );
      return `<div class="night-satellite-v30" title="${title}" style="margin-top:5px;font-size:.72rem;line-height:1.25;color:var(--primary-text-color)"><span style="font-weight:700">🛰 Satelit vs aktuální modely:</span> <span style="font-weight:800;color:${tone}">${agreement.toFixed(0)} % shoda</span><span style="color:var(--secondary-text-color)"> · satelit ${Number.isFinite(sat) ? sat.toFixed(0) + " %" : "—"}</span></div>`;
    }

    const status = satellite?.credential_status;
    const text = status === "required"
      ? "čeká na EUMETSAT CLM přístup"
      : satellite?.reason || comparison?.reason || "bez kvantitativních dat";
    return `<div class="night-satellite-v30" style="margin-top:5px;font-size:.72rem;line-height:1.25;color:var(--secondary-text-color)"><span style="font-weight:700">🛰 Satelit:</span> ${this._escape(text)}</div>`;
  };

  proto._nightSummaryHtml = function(a, idx) {
    let html = oldNightSummary.call(this, a, idx);
    html = html.replace(
      '<div class="night-models">',
      '<div class="night-models" title="Průměry oblačnosti za astronomickou noc">',
    );
    return html;
  };

  proto._detailHtml = function(a) {
    let html = oldDetail.call(this, a);

    // The same nightly cloud averages are already shown in the top night card.
    // Remove their second presentation from detail, but keep score, model
    // agreement, usable hours and model-coverage diagnostics.
    const duplicateNightAverages = [
      /\s*<span>Průměr MET: <b>[^<]*<\/b><\/span>/,
      /\s*<span>ALADIN: <b>[^<]*<\/b><\/span>/,
      /\s*<span>ICON: <b>[^<]*<\/b><\/span>/,
      /\s*<span>Kombinovaná oblačnost: <b>[^<]*<\/b><\/span>/,
    ];
    for (const pattern of duplicateNightAverages) html = html.replace(pattern, "");
    return html;
  };

  proto._modelPercentCleanupV32 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v32",
    description: "Noční modelové průměry jsou zobrazené pouze jednou; aktuální satelitní porovnání je jasně odlišeno od nočního průměru.",
  });
}
