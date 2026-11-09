# Astro Weather Backend pro Azure AKS

Samostatná cloudová varianta veřejného backendu 12.4.18. Používá `astro_weather_backend/app.py`
a stejné výpočty MET/ALADIN/ICON, aerosolů, seeingu, Měsíce a rozhodnutí o focení.
Původní HA Dockerfile, konfigurace a instalace doplňku se nemění.

## Co tato verze obsahuje

- Docker image pro Linux/amd64, sestavitelný přímo v Azure Container Registry.
- Webový přehled bez Home Assistantu: počasí, nejbližší noci, výběr archivní předpovědi.
- PostgreSQL: historie celých výstupů `weather`, `decision`, `moon` v JSONB, včetně
  jednotlivých hodin a informací o stáří/zdrojích dat.
- AKS Deployment, Service, ConfigMap/Secret při nasazení, trvalý disk pro cache a
  nezapsaný snímek. Databáze je samostatný **Azure Database for PostgreSQL Flexible Server**.
- PowerShell 7 nasazovací skript s kontrolou návratových kódů, sestavením image a kontrolou rollout.
- Oddělená liveness/readiness; výpadek DB nezpůsobuje restartovou smyčku liveness.
- Testy v CI se skutečným PostgreSQL 16, sestavení image a validace Kubernetes manifestů.

Historie znamená **co backend předpovídal v daný okamžik**. Nejde o měření skutečného
počasí a sama o sobě nedokazuje úspěšnost předpovědi. `generated_at` je čas výpočtu
backendu, `sources.*` obsahují dostupné časy běhů zdrojových modelů. Nový výpočet
nemusí znamenat nové vydání modelu.

## Provozní model první verze

Jeden pod pro jednu lokalitu, jeden sběrný proces, strategie Recreate. Aktualizace
má krátký výpadek; není to HA/škálovaná služba. **Nezvyšovat replicas ani nezapínat HPA**
bez oddělení sběrače a API a náhrady lokální cache. PostgreSQL advisory lock brání
souběžnému sběru stejné lokality při nechtěném překryvu, nenahrazuje architekturu více replik.

Cache a dočasně nezapsaný snímek jsou na PVC `astro-cache`. Zápis do DB je idempotentní
podle `(location_key, generated_at)`. Pokud INSERT selže, soubor `pending_*.json`
zůstane na disku a před dalším sběrem se znovu odešle. Při restartu se poslední
uložená předpověď načte z DB. Výpadek všech zdrojů může podle původních pravidel
backendu ponechat poslední platný stav; jeho původní čas zůstává viditelný.

Archiv se automaticky nemaže. Nastav zálohování a sleduj velikost PostgreSQL;
retenci můžeme později zavést podle požadovaného počtu měsíců. Nesmazat PVC,
pokud obsahuje dosud nezapsaný snímek. Probíhající, ještě nedokončený výpočet
není při ukončení kontejneru garantován; další start ho zopakuje.

## 1. Prostředky v Azure

Před spuštěním `deploy.ps1` musí existovat:

| Prostředek | Nastavení pro první pokus |
|---|---|
| Resource group | Samostatná testovací skupina, například `rg-astro-weather` |
| Azure Container Registry | Basic, klasický RBAC režim |
| AKS | Linux/amd64, Free řídicí rovina, jeden systémový uzel dle povolených SKU/kvót |
| PostgreSQL Flexible Server | PostgreSQL 16, databáze `astro_weather` |
| Síť | AKS má DNS a TCP 5432 přístup k PostgreSQL a HTTPS odchozí přístup ke zdrojům počasí |
| Identita | Kubelet identita AKS má `AcrPull` na vybraném ACR |

Pro PostgreSQL preferuj privátní síť: server v delegovaném subnetu téže/propojené VNet
a privátní DNS zónu připojenou k VNet AKS. AKS a PostgreSQL mají **různé subnety**.
Pokud testuješ přes veřejný endpoint DB, povol pouze skutečné odchozí IP clusteru,
nikoli všechny sítě. Používej FQDN serveru, ne jeho IP (ověření TLS a privátní DNS).

