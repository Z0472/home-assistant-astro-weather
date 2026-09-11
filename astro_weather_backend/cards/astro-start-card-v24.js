// astro-start-card v24 - score and confidence shown together.
import "/local/astro-start-card-v23.js";

const AstroStartCardV24 = customElements.get("astro-start-card");

if (AstroStartCardV24 && !AstroStartCardV24.prototype._confidenceV24) {
  const proto = AstroStartCardV24.prototype;
  const oldNightSummary = proto._nightSummaryHtml;
  const oldDetail = proto._detailHtml;

  const numberText = (value, suffix = "") => Number.isFinite(Number(value))
    ? `${Number(value).toFixed(0)}${suffix}`
    : "—";

  proto._nightSummaryHtml = function(a, idx) {
    let html = oldNightSummary.call(this, a, idx);
    const score = numberText(a?.scoreAvg);
    const confidence = numberText(a?.confidenceAvg, " %");
    html = html.replace(
      /(<span>Vhodné hodiny [^<]*<\/span>)/,
      `<span>Skóre ${score}</span><span>Důvěra ${confidence}</span>$1`,
    );
    return html;
  };

  proto._detailHtml = function(a) {
    let html = oldDetail.call(this, a);
    if (!a?.hours?.length) return html;

    const score = numberText(a?.scoreAvg);
    const confidence = numberText(a?.confidenceAvg, " %");
    html = html.replace(
      /(<span>Kombinovaná oblačnost: <b>[^<]*<\/b><\/span>)/,
      `$1\n        <span>Průměrné skóre: <b>${score}</b></span>\n        <span>Průměrná důvěra: <b>${confidence}</b></span>`,
    );

    let hourIndex = 0;
    html = html.replace(/<div class="s">([^<]*)<\/div>/g, (match, scoreText) => {
      const hour = a.hours[hourIndex++];
      const conf = Number(hour?.confidence);
      const confText = Number.isFinite(conf) ? `${Math.round(conf)} %` : "—";
      const title = Number.isFinite(conf)
        ? `Důvěra modelů ${conf.toFixed(0)} %`
        : "Důvěra modelů není dostupná";
      return `${match}<div class="c" title="${this._escape(title)}" style="margin-top:1px;font-size:.60rem;font-weight:700;color:var(--secondary-text-color);white-space:nowrap">D ${this._escape(confText)}</div>`;
    });
    return html;
  };

  proto._confidenceV24 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v24",
    description: "Centrální rozhodnutí observatoře s MET, ALADIN, DWD ICON, skóre a důvěrou modelů.",
  });
}
