// astro-start-card v23 - DWD ICON and multi-model consensus extension.
import "/local/astro-start-card-base-v22.js";

const AstroStartCardV23 = customElements.get("astro-start-card");

if (AstroStartCardV23 && !AstroStartCardV23.prototype._multiModelV23) {
  const proto = AstroStartCardV23.prototype;
  const oldNightSummary = proto._nightSummaryHtml;
  const oldDetail = proto._detailHtml;
  const oldHourLimit = proto._hourLimit;

  const pct = (value) => Number.isFinite(Number(value))
    ? `${Number(value).toFixed(0)} %`
    : "—";

  const agreementLabel = (value) => ({
    good: "dobrá shoda",
    outlier: "jeden model mimo shodu",
    reduced: "nižší shoda",
    conflict: "konflikt modelů",
    single: "jen jeden model",
    none: "bez modelu",
  })[value] || "";

  proto._nightSummaryHtml = function(a, idx) {
    let html = oldNightSummary.call(this, a, idx);
    const icon = pct(a?.iconAvg);
    html = html.replace(
      /(<span>ALADIN [^<]*<\/span>)(<span>KOMB)/,
      `$1<span>ICON ${icon}</span>$2`,
    );
    html = html.replace("Oba modely: převážně zataženo", "Modely: převážně zataženo");
    return html;
  };

  proto._hourLimit = function(h) {
    const result = oldHourLimit.call(this, h);
    const models = [
      `MET ${pct(h?.metTotal)}`,
      `ALADIN ${pct(h?.aladinTotal)}`,
      `ICON ${pct(h?.iconTotal)}`,
    ].join(" · ");
    const spread = Number(h?.modelSpread);
    const agreement = agreementLabel(h?.modelAgreement);
    const modelInfo = [
      `Modely: ${models}`,
      Number.isFinite(spread) ? `rozptyl ${spread.toFixed(0)} p. b.` : null,
      agreement || null,
      h?.modelOutlierName ? `mimo shodu: ${h.modelOutlierName}` : null,
    ].filter(Boolean).join(" · ");
    return { ...result, title: `${result.title} ${modelInfo}.` };
  };

  proto._detailHtml = function(a) {
    let html = oldDetail.call(this, a);
    if (!a?.hours?.length) return html;

    html = html.replace(
      /(<span>ALADIN: <b>[^<]*<\/b><\/span>)(\s*<span>Kombinovaná oblačnost:)/,
      `$1\n        <span>ICON: <b>${pct(a?.iconAvg)}</b></span>$2`,
    );

    const coverage2 = Number.isFinite(Number(a?.modelCoverage))
      ? `${Math.round(Number(a.modelCoverage) * 100)} %`
      : "—";
    const coverage3 = Number.isFinite(Number(a?.threeModelCoverage))
      ? `${Math.round(Number(a.threeModelCoverage) * 100)} %`
      : "—";

    html = html.replace(
      /<span>Oba modely dostupné: <b>[^<]*<\/b><\/span>/,
      `<span>≥2 modely dostupné: <b>${coverage2}</b></span><span>3 modely dostupné: <b>${coverage3}</b></span>`,
    );
    return html;
  };

  proto._multiModelV23 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v23",
    description: "Centrální rozhodnutí observatoře s konsenzem MET, ALADIN a DWD ICON, AOD 550 a seeingem.",
  });
}
