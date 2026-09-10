// Stable Astro Weather Cards loader. Keep this resource URL unchanged.
const ASTRO_WEATHER_LOADER_STATE = "__astroWeatherCardsLoaderPromise";
const ASTRO_WEATHER_MANIFEST_URL = "/local/astro-weather-cards-manifest.json";

if (!window[ASTRO_WEATHER_LOADER_STATE]) {
  window[ASTRO_WEATHER_LOADER_STATE] = (async () => {
    const response = await fetch(ASTRO_WEATHER_MANIFEST_URL, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Astro Weather manifest: HTTP ${response.status}`);
    }

    const manifest = await response.json();
    const cards = Array.isArray(manifest?.cards) ? manifest.cards : [];
    if (!cards.length) {
      throw new Error("Astro Weather manifest neobsahuje žádné karty.");
    }

    for (const card of cards) {
      const url = String(card?.url || "");
      if (!/^\/local\/[a-z0-9-]+-v\d+\.js$/i.test(url)) {
        throw new Error(`Astro Weather manifest obsahuje neplatnou URL: ${url}`);
      }
      await import(url);
    }

    window.dispatchEvent(new CustomEvent("astro-weather-cards-loaded", {
      detail: manifest,
    }));
    return manifest;
  })().catch((error) => {
    delete window[ASTRO_WEATHER_LOADER_STATE];
    console.error("Astro Weather Cards loader selhal:", error);
    throw error;
  });
}

await window[ASTRO_WEATHER_LOADER_STATE];
