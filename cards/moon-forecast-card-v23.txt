// Moon Forecast Card v23 - direct CAMS/Open-Meteo and 7Timer source links.
class MoonForecastCard extends HTMLElement {
  static getStubConfig() {
    return {
      entity: "sensor.mesic_foceni_predpoved",
      weather_entity: "sensor.astro_weather_detail",
      decision_entity: "sensor.astro_vhodnost_foceni",
      days: 45,
    };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._drag = null;
    this._touchTap = null;
    this._lastSignature = null;
    this._scrollLeft = 0;
    this._selectedDayIndex = null;
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Je nutné zadat entity.");
    }

    this._config = {
      days: 45,
      weather_entity: null,
      dewpoint_entity: null,
      decision_entity: "sensor.astro_vhodnost_foceni",

      // Výchozí prahy pro astrofotografii; lze přepsat v YAML karty.
      cloud_good: 20,
      cloud_bad: 60,
      wind_good: 12,
      wind_bad: 22,
      humidity_warn: 90,
      dew_margin_warn: 2.0,

      ...config,
    };

    this._lastSignature = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;

    const moon = hass.states[this._config.entity];
    const weather = this._config.weather_entity
      ? hass.states[this._config.weather_entity]
      : null;
    const decision = this._config.decision_entity
      ? hass.states[this._config.decision_entity]
      : null;
    const signature = [
      moon?.state ?? "moon-missing",
      moon?.attributes?.generated_at ?? moon?.last_updated ?? "",
      weather?.state ?? "weather-missing",
      weather?.last_updated ?? "",
      decision?.state ?? "decision-missing",
      decision?.attributes?.generated_at ?? decision?.last_updated ?? "",
      decision?.last_updated ?? "",
    ].join("|");

