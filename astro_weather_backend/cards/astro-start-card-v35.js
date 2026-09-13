// astro-start-card v35 - keep decision and its reason on one compact row.
import "/local/astro-start-card-v34.js";

const AstroStartCardV35 = customElements.get("astro-start-card");

if (AstroStartCardV35 && !AstroStartCardV35.prototype._compactDecisionReasonV35) {
  const proto = AstroStartCardV35.prototype;
  const oldDetail = proto._detailHtml;

  proto._detailHtml = function(a) {
    let html = oldDetail.call(this, a);

    // The selected night is already obvious from the highlighted summary card.
    // Remove the duplicated date/time block from the expanded detail header.
    html = html.replace(
      /(<div class="detail-head">\s*)<div>\s*<div class="detail-title">[\s\S]*?<\/div>(?:\s*<div class="detail-sub">[\s\S]*?<\/div>)?\s*<\/div>/,
      "$1",
    );

    // Put the explanation and the final verdict next to each other instead of
    // spending a separate full-width row on each one.
    html = html.replace(
      /<div class="detail-head">\s*(<div class="decision [^"]+">\s*<div class="label">[\s\S]*?<\/div>\s*<\/div>)\s*<\/div>\s*(<div class="reason [^"]+">\s*<strong>[\s\S]*?<\/strong>\s*<div>[\s\S]*?<\/div>\s*<\/div>)/,
      '<div class="decision-reason-row-v35">$2$1</div>',
    );

    const compactStyles = `
      <style>
        .decision-reason-row-v35 {
          display:grid;
          grid-template-columns:minmax(0,1fr) auto;
          gap:16px;
          align-items:center;
          margin-top:0;
        }
        .decision-reason-row-v35 > .reason {
          margin-top:0 !important;
          min-width:0;
        }
        .decision-reason-row-v35 > .decision {
          min-width:max-content;
          text-align:right;
          align-self:center;
        }

        @media (max-width:760px) {
          .decision-reason-row-v35 {
            grid-template-columns:1fr;
            gap:8px;
          }
          .decision-reason-row-v35 > .decision {
            text-align:left;
          }
        }
      </style>`;

    return compactStyles + html;
  };

  proto._compactDecisionReasonV35 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v35",
    description: "Kompaktní detail bez duplicitního data; důvod rozhodnutí a verdikt jsou vedle sebe.",
  });
}
