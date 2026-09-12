// astro-start-card v25 - model agreement wording, sunset-to-sunrise strip and night-only icons.
import "/local/astro-start-card-v24.js";

const AstroStartCardV25 = customElements.get("astro-start-card");

if (AstroStartCardV25 && !AstroStartCardV25.prototype._nightDisplayV25) {
  const proto = AstroStartCardV25.prototype;
  const oldCloudBand = proto._cloudBand;
  const oldHourLimit = proto._hourLimit;
  const oldNightSummary = proto._nightSummaryHtml;
  const oldDetail = proto._detailHtml;

  proto._cloudBand = function(cloud) {
    const band = oldCloudBand.call(this, cloud);
    const nightIconByClass = {
      clear: "mdi:weather-night",
      "mostly-clear": "mdi:weather-night-partly-cloudy",
      "light-cloud": "mdi:weather-night-partly-cloudy",
      cloudy: "mdi:weather-cloudy",
      overcast: "mdi:cloud",
      unknown: "mdi:help-circle-outline",
    };
    return { ...band, icon: nightIconByClass[band.cls] || band.icon };
  };

  proto._hourLimit = function(h) {
    if (h?.twilight) {
      return {
        label: "soumrak",
        tone: "neutral",
        title: "Slunce je pod horizontem, ale tato hodina není celá v astronomické tmě. Počasí je informativní; do rozhodnutí o focení se započítává jen astronomická noc.",
      };
    }
    return oldHourLimit.call(this, h);
  };

  proto._nightSummaryHtml = function(a, idx) {
    const modelAgreement = Number(a?.modelAgreementAvg);
    const source = Number.isFinite(modelAgreement)
      ? { ...a, confidenceAvg: modelAgreement }
      : a;
    return oldNightSummary.call(this, source, idx)
      .replace("Důvěra ", "Shoda modelů ");
  };

  proto._detailHtml = function(a) {
    const modelAgreement = Number(a?.modelAgreementAvg);
    const displayHours = Array.isArray(a?.displayHours) && a.displayHours.length
      ? a.displayHours
      : a?.hours;
    const source = a
      ? {
          ...a,
          hours: displayHours,
          confidenceAvg: Number.isFinite(modelAgreement) ? modelAgreement : a.confidenceAvg,
        }
      : a;

    let html = oldDetail.call(this, source);
    html = html
      .replaceAll("Důvěra modelů", "Shoda modelů")
      .replaceAll("Průměrná důvěra", "Průměrná shoda modelů")
      .replaceAll(">D ", ">Sh ")
      .replaceAll("mdi:weather-partly-cloudy", "mdi:weather-night-partly-cloudy");

    if (Array.isArray(a?.displayHours) && a.displayHours.length) {
      const sunset = a?.sunset ? this._formatTime(a.sunset) : "—";
      const sunrise = a?.sunrise ? this._formatTime(a.sunrise) : "—";
      html = html.replace(
        '<div class="strip-title">Hodinový přehled ·',
        `<div class="strip-title">Hodinový přehled ${this._escape(sunset)}–${this._escape(sunrise)} (západ–východ Slunce) · rozhodnutí pouze v astronomické tmě ·`,
      );
    }
    return html;
  };

  proto._nightDisplayV25 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v25",
    description: "Centrální rozhodnutí observatoře s hodinovým přehledem od západu do východu Slunce, shodou modelů a nočními ikonami.",
  });
}
