// astro-start-card v18 - direct CAMS/Open-Meteo and 7Timer source links.
class AstroStartCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._lastSignature = null;
    this._selectedNightIndex = 0;
  }

  setConfig(config) {
    if (!config) throw new Error("Chybí konfigurace karty.");
    this._config = {
      weather_entity: "sensor.astro_weather_detail", // kompatibilita se starou konfigurací
      moon_entity: "sensor.mesic_foceni_predpoved", // kompatibilita se starou konfigurací
      decision_entity: "sensor.astro_vhodnost_foceni",
      days: 3,
      ...config,
    };
    this._lastSignature = null;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;

    const decision = hass.states[this._config.decision_entity];
    const signature = [
      decision?.state ?? "decision-missing",
      decision?.attributes?.generated_at ?? decision?.last_updated ?? "",
      decision?.last_updated ?? "",
    ].join("|");

    if (signature !== this._lastSignature) {
      this._lastSignature = signature;
      this._render();
    }
  }

  getCardSize() { return 8; }

  _clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }
  _num(v) { const n = Number(v); return Number.isFinite(n) ? n : null; }

  _timezone() {
    return this._hass?.config?.time_zone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  }

  _dateInTimezone(date = new Date()) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: this._timezone(), year: "numeric", month: "2-digit", day: "2-digit",
    }).formatToParts(date);
    const get = (t) => parts.find((p) => p.type === t)?.value;
    return `${get("year")}-${get("month")}-${get("day")}`;
  }

  _formatTime(value) {
    if (!value) return "—";
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return "—";
    return new Intl.DateTimeFormat("cs-CZ", {
      timeZone: this._timezone(), hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(d);
  }

  _formatDate(value) {
    if (!value) return "—";
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return "—";
    return new Intl.DateTimeFormat("cs-CZ", {
      timeZone: this._timezone(), weekday: "short", day: "numeric", month: "numeric",
    }).format(d);
  }

  _escape(v) {
    return String(v ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  _decisionAnalyses() {
    const obj = this._hass?.states?.[this._config.decision_entity];
    const rows = obj?.attributes?.daily;
    return Array.isArray(rows) ? rows : [];
  }


  _decisionIcon(decision) {
    return ({ good: "🟢", uncertain: "🟠", bad: "🔴", unavailable: "⚪" })[decision] || "⚪";
  }

  _decisionClass(decision) {
    return ["good", "uncertain", "bad"].includes(decision) ? decision : "neutral";
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

  _moonInfo(night) {
    const phase = night?.phase || "Měsíc";
    const emoji = this._phaseEmoji(phase);
    const illumination = Number.isFinite(Number(night?.moon_illumination))
      ? `${Number(night.moon_illumination).toFixed(0)} %`
      : "—";
    const clean = Number(night?.clean_hours);
    const dark = Number(night?.dark_hours);
    const rise = night?.moonrise ? new Date(night.moonrise) : null;
    const set = night?.moonset ? new Date(night.moonset) : null;
    const ds = night?.astronomical_dark_start ? new Date(night.astronomical_dark_start) : null;
    const de = night?.astronomical_dark_end ? new Date(night.astronomical_dark_end) : null;
    const valid = (x) => x instanceof Date && !Number.isNaN(x.getTime());

    let cls = "neutral";
    let title = "Měsíc nelze vyhodnotit";
    let availability = "Bez hodinového vyhodnocení rušení.";

    if (Number.isFinite(clean) && Number.isFinite(dark) && dark > 0) {
      if (clean >= dark - 0.05) {
        cls = "good";
        title = "Měsíc neruší";
        availability = `Bez rušení ${clean.toFixed(1)} h z ${dark.toFixed(1)} h astronomické tmy.`;
      } else if (clean <= 0.05) {
        cls = "bad";
        title = "Měsíc ruší celou noc";
        availability = `Bez rušení jen ${clean.toFixed(1)} h z ${dark.toFixed(1)} h astronomické tmy.`;
      } else {
        cls = "uncertain";
        title = "Měsíc ruší část noci";
        availability = `Bez rušení ${clean.toFixed(1)} h z ${dark.toFixed(1)} h astronomické tmy.`;
      }
    }

    let timing = "";
    if (valid(ds) && valid(de) && valid(rise) && valid(set)) {
      const dsMs = ds.getTime();
      const deMs = de.getTime();
      const riseMs = rise.getTime();
      const setMs = set.getTime();

      if (setMs < dsMs && riseMs > deMs) {
        timing = "Po celou astronomickou noc je Měsíc pod horizontem.";
      } else if (riseMs < dsMs && setMs > deMs) {
        timing = "Po celou astronomickou noc je Měsíc nad horizontem.";
      } else if (setMs >= dsMs && setMs <= deMs && riseMs > deMs) {
        timing = `Měsíc zapadne během noci v ${this._formatTime(set)}.`;
      } else if (riseMs >= dsMs && riseMs <= deMs && setMs < dsMs) {
        timing = `Měsíc vyjde během noci v ${this._formatTime(rise)}.`;
      } else if (riseMs >= dsMs && riseMs <= deMs && setMs >= dsMs && setMs <= deMs) {
        timing = riseMs < setMs
          ? `Měsíc vyjde v ${this._formatTime(rise)} a zapadne v ${this._formatTime(set)}.`
          : `Měsíc zapadne v ${this._formatTime(set)} a znovu vyjde v ${this._formatTime(rise)}.`;
      } else {
        timing = `Západ ${this._formatTime(set)} · východ ${this._formatTime(rise)}.`;
      }
    }

    return {
      cls,
      emoji,
      phase,
      illumination,
      title,
      availability,
      timing,
      riseText: valid(rise) ? this._formatTime(rise) : "—",
      setText: valid(set) ? this._formatTime(set) : "—",
    };
  }

  _nightSummaryHtml(a, idx) {
    const selected = idx === this._selectedNightIndex ? " selected" : "";
    const cls = this._decisionClass(a?.decision);
    const icon = this._decisionIcon(a?.decision);
    const label = a?.label || "BEZ DAT";
    const nightDate = a?.darkStart ? this._formatDate(a.darkStart) : (a?.night?.label || "—");
    const astro = a?.darkStart && a?.darkEnd ? `${this._formatTime(a.darkStart)}–${this._formatTime(a.darkEnd)}` : "—";
    const b = a?.launchBlock || a?.bestBlock;
    const block = b ? `${this._formatTime(b.start)}–${this._formatTime(b.end)} · ${b.hours.toFixed(1)} h` : "nenalezen";
    const met = Number.isFinite(a?.metAvg) ? `${a.metAvg.toFixed(0)} %` : "—";
    const ala = Number.isFinite(a?.aladinAvg) ? `${a.aladinAvg.toFixed(0)} %` : "—";
    const combined = Number.isFinite(a?.effectiveCloudAvg) ? `${a.effectiveCloudAvg.toFixed(0)} %` : "—";
    const usable = Number.isFinite(a?.usableHours) ? `${a.usableHours.toFixed(1)} h` : "—";
    const moon = this._moonInfo(a?.night);
    const aerosol = this._aerosolInfo(a);
    const seeing = this._seeingInfo(a);
    const qualityBits = [aerosol.compact, seeing.compact].filter(Boolean);
    const qualityTone = [aerosol.tone, seeing.tone].includes("bad") ? "bad"
      : [aerosol.tone, seeing.tone].includes("warning") ? "warning" : aerosol.tone || seeing.tone;
    const qualityTitle = [aerosol.message, seeing.message].filter(Boolean).join(" · ");
    const cloudNote = (!b && Number.isFinite(a?.metAvg) && Number.isFinite(a?.aladinAvg) && a.metAvg >= 80 && a.aladinAvg >= 80)
      ? `<div class="night-note">Oba modely: převážně zataženo</div>`
      : "";

    return `
      <button class="night-card ${cls}${selected}" type="button" data-index="${idx}">
        <div class="night-date">${this._escape(nightDate)}</div>
        <div class="night-decision">${icon} ${this._escape(label)}</div>
        <div class="night-astro"><b>Astronomická noc:</b> ${astro}</div>
        <div class="night-block"><b>Dobrý blok:</b> ${block}</div>
        <div class="night-models"><span>MET ${met}</span><span>ALADIN ${ala}</span><span>KOMB ${combined}</span><span>Vhodné hodiny ${usable}</span></div>
        <div class="night-aerosols ${qualityTone}" title="${this._escape(qualityTitle)}">${this._escape(qualityBits.join(" · "))}</div>
        <div class="night-moon">${moon.emoji} ${this._escape(moon.title)} · ${this._escape(moon.illumination)}</div>
        ${cloudNote}
      </button>`;
  }


  _cloudBand(cloud) {
    if (!Number.isFinite(cloud)) return { cls: "unknown", label: "bez dat", icon: "mdi:help-circle-outline" };
    if (cloud <= 10) return { cls: "clear", label: "jasno", icon: "mdi:weather-night" };
    if (cloud <= 25) return { cls: "mostly-clear", label: "málo oblačnosti", icon: "mdi:weather-night-partly-cloudy" };
    if (cloud <= 45) return { cls: "light-cloud", label: "slabá oblačnost", icon: "mdi:weather-partly-cloudy" };
    if (cloud <= 70) return { cls: "cloudy", label: "oblačno", icon: "mdi:weather-cloudy" };
    return { cls: "overcast", label: "zataženo", icon: "mdi:cloud" };
  }

  _scoreMeaning(score) {
    if (!Number.isFinite(score)) return "bez hodnocení";
    if (score >= 80) return "výborné";
    if (score >= 60) return "dobré";
    if (score >= 40) return "nejisté";
    return "špatné";
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

  _hourDustSummary(source) {
    if (Number.isFinite(source?.dustUgm3)) return `prach ${this._dust(source.dustUgm3)}`;
    if (Number.isFinite(source?.dustAod550)) return `prach AOD ${this._aod(source.dustAod550)}`;
    return "prach —";
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

  _hourLimit(h) {
    const reasons = Array.isArray(h?.reasons) ? h.reasons.filter(Boolean).map(String) : [];
    const joined = reasons.join(", ");
    const text = joined.toLowerCase();
    const attrs = this._hass?.states?.[this._config.decision_entity]?.attributes || {};
    const settings = attrs.settings || {};
    const windBadSetting = Number(settings.wind_bad_ms);
    const aodBadSetting = Number(settings.aod_bad);
    const seeingBadSetting = Number(settings.seeing_bad_arcsec);
    const windBad = Number.isFinite(windBadSetting) ? windBadSetting : 12;
    const aodBad = Number.isFinite(aodBadSetting) ? aodBadSetting : 0.40;
    const seeingBad = Number.isFinite(seeingBadSetting) ? seeingBadSetting : 2.5;
    const status = h?.status || "unknown";
    const baseTone = status === "bad" ? "bad" : status === "good" ? "good" : "warning";
    const extra = reasons.length > 1 ? ` +${reasons.length - 1}` : "";
    const title = reasons.length
      ? `Hlavní omezení: ${joined}.`
      : status === "good"
        ? "Hodina je vhodná pro focení."
        : "Hodina nemá konkrétní důvod z backendu, rozhodlo nízké celkové skóre.";
    const pick = (label, tone = baseTone) => ({ label: `${label}${extra}`, tone, title });

    if (status === "good") return { label: "OK", tone: "good", title };
    if (Number(h?.precip) > 0 || text.includes("sráž")) return pick("srážky", "bad");
    if (h?.moonInterferes || text.includes("měsíc")) return pick("Měsíc", "bad");
    if (Number(h?.fog) >= 20 || text.includes("mlha")) return pick("mlha", "bad");
    if (Number(h?.wind) >= windBad || text.includes("vítr")) return pick("vítr", baseTone);
    if (Number(h?.seeingArcsec) >= seeingBad || h?.seeingStatus === "bad" || text.includes("seeing")) return pick("seeing", baseTone);
    if (Number(h?.aod550) >= aodBad || h?.aerosolStatus === "bad" || text.includes("zákal") || text.includes("aerosol")) return pick("AOD", baseTone);
    if (Number(h?.effectiveCloud) > 20 || text.includes("oblačnost")) return pick("oblačnost", baseTone);
    const dewMargin = Number(h?.dewMargin);
    if ((Number.isFinite(dewMargin) && dewMargin <= 3) || text.includes("rosa") || text.includes("opar") || text.includes("δt")) return pick("rosa", baseTone);
    if (text.includes("model")) return pick("modely", "warning");
    if (h?.aerosolFallback) return pick("AOD?", "warning");
    if (h?.seeingFallback) return pick("seeing?", "warning");
    if (status === "partial") return { label: "hraniční", tone: "warning", title };
    if (status === "uncertain") return { label: "nejisté", tone: "warning", title };
    return { label: "nízké skóre", tone: "bad", title };
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

  _detailHtml(a) {
    if (!a) return `<div class="empty">Pro vybranou noc nejsou data.</div>`;

    const cls = this._decisionClass(a.decision);
    const icon = this._decisionIcon(a.decision);

    if (!a.hours?.length) {
      return `
        <div class="detail-head">
          <div><div class="detail-title">${this._formatDate(a.darkStart)}</div><div class="detail-sub">${this._formatTime(a.darkStart)}–${this._formatTime(a.darkEnd)}</div></div>
          <div class="decision ${cls}"><div class="label">${icon} ${this._escape(a.label)}</div></div>
        </div>
        <div class="reason neutral"><strong>Hodinová data nejsou k dispozici</strong><div>${this._escape(a.reason)}</div></div>`;
    }

    const block = a.launchBlock || a.bestBlock;
    const moon = this._moonInfo(a.night);
    const blockText = block ? `${this._formatTime(block.start)}–${this._formatTime(block.end)} (${block.hours.toFixed(1)} h)` : "Nenalezen";
    const startText = block ? this._formatTime(block.start) : "Není doporučen";
    const prepText = a.prepTime ? this._formatTime(a.prepTime) : "Není doporučeno";
    const today = this._dateInTimezone();
    const isToday = a.night?.date === today;
    const now = new Date();
    const actionText = a.decision === "good" && a.prepTime
      ? (isToday && now >= new Date(a.prepTime) ? "Začít chladit / připravovat nyní" : `${isToday ? "Začít" : "Plán: začít"} chladit kolem ${prepText}`)
      : a.decision === "uncertain" ? "Před spuštěním zkontrolovat aktuální satelit/kamery" : "Techniku zatím nespouštět";

    const aerosolInfo = this._aerosolInfo(a);
    const seeingInfo = this._seeingInfo(a);
    const showHourlyAod = ["full", "partial", "fallback"].includes(aerosolInfo.mode);
    const showHourlySeeing = ["full", "partial", "fallback"].includes(seeingInfo.mode);
    const strip = a.hours.map((h) => {
      const band = this._cloudBand(h.effectiveCloud);
      const limit = this._hourLimit(h);
      const scoreMeaning = this._scoreMeaning(h.score);
      const cloudText = Number.isFinite(h.effectiveCloud)
        ? `${band.label} (${h.effectiveCloud.toFixed(0)} %)`
        : band.label;
      const title = [
        `${this._formatTime(h.start)}–${this._formatTime(h.end)}`,
        `skóre ${h.score.toFixed(0)} = ${scoreMeaning}`,
        `oblačnost ${cloudText}`,
        `důvěra ${h.confidence.toFixed(0)} %`,
        `MET ${h.metTotal === null ? "—" : h.metTotal.toFixed(0) + "%"}`,
        `ALADIN ${h.aladinTotal === null ? "—" : h.aladinTotal.toFixed(0) + "%"}`,
        h.dewMargin === null ? null : `ΔT ${h.dewMargin.toFixed(1)} °C`,
        showHourlyAod ? `AOD 550 ${this._aod(h.aod550)} · ${this._hourDustSummary(h)}` : null,
        showHourlyAod ? `průzračnost ${this._aerosolLabel(h.aerosolStatus)}` : null,
        h.aerosolFallback ? "aerosoly nezapočteny – hodnocení jako ve v7" : null,
        showHourlySeeing ? `seeing ${this._seeing(h.seeingArcsec)}` : null,
        h.seeingFallback ? "seeing nezapočten" : null,
        h.reasons.length ? h.reasons.join(", ") : "bez omezení",
      ].filter(Boolean).join(" · ");
      const aodWarning = ["poor", "bad", "unknown"].includes(h.aerosolStatus) || h.aerosolsStale || ["poor", "bad", "unknown"].includes(h.seeingStatus) || h.seeingStale;
      const qualityLines = [
        showHourlyAod ? `AOD ${this._aod(h.aod550)}${h.aerosolsStale ? "*" : ""}` : "",
        showHourlySeeing ? `S ${this._seeing(h.seeingArcsec)}${h.seeingStale ? "*" : ""}` : "",
      ].filter(Boolean).join(" · ");
      return `<div class="hour ${band.cls}" title="${this._escape(`${limit.title} ${title}`)}"><div class="t">${this._formatTime(h.start)}</div><div class="s">${Math.round(h.score)}</div><div class="sky"><ha-icon icon="${band.icon}"></ha-icon></div><div class="hour-reason ${limit.tone}" title="${this._escape(limit.title)}">${this._escape(limit.label)}</div>${qualityLines ? `<div class="hour-aod${aodWarning ? " warning" : ""}">${qualityLines}</div>` : ""}</div>`;
    }).join("");

    const avgModel = (v) => Number.isFinite(v) ? `${v.toFixed(0)} %` : "—";
    const coverage = Number.isFinite(a.modelCoverage) ? `${Math.round(a.modelCoverage * 100)} %` : "—";

    return `
      <div class="detail-head">
        <div>
          <div class="detail-title">${this._formatDate(a.darkStart)}</div>
          <div class="detail-sub">Astronomická noc ${this._formatTime(a.darkStart)}–${this._formatTime(a.darkEnd)}</div>
        </div>
        <div class="decision ${cls}"><div class="label">${icon} ${this._escape(a.label)}</div></div>
      </div>

      <div class="reason ${cls}">
        <strong>${this._escape(actionText)}</strong>
        <div>${this._escape(a.reason)}</div>
      </div>

      <div class="grid">
        <div><div class="k">Astronomická noc</div><div class="v">${this._formatTime(a.darkStart)}–${this._formatTime(a.darkEnd)}</div></div>
        <div><div class="k">Dobrý souvislý blok</div><div class="v">${blockText}</div></div>
        <div><div class="k">Doporučený start focení</div><div class="v">${startText}</div></div>
        <div><div class="k">Začít chladit / připravovat</div><div class="v">${prepText}</div></div>
      </div>

      <div class="models">
        <span>Průměr MET: <b>${avgModel(a.metAvg)}</b></span>
        <span>ALADIN: <b>${avgModel(a.aladinAvg)}</b></span>
        <span>Kombinovaná oblačnost: <b>${avgModel(a.effectiveCloudAvg)}</b></span>
        <span>Použitelné: <b>${a.usableHours.toFixed(1)} h</b></span>
        <span>Oba modely dostupné: <b>${coverage}</b></span>
      </div>

      ${this._aerosolPanel(a, block)}

      <div class="moon-panel ${moon.cls}">
        <div class="moon-main">
          <div class="moon-emoji">${moon.emoji}</div>
          <div class="moon-copy">
            <div class="moon-title">${this._escape(moon.title)}</div>
            <div class="moon-sub">${this._escape(moon.phase)} · osvětlení ${this._escape(moon.illumination)}</div>
          </div>
        </div>
        <div class="moon-meta">
          <span><b>Bez rušení:</b> ${this._escape(moon.availability)}</span>
          <span><b>Pohyb:</b> ${this._escape(moon.timing || `Západ ${moon.setText} · východ ${moon.riseText}`)}</span>
        </div>
      </div>

      <div class="strip-title">Hodinový přehled · popisek = hlavní omezení hodiny · barva = oblačnost${a.hours.some(h => h.aerosolsStale || h.seeingStale) ? " · * neobnovené údaje, nezapočítávají se" : ""}</div>
      <div class="strip">${strip}</div>
      <div class="cloud-legend">
        <span class="legend-item clear"><span class="legend-swatch"></span><ha-icon icon="mdi:weather-night"></ha-icon><span>Jasno</span></span>
        <span class="legend-item mostly-clear"><span class="legend-swatch"></span><ha-icon icon="mdi:weather-night-partly-cloudy"></ha-icon><span>Málo oblačnosti</span></span>
        <span class="legend-item light-cloud"><span class="legend-swatch"></span><ha-icon icon="mdi:weather-partly-cloudy"></ha-icon><span>Slabá oblačnost</span></span>
        <span class="legend-item cloudy"><span class="legend-swatch"></span><ha-icon icon="mdi:weather-cloudy"></ha-icon><span>Oblačno</span></span>
        <span class="legend-item overcast"><span class="legend-swatch"></span><ha-icon icon="mdi:cloud"></ha-icon><span>Zataženo</span></span>
      </div>
      <div class="score-help"><b>Skóre:</b> 80–100 výborné · 60–79 dobré · 40–59 nejisté · pod 40 špatné.</div>`;
  }

  _render() {
    if (!this._hass || !this._config) return;

    const decision = this._hass.states[this._config.decision_entity];
    if (!decision) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">Chybí centrální rozhodovací entita ${this._escape(this._config.decision_entity)}.</div></ha-card>`;
      return;
    }

    // Žádný lokální výpočet verdiktu. Karta pouze zobrazuje centrální sensor.
    const maxDays = Math.max(1, Number(this._config.days) || 3);
    const analyses = this._decisionAnalyses().slice(0, maxDays);
    if (!analyses.length) {
      this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px"><b>Rozhodnutí observatoře</b><br>Nejsou dostupné budoucí noci.</div></ha-card>`;
      return;
    }

    if (this._selectedNightIndex >= analyses.length) this._selectedNightIndex = 0;
    const selected = analyses[this._selectedNightIndex];
    const summaries = analyses.map((a, i) => this._nightSummaryHtml(a, i)).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; min-width:0; }
        ha-card { overflow:hidden; }
        .wrap { padding:14px 16px 16px; }
        .top { display:flex; align-items:flex-start; }
        .title { font-size:1.08rem; font-weight:700; }
        .nights { margin-top:12px; display:grid; grid-template-columns:repeat(${Math.max(1, analyses.length)}, minmax(190px,1fr)); gap:8px; overflow-x:auto; padding-bottom:4px; }
        .night-card { min-width:190px; text-align:left; border:1px solid var(--divider-color); border-radius:10px; padding:10px 11px; background:color-mix(in srgb,var(--secondary-background-color) 68%,transparent); color:inherit; cursor:pointer; font:inherit; }
        .night-card:hover { background:color-mix(in srgb,var(--primary-text-color) 6%,var(--secondary-background-color)); }
        .night-card.selected { outline:2px solid color-mix(in srgb,var(--primary-color) 70%,transparent); outline-offset:-2px; }
        .night-card.good { border-left:4px solid var(--success-color,#4caf50); }
        .night-card.uncertain { border-left:4px solid var(--warning-color,#ff9800); }
        .night-card.bad { border-left:4px solid var(--error-color,#f44336); }
        .night-card.neutral { border-left:4px solid var(--secondary-text-color); }
        .night-date { font-weight:700; font-size:.88rem; }
        .night-decision { margin-top:3px; font-weight:750; font-size:.95rem; }
        .night-card.good .night-decision { color:var(--success-color,#4caf50); }
        .night-card.uncertain .night-decision { color:var(--warning-color,#ff9800); }
        .night-card.bad .night-decision { color:var(--error-color,#f44336); }
        .night-astro,.night-block { margin-top:4px; color:var(--secondary-text-color); font-size:.73rem; }
        .night-astro b,.night-block b { color:var(--primary-text-color); font-weight:600; }
        .night-models { margin-top:7px; display:flex; flex-wrap:wrap; gap:7px 11px; font-size:.70rem; color:var(--secondary-text-color); }
        .night-note { margin-top:5px; font-size:.70rem; color:var(--secondary-text-color); font-style:italic; }
        .night-moon { margin-top:6px; font-size:.72rem; color:var(--secondary-text-color); }
        .night-aerosols { margin-top:6px; font-size:.72rem; color:var(--secondary-text-color); }
        .night-aerosols.good { color:var(--success-color,#4caf50); font-weight:700; }
        .night-aerosols.warning { color:var(--warning-color,#ff9800); font-weight:700; }
        .night-aerosols.bad { color:var(--error-color,#f44336); font-weight:700; }
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
        .hour-aod { margin-top:4px; font-size:.61rem; color:var(--secondary-text-color); white-space:nowrap; }
        .hour-aod.warning { color:var(--warning-color,#ff9800); font-weight:700; }
        .detail { margin-top:12px; border-top:1px solid var(--divider-color); padding-top:12px; }
        .detail-head { display:flex; align-items:flex-start; justify-content:space-between; gap:14px; }
        .detail-title { font-size:1rem; font-weight:700; }
        .detail-sub { margin-top:2px; color:var(--secondary-text-color); font-size:.79rem; }
        .decision { text-align:right; white-space:nowrap; }
        .decision .label { font-size:1.15rem; font-weight:800; }
        .decision.good .label { color:var(--success-color,#4caf50); }
        .decision.uncertain .label { color:var(--warning-color,#ff9800); }
        .decision.bad .label { color:var(--error-color,#f44336); }
        .reason { margin-top:10px; padding:10px 12px; border-radius:9px; background:color-mix(in srgb,var(--secondary-background-color) 80%,transparent); border-left:4px solid var(--divider-color); }
        .reason.good { border-left-color:var(--success-color,#4caf50); }
        .reason.uncertain { border-left-color:var(--warning-color,#ff9800); }
        .reason.bad { border-left-color:var(--error-color,#f44336); }
        .reason strong { display:block; margin-bottom:3px; }
        .grid { display:grid; grid-template-columns:repeat(4,minmax(120px,1fr)); gap:10px 18px; margin-top:12px; }
        .k { color:var(--secondary-text-color); font-size:.72rem; margin-bottom:2px; }
        .v { font-weight:550; }
        .models { margin-top:11px; display:flex; gap:16px; flex-wrap:wrap; color:var(--secondary-text-color); font-size:.80rem; }
        .moon-panel { margin-top:12px; padding:11px 12px; border-radius:10px; border:1px solid var(--divider-color); background:color-mix(in srgb,var(--secondary-background-color) 75%,transparent); }
        .moon-panel.good { border-left:4px solid var(--success-color,#4caf50); }
        .moon-panel.uncertain { border-left:4px solid var(--warning-color,#ff9800); }
        .moon-panel.bad { border-left:4px solid var(--error-color,#f44336); }
        .moon-main { display:flex; align-items:center; gap:12px; }
        .moon-emoji { font-size:1.9rem; line-height:1; }
        .moon-title { font-weight:700; }
        .moon-sub { margin-top:2px; color:var(--secondary-text-color); font-size:.80rem; }
        .moon-meta { margin-top:9px; display:grid; gap:5px; color:var(--secondary-text-color); font-size:.80rem; }
        .moon-meta b { color:var(--primary-text-color); }
        .cloud-legend { margin-top:10px; display:flex; flex-wrap:wrap; gap:7px 10px; align-items:center; }
        .legend-item { display:inline-flex; align-items:center; gap:5px; padding:4px 7px; border-radius:7px; border:1px solid var(--divider-color); font-size:.76rem; color:var(--secondary-text-color); }
        .legend-item ha-icon { --mdc-icon-size:17px; color:var(--primary-text-color); }
        .legend-swatch { width:9px; height:9px; border-radius:50%; display:inline-block; }
        .legend-item.clear .legend-swatch { background:var(--success-color,#4caf50); }
        .legend-item.mostly-clear .legend-swatch { background:#8bc34a; }
        .legend-item.light-cloud .legend-swatch { background:#fdd835; }
        .legend-item.cloudy .legend-swatch { background:var(--warning-color,#ff9800); }
        .legend-item.overcast .legend-swatch { background:var(--error-color,#f44336); }
        .score-help { margin-top:8px; color:var(--secondary-text-color); font-size:.80rem; }
        .score-help b { color:var(--primary-text-color); }
        .models b { color:var(--primary-text-color); }
        .strip-title { margin-top:13px; font-size:.76rem; color:var(--secondary-text-color); }
        .strip { margin-top:6px; display:flex; overflow-x:auto; gap:3px; padding-bottom:3px; scrollbar-width:thin; }
        .hour { flex:0 0 64px; border-radius:7px; padding:5px 3px; text-align:center; border:1px solid var(--divider-color); }
        .hour .t { font-size:.68rem; color:var(--secondary-text-color); }
        .hour .s { margin-top:2px; font-size:.80rem; font-weight:700; color:var(--primary-text-color); }
        .hour .sky { margin-top:2px; height:18px; display:flex; align-items:center; justify-content:center; }
        .hour .sky ha-icon { --mdc-icon-size:18px; color:var(--primary-text-color); }
        .hour-reason { margin-top:3px; min-height:1.05em; font-size:.58rem; line-height:1.05; font-weight:750; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .hour-reason.good { color:var(--success-color,#4caf50); }
        .hour-reason.warning { color:var(--warning-color,#ff9800); }
        .hour-reason.bad { color:var(--error-color,#f44336); }
        .hour.clear { background:color-mix(in srgb,var(--success-color,#4caf50) 20%,transparent); border-color:color-mix(in srgb,var(--success-color,#4caf50) 55%,var(--divider-color)); }
        .hour.mostly-clear { background:color-mix(in srgb,#8bc34a 24%,transparent); border-color:color-mix(in srgb,#8bc34a 55%,var(--divider-color)); }
        .hour.light-cloud { background:color-mix(in srgb,#fdd835 24%,transparent); border-color:color-mix(in srgb,#fdd835 55%,var(--divider-color)); }
        .hour.cloudy { background:color-mix(in srgb,var(--warning-color,#ff9800) 22%,transparent); border-color:color-mix(in srgb,var(--warning-color,#ff9800) 55%,var(--divider-color)); }
        .hour.overcast { background:color-mix(in srgb,var(--error-color,#f44336) 18%,transparent); border-color:color-mix(in srgb,var(--error-color,#f44336) 55%,var(--divider-color)); }
        .hour.unknown { background:color-mix(in srgb,var(--disabled-text-color,#9e9e9e) 16%,transparent); }
        .empty { padding:8px 0; color:var(--secondary-text-color); }
        @media(max-width:900px){ .nights{grid-template-columns:none; grid-auto-flow:column; grid-auto-columns:minmax(210px,75%);} .grid{grid-template-columns:repeat(2,minmax(120px,1fr));} .detail-head{flex-direction:column;} .decision{text-align:left;} }
      </style>
      <ha-card>
        <div class="wrap">
          <div class="top">
            <div class="title">🌌 Vhodnost focení</div>
          </div>

          <div class="nights">${summaries}</div>

          <div class="detail">${this._detailHtml(selected)}</div>
        </div>
      </ha-card>`;

    this.shadowRoot.querySelectorAll(".night-card").forEach((el) => {
      el.addEventListener("click", () => {
        const idx = Number(el.dataset.index);
        if (!Number.isInteger(idx)) return;
        this._selectedNightIndex = idx;
        this._render();
      });
    });
  }
}

if (!customElements.get("astro-start-card")) {
  customElements.define("astro-start-card", AstroStartCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "astro-start-card")) {
  window.customCards.push({
    type: "astro-start-card",
    name: "Astro Start Decision Card v18",
    description: "Centrální rozhodnutí observatoře včetně AOD 550 a seeingu.",
    preview: false,
  });
}
