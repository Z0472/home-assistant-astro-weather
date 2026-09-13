// astro-satellite-card v9 - client-side EUMETView IR history timelapse without SD-card image storage.
import "/local/astro-satellite-card-v8.js";

const AstroSatelliteCardV9 = customElements.get("astro-satellite-card");

if (AstroSatelliteCardV9 && !AstroSatelliteCardV9.prototype._irHistoryV9) {
  const proto = AstroSatelliteCardV9.prototype;
  const oldRender = proto._render;
  const oldDisconnected = proto.disconnectedCallback;

  proto._historySettingsV9 = function(sat) {
    const frameCount = Math.max(5, Math.min(60, Number(
      this._config?.history_frames ?? sat?.visual_history_frames ?? 20
    ) || 20));
    const stepMinutes = Math.max(5, Math.min(60, Number(
      this._config?.history_step_minutes ?? sat?.visual_history_step_minutes ?? sat?.cadence_minutes ?? 10
    ) || 10));
    const delayMs = Math.max(250, Math.min(3000, Number(
      this._config?.history_frame_delay_ms ?? 650
    ) || 650));
    return { frameCount, stepMinutes, delayMs };
  };

  proto._historyAnchorV9 = function(sat) {
    const candidate = sat?.as_of ? new Date(sat.as_of) : new Date();
    return Number.isNaN(candidate.getTime()) ? new Date() : candidate;
  };

  proto._historyUrlV9 = function(baseUrl, stamp) {
    if (!baseUrl || !(stamp instanceof Date) || Number.isNaN(stamp.getTime())) return "";
    try {
      const url = new URL(String(baseUrl), window.location.href);
      url.searchParams.set("time", stamp.toISOString());
      // Explicit frame token prevents browser/proxy cache collisions between
      // historical WMS requests with otherwise identical map geometry.
      url.searchParams.set("_astro_history", String(stamp.getTime()));
      return url.toString();
    } catch (_) {
      const separator = String(baseUrl).includes("?") ? "&" : "?";
      return `${baseUrl}${separator}time=${encodeURIComponent(stamp.toISOString())}` +
        `&_astro_history=${stamp.getTime()}`;
    }
  };

  proto._historyFramesV9 = function(sat) {
    const baseUrl = String(sat?.visual_url || "");
    if (!baseUrl) return [];
    const settings = this._historySettingsV9(sat);
    const anchor = this._historyAnchorV9(sat);
    const stepMs = settings.stepMinutes * 60000;
    const frames = [];
    for (let index = 0; index < settings.frameCount; index += 1) {
      const reverseIndex = settings.frameCount - 1 - index;
      const stamp = new Date(anchor.getTime() - reverseIndex * stepMs);
      frames.push({ stamp, url: this._historyUrlV9(baseUrl, stamp) });
    }
    return frames.filter((row) => row.url);
  };

  proto._historyLabelV9 = function(stamp) {
    if (!(stamp instanceof Date) || Number.isNaN(stamp.getTime())) return "—";
    return new Intl.DateTimeFormat("cs-CZ", {
      timeZone: this._timezone(),
      day: "numeric",
      month: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(stamp);
  };

  proto._historySpanLabelV9 = function(frames) {
    if (!Array.isArray(frames) || frames.length < 2) return "historie";
    const minutes = Math.round((frames[frames.length - 1].stamp - frames[0].stamp) / 60000);
    if (minutes >= 120) {
      const hours = minutes / 60;
      return `${hours.toFixed(hours % 1 ? 1 : 0).replace(".", ",")} h`;
    }
    return `${minutes} min`;
  };

  proto._setHistoryOverlayV9 = function(historyMode) {
    const section = this.shadowRoot?.querySelector(".visual-section");
    if (!section) return;
    section.classList.toggle("history-mode-v9", Boolean(historyMode));
    const note = section.querySelector(".visual-note-v4");
    if (note) {
      if (!note.dataset.liveTextV9) note.dataset.liveTextV9 = note.textContent || "";
      note.textContent = historyMode
        ? "historie IR10.5 · CLM body jsou skryté, protože patří k aktuálnímu snímku · kruhy 15 / 30 km"
        : note.dataset.liveTextV9;
    }
  };

  proto._setHistoryHeadV9 = function(frame, live = false) {
    const head = this.shadowRoot?.querySelector(".visual-head span");
    if (!head) return;
    if (!head.dataset.liveTextV9) head.dataset.liveTextV9 = head.textContent || "";
    head.textContent = live
      ? head.dataset.liveTextV9
      : `historie ${this._historyLabelV9(frame?.stamp)} · výřez ±${(this._num(this._hass?.states?.[this._config?.satellite_entity]?.attributes?.visual_radius_km) ?? 150).toFixed(0)} km`;
  };

  proto._showHistoryFrameV9 = function(index) {
    const frames = this._satHistoryFramesV9 || [];
    if (!frames.length) return;
    const safeIndex = Math.max(0, Math.min(frames.length - 1, Number(index) || 0));
    const frame = frames[safeIndex];
    const image = this.shadowRoot?.querySelector(".visual-image");
    if (!image) return;

    this._satHistoryIndexV9 = safeIndex;
    image.src = frame.url;
    image.alt = `Historický EUMETSAT MTG IR10.5 ${this._historyLabelV9(frame.stamp)}`;
    this._setHistoryOverlayV9(true);
    this._setHistoryHeadV9(frame, false);

    const slider = this.shadowRoot.querySelector(".history-slider-v9");
    const time = this.shadowRoot.querySelector(".history-time-v9");
    const live = this.shadowRoot.querySelector(".history-live-v9");
    if (slider) slider.value = String(safeIndex);
    if (time) time.textContent = this._historyLabelV9(frame.stamp);
    if (live) live.classList.remove("active");
  };

  proto._showLiveImageV9 = function() {
    const satObj = this._hass?.states?.[this._config?.satellite_entity];
    const sat = satObj?.attributes || {};
    const image = this.shadowRoot?.querySelector(".visual-image");
    if (image) {
      const liveUrl = this._visualUrl(sat, satObj);
      if (liveUrl) image.src = liveUrl;
      image.alt = "Aktuální EUMETSAT MTG IR10.5";
    }
    this._satHistoryIndexV9 = null;
    this._setHistoryOverlayV9(false);
    this._setHistoryHeadV9(null, true);
    const slider = this.shadowRoot?.querySelector(".history-slider-v9");
    const time = this.shadowRoot?.querySelector(".history-time-v9");
    const live = this.shadowRoot?.querySelector(".history-live-v9");
    if (slider && this._satHistoryFramesV9?.length) slider.value = String(this._satHistoryFramesV9.length - 1);
    if (time) time.textContent = "živě";
    if (live) live.classList.add("active");
  };

  proto._pauseHistoryV9 = function() {
    if (this._satHistoryTimerV9) {
      clearInterval(this._satHistoryTimerV9);
      this._satHistoryTimerV9 = null;
    }
    const play = this.shadowRoot?.querySelector(".history-play-v9");
    if (play) play.textContent = "▶ Přehrát";
  };

  proto._startHistoryV9 = function() {
    const frames = this._satHistoryFramesV9 || [];
    if (!frames.length) return;
    this._pauseHistoryV9();

    // If we are on live/latest, replay from the oldest frame. If the user
    // scrubbed the slider, continue from that selected historical frame.
    let index = Number.isInteger(this._satHistoryIndexV9) ? this._satHistoryIndexV9 : 0;
    if (index >= frames.length - 1) index = 0;
    this._showHistoryFrameV9(index);

    const play = this.shadowRoot?.querySelector(".history-play-v9");
    if (play) play.textContent = "⏸ Pozastavit";
    const delay = this._historySettingsV9(this._hass?.states?.[this._config?.satellite_entity]?.attributes || {}).delayMs;
    this._satHistoryTimerV9 = setInterval(() => {
      index += 1;
      if (index >= frames.length) {
        this._pauseHistoryV9();
        this._showLiveImageV9();
        return;
      }
      this._showHistoryFrameV9(index);
    }, delay);
  };

  proto._preloadHistoryV9 = function() {
    const frames = this._satHistoryFramesV9 || [];
    if (this._satHistoryPreloadedKeyV9 === frames.map((row) => row.url).join("|")) return;
    this._satHistoryPreloadedKeyV9 = frames.map((row) => row.url).join("|");
    // Browser cache only: no satellite JPEG is written to the Home Assistant
    // data/cache directory or SD card.
    frames.forEach((frame) => {
      const preload = new Image();
      preload.decoding = "async";
      preload.src = frame.url;
    });
  };

  proto._installHistoryUiV9 = function() {
    if (!this.shadowRoot || !this._config || !this._hass) return;
    const satObj = this._hass.states?.[this._config.satellite_entity];
    const sat = satObj?.attributes || {};
    const section = this.shadowRoot.querySelector(".visual-section");
    const panel = this.shadowRoot.querySelector(".visual-panel");
    if (!section || !panel || !sat.visual_url || !sat.available) return;

    const frames = this._historyFramesV9(sat);
    if (frames.length < 2) return;
    this._satHistoryFramesV9 = frames;
    this._satHistoryIndexV9 = null;

    const controls = document.createElement("div");
    controls.className = "history-controls-v9";
    controls.innerHTML = `
      <button type="button" class="history-play-v9" title="Přehrát posledních ${this._historySpanLabelV9(frames)} IR10.5">▶ Přehrát</button>
      <input class="history-slider-v9" type="range" min="0" max="${frames.length - 1}" value="${frames.length - 1}" step="1" aria-label="Historie satelitního IR snímku">
      <span class="history-time-v9">živě</span>
      <button type="button" class="history-live-v9 active" title="Vrátit aktuální IR snímek a aktuální CLM body">Živě</button>`;
    panel.before(controls);

    const style = document.createElement("style");
    style.textContent = `
      .history-controls-v9 {
        display:grid;
        grid-template-columns:auto minmax(70px,1fr) auto auto;
        align-items:center;
        gap:7px;
        margin:0 1px 7px;
        font-size:.66rem;
      }
      .history-controls-v9 button {
        border:1px solid var(--divider-color);
        border-radius:7px;
        background:var(--secondary-background-color);
        color:var(--primary-text-color);
        padding:5px 7px;
        font:inherit;
        font-weight:700;
        cursor:pointer;
        white-space:nowrap;
      }
      .history-controls-v9 button.active {
        border-color:var(--primary-color);
        color:var(--primary-color);
      }
      .history-slider-v9 { width:100%; min-width:0; cursor:pointer; }
      .history-time-v9 { color:var(--secondary-text-color); white-space:nowrap; min-width:58px; text-align:center; }
      .visual-section.history-mode-v9 .sample-v4 { opacity:0 !important; }
      @media (max-width:430px) {
        .history-controls-v9 { grid-template-columns:auto 1fr auto; }
        .history-time-v9 { grid-column:1 / -1; grid-row:2; text-align:center; }
      }`;
    section.prepend(style);

    const play = controls.querySelector(".history-play-v9");
    const slider = controls.querySelector(".history-slider-v9");
    const live = controls.querySelector(".history-live-v9");
    play?.addEventListener("click", () => {
      this._preloadHistoryV9();
      if (this._satHistoryTimerV9) this._pauseHistoryV9();
      else this._startHistoryV9();
    });
    slider?.addEventListener("input", (event) => {
      this._preloadHistoryV9();
      this._pauseHistoryV9();
      this._showHistoryFrameV9(Number(event.target.value));
    });
    live?.addEventListener("click", () => {
      this._pauseHistoryV9();
      this._showLiveImageV9();
    });
  };

  proto._render = function() {
    // A fresh HA entity publication replaces the card DOM. Stop an old playback
    // timer first, then rebuild controls against the new satellite timestamps.
    this._pauseHistoryV9();
    oldRender.call(this);
    this._installHistoryUiV9();
  };

  proto.disconnectedCallback = function() {
    this._pauseHistoryV9();
    if (oldDisconnected) oldDisconnected.call(this);
  };

  proto._irHistoryV9 = true;
}

window.customCards = window.customCards || [];
const registration = window.customCards.find((card) => card.type === "astro-satellite-card");
if (registration) {
  Object.assign(registration, {
    name: "Astro Satellite Nowcast Card v9",
    description: "IR10.5 historie posledních cca 3 hodin s přehráváním a sliderem; snímky se načítají z EUMETView WMS přímo do prohlížeče bez ukládání na SD kartu.",
  });
}
