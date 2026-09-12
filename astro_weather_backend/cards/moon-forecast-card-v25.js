// Moon Forecast Card v25 - confidence wording aligned with actual model agreement.
import "/local/moon-forecast-card-v24.js";

const MoonForecastCardV25 = customElements.get("moon-forecast-card");

if (MoonForecastCardV25 && !MoonForecastCardV25.prototype._modelAgreementV25) {
  const proto = MoonForecastCardV25.prototype;
  const oldRender = proto._render;

  proto._render = function() {
    if (this._agreementObserverV25) {
      this._agreementObserverV25.disconnect();
      this._agreementObserverV25 = null;
    }

    oldRender.call(this);

    const rename = () => {
      this.shadowRoot?.querySelectorAll(".details-label").forEach((label) => {
        const text = label.textContent?.trim();
        if (text === "Průměrná důvěra") {
          label.textContent = "Průměrná shoda modelů";
        }
      });
    };

    if (this.shadowRoot) {
      this._agreementObserverV25 = new MutationObserver(rename);
      this._agreementObserverV25.observe(this.shadowRoot, { childList: true, subtree: true });
      queueMicrotask(rename);
    }
  };

  proto._modelAgreementV25 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "moon-forecast-card");
if (registration) {
  Object.assign(registration, {
    name: "Moon Forecast Card v25",
    description: "Měsíc + centrální rozhodnutí se shodou meteorologických modelů, skóre, AOD 550 a seeingem.",
  });
}
