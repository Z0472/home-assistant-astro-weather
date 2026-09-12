// astro-satellite-card v1 - EUMETSAT MTG/FCI current cloud reality and 0-3 h nowcast.
class AstroSatelliteCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._signature = null;
  }

  setConfig(config) {
    this._config = {
      satellite_entity: "sensor.astro_satelit_oblacnost",
      comparison_entity: "sensor.astro_model_satelit_shoda",
      title: "Satelit – aktuální oblačnost",
      show_image: false,
      ...config,
    };
    this._signature = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    const sat = hass.states[this._config.satellite_entity];
    const cmp = hass.states[this._config.comparison_entity];
    const signature = [
      sat?.state ?? "missing",
      sat?.last_updated ?? "",
      sat?.attributes?.as_of ?? "",
      cmp?.state ?? "missing",
      cmp?.last_updated ?? "",
    ].join("|");
    if (signature !== this._signature) {
      this._signature = signature;
      this._render();
    }
  }

  getCardSize() { return this._config?.show_image ? 6 : 4; }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  _timezone() {
    return this._hass?.config?.time_zone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  }

  _time(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "—";
    return new Intl.DateTimeFormat("cs-CZ", {
      timeZone: this._timezone(), hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(d);
  }

  _num(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  _cloudIcon(value) {
    const cloud = this._num(value);
    if (cloud === null) return "❔";
    if (cloud <= 10) return "🌙";
    if (cloud <= 25) return "🌙";
    if (cloud <= 45) return "🌥️";
    if (cloud <= 70) return "☁️";
    return "☁️";
  }

  _cloudLabel(value) {
    const cloud = this._num(value);
    if (cloud === null) return "bez dat";
    if (cloud <= 10) return "jasno";
    if (cloud <= 25) return "málo oblačnosti";
    if (cloud <= 45) return "polojasno";
    if (cloud <= 70) return "oblačno";
    return "zataženo";
  }

  _agreementTone(value) {
    const n = this._num(value);
    if (n === null) return "var(--secondary-text-color)";
    if (n >= 85) return "var(--success-color,#4caf50)";
    if (n >= 70) return "var(--info-color,#2196f3)";
    if (n >= 50) return "var(--warning-color,#ff9800)";
    return "var(--error-color,#f44336)";
  }

  _unavailable(attrs) {
    const needsKey = attrs?.credential_status === "required";
    const reason = attrs?.reason || "Kvantitativní satelitní data zatím nejsou dostupná.";
    const visual = attrs?.visual_url;
    return `
      <ha-card>
        <div class="wrap">
          <div class="head">
            <div><span class="sat">🛰</span><b>${this._escape(this._config.title)}</b></div>
            <span class="age">MTG / FCI</span>
          </div>
          <div class="unavailable">
            <div class="status">${needsKey ? "CLM čeká na přístup" : "Satelitní data nedostupná"}</div>
            <div>${this._escape(reason)}</div>
            ${visual ? `<a href="${this._escape(visual)}" target="_blank" rel="noopener noreferrer">Otevřít aktuální EUMETView IR10.5</a>` : ""}
          </div>
        </div>
      </ha-card>`;
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const satObj = this._hass?.states?.[this._config.satellite_entity];
    const cmpObj = this._hass?.states?.[this._config.comparison_entity];
    const sat = satObj?.attributes || {};
    const cmp = cmpObj?.attributes || {};

    const styles = `
      <style>
        :host { display:block; }
        ha-card { overflow:hidden; }
        .wrap { padding:14px 16px 15px; }
        .head { display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px; }
        .head b { font-size:1.02rem; }
        .sat { margin-right:6px; }
        .age { color:var(--secondary-text-color);font-size:.76rem;white-space:nowrap; }
        .current { display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:center;padding:10px 0 12px; }
        .current .icon { font-size:2.2rem;line-height:1; }
        .cloud { font-size:1.3rem;font-weight:800; }
        .summary { font-size:.82rem;color:var(--secondary-text-color);margin-top:2px;line-height:1.35; }
        .timeline { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin-top:3px; }
        .hour { text-align:center;padding:8px 3px;border:1px solid var(--divider-color);border-radius:9px;background:var(--secondary-background-color); }
        .hour .t { font-size:.73rem;color:var(--secondary-text-color);font-weight:700; }
        .hour .i { font-size:1.35rem;line-height:1.5; }
        .hour .p { font-size:.9rem;font-weight:800; }
        .hour .l { font-size:.65rem;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
        .compare { margin-top:10px;padding-top:9px;border-top:1px solid var(--divider-color);font-size:.78rem;line-height:1.4; }
        .compare b { font-weight:800; }
        .meta { margin-top:8px;color:var(--secondary-text-color);font-size:.70rem;line-height:1.35; }
        .unavailable { padding:9px 0 3px;color:var(--secondary-text-color);font-size:.82rem;line-height:1.45; }
        .unavailable .status { color:var(--primary-text-color);font-weight:800;margin-bottom:4px; }
        a { color:var(--primary-color);text-decoration:none; }
        .image { margin-top:10px;width:100%;border-radius:8px;display:block; }
      </style>`;

    if (!satObj || satObj.state === "unavailable" || !sat.available) {
      this.shadowRoot.innerHTML = styles + this._unavailable(sat);
      return;
    }

    const cloud = this._num(sat.cloud_pct ?? satObj.state);
    const age = this._num(sat.age_minutes);
    const nowcast = Array.isArray(sat.nowcast) ? sat.nowcast.slice(0, 4) : [];
    while (nowcast.length < 4) {
      nowcast.push({ offset_hours: nowcast.length, label: nowcast.length ? `+${nowcast.length} h` : "TEĎ", cloud_pct: null });
    }
    const edge = sat.edge || {};
    let edgeText = "";
    if (edge?.stable && edge?.direction) {
      edgeText = ` · hrana ${edge.direction}`;
      if (edge.approaching && Number.isFinite(Number(edge.eta_minutes))) {
        edgeText += ` · ETA ~${Number(edge.eta_minutes).toFixed(0)} min`;
      }
    }
    const confidence = this._num(sat.nowcast_confidence_pct);
    const trend = sat.short_text || `${sat.arrow || "→"} ${this._cloudLabel(cloud)}`;
    const edgeSuffix = sat.short_text ? "" : edgeText;

    let compareHtml = `<span style="color:var(--secondary-text-color)">Modelový konsensus zatím nelze porovnat.</span>`;
    if (cmpObj && cmpObj.state !== "unavailable" && cmp.available) {
      const agreement = this._num(cmp.agreement_pct ?? cmpObj.state);
      const model = this._num(cmp.model_cloud_pct);
      const real = this._num(cmp.satellite_cloud_pct);
      compareHtml = `<b style="color:${this._agreementTone(agreement)}">${agreement?.toFixed(0) ?? "—"} % shoda</b>` +
        ` · model ${model?.toFixed(0) ?? "—"} % / satelit ${real?.toFixed(0) ?? "—"} %`;
    }

    const image = this._config.show_image && sat.visual_url
      ? `<img class="image" src="${this._escape(sat.visual_url)}" alt="Aktuální EUMETSAT MTG IR10.5">`
      : "";

    this.shadowRoot.innerHTML = styles + `
      <ha-card>
        <div class="wrap">
          <div class="head">
            <div><span class="sat">🛰</span><b>${this._escape(this._config.title)}</b></div>
            <span class="age">${this._time(sat.as_of)}${age !== null ? ` · ${age.toFixed(0)} min` : ""}</span>
          </div>

          <div class="current">
            <div class="icon">${this._cloudIcon(cloud)}</div>
            <div>
              <div class="cloud">${cloud !== null ? cloud.toFixed(0) + " %" : "—"} · ${this._escape(this._cloudLabel(cloud))}</div>
              <div class="summary">${this._escape(trend)}${this._escape(edgeSuffix)}</div>
            </div>
          </div>

          <div class="timeline">
            ${nowcast.map((row) => {
              const value = this._num(row.cloud_pct);
              return `<div class="hour" title="${row.estimated ? "Krátkodobý extrapolační nowcast z posledních satelitních snímků" : "Poslední skutečný satelitní snímek"}">
                <div class="t">${this._escape(row.label || "—")}</div>
                <div class="i">${this._cloudIcon(value)}</div>
                <div class="p">${value !== null ? value.toFixed(0) + " %" : "—"}</div>
                <div class="l">${this._escape(this._cloudLabel(value))}</div>
              </div>`;
            }).join("")}
          </div>

          <div class="compare"><span>Modely vs realita:</span> ${compareHtml}</div>
          <div class="meta">
            FCI Cloud Mask · 2 km · 10 min · okolí ${Number(sat.radius_km ?? 30).toFixed(0)} km
            ${confidence !== null ? ` · jistota trendu ${confidence.toFixed(0)} %` : ""}
            · +1 až +3 h je nowcast, nikoli nový satelitní snímek
          </div>
          ${image}
        </div>
      </ha-card>`;
  }
}

if (!customElements.get("astro-satellite-card")) {
  customElements.define("astro-satellite-card", AstroSatelliteCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "astro-satellite-card")) {
  window.customCards.push({
    type: "astro-satellite-card",
    name: "Astro Satellite Nowcast Card v1",
    description: "Aktuální EUMETSAT MTG/FCI oblačnost, krátký satelitní nowcast a shoda s MET + ALADIN + ICON.",
    preview: true,
  });
}
