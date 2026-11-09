'use strict';
const $ = id => document.getElementById(id);
let tz = 'Europe/Prague', before = null, requestNumber = 0;
const stamp = value => value ? new Date(value).toLocaleString('cs-CZ', {timeZone:tz}) : '—';
const unit = (value, suffix) => typeof value === 'number' ? `${value} ${suffix}` : '—';
async function api(path) { const response = await fetch(path); if (!response.ok) throw new Error(`Služba není dostupná (${response.status}).`); return response.json(); }
function render(weather, decision) {
  tz = weather.location?.timezone || 'Europe/Prague';
  $('location').textContent = weather.location?.latitude != null ? `${weather.location.latitude}° N / ${weather.location.longitude}° E · ${weather.location.altitude} m · ${tz}` : 'Čekám na první předpověď';
  $('verdict').textContent = decision.state || 'Čekám na data';
  $('reason').textContent = decision.reason || '';
  const age = weather.generated_at ? (Date.now() - Date.parse(weather.generated_at)) / 3600000 : 0;
  $('updated').textContent = `Výpočet: ${stamp(weather.generated_at)} · zdroje: ${weather.state || 'starting'}${age > 3 ? ' · STARŠÍ DATA' : ''}${weather.last_refresh_error ? ' · poslední obnova selhala' : ''}`;
  $('nights').replaceChildren();
  for (const night of decision.daily || []) {
    const box = document.createElement('article'); box.className = 'night';
    const title = document.createElement('h3'); title.textContent = night.darkStart ? stamp(night.darkStart) : 'Noc';
    const status = document.createElement('strong'); status.textContent = night.label || night.state || '—';
    const reason = document.createElement('p'); reason.textContent = night.reason || '';
    box.append(title,status,reason); $('nights').append(box);
  }
  $('hours').replaceChildren();
  for (const row of (weather.forecast || []).slice(0, 72)) {
    const met = row.met || {}, tr = document.createElement('tr');
    for (const value of [stamp(row.datetime),unit(met.cloud_total,'%'),unit(met.cloud_low,'%'),unit(met.cloud_medium,'%'),unit(met.cloud_high,'%'),unit(met.temperature,'°C'),unit(met.dew_point,'°C'),unit(met.wind_speed_ms,'m/s'),unit(met.precipitation_1h,'mm')]) {
      const td = document.createElement('td'); td.textContent = value; tr.append(td);
    }
    $('hours').append(tr);
  }
}
async function loadCurrent() {
  const request = ++requestNumber;
  try {
    const [weather,decision] = await Promise.all([api('/forecast?hours=72'),api('/decision')]);
    if(request !== requestNumber) return;
    render(weather,decision); $('error').textContent = ''; $('archive').textContent = '';
  } catch(e) { if(request === requestNumber) $('error').textContent = e.message; }
}
async function loadHistory(reset = false) {
  try {
    const page = await api('/history?limit=50' + (!reset && before ? `&before=${before}` : ''));
    if(reset) { $('history').replaceChildren(new Option('Aktuální předpověď','')); before = null; }
    for(const row of page.items) $('history').append(new Option(`${stamp(row.generated_at)} · ${row.decision || row.state}`, row.id));
    before = page.next_before; $('more').disabled = !before;
  } catch(e) { $('error').textContent = e.message; }
}
$('history').addEventListener('change',async () => {
  const id = $('history').value;
  if(!id) return loadCurrent();
  const request = ++requestNumber;
  try { const result = await api(`/history/${id}`); if(request !== requestNumber) return;
    render(result.weather,result.decision); $('error').textContent = '';
    $('archive').textContent = 'Zobrazuješ archivní předpověď. Pro aktuální data zvol „Aktuální předpověď“.';
  } catch(e) { if(request === requestNumber) $('error').textContent = e.message; }
});
$('more').addEventListener('click',() => loadHistory());
$('refresh').addEventListener('click',async () => { $('history').value=''; await loadCurrent(); await loadHistory(true); });
(async () => {await loadCurrent(); await loadHistory(true);})();
setInterval(() => {if(!$('history').value) loadCurrent();},60000);