Skript tyto placené prostředky nevytváří. Region, předplatné, velikost uzlu a DB
je nutné vybrat předem podle dostupnosti a ceny. AKS Free neznamená bezplatné uzly,
disky, registry ani databázi. Zastavení clusteru neodstraní všechny náklady.

Připojení běžného RBAC ACR k AKS (vyžaduje právo přidělit roli):

```powershell
az account set --subscription '<subscription-id>'
az aks update --resource-group rg-astro-weather --name aks-astro-weather --attach-acr '<acr-name>'
```

Pro ACR s ABAC je potřeba odpovídající repository reader role místo `--attach-acr`.

### Databázová role

V Azure vytvoř databázi `astro_weather` a samostatnou přihlašovací roli `astro_app`.
Pro první pokus musí mít právo CONNECT do této DB a USAGE/CREATE v jejím schématu
`public`: init container vytvoří tabulku a index. Například přes přihlášení správce:

```sql
-- Heslo pro roli nastav bezpečně v nástroji správce, ne v repozitáři.
-- Příklad předpokládá již vytvořenou LOGIN roli astro_app a databázi astro_weather.
GRANT CONNECT ON DATABASE astro_weather TO astro_app;
-- Následující příkaz spusť připojený k databázi astro_weather:
GRANT USAGE, CREATE ON SCHEMA public TO astro_app;
```

Před ostrým provozem lze migrace oddělit pod jinou roli a aplikaci ponechat pouze
SELECT/INSERT a právo na identity sequence. První verze má migrace i runtime pod
jednou rolí. TLS používá `verify-full` se systémovým CA bundle; ověřuje certifikát i hostname.

## 2. Nastavení lokality

Z kořene repozitáře:

```powershell
Copy-Item cloud/options.example.json astro-options.local.json
notepad astro-options.local.json
```

Souřadnice v příkladu jsou **Praha**, nikoli tvoje observatoř. Uprav latitude,
longitude, altitude a timezone. Soubor přijímá také rozhodovací parametry původního
doplňku. Chybný JSON nebo chybějící souřadnice zastaví start, aby se nepoužila jiná lokalita.
Cloudová varianta vždy vypne publikaci HA entit a instalaci HA karet.

Satelit je v příkladu vypnutý. Volitelně zapni `use_satellite` a přidej proměnné
`EUMETSAT_CONSUMER_KEY` / `EUMETSAT_CONSUMER_SECRET` do Kubernetes Secretu.
V této verzi se satelit vyhodnocuje spolu s hlavním refreshem (výchozí 30 min),
nikoli samostatně každých 10 min. Snímky satelitních souborů se nearchivují; ukládají
se pouze vypočtené hodnoty obsažené ve výstupu backendu. Satelit může vyžadovat vyšší paměť.

MET používá persistentní HTTP cache nejméně 3 hodiny, případně déle podle `Expires`,
a podmíněné požadavky `If-Modified-Since`. Stejné chování platí i po restartu podu.
Interval obnovy rozhodnutí 30 min tedy neznamená stahování MET každých 30 min.
Mimo severskou oblast MET požaduje nejméně tříhodinový odstup a žádné plánované
požadavky přesně v XX:00. Nastavení `MET_USER_AGENT` v Secretu může obsahovat vlastní
identifikaci aplikace/kontaktní web. Uživatel provozující službu musí respektovat
podmínky a licenci každého zdroje; web uvádí poskytovatele.

## 3. Sestavení a nasazení v Azure

PowerShell 7, Azure CLI, kubectl; lze použít také PowerShell v Azure Cloud Shell.
Lokální Docker není potřeba, image sestavuje `az acr build` v Azure.

```powershell
az login
$dbCredential = Get-Credential -UserName 'astro_app' -Message 'Přístup do PostgreSQL'
./cloud/deploy.ps1 `
  -SubscriptionId '<subscription-id>' `
  -ResourceGroup 'rg-astro-weather' `
  -AksName 'aks-astro-weather' `
  -RegistryName '<acr-name>' `
  -PostgresHost '<server>.postgres.database.azure.com' `
  -PostgresDatabase 'astro_weather' `
  -PostgresCredential $dbCredential `
  -OptionsFile './astro-options.local.json' `
  -ImageTag 'azure-v0.1.0'