    if (signature !== this._lastSignature) {
      this._lastSignature = signature;
      this._render();
    }
  }

  getCardSize() {
    return 3;
  }

  _timezone() {
    return this._hass?.config?.time_zone ||
      Intl.DateTimeFormat().resolvedOptions().timeZone;
  }

  _todayInHaTimezone() {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: this._timezone(),
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());

    const get = (type) => parts.find((p) => p.type === type)?.value;
    return `${get("year")}-${get("month")}-${get("day")}`;
  }

  _phaseEmoji(phase) {
    switch (phase) {
      case "nov": return "🌑";
      case "dorůstající srpek": return "🌒";
      case "první čtvrť": return "🌓";
      case "dorůstající Měsíc": return "🌔";
      case "úplněk": return "🌕";
      case "couvající Měsíc": return "🌖";
      case "poslední čtvrť": return "🌗";
      case "couvající srpek": return "🌘";
      default: return "🌙";
    }
  }

  _formatDateTime(iso) {
    if (!iso) return "—";
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return String(iso);

    return new Intl.DateTimeFormat("cs-CZ", {
      timeZone: this._timezone(),
      day: "numeric",
      month: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(dt);
  }

  _formatTimeOnly(value) {
    if (!value) return "—";
    const dt = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(dt.getTime())) return String(value);

    return new Intl.DateTimeFormat("cs-CZ", {
      timeZone: this._timezone(),
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(dt);
  }

  _nightLabel(dateIso) {
    if (!dateIso) return "";
    const [y, m, d] = dateIso.split("-").map(Number);
    const start = new Date(Date.UTC(y, m - 1, d));
    const end = new Date(Date.UTC(y, m - 1, d + 1));
    return `${start.getUTCDate()}. ${start.getUTCMonth() + 1}. → ${end.getUTCDate()}. ${end.getUTCMonth() + 1}.`;
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _dewPointC(tempC, humidityPct) {
    const t = Number(tempC);
    const rh = Number(humidityPct);

    if (!Number.isFinite(t) || !Number.isFinite(rh) || rh <= 0 || rh > 100) {
      return null;
    }

    // Magnusova aproximace pro vodu.
    const a = 17.62;
    const b = 243.12;
    const gamma = Math.log(rh / 100) + (a * t) / (b + t);
    const dp = (b * gamma) / (a - gamma);
    return Number.isFinite(dp) ? dp : null;
  }

  _nightInterpretation(d) {
    const darkStart = d.astronomical_dark_start ? new Date(d.astronomical_dark_start) : null;
    const darkEnd = d.astronomical_dark_end ? new Date(d.astronomical_dark_end) : null;
    const rise = d.moonrise ? new Date(d.moonrise) : null;
    const set = d.moonset ? new Date(d.moonset) : null;

    const valid = (x) => x instanceof Date && !Number.isNaN(x.getTime());
    const clean = Number(d.clean_hours);
    const dark = Number(d.dark_hours);

    let photoSummary = "Podmínky Měsíce nelze vyhodnotit.";
    let summaryClass = "neutral";

    if (Number.isFinite(clean) && Number.isFinite(dark) && dark > 0) {
      if (clean >= dark - 0.05) {
        photoSummary = "Celá astronomická noc bez rušení Měsícem.";
        summaryClass = "good";
      } else if (clean <= 0.05) {
        photoSummary = "Měsíc ruší prakticky celou astronomickou noc.";
        summaryClass = "bad";
      } else {
        photoSummary = `Bez rušení Měsícem je ${clean.toFixed(2)} h z ${dark.toFixed(2)} h astronomické tmy.`;
        summaryClass = "partial";
      }
    }

    let horizonSummary = "";

    if (valid(darkStart) && valid(darkEnd) && valid(rise) && valid(set)) {
      const ds = darkStart.getTime();
      const de = darkEnd.getTime();
      const r = rise.getTime();
      const s = set.getTime();

      if (s < ds && r > de) {
        horizonSummary =
          `Měsíc zapadne ještě před astronomickou tmou (${this._formatDateTime(d.moonset)}) ` +
          `a vyjde až po jejím skončení (${this._formatDateTime(d.moonrise)}). ` +
          `Po celou astronomickou noc je pod horizontem.`;
      } else if (r < ds && s > de) {
        horizonSummary =
          `Měsíc vyjde už před astronomickou tmou (${this._formatDateTime(d.moonrise)}) ` +
          `a zapadne až po jejím skončení (${this._formatDateTime(d.moonset)}). ` +
          `Po celou astronomickou noc je nad horizontem.`;
      } else if (s >= ds && s <= de && r > de) {
        horizonSummary =
          `Měsíc zapadne během astronomické noci v ${this._formatTimeOnly(d.moonset)}. ` +
          `Od té chvíle je pod horizontem.`;
      } else if (r >= ds && r <= de && s < ds) {
        horizonSummary =
          `Měsíc vyjde během astronomické noci v ${this._formatTimeOnly(d.moonrise)}. ` +
          `Do té doby je pod horizontem.`;
      } else if (r >= ds && r <= de && s >= ds && s <= de) {
        if (r < s) {
          horizonSummary =
            `Měsíc vyjde v ${this._formatTimeOnly(d.moonrise)} a zapadne v ${this._formatTimeOnly(d.moonset)}.`;
        } else {
          horizonSummary =
            `Měsíc zapadne v ${this._formatTimeOnly(d.moonset)} a znovu vyjde v ${this._formatTimeOnly(d.moonrise)}.`;
        }
      } else {
        horizonSummary =
          `Západ: ${this._formatDateTime(d.moonset)}, východ: ${this._formatDateTime(d.moonrise)}.`;
      }
    }

    return { photoSummary, horizonSummary, summaryClass };
  }

  _weatherForecast() {
    if (!this._config.weather_entity) return [];
    const obj = this._hass?.states?.[this._config.weather_entity];
    return Array.isArray(obj?.attributes?.forecast) ? obj.attributes.forecast : [];
  }

  _moonHourly() {
    const obj = this._hass?.states?.[this._config.entity];
    return Array.isArray(obj?.attributes?.hourly) ? obj.attributes.hourly : [];
  }

  _decisionDaily() {
    if (!this._config.decision_entity) return [];
    const obj = this._hass?.states?.[this._config.decision_entity];
    return Array.isArray(obj?.attributes?.daily) ? obj.attributes.daily : [];
  }

  _decisionForDate(date) {
    return this._decisionDaily().find((a) => a?.night?.date === date) || null;
  }

  _decisionIcon(decision) {
    return ({ good: "🟢", uncertain: "🟠", bad: "🔴", unavailable: "⚪" })[decision] || "⚪";
  }

  _aod(value) {
    return Number.isFinite(value) && value >= 0
      ? value.toFixed(value > 0 && value < 0.01 ? 3 : 2).replace(".", ",") : "—";
  }

  _dust(value) {
    return Number.isFinite(value) && value >= 0
      ? `${value.toFixed(value < 10 ? 1 : 0).replace(".", ",")} µg/m³` : "—";
  }

  _dustSummary(source, prefix = "Prach") {
    if (Number.isFinite(source?.dustUgm3Avg)) return `${prefix} ${this._dust(source.dustUgm3Avg)}`;
    if (Number.isFinite(source?.dustAodAvg)) return `${prefix} AOD ${this._aod(source.dustAodAvg)}`;
    return `${prefix} —`;
  }

  _skySourceLinks() {
    const links = [
      { url: "https://open-meteo.com/en/docs/air-quality-api", label: "CAMS/Open-Meteo" },
      { url: "https://www.7timer.info/doc.php?lang=en", label: "7Timer" },
    ];
    return links.map((item) =>
      `<a href="${this._escape(item.url)}" target="_blank" rel="noopener noreferrer">${this._escape(item.label)}</a>`
    ).join(" · ");
  }

  _aerosolLabel(status) {
    return ({ excellent: "výborná", good: "dobrá", reduced: "zhoršená",
      poor: "silnější zákal", bad: "silný zákal", stale: "neobnovená data",
      disabled: "vypnuto" })[status] || "bez dat";
  }

  _aerosolState(status, mode) {
    if (mode === "fallback") return { tone: "warning", label: "Bez dat", text: "aerosoly se nezapočítaly" };
    if (mode === "unavailable") return { tone: "neutral", label: "Bez údajů", text: "backend neposlal údaje o aerosolech" };
    if (mode === "disabled") return { tone: "neutral", label: "Vypnuto", text: "hodnocení aerosolů je vypnuté" };
    return ({
      excellent: { tone: "good", label: "OK", text: "výborná průzračnost" },
      good: { tone: "good", label: "OK", text: "dobrá průzračnost" },
      reduced: { tone: "warning", label: "Zhoršené", text: "zhoršená průzračnost" },
      poor: { tone: "warning", label: "Varování", text: "silnější zákal" },
      bad: { tone: "bad", label: "Špatné", text: "silný zákal" },
      stale: { tone: "warning", label: "Neobnoveno", text: "neobnovená data" },
      unknown: { tone: "warning", label: "Bez dat", text: "aerosoly se nezapočítaly" },
    })[status] || { tone: "neutral", label: "Bez dat", text: "bez dat o aerosolech" };
  }

  _aerosolImpact(a, settings) {
    const value = Number.isFinite(a?.aodMax) ? a.aodMax : a?.aodAvg;
    if (!Number.isFinite(value) || value < 0) {
      return { tone: "neutral", text: "Vliv: bez dat", title: "Bez platné hodnoty AOD se průzračnost do rozhodnutí nezapočítá." };
    }
    const warn = Number.isFinite(settings.aod_warn) ? settings.aod_warn : 0.30;
    const bad = Number.isFinite(settings.aod_bad) ? settings.aod_bad : 0.40;
    let penalty = 0;
    if (value > 0.10 && warn > 0.10 && bad > warn) {
      penalty = value < warn
        ? 25 * (value - 0.10) / (warn - 0.10)
        : Math.min(70, 25 + 25 * (value - warn) / (bad - warn));
    }
    const title = `Backend počítá AOD po hodinách. Do 0,10 bez penalizace. Mezi 0,10 a ${this._aod(warn)} ubírá až 25 bodů ze skóre hodiny, mezi ${this._aod(warn)} a ${this._aod(bad)} přibližně 25 až 50 bodů. Od ${this._aod(bad)} hodinu označí jako špatnou. Prach z Open-Meteo je jen informativní koncentrace u země, ne druhá penalizace.`;
    if (value >= bad) return { tone: "bad", text: "Vliv: stop hodiny", title };
    if (penalty <= 0.5) return { tone: "good", text: "Vliv: 0 b/h", title };
    return { tone: penalty >= 25 ? "warning" : "neutral", text: `Vliv: -${Math.round(penalty)} b/h`, title };
  }

  _seeing(value) {
    if (!Number.isFinite(value) || value <= 0) return "—";
    const text = value < 2 ? value.toFixed(2) : value.toFixed(1);
    return `${text.replace(/\.?0+$/, "").replace(".", ",")}"`;
  }

  _seeingState(status, mode) {
    if (mode === "fallback") return { tone: "warning", label: "Bez seeingu", text: "seeing se nezapočítal" };
    if (mode === "unavailable") return { tone: "neutral", label: "Bez údajů", text: "backend neposlal údaje o seeingu" };
    if (mode === "disabled") return { tone: "neutral", label: "Vypnuto", text: "hodnocení seeingu je vypnuté" };
    return ({
      excellent: { tone: "good", label: "Seeing OK", text: "výborný seeing" },
      good: { tone: "good", label: "Seeing OK", text: "dobrý seeing" },
      poor: { tone: "warning", label: "Seeing horší", text: "horší seeing" },
      bad: { tone: "bad", label: "Seeing špatný", text: "špatný seeing" },
      stale: { tone: "warning", label: "Seeing neobnoven", text: "neobnovený seeing" },
      unknown: { tone: "warning", label: "Bez seeingu", text: "seeing se nezapočítal" },
    })[status] || { tone: "neutral", label: "Bez seeingu", text: "bez dat o seeingu" };
  }

  _seeingImpact(a, settings) {
    const value = Number.isFinite(a?.seeingMax) ? a.seeingMax : a?.seeingAvg;
    if (!Number.isFinite(value) || value <= 0) {
      return { tone: "neutral", text: "Seeing: bez dat", title: "Bez platné hodnoty seeingu se seeing do rozhodnutí nezapočítá." };
    }
    const warn = Number.isFinite(settings.seeing_warn_arcsec) ? settings.seeing_warn_arcsec : 1.8;
    const bad = Number.isFinite(settings.seeing_bad_arcsec) ? settings.seeing_bad_arcsec : 2.5;
    let penalty = 0;
    if (value > warn && bad > warn) penalty = Math.min(45, 15 + 30 * (value - warn) / (bad - warn));
    const title = `Seeing je měkký faktor po hodinách. Pod ${this._seeing(warn)} je bez penalizace. Od ${this._seeing(warn)} ubírá body a znejistí hodinu, od ${this._seeing(bad)} může hodinu vyřadit ze souvislého dobrého bloku.`;
    if (value >= bad) return { tone: "bad", text: "Seeing: stop hodiny", title };
    if (penalty <= 0.5) return { tone: "good", text: "Seeing: 0 b/h", title };
    return { tone: "warning", text: `Seeing: -${Math.round(penalty)} b/h`, title };
  }

  _aerosolInfo(a) {
    const attrs = this._hass?.states?.[this._config.decision_entity]?.attributes || {};
    const settings = attrs.settings || {};
    if (settings.use_aerosols === false || a?.aerosolMode === "disabled") {
      return { mode: "disabled", compact: "AOD vypnuto", tone: "neutral",
        message: "Hodnocení aerosolů je vypnuté.", settings };
    }
    if (!a) {
      return { mode: "outlook", compact: "", tone: "neutral",
        message: "Pro tuto noc zatím není předpověď aerosolů k dispozici.", settings };
    }
    if (a.aerosolMode == null && a.aerosolCoverage == null) {
      const version = typeof attrs.backend_version === "string" ? ` ${attrs.backend_version}` : "";
      return { mode: "unavailable", compact: "AOD bez údajů", tone: "neutral",
        message: `V datech z backendu${version} chybějí údaje o aerosolech.`, settings };
    }
    const coverage = Number.isFinite(a.aerosolCoverage)
      ? Math.max(0, Math.min(1, a.aerosolCoverage)) : 0;
    const hasData = a.aerosolMode !== "fallback" && coverage > 0 &&
      Number.isFinite(a.aodAvg) && a.aodAvg >= 0;
    const mode = !hasData ? "fallback"
      : a.aerosolMode === "partial" || coverage < 1 ? "partial" : "full";
    const coverageText = (coverage * 100).toFixed(1).replace(/\.0$/, "").replace(".", ",");
    const warning = mode === "fallback"
      ? "Aerosoly nedostupné nebo neobnovené; rozhodnutí bez nich jako ve v7."
      : mode === "partial"
        ? `Data pro ${coverageText} % hodnocené noci; zbytek bez aerosolů jako ve v7.` : "";
    const state = this._aerosolState(a.aerosolStatus, mode);
    const tone = mode !== "full" && state.tone === "good" ? "warning" : state.tone;
    const compact = hasData ? `${state.label} · AOD ${this._aod(a.aodAvg)}${warning ? "*" : ""}` : "AOD bez dat";
    const message = hasData
      ? `${state.text}; AOD 550 za noc ${this._aod(a.aodAvg)} · max. ${this._aod(a.aodMax)} · ${this._dustSummary(a)}` +
        (warning ? ` · ${warning}` : " · všechna hodnocená období pokryta")
      : warning;
    return { mode, compact, tone, message, warning, coverage, hasData, settings, state };
  }

  _seeingInfo(a) {
    const attrs = this._hass?.states?.[this._config.decision_entity]?.attributes || {};
    const settings = attrs.settings || {};
    if (settings.use_seeing === false || a?.seeingMode === "disabled") {
      return { mode: "disabled", compact: "seeing vypnuto", tone: "neutral",
        message: "Hodnocení seeingu je vypnuté.", settings };
    }
    if (!a) {
      return { mode: "outlook", compact: "", tone: "neutral",
        message: "Pro tuto noc zatím není předpověď seeingu k dispozici.", settings };
    }
    if (a.seeingMode == null && a.seeingCoverage == null) {
      const version = typeof attrs.backend_version === "string" ? ` ${attrs.backend_version}` : "";
      return { mode: "unavailable", compact: "seeing bez údajů", tone: "neutral",
        message: `V datech z backendu${version} chybějí údaje o seeingu.`, settings };
    }
    const coverage = Number.isFinite(a.seeingCoverage)
      ? Math.max(0, Math.min(1, a.seeingCoverage)) : 0;
    const hasData = a.seeingMode !== "fallback" && coverage > 0 &&
      Number.isFinite(a.seeingAvg) && a.seeingAvg > 0;
    const mode = !hasData ? "fallback"
      : a.seeingMode === "partial" || coverage < 1 ? "partial" : "full";
    const coverageText = (coverage * 100).toFixed(1).replace(/\.0$/, "").replace(".", ",");
    const warning = mode === "fallback"
      ? "Seeing nedostupný nebo neobnovený; rozhodnutí bez něj."
      : mode === "partial"
        ? `Data pro ${coverageText} % hodnocené noci; zbytek bez seeingu.` : "";
    const state = this._seeingState(a.seeingStatus, mode);
    const tone = mode !== "full" && state.tone === "good" ? "warning" : state.tone;
    const compact = hasData ? `${state.label} ${this._seeing(a.seeingAvg)}${warning ? "*" : ""}` : "seeing bez dat";
    const message = hasData
      ? `${state.text}; seeing za noc ${this._seeing(a.seeingAvg)} · max ${this._seeing(a.seeingMax)}` +
        (warning ? ` · ${warning}` : " · všechna hodnocená období pokryta")
      : warning;
    return { mode, compact, tone, message, warning, coverage, hasData, settings, state };
  }

  _aerosolPanel(a, block) {
    const info = this._aerosolInfo(a);
    const seeing = this._seeingInfo(a);
    const settings = info.settings;
    const help = "Kvalita oblohy z CAMS/Open-Meteo a 7Timer: AOD 550 popisuje zákal aerosoly, seeing je odhad rozmazání v arcsec. Nižší hodnoty jsou lepší.";
    const links = this._skySourceLinks();
    const impact = info.hasData ? this._aerosolImpact(a, settings) : null;
    const seeingImpact = seeing.hasData ? this._seeingImpact(a, settings) : null;
    const panelTone = [info.tone, seeing.tone].includes("bad") ? "bad"
      : [info.tone, seeing.tone].includes("warning") ? "warning" : info.tone || seeing.tone;
    const body = [
      info.hasData
      ? `<span class="aerosol-status ${info.tone}" title="${this._escape(info.message)}"><span class="aerosol-dot"></span>${this._escape(info.state.label)}</span>
         <span>AOD <b>${this._aod(a.aodAvg)}</b> · max <b>${this._aod(a.aodMax)}</b></span>
         <span title="Prach z Open-Meteo je povrchová koncentrace, AOD rozhoduje samostatně.">${this._escape(this._dustSummary(a))}</span>
         <span class="aerosol-impact ${impact.tone}" title="${this._escape(impact.title)}">${this._escape(impact.text)}</span>`
      : `<span class="aerosol-status ${info.tone}"><span class="aerosol-dot"></span>${this._escape(info.state?.label || "Bez dat")}</span>
         <span class="${info.mode === "fallback" ? "aerosol-warning" : "aerosol-note"}">${this._escape(info.message)}</span>`,
      seeing.hasData
      ? `<span class="aerosol-status ${seeing.tone}" title="${this._escape(seeing.message)}"><span class="aerosol-dot"></span>${this._escape(seeing.state.label)}</span>
         <span>Seeing <b>${this._seeing(a.seeingAvg)}</b> · max <b>${this._seeing(a.seeingMax)}</b></span>
         <span class="aerosol-impact ${seeingImpact.tone}" title="${this._escape(seeingImpact.title)}">${this._escape(seeingImpact.text)}</span>`
      : `<span class="aerosol-status ${seeing.tone}"><span class="aerosol-dot"></span>${this._escape(seeing.state?.label || "Bez seeingu")}</span>
         <span class="${seeing.mode === "fallback" ? "aerosol-warning" : "aerosol-note"}">${this._escape(seeing.message)}</span>`,
      info.warning ? `<span class="aerosol-warning">${this._escape(info.warning)}</span>` : "",
      seeing.warning ? `<span class="aerosol-warning">${this._escape(seeing.warning)}</span>` : "",
    ].filter(Boolean).join("");
    return `<div class="aerosol-panel ${panelTone}">
      <div class="aerosol-head"><span class="aerosol-title" title="${this._escape(help)}">Kvalita oblohy</span>
        ${links ? `<span class="aerosol-links">${links}</span>` : ""}</div>
      <div class="aerosol-values">${body}</div>
    </div>`;
  }

  _nearestMoonHour(ms, moonHours) {
    let best = null;
    let bestDiff = Infinity;

    for (const h of moonHours) {
      const t = Date.parse(h?.time);
      if (!Number.isFinite(t)) continue;
      const diff = Math.abs(t - ms);

      if (diff < bestDiff) {
        bestDiff = diff;
        best = h;
      }
    }

    return bestDiff <= 45 * 60 * 1000 ? best : null;
  }

  _classifyWeatherHour(row, moonHour, d) {
    const cloud = Number(row?.cloud_coverage);
    const wind = Number(row?.wind_speed);
    const precipitation = Number(row?.precipitation);
    const humidity = Number(row?.humidity);
    const temp = Number(row?.temperature);

    const dewPoint = this._dewPointC(temp, humidity);
    const dewMargin = Number.isFinite(dewPoint) && Number.isFinite(temp)
      ? temp - dewPoint
      : null;

    let moonInterferes = null;
    if (moonHour && typeof moonHour.interferes === "boolean") {
      moonInterferes = moonHour.interferes;
    } else {
      const interference = Number(d?.interference_hours);
      const dark = Number(d?.dark_hours);

      if (Number.isFinite(interference) && interference <= 0.05) {
        moonInterferes = false;
      } else if (Number.isFinite(interference) && Number.isFinite(dark) && dark > 0 &&
                 interference >= dark - 0.05) {
        moonInterferes = true;
      }
    }

    const hardReasons = [];
    const warnReasons = [];

    if (moonInterferes === true) hardReasons.push("Měsíc");
    if (Number.isFinite(precipitation) && precipitation > 0) hardReasons.push("srážky");
    if (Number.isFinite(cloud) && cloud >= this._config.cloud_bad) hardReasons.push("oblačnost");
    if (Number.isFinite(wind) && wind >= this._config.wind_bad) hardReasons.push("vítr");

    if (!hardReasons.length) {
      if (Number.isFinite(cloud) && cloud > this._config.cloud_good) warnReasons.push("oblačnost");
      if (Number.isFinite(wind) && wind > this._config.wind_good) warnReasons.push("vítr");
      if (
        (Number.isFinite(humidity) && humidity >= this._config.humidity_warn) ||
        (Number.isFinite(dewMargin) && dewMargin <= this._config.dew_margin_warn)
      ) {
        warnReasons.push("riziko rosy / nízká rezerva k rosnému bodu");
      }
    }

    const status = hardReasons.length
      ? "bad"
      : warnReasons.length
        ? "partial"
        : "good";

    return {
      status,
      reasons: hardReasons.length ? hardReasons : warnReasons,
      cloud,
      wind,
      precipitation,
      humidity,
      temp,
      dewPoint,
      dewMargin,
      moonInterferes,
    };
  }

  _analyzeNightWeather(d) {
    const weather = this._weatherForecast();
    if (!weather.length || !d?.astronomical_dark_start || !d?.astronomical_dark_end) {
      return null;
    }

    const ds = Date.parse(d.astronomical_dark_start);
    const de = Date.parse(d.astronomical_dark_end);
    if (!Number.isFinite(ds) || !Number.isFinite(de) || de <= ds) return null;

    const moonHours = this._moonHourly();
    const rows = [];

    let goodHours = 0;
    let partialHours = 0;
    let badHours = 0;
    let coveredHours = 0;

    let weightedCloud = 0;
    let weightedHumidity = 0;
    let maxWind = null;
    let rainTotal = 0;
    let minDewMargin = null;

    const reasonWeights = new Map();

    for (const row of weather) {
      const start = Date.parse(row?.datetime);
      if (!Number.isFinite(start)) continue;

      const end = start + 60 * 60 * 1000;
      const overlapStart = Math.max(start, ds);
      const overlapEnd = Math.min(end, de);
      const overlapHours = Math.max(0, overlapEnd - overlapStart) / 3600000;

      if (overlapHours <= 0) continue;

      const moonHour = this._nearestMoonHour(start, moonHours);
      const cls = this._classifyWeatherHour(row, moonHour, d);

      coveredHours += overlapHours;

      if (cls.status === "good") goodHours += overlapHours;
      else if (cls.status === "partial") partialHours += overlapHours;
      else badHours += overlapHours;

      if (Number.isFinite(cls.cloud)) weightedCloud += cls.cloud * overlapHours;
      if (Number.isFinite(cls.humidity)) weightedHumidity += cls.humidity * overlapHours;

      if (Number.isFinite(cls.wind)) {
        maxWind = maxWind === null ? cls.wind : Math.max(maxWind, cls.wind);
      }

      if (Number.isFinite(cls.precipitation)) {
        rainTotal += cls.precipitation * overlapHours;
      }

      if (Number.isFinite(cls.dewMargin)) {
        minDewMargin = minDewMargin === null
          ? cls.dewMargin
          : Math.min(minDewMargin, cls.dewMargin);
      }

      for (const reason of cls.reasons) {
        reasonWeights.set(reason, (reasonWeights.get(reason) || 0) + overlapHours);
      }

      rows.push({
        start: new Date(overlapStart),
        end: new Date(overlapEnd),
        hours: overlapHours,
        ...cls,
      });
    }

    if (coveredHours <= 0) return null;

    // Nejdelší souvislé zelené okno.
    let bestStart = null;
    let bestEnd = null;
    let currentStart = null;
    let currentEnd = null;

    for (const row of rows) {
      if (row.status === "good") {
        if (currentStart === null || row.start.getTime() > currentEnd.getTime() + 5 * 60 * 1000) {
          currentStart = row.start;
          currentEnd = row.end;
        } else {
          currentEnd = row.end;
        }

        if (
          bestStart === null ||
          (currentEnd.getTime() - currentStart.getTime()) >
            (bestEnd.getTime() - bestStart.getTime())
        ) {
          bestStart = new Date(currentStart);
          bestEnd = new Date(currentEnd);
        }
      } else {
        currentStart = null;
        currentEnd = null;
      }
    }

    const usableHours = goodHours + partialHours;

    let overall = "bad";
    let label = "NEFOTIT";

    if (goodHours >= 2.0) {
      overall = "good";
      label = "FOTIT";
    } else if (usableHours >= 2.0 || goodHours >= 0.75) {
      overall = "partial";
      label = "OMEZENĚ";
    }

    const reasons = [...reasonWeights.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([name]) => name);

    return {
      overall,
      label,
      goodHours,
      partialHours,
      badHours,
      usableHours,
      coveredHours,
      avgCloud: coveredHours > 0 ? weightedCloud / coveredHours : null,
      avgHumidity: coveredHours > 0 ? weightedHumidity / coveredHours : null,
      maxWind,
      rainTotal,
      minDewMargin,
      reasons,
      bestStart,
      bestEnd,
      rows,
    };
  }

  _astroCompact(decision) {
    if (!decision) return `<div class="astro outlook">🔵 VÝHLED</div>`;

    const icon = this._decisionIcon(decision.decision);
    if (decision.decision === "good") {
      return `<div class="astro good">${icon} ${this._escape(decision.label || "SPUSTIT")}</div>`;
    }
    if (decision.decision === "uncertain") {
      return `<div class="astro partial">${icon} ${this._escape(decision.label || "NEJISTÉ")}</div>`;
    }
    if (decision.decision === "bad") {
      return `<div class="astro bad">${icon} ${this._escape(decision.label || "NESPOUŠTĚT")}</div>`;
    }
    return `<div class="astro unavailable">${icon} ${this._escape(decision.label || "BEZ DAT")}</div>`;
  }

  _render() {
    if (!this._config || !this._hass) return;

    const oldScroller = this.shadowRoot.querySelector(".scroller");
    if (oldScroller) this._scrollLeft = oldScroller.scrollLeft;

    const stateObj = this._hass.states[this._config.entity];

    if (!stateObj) {
      this.shadowRoot.innerHTML = `
        <ha-card>
          <div style="padding:16px">
            Entita ${this._escape(this._config.entity)} nebyla nalezena.
          </div>
        </ha-card>`;
      return;
    }

    const allDays = Array.isArray(stateObj.attributes.daily) ? stateObj.attributes.daily : [];
    const today = this._todayInHaTimezone();
    const maxDays = Math.max(1, Number(this._config.days) || 45);

    const days = allDays
      .filter((d) => d && typeof d.date === "string" && d.date >= today)
      .slice(0, maxDays);

    // Počasí z weather.forecast_hvh zůstává jen jako doplňkový detail.
    // Provozní verdikt se bere výhradně z centrální entity.
    const analyses = days.map((d) => this._analyzeNightWeather(d));
    const decisions = days.map((d) => this._decisionForDate(d.date));

    const columns = days.map((d, idx) => {
      const analysis = analyses[idx];
      const decision = decisions[idx];
      const date = this._escape(d.label);
      const phase = this._phaseEmoji(d.phase);

      const illumination = Number.isFinite(Number(d.moon_illumination))
        ? `${Math.round(Number(d.moon_illumination))} %`
        : "–";

      const clean = Number.isFinite(Number(d.clean_hours))
        ? `${Number(d.clean_hours).toFixed(1)} h`
        : "–";

      const tooltip = this._escape(
        `Noc ${d.label} · ${d.phase ?? "Měsíc"} · osvětlení ${illumination} · ` +
        `Měsíc neruší ${clean}` +
        (decision ? ` · ${decision.label}` : " · provozní výhled")
      );

      return `
        <button class="day" type="button" data-index="${idx}" title="${tooltip}">
          <div class="date">${date}</div>
          <div class="moon" aria-hidden="true">${phase}</div>
          <div class="illumination">${illumination}</div>
          <div class="clean">${clean}</div>
          ${this._astroCompact(decision)}
        </button>`;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-width: 0;
        }

        ha-card {
          overflow: hidden;
        }

        .header {
          display: flex;
          align-items: baseline;
          gap: 8px;
          padding: 12px 14px 4px 14px;
          min-width: 0;
        }

        .title {
          font-weight: 600;
          color: var(--primary-text-color);
          white-space: nowrap;
        }

        .period {
          color: var(--secondary-text-color);
          font-size: .9em;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .legend {
          margin-left: auto;
          color: var(--secondary-text-color);
          font-size: .73rem;
          white-space: nowrap;
        }

        .scroller {
          display: flex;
          gap: 0;
          overflow-x: auto;
          overflow-y: hidden;
          padding: 6px 8px 10px 8px;
          cursor: grab;
          user-select: none;
          -webkit-user-select: none;
          -webkit-overflow-scrolling: touch;
          scrollbar-width: none;
          overscroll-behavior-x: contain;
        }

        .scroller::-webkit-scrollbar {
          display: none;
        }

        .scroller.dragging {
          cursor: grabbing;
        }

        .day {
          flex: 0 0 78px;
          min-width: 78px;
          text-align: center;
          padding: 3px 2px 5px 2px;
          box-sizing: border-box;
          border: 0;
          border-right: 1px solid color-mix(in srgb, var(--divider-color) 60%, transparent);
          background: transparent;
          color: inherit;
          font: inherit;
          cursor: pointer;
          border-radius: 8px;
        }

        .day:hover {
          background: color-mix(in srgb, var(--primary-text-color) 6%, transparent);
        }

        .day:focus-visible {
          outline: 2px solid var(--primary-color);
          outline-offset: -2px;
        }

        .day.selected {
          background: color-mix(in srgb, var(--primary-color) 14%, transparent);
          outline: 1px solid color-mix(in srgb, var(--primary-color) 45%, transparent);
          outline-offset: -1px;
        }

        .day:last-child {
          border-right: 0;
        }

        .date {
          font-size: .78rem;
          font-weight: 600;
          color: var(--primary-text-color);
          white-space: nowrap;
        }

        .moon {
          font-size: 1.35rem;
          line-height: 1.55;
          margin: 1px 0;
        }

        .illumination {
          font-size: .76rem;
          color: var(--primary-text-color);
          white-space: nowrap;
        }

        .clean {
          margin-top: 2px;
          font-size: .73rem;
          color: var(--secondary-text-color);
          white-space: nowrap;
        }

        .astro {
          margin-top: 3px;
          font-size: .68rem;
          font-weight: 650;
          white-space: nowrap;
        }

        .astro.good {
          color: var(--success-color, #4caf50);
        }

        .astro.partial {
          color: var(--warning-color, #ff9800);
        }

        .astro.bad {
          color: var(--error-color, #f44336);
        }

        .astro.unavailable {
          color: var(--secondary-text-color);
          font-weight: 400;
        }

        .astro.outlook {
          color: var(--info-color, #2196f3);
        }

        .aerosol-panel { margin-top:8px; padding:5px 9px; width:100%; max-width:100%; box-sizing:border-box; display:flex; align-items:center; gap:10px; overflow-x:auto; border:1px solid var(--divider-color); border-left:4px solid var(--divider-color); border-radius:7px; background:rgba(255,255,255,.02); scrollbar-width:thin; }
        .aerosol-panel.good { border-left-color:var(--success-color,#4caf50); background:rgba(76,175,80,.08); }
        .aerosol-panel.warning { border-left-color:var(--warning-color,#ff9800); background:rgba(255,152,0,.08); }
        .aerosol-panel.bad { border-left-color:var(--error-color,#f44336); background:rgba(244,67,54,.08); }
        .aerosol-head { display:flex; align-items:baseline; flex:0 0 auto; gap:8px; white-space:nowrap; }
        .aerosol-title { font-weight:700; }
        .aerosol-head a,.aerosol-links a { color:var(--primary-color); font-size:.75rem; }
        .aerosol-values { display:flex; align-items:center; flex:1 1 auto; gap:10px; min-width:max-content; font-size:.76rem; line-height:1.2; white-space:nowrap; }
        .aerosol-status { display:inline-flex; align-items:center; gap:5px; padding:2px 7px; border-radius:999px; font-weight:800; color:var(--secondary-text-color); background:rgba(255,255,255,.06); }
        .aerosol-status.good { color:var(--success-color,#4caf50); background:rgba(76,175,80,.14); }
        .aerosol-status.warning { color:var(--warning-color,#ff9800); background:rgba(255,152,0,.14); }
        .aerosol-status.bad { color:var(--error-color,#f44336); background:rgba(244,67,54,.14); }
        .aerosol-dot { width:7px; height:7px; border-radius:50%; background:currentColor; display:inline-block; }
        .aerosol-impact { font-weight:700; }
        .aerosol-impact.good { color:var(--success-color,#4caf50); }
        .aerosol-impact.warning { color:var(--warning-color,#ff9800); }
        .aerosol-impact.bad { color:var(--error-color,#f44336); }
        .aerosol-note { color:var(--secondary-text-color); }
        .aerosol-warning { color:var(--warning-color,#ff9800); }

        .details-inline {
          display: none;
          margin: 0 12px 12px 12px;
          border-top: 1px solid var(--divider-color);
          padding-top: 10px;
        }

        .details-inline.open {
          display: block;
        }

        .details-head {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 0 2px 8px 2px;
        }

        .details-title {
          font-weight: 650;
          font-size: 1rem;
        }

        .details-close {
          border: 1px solid var(--divider-color);
          background: transparent;
          color: var(--secondary-text-color);
          font-size: .82rem;
          line-height: 1.2;
          cursor: pointer;
          padding: 6px 10px;
          border-radius: 8px;
          white-space: nowrap;
        }

        .details-close:hover {
          background: color-mix(in srgb, var(--primary-text-color) 8%, transparent);
        }

        .details-body {
          padding: 0 2px 4px 2px;
        }

        .summary {
          margin: 0 0 10px 0;
          padding: 9px 11px;
          border-radius: 9px;
          background: color-mix(in srgb, var(--secondary-background-color) 75%, transparent);
          border-left: 3px solid var(--divider-color);
        }

        .summary.good {
          border-left-color: var(--success-color, #4caf50);
        }

        .summary.partial {
          border-left-color: var(--warning-color, #ff9800);
        }

        .summary.uncertain {
          border-left-color: var(--warning-color, #ff9800);
        }

        .summary.outlook {
          border-left-color: var(--info-color, #2196f3);
        }

        .summary.bad {
          border-left-color: var(--error-color, #f44336);
        }

        .summary-title {
          font-weight: 650;
          margin-bottom: 3px;
        }

        .summary-text {
          color: var(--secondary-text-color);
          line-height: 1.35;
          font-size: .86rem;
        }

        .details-phase {
          display: flex;
          align-items: center;
          gap: 10px;
          margin: 8px 0 10px 0;
        }

        .big-moon {
          font-size: 2rem;
          line-height: 1;
        }

        .details-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(120px, 1fr));
          gap: 9px 18px;
          align-items: start;
        }

        .detail-item {
          min-width: 0;
        }

        .details-label {
          color: var(--secondary-text-color);
          font-size: .74rem;
          margin-bottom: 2px;
        }

        .details-value {
          font-weight: 500;
          white-space: nowrap;
        }

        .weather-section {
          margin-top: 12px;
          padding-top: 10px;
          border-top: 1px solid var(--divider-color);
        }

        .weather-title {
          font-weight: 650;
          margin-bottom: 7px;
        }

        .current-dew {
          color: var(--secondary-text-color);
          font-size: .8rem;
          margin-top: 7px;
        }

        .empty {
          padding: 12px 14px 16px 14px;
          color: var(--secondary-text-color);
        }

        @media (max-width: 800px) {
          .legend {
            display: none;
          }

          .details-grid {
            grid-template-columns: repeat(2, minmax(120px, 1fr));
          }
        }
      </style>

      <ha-card>
        <div class="header">
          <div class="title">🌌 Astro předpověď</div>
          <div class="period">Měsíc neruší ${this._escape(stateObj.state)}</div>
          <div class="legend">🟢/🟠/🔴 společný verdikt · 🔵 výhled · AOD* neúplná data</div>
        </div>

        ${
          days.length
            ? `<div class="scroller" role="region" aria-label="Astro předpověď">${columns}</div>`
            : `<div class="empty">Nejsou dostupná budoucí data.</div>`
        }

        <div class="details-inline" aria-hidden="true">
          <div class="details-head">
            <div class="details-title">Detail noci</div>
            <button class="details-close" type="button" aria-label="Zavřít">Zavřít ×</button>
          </div>
          <div class="details-body"></div>
        </div>
      </ha-card>
    `;

    const scroller = this.shadowRoot.querySelector(".scroller");
    if (!scroller) return;

    const detailsInline = this.shadowRoot.querySelector(".details-inline");
    const detailsBody = this.shadowRoot.querySelector(".details-body");
    const detailsTitle = this.shadowRoot.querySelector(".details-title");
    const closeButton = this.shadowRoot.querySelector(".details-close");

    const closeDetails = () => {
      if (!detailsInline) return;
      detailsInline.classList.remove("open");
      detailsInline.setAttribute("aria-hidden", "true");
      this._selectedDayIndex = null;
      this.shadowRoot.querySelectorAll(".day")
        .forEach((el) => el.classList.remove("selected"));
    };

    const openDetails = (idx) => {
      if (this._selectedDayIndex === idx && detailsInline?.classList.contains("open")) {
        closeDetails();
        return;
      }

      const d = days[idx];
      const analysis = analyses[idx];
      const decision = decisions[idx];

      if (!d || !detailsInline || !detailsBody || !detailsTitle) return;

      const phase = this._phaseEmoji(d.phase);
      const moonInterpretation = this._nightInterpretation(d);

      const illumination = Number.isFinite(Number(d.moon_illumination))
        ? `${Number(d.moon_illumination).toFixed(1)} %`
        : "—";

      const altitude = Number.isFinite(Number(d.moon_altitude_midnight))
        ? `${Number(d.moon_altitude_midnight).toFixed(1)}°`
        : "—";

      const clean = Number.isFinite(Number(d.clean_hours))
        ? `${Number(d.clean_hours).toFixed(2)} h`
        : "—";

      const dark = Number.isFinite(Number(d.dark_hours))
        ? `${Number(d.dark_hours).toFixed(2)} h`
        : "—";

      const decisionClass = decision?.decision === "uncertain"
        ? "uncertain"
        : decision?.decision === "good"
          ? "good"
          : decision?.decision === "bad"
            ? "bad"
            : decision
              ? "partial"
              : "outlook";

      const decisionIcon = decision ? this._decisionIcon(decision.decision) : "🔵";
      const decisionLabel = decision?.label || "VÝHLED";
      const decisionReason = decision?.reason ||
        "Pro tuto vzdálenější noc zatím není provozní verdikt MET + ALADIN k dispozici.";

      let decisionBlock = "—";
      const centralBlock = decision?.launchBlock || decision?.bestBlock;
      if (centralBlock?.start && centralBlock?.end && Number.isFinite(Number(centralBlock?.hours))) {
        decisionBlock = `${this._formatTimeOnly(centralBlock.start)}–${this._formatTimeOnly(centralBlock.end)} · ${Number(centralBlock.hours).toFixed(1)} h`;
      }

      const metCentral = Number.isFinite(Number(decision?.metAvg)) ? `${Number(decision.metAvg).toFixed(0)} %` : "—";
      const alaCentral = Number.isFinite(Number(decision?.aladinAvg)) ? `${Number(decision.aladinAvg).toFixed(0)} %` : "—";
      const combinedCentral = Number.isFinite(Number(decision?.effectiveCloudAvg)) ? `${Number(decision.effectiveCloudAvg).toFixed(0)} %` : "—";
      const usableCentral = Number.isFinite(Number(decision?.usableHours)) ? `${Number(decision.usableHours).toFixed(1)} h` : "—";

      let weatherHtml = `
        <div class="weather-section">
          <div class="weather-title">Rozhodnutí observatoře</div>
          <div class="summary ${decisionClass}">
            <div class="summary-title">${decisionIcon} ${this._escape(decisionLabel)}</div>
            <div class="summary-text">${this._escape(decisionReason)}</div>
          </div>
          ${decision ? `
          <div class="details-grid">
            <div class="detail-item"><div class="details-label">Dobrý souvislý blok</div><div class="details-value">${decisionBlock}</div></div>
            <div class="detail-item"><div class="details-label">MET</div><div class="details-value">${metCentral}</div></div>
            <div class="detail-item"><div class="details-label">ALADIN</div><div class="details-value">${alaCentral}</div></div>
            <div class="detail-item"><div class="details-label">Kombinovaná oblačnost MET+ALADIN</div><div class="details-value">${combinedCentral}</div></div>
            <div class="detail-item"><div class="details-label">Použitelné hodiny</div><div class="details-value">${usableCentral}</div></div>
          </div>` : ""}
        </div>
        ${this._aerosolPanel(decision, centralBlock)}`;

      // Původní weather.forecast_hvh už nerozhoduje. Zůstává jen jako doplňkový
      // meteorologický pohled, aby se neztratil užitečný detail dlouhé karty.
      if (analysis) {
        const bestWindow = analysis.bestStart && analysis.bestEnd
          ? `${this._formatTimeOnly(analysis.bestStart)}–${this._formatTimeOnly(analysis.bestEnd)}`
          : "—";
        const maxWind = Number.isFinite(analysis.maxWind) ? `${analysis.maxWind.toFixed(1)} km/h` : "—";
        const humidity = Number.isFinite(analysis.avgHumidity) ? `${analysis.avgHumidity.toFixed(0)} %` : "—";
        const dewMargin = Number.isFinite(analysis.minDewMargin) ? `${analysis.minDewMargin.toFixed(1)} °C` : "—";
        const rain = Number.isFinite(analysis.rainTotal) ? `${analysis.rainTotal.toFixed(1)} mm` : "—";
        const reasonText = analysis.reasons.length
          ? `Omezuje: ${analysis.reasons.join(", ")}.`
          : "Bez významného omezení v doplňkovém zdroji.";

        weatherHtml += `
          <div class="weather-section">
            <div class="weather-title">Doplňkový výhled weather.forecast_hvh</div>
            <div class="summary-text">${this._escape(reasonText)}</div>
            <div class="details-grid" style="margin-top:8px">
              <div class="detail-item"><div class="details-label">Nejlepší čisté okno</div><div class="details-value">${bestWindow}</div></div>
              <div class="detail-item"><div class="details-label">Max. vítr</div><div class="details-value">${maxWind}</div></div>
              <div class="detail-item"><div class="details-label">Srážky</div><div class="details-value">${rain}</div></div>
              <div class="detail-item"><div class="details-label">Prům. vlhkost</div><div class="details-value">${humidity}</div></div>
              <div class="detail-item"><div class="details-label">Min. rezerva k rosnému bodu</div><div class="details-value">${dewMargin}</div></div>
            </div>
          </div>`;
      }

      let actualDewHtml = "";
      if (this._config.dewpoint_entity) {
        const dewState = this._hass.states[this._config.dewpoint_entity];
        const val = Number(dewState?.state);

        if (Number.isFinite(val) && d.date === this._todayInHaTimezone()) {
          actualDewHtml =
            `<div class="current-dew">Aktuálně měřený rosný bod: ${val.toFixed(1)} °C.</div>`;
        }
      }

      detailsTitle.textContent = `Noc ${this._nightLabel(d.date)}`;

      detailsBody.innerHTML = `
        <div class="summary ${moonInterpretation.summaryClass}">
          <div class="summary-title">${this._escape(moonInterpretation.photoSummary)}</div>
          <div class="summary-text">${this._escape(moonInterpretation.horizonSummary)}</div>
        </div>

        <div class="details-phase">
          <div class="big-moon">${phase}</div>
          <div>
            <div><strong>${this._escape(d.phase ?? "Měsíc")}</strong> · ${illumination}</div>
            <div style="color:var(--secondary-text-color);font-size:.84rem">
              výška o půlnoci ${altitude}
            </div>
          </div>
        </div>

        <div class="details-grid">
          <div class="detail-item">
            <div class="details-label">Astronomická tma</div>
            <div class="details-value">
              ${this._formatTimeOnly(d.astronomical_dark_start)}–${this._formatTimeOnly(d.astronomical_dark_end)}
            </div>
          </div>

          <div class="detail-item">
            <div class="details-label">Bez rušení Měsícem</div>
            <div class="details-value">${clean} z ${dark}</div>
          </div>

          <div class="detail-item">
            <div class="details-label">Západ Měsíce</div>
            <div class="details-value">${this._escape(this._formatDateTime(d.moonset))}</div>
          </div>

          <div class="detail-item">
            <div class="details-label">Východ Měsíce</div>
            <div class="details-value">${this._escape(this._formatDateTime(d.moonrise))}</div>
          </div>
        </div>

        ${weatherHtml}
        ${actualDewHtml}
      `;

      this.shadowRoot.querySelectorAll(".day")
        .forEach((el) => el.classList.remove("selected"));

      const selected = this.shadowRoot.querySelector(`.day[data-index="${idx}"]`);
      if (selected) selected.classList.add("selected");

      this._selectedDayIndex = idx;
      detailsInline.classList.add("open");
      detailsInline.setAttribute("aria-hidden", "false");
    };

    if (closeButton) {
      closeButton.addEventListener("click", (e) => {
        e.stopPropagation();
        closeDetails();
      });
    }

    this.shadowRoot.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeDetails();
    });

    scroller.scrollLeft = this._scrollLeft;

    scroller.addEventListener("scroll", () => {
      this._scrollLeft = scroller.scrollLeft;
    }, { passive: true });

    // Myš: krátký klik otevře detail, tažení posouvá pás.
    scroller.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "mouse" || e.button !== 0) return;

      const dayButton = e.target.closest ? e.target.closest(".day") : null;

      this._drag = {
        pointerId: e.pointerId,
        startX: e.clientX,
        startScrollLeft: scroller.scrollLeft,
        dayIndex: dayButton ? Number(dayButton.dataset.index) : null,
      };

      scroller.classList.add("dragging");
      scroller.setPointerCapture(e.pointerId);
    });

    scroller.addEventListener("pointermove", (e) => {
      if (!this._drag || e.pointerId !== this._drag.pointerId) return;

      const dx = e.clientX - this._drag.startX;
      if (Math.abs(dx) > 5) this._drag.moved = true;

      if (this._drag.moved) {
        scroller.scrollLeft = this._drag.startScrollLeft - dx;
        this._scrollLeft = scroller.scrollLeft;
        e.preventDefault();
      }
    });

    const finishMouse = (e) => {
      if (!this._drag || e.pointerId !== this._drag.pointerId) return;

      const moved = Boolean(this._drag.moved);
      const idx = this._drag.dayIndex;

      this._drag = null;
      scroller.classList.remove("dragging");

      try {
        scroller.releasePointerCapture(e.pointerId);
      } catch (_) {}

      if (!moved && Number.isInteger(idx)) openDetails(idx);
    };

    scroller.addEventListener("pointerup", finishMouse);
    scroller.addEventListener("pointercancel", finishMouse);

    // Touch: nativní swipe, krátký tap otevře detail.
    scroller.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "touch") return;

      const dayButton = e.target.closest ? e.target.closest(".day") : null;
      this._touchTap = {
        pointerId: e.pointerId,
        startX: e.clientX,
        startY: e.clientY,
        dayIndex: dayButton ? Number(dayButton.dataset.index) : null,
      };
    });

    scroller.addEventListener("pointerup", (e) => {
      if (!this._touchTap || e.pointerId !== this._touchTap.pointerId) return;

      const dx = Math.abs(e.clientX - this._touchTap.startX);
      const dy = Math.abs(e.clientY - this._touchTap.startY);
      const idx = this._touchTap.dayIndex;

      this._touchTap = null;

      if (dx <= 8 && dy <= 8 && Number.isInteger(idx)) openDetails(idx);
    });

    scroller.addEventListener("wheel", (e) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
        scroller.scrollLeft += e.deltaY;
        this._scrollLeft = scroller.scrollLeft;
        e.preventDefault();
      }
    }, { passive: false });

    // Pokud se karta překreslila kvůli nové předpovědi počasí,
    // zachovej otevřený detail stejného dne.
    const reopenIndex = this._selectedDayIndex;
    if (
      Number.isInteger(reopenIndex) &&
      reopenIndex >= 0 &&
      reopenIndex < days.length
    ) {
      this._selectedDayIndex = null;
      openDetails(reopenIndex);
    }
  }
}

if (!customElements.get("moon-forecast-card")) {
  customElements.define("moon-forecast-card", MoonForecastCard);
}

window.customCards = window.customCards || [];
const moonForecastCardRegistration = {
  type: "moon-forecast-card",
  name: "Moon Forecast Card v23",
  description: "Měsíc + centrální rozhodnutí, CAMS AOD 550 a 7Timer seeing.",
  preview: false,
};
const registeredMoonForecastCard = window.customCards.find(
  (card) => card.type === moonForecastCardRegistration.type,
);
if (registeredMoonForecastCard) {
  Object.assign(registeredMoonForecastCard, moonForecastCardRegistration);
} else {
  window.customCards.push(moonForecastCardRegistration);
}
