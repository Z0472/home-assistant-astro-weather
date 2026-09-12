// astro-start-card v30 - live satellite agreement only in today's top summary.
import "/local/astro-start-card-v29.js";

const AstroStartCardV30 = customElements.get("astro-start-card");

if (AstroStartCardV30 && !AstroStartCardV30.prototype._satelliteSummaryV30) {
  const proto = AstroStartCardV30.prototype;
  const oldNightSummary = proto._nightSummaryHtml;
  const oldDetail = proto._detailHtml;

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
        `Aktuální satelit ${Number.isFinite(sat) ? sat.toFixed(0) + " %" : "—"} · ` +
        `modelový konsensus ${Number.isFinite(model) ? model.toFixed(0) + " %" : "—"} · ` +
        `absolutní rozdíl ${Number(comparison.absolute_error_pp ?? 0).toFixed(0)} p. b.`
      );
      return `<div class="night-satellite-v30" title="${title}" style="margin-top:5px;font-size:.72rem;line-height:1.25;color:var(--primary-text-color)"><span style="font-weight:700">🛰 Satelit vs modely:</span> <span style="font-weight:800;color:${tone}">${agreement.toFixed(0)} % shoda</span><span style="color:var(--secondary-text-color)"> · model ${Number.isFinite(model) ? model.toFixed(0) + " %" : "—"} / satelit ${Number.isFinite(sat) ? sat.toFixed(0) + " %" : "—"}</span></div>`;
    }

    const status = satellite?.credential_status;
    const text = status === "required"
      ? "čeká na EUMETSAT CLM přístup"
      : satellite?.reason || comparison?.reason || "bez kvantitativních dat";
    return `<div class="night-satellite-v30" style="margin-top:5px;font-size:.72rem;line-height:1.25;color:var(--secondary-text-color)"><span style="font-weight:700">🛰 Satelit:</span> ${this._escape(text)}</div>`;
  };

  proto._nightSummaryHtml = function(a, idx) {
    let html = oldNightSummary.call(this, a, idx);
    if (idx !== 0) return html;
    const line = this._satelliteAgreementSummaryV30();
    if (!line) return html;

    const modelRow = /(<div class="night-models">[\s\S]*?<\/div>)/;
    if (modelRow.test(html)) {
      return html.replace(modelRow, `$1${line}`);
    }
    return html.replace("</button>", `${line}</button>`);
  };

  // v29 inserted the live satellite line into the expanded detail.  In v30 it
  // belongs only to today's top card, because it is current reality rather than
  // a per-night forecast.
  proto._detailHtml = function(a) {
    const html = oldDetail.call(this, a);
    return html.replace(/<div class="satellite-agreement-v29"[\s\S]*?<\/div>/, "");
  };

  proto._satelliteSummaryV30 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v30",
    description: "Centrální rozhodnutí observatoře; živá shoda se satelitem je pouze v horním rámečku dneška.",
  });
}
