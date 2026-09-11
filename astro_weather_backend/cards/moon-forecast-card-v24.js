// Moon Forecast Card v24 - expanded-day detail shows ICON, score and confidence.
import "/local/moon-forecast-card-v23.js";

const MoonForecastCardV24 = customElements.get("moon-forecast-card");

if (MoonForecastCardV24 && !MoonForecastCardV24.prototype._confidenceV24) {
  const proto = MoonForecastCardV24.prototype;
  const oldRender = proto._render;

  const valueText = (value, suffix = "") => Number.isFinite(Number(value))
    ? `${Number(value).toFixed(0)}${suffix}`
    : "—";

  proto._render = function() {
    if (this._confidenceObserverV24) {
      this._confidenceObserverV24.disconnect();
      this._confidenceObserverV24 = null;
    }

    oldRender.call(this);

    const body = this.shadowRoot?.querySelector(".details-body");
    if (!body) return;

    const enhanceDetail = () => {
      const selected = this.shadowRoot?.querySelector(".day.selected");
      const idx = Number(selected?.dataset?.index);
      if (!Number.isInteger(idx)) return;

      const stateObj = this._hass?.states?.[this._config?.entity];
      const allDays = Array.isArray(stateObj?.attributes?.daily) ? stateObj.attributes.daily : [];
      const today = this._todayInHaTimezone();
      const maxDays = Math.max(1, Number(this._config?.days) || 45);
      const days = allDays
        .filter((d) => d && typeof d.date === "string" && d.date >= today)
        .slice(0, maxDays);
      const day = days[idx];
      const decision = day ? this._decisionForDate(day.date) : null;
      if (!decision) return;

      const sections = Array.from(body.querySelectorAll(".weather-section"));
      const section = sections.find((item) =>
        item.querySelector(".weather-title")?.textContent?.trim() === "Rozhodnutí observatoře"
      );
      const grid = section?.querySelector(".details-grid");
      if (!grid || grid.dataset.confidenceV24 === "1") return;

      grid.querySelectorAll(".detail-item").forEach((item) => {
        const label = item.querySelector(".details-label");
        if (label?.textContent?.trim() === "Kombinovaná oblačnost MET+ALADIN") {
          label.textContent = "Kombinovaná oblačnost modelů";
        }
      });

      const items = [
        ["ICON", valueText(decision.iconAvg, " %")],
        ["Průměrné skóre", valueText(decision.scoreAvg)],
        ["Průměrná důvěra", valueText(decision.confidenceAvg, " %")],
      ];
      for (const [label, value] of items) {
        const item = document.createElement("div");
        item.className = "detail-item";
        item.innerHTML = `<div class="details-label">${this._escape(label)}</div><div class="details-value">${this._escape(value)}</div>`;
        grid.appendChild(item);
      }
      grid.dataset.confidenceV24 = "1";
    };

    this._confidenceObserverV24 = new MutationObserver(enhanceDetail);
    this._confidenceObserverV24.observe(body, { childList: true, subtree: true });
    queueMicrotask(enhanceDetail);
  };

  proto._confidenceV24 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "moon-forecast-card");
if (registration) {
  Object.assign(registration, {
    name: "Moon Forecast Card v24",
    description: "Měsíc + centrální rozhodnutí s ICON, skóre, důvěrou, AOD 550 a seeingem.",
  });
}
