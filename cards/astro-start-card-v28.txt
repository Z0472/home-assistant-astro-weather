// astro-start-card v28 - distinguish evening twilight from morning dawn.
import "/local/astro-start-card-v27.js";

const AstroStartCardV28 = customElements.get("astro-start-card");

if (AstroStartCardV28 && !AstroStartCardV28.prototype._dawnDuskV28) {
  const proto = AstroStartCardV28.prototype;
  const oldHourLimit = proto._hourLimit;

  proto._hourLimit = function(h) {
    if (h?.twilight) {
      const phase = h?.twilightPhase;
      if (phase === "morning") {
        return {
          label: "svítání",
          tone: "neutral",
          title: "Ranní svítání: Slunce je pod horizontem, ale tato hodina už není celá v astronomické tmě. Počasí je informativní; do rozhodnutí o focení se započítává jen astronomická noc.",
        };
      }
      if (phase === "evening") {
        return {
          label: "soumrak",
          tone: "neutral",
          title: "Večerní soumrak: Slunce je pod horizontem, ale tato hodina ještě není celá v astronomické tmě. Počasí je informativní; do rozhodnutí o focení se započítává jen astronomická noc.",
        };
      }
      return {
        label: "přechod",
        tone: "neutral",
        title: "Přechod mezi astronomickou tmou a občanským/nautickým soumrakem nebo svítáním. Do rozhodnutí o focení se započítává jen astronomická noc.",
      };
    }
    return oldHourLimit.call(this, h);
  };

  proto._dawnDuskV28 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v28",
    description: "Centrální rozhodnutí observatoře s aktuálním trendem, hodinovými šipkami a správným rozlišením soumraku a svítání.",
  });
}
