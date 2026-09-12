// astro-start-card v31 - compact night cards without duplicate astronomical-night rows.
import "/local/astro-start-card-v30.js";

const AstroStartCardV31 = customElements.get("astro-start-card");

if (AstroStartCardV31 && !AstroStartCardV31.prototype._compactNightRowsV31) {
  const proto = AstroStartCardV31.prototype;
  const oldNightSummary = proto._nightSummaryHtml;
  const oldDetail = proto._detailHtml;

  proto._nightSummaryHtml = function(a, idx) {
    const html = oldNightSummary.call(this, a, idx);
    return html.replace(/\s*<div class="night-astro">[\s\S]*?<\/div>/, "");
  };

  proto._detailHtml = function(a) {
    const html = oldDetail.call(this, a);
    return html.replace(/\s*<div class="detail-sub">Astronomická noc[\s\S]*?<\/div>/, "");
  };

  proto._compactNightRowsV31 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v31",
    description: "Kompaktní hlavní karta bez duplicitních řádků astronomické noci; živá shoda se satelitem zůstává jen u dneška.",
  });
}
