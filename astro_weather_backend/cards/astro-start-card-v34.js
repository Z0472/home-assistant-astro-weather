// astro-start-card v34 - compact wide-screen layout for spatial trend and Moon details.
import "/local/astro-start-card-v33.js";

const AstroStartCardV34 = customElements.get("astro-start-card");

if (AstroStartCardV34 && !AstroStartCardV34.prototype._compactDetailLayoutV34) {
  const proto = AstroStartCardV34.prototype;
  const oldDetail = proto._detailHtml;

  proto._detailHtml = function(a) {
    let html = oldDetail.call(this, a);

    // Current trend and the night forecast describe the same cloud development
    // at two time scopes, so keep them together on one row on wide screens.
    html = html.replace(
      /(<div class="current-spatial-panel"[\s\S]*?<\/div>)\s*(<div class="spatial-cloud-panel[^"]*"[\s\S]*?<\/div>)/,
      '<div class="spatial-compact-row-v34">$1$2</div>',
    );

    const compactStyles = `
      <style>
        .spatial-compact-row-v34 {
          display:grid;
          grid-template-columns:repeat(2,minmax(0,1fr));
          gap:10px;
          margin-top:10px;
          align-items:stretch;
        }
        .spatial-compact-row-v34 > .current-spatial-panel,
        .spatial-compact-row-v34 > .spatial-cloud-panel {
          margin-top:0 !important;
          min-width:0;
          box-sizing:border-box;
          display:flex;
          align-items:center;
        }

        /* Moon headline stays on the left; the two explanatory lines move
           beside it instead of occupying two extra rows below the icon. */
        .moon-panel {
          display:grid;
          grid-template-columns:minmax(240px,.75fr) minmax(0,1.8fr);
          column-gap:18px;
          align-items:center;
        }
        .moon-main { min-width:0; }
        .moon-meta {
          margin-top:0 !important;
          gap:4px !important;
          min-width:0;
        }

        @media (max-width:760px) {
          .spatial-compact-row-v34 {
            grid-template-columns:1fr;
          }
          .moon-panel {
            display:block;
          }
          .moon-meta {
            margin-top:9px !important;
          }
        }
      </style>`;

    return compactStyles + html;
  };

  proto._compactDetailLayoutV34 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-start-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Start Decision Card v34",
    description: "Kompaktnější detail: aktuální trend a předpověď noci jsou vedle sebe; informace o Měsíci jsou vedle hlavního stavu.",
  });
}