```

Používej nový tag pro každé sestavení. Skript nepíše heslo do souboru ani argumentů
procesu; předá Secret přes stdin. Nezapínej debug transcript při práci s tajnými údaji.
Každé nasazení znovu nastaví Secret `astro-postgres`; volitelné EUMETSAT proměnné
spravuj odděleným Secretem a přidej jej do `envFrom`, aby nebyly při nasazení přepsané.

Init container provede opakovatelnou migraci. Nasazení používá jednu repliku a PVC,
které v AKS poskytuje `managed-csi`. RAM volume `/dev/shm` má 1 GiB pro rozbalení
GRIB; jeho využití se počítá do paměťového limitu podu. Při OOMKilled uprav limit
podle skutečného využití, zejména při zapnutém satelitu.

## 4. Otevření webu a kontrola

Na svém PC (Cloud Shell port-forward není automaticky localhost tvého PC):

```powershell
az aks get-credentials -g rg-astro-weather -n aks-astro-weather
kubectl -n astro-weather get pods,pvc,svc
kubectl -n astro-weather logs deployment/astro-weather -c migrate
kubectl -n astro-weather logs deployment/astro-weather -c backend --tail=100
kubectl -n astro-weather port-forward service/astro-weather 8080:80
```

Otevři http://localhost:8080. První sběr může trvat několik minut; během něj web ukáže,
že čeká na data. Rozhodnutí a historie zůstávají dostupné po obnovení podu.
Nedostupnost zdroje se promítne do diagnostiky původního backendu.

| Endpoint | Význam |
|---|---|
| `/` | Web |
| `/forecast?hours=72` | Aktuální předpověď |
| `/decision` | Aktuální rozhodnutí |
| `/moon` | Interní výpočet Měsíce |
| `/history?limit=50&before=123` | Stránkované záznamy aktuální lokality, limit 1–200 |
| `/history/123` | Celý archivní snímek |
| `/livez` | HTTP proces žije; nezávisí na DB ani počasí |
| `/readyz` | DB schéma dostupné, sběrač běží, bez poslední chyby zápisu/sběru |

Readiness neznamená, že modely mají čerstvá data; řiď se `generated_at`, `sources`
a `errors`. Hodiny dat zdrojů se mohou lišit. Historie zůstává vždy původní.

Výchozí Service je interní ClusterIP. Pro veřejný web přidej HTTPS ingress/gateway
ve svém AKS, DNS a certifikát. Aplikace zatím nemá vlastní přihlášení ani uživatelské
účty; při zveřejnění bude dostupná i historie a souřadnice. Pro soukromou observatoř
použij autentizaci na vstupní bráně. Veřejný endpoint není vytvářen automaticky.

## Testy a lokální pokus

```powershell
python -m pip install -r cloud/requirements.txt
python -m unittest discover -s cloud/tests -v
node --check cloud/web/dashboard.js
```

Bez `ASTRO_TEST_POSTGRES=1` se přeskočí pouze PostgreSQL integrační testy.
Tyto testy **mažou obsah testovací tabulky** a patří výhradně do izolované testovací DB.
CI je spouští proti dočasnému PostgreSQL 16. Stávající testy repozitáře spouštěj každý
v samostatném Python procesu podle původního `tests.yml` (patch moduly mění globální stav).

S lokálním Dockerem je k dispozici volitelný Compose:

```powershell
$env:ASTRO_LOCAL_PASSWORD = '<pouze-lokalni-testovaci-heslo>'
docker compose -f cloud/compose.yaml up --build
```

Web je na http://localhost:8099. Lokální Compose používá PostgreSQL kontejner s vlastním
volume a vypnutým TLS v izolované Docker síti; v Azure se používá spravovaná DB a TLS.

## Odkazy

- https://learn.microsoft.com/azure/aks/cluster-container-registry-integration
- https://learn.microsoft.com/azure/container-registry/container-registry-quickstart-task-cli
- https://learn.microsoft.com/azure/postgresql/security/security-tls-how-to-connect
- https://api.met.no/doc/locationforecast/FAQ
- https://www.psycopg.org/psycopg3/docs/basic/usage.html
