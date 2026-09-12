// astro-satellite-card v3 - large fresh IR image with CLM sampling overlay and 0-3 h nowcast.
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
      show_clm_map: true,
      show_image: true,
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
      sat?.attributes?.clm_map_time ?? "",
      cmp?.state ?? "missing",
      cmp?.last_updated ?? "",
    ].join("|");
    if (signature !== this._signature) {
      this._signature = signature;
      this._render();
    }
  }

  getCardSize() {
    return this._config?.show_image === false ? 4 : 9;
  }

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
    if (cloud <= 25) return "🌙";
    if (cloud <= 45) return "🌥️";
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

  _clmLabel(value) {
    if (value === 0 || value === "0") return "jasno";
    if (value === 1 || value === "1") return "mrak";
    return "bez dat";
  }

  _sampleClass(value) {
    if (value === 0 || value === "0") return "sample-clear";
    if (value === 1 || value === "1") return "sample-cloud";
    return "sample-nodata";
  }

  _visualUrl(attrs, satObj) {
    const base = String(attrs?.visual_url || "");
    if (!base) return "";
    // The WMS request itself is intentionally stable.  Force a fresh HTTP image
    // request whenever the HA satellite entity is republished so the browser
    // cannot keep showing an old EUMETView frame from cache.
    const token = satObj?.last_updated || attrs?.as_of || new Date().toISOString();
    const separator = base.includes("?") ? "&" : "?";
    return `${base}${separator}_astro_refresh=${encodeURIComponent(token)}`;
  }

  _samplePosition(id, mapRadiusKm, visualRadiusKm, size) {
    const center = size / 2;
    if (id === "C") return { x: center, y: center, center: true };
    const match = /^(inner|outer)_(\d{3})$/.exec(String(id));
    if (!match) return null;
    const distanceKm = match[1] === "inner" ? mapRadiusKm / 2 : mapRadiusKm;
    const pxPerKm = center / visualRadiusKm;
    const radiusPx = distanceKm * pxPerKm;
    const bearing = Number(match[2]);
    const angle = bearing * Math.PI / 180;
    return {
      x: center + Math.sin(angle) * radiusPx,
      y: center - Math.cos(angle) * radiusPx,
      center: false,
    };
  }

  _visualPanel(attrs, satObj) {
    if (this._config?.show_image === false) return "";
    const imageUrl = this._visualUrl(attrs, satObj);
    if (!imageUrl) return "";

    const size = this._num(attrs.visual_size_px) ?? 900;
    const center = size / 2;
    const visualRadius = this._num(attrs.visual_radius_km) ?? 150;
    const mapRadius = this._num(attrs.clm_map_radius_km ?? attrs.radius_km) ?? 30;
    const pxPerKm = center / visualRadius;
    const innerPx = mapRadius * 0.5 * pxPerKm;
    const outerPx = mapRadius * pxPerKm;
    const points = attrs?.clm_points;
    const showOverlay = this._config?.show_clm_map !== false && points && typeof points === "object" && !Array.isArray(points);

    let clear = 0;
    let cloud = 0;
    let noData = 0;
    const samples = [];
    if (showOverlay) {
      for (const [id, value] of Object.entries(points)) {
        const pos = this._samplePosition(id, mapRadius, visualRadius, size);
        if (!pos) continue;
        if (value === 0 || value === "0") clear += 1;
        else if (value === 1 || value === "1") cloud += 1;
        else noData += 1;
        samples.push(`
          <circle class="sample ${this._sampleClass(value)}" cx="${pos.x.toFixed(1)}" cy="${pos.y.toFixed(1)}" r="${pos.center ? 10 : 8}">
            <title>${this._escape(`${id}: ${this._clmLabel(value)}`)}</title>
          </circle>`);
      }
    }

    const overlay = showOverlay ? `
      <svg class="visual-overlay" viewBox="0 0 ${size} ${size}" role="img" aria-label="IR10.5 se skutečnými CLM vzorky kolem observatoře">
        <circle class="range-ring inner" cx="${center}" cy="${center}" r="${innerPx.toFixed(1)}"></circle>
        <circle class="range-ring outer" cx="${center}" cy="${center}" r="${outerPx.toFixed(1)}"></circle>
        <text class="range-label" x="${(center + innerPx + 8).toFixed(1)}" y="${(center - 8).toFixed(1)}">${(mapRadius / 2).toFixed(0)} km</text>
        <text class="range-label" x="${(center + outerPx + 8).toFixed(1)}" y="${(center + 24).toFixed(1)}">${mapRadius.toFixed(0)} km</text>
        ${samples.join("")}
        <circle class="observatory-ring" cx="${center}" cy="${center}" r="17"></circle>
        <line class="observatory-cross" x1="${center - 24}" y1="${center}" x2="${center + 24}" y2="${center}"></line>
        <line class="observatory-cross" x1="${center}" y1="${center - 24}" x2="${center}" y2="${center + 24}"></line>
        <text class="observatory-label" x="${center + 24}" y="${center - 23}">observatoř</text>
        <g class="overlay-legend" transform="translate(20 ${size - 104})">
          <rect class="legend-bg" width="310" height="84" rx="10"></rect>
          <circle class="legend-clear" cx="22" cy="23" r="8"></circle>
          <text x="40" y="30">jasno ${clear}</text>
          <circle class="legend-cloud" cx="150" cy="23" r="8"></circle>
          <text x="168" y="30">mrak ${cloud}</text>
          ${noData ? `<circle class="legend-nodata" cx="258" cy="23" r="8"></circle><text x="276" y="30">?</text>` : ""}
          <text class="legend-small" x="20" y="61">CLM vzorky · kruhy ${(mapRadius / 2).toFixed(0)} / ${mapRadius.toFixed(0)} km</text>
        </g>
      </svg>` : "";

    const cycleTime = this._time(satObj?.last_updated);
    return `
      <div class="visual-section">
        <div class="visual-head"><b>MTG/FCI IR10.5 + CLM vzorky</b><span>výřez ±${visualRadius.toFixed(0)} km · načteno ${cycleTime}</span></div>
        <div class="visual-panel">
          <img class="visual-image" src="${this._escape(imageUrl)}" alt="Aktuální EUMETSAT MTG IR10.5">
          ${overlay}
        </div>
        <div class="visual-note">Modrá = jasno · šedá = mrak · žlutý terč = observatoř. Body jsou přesně vzorky použité pro výpočet, nejde o interpolaci.</div>
      </div>`;
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
        .visual-section { margin-top:12px;padding-top:10px;border-top:1px solid var(--divider-color); }
        .visual-head { display:flex;justify-content:space-between;gap:8px;align-items:baseline;margin-bottom:6px; }
        .visual-head b { font-size:.82rem; }
        .visual-head span { color:var(--secondary-text-color);font-size:.67rem;text-align:right; }
        .visual-panel { position:relative;width:100%;aspect-ratio:1/1;border-radius:10px;overflow:hidden;background:#111; }
        .visual-image { position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block; }
        .visual-overlay { position:absolute;inset:0;width:100%;height:100%;pointer-events:none; }
        .range-ring { fill:none;stroke:rgba(255,255,255,.82);stroke-width:3;filter:drop-shadow(0 1px 2px #000); }
        .range-ring.inner { stroke-dasharray:10 8; }
        .range-label,.observatory-label,.overlay-legend text { fill:#fff;font-size:22px;font-weight:700;paint-order:stroke;stroke:#111;stroke-width:5px;stroke-linejoin:round; }
        .sample { stroke:#fff;stroke-width:3;filter:drop-shadow(0 1px 2px #000); }
        .sample-clear,.legend-clear { fill:#2196f3; }
        .sample-cloud,.legend-cloud { fill:#9e9e9e; }
        .sample-nodata,.legend-nodata { fill:#616161; }
        .observatory-ring { fill:none;stroke:#ffca28;stroke-width:5;filter:drop-shadow(0 1px 3px #000); }
        .observatory-cross { stroke:#ffca28;stroke-width:3;filter:drop-shadow(0 1px 3px #000); }
        .legend-bg { fill:rgba(0,0,0,.55);stroke:rgba(255,255,255,.25);stroke-width:1; }
        .overlay-legend text { font-size:20px;stroke-width:4px; }
        .overlay-legend .legend-small { font-size:17px;font-weight:600; }
        .visual-note { margin-top:6px;color:var(--secondary-text-color);font-size:.68rem;line-height:1.35; }
        .unavailable { padding:9px 0 3px;color:var(--secondary-text-color);font-size:.82rem;line-height:1.45; }
        .unavailable .status { color:var(--primary-text-color);font-weight:800;margin-bottom:4px; }
        a { color:var(--primary-color);text-decoration:none; }
        @media (max-width:430px) {
          .visual-head { display:block; }
          .visual-head span { display:block;margin-top:2px;text-align:left; }
        }
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

          ${this._visualPanel(sat, satObj)}

          <div class="compare"><span>Modely vs realita:</span> ${compareHtml}</div>
          <div class="meta">
            FCI Cloud Mask · 2 km · 10 min · výpočet z okolí ${Number(sat.radius_km ?? 30).toFixed(0)} km
            ${confidence !== null ? ` · jistota trendu ${confidence.toFixed(0)} %` : ""}
            · +1 až +3 h je nowcast, nikoli nový satelitní snímek
          </div>
        </div>
      </ha-card>`;
  }
}

if (!customElements.get("astro-satellite-card")) {
  customElements.define("astro-satellite-card", AstroSatelliteCard);
}

window.customCards = window.customCards || [];
const existing = window.customCards.find((card) => card.type === "astro-satellite-card");
if (existing) {
  Object.assign(existing, {
    name: "Astro Satellite Nowcast Card v3",
    description: "Aktuální MTG/FCI IR snímek s přesnými CLM vzorky, kruhy 15/30 km, nowcastem a porovnáním modelů.",
  });
} else {
  window.customCards.push({
    type: "astro-satellite-card",
    name: "Astro Satellite Nowcast Card v3",
    description: "Aktuální MTG/FCI IR snímek s přesnými CLM vzorky, kruhy 15/30 km, nowcastem a porovnáním modelů.",
    preview: true,
  });
}
