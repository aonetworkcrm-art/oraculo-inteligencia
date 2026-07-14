# 🗄️ DumpFinder — Manual Completo del Buscador de Bases de Datos Filtradas

**Versión:** 2.0  
**Sistema:** Oráculo de Inteligencia — Threat Intelligence OSINT  
**Inspirado en:** Joker Combo Leecher v1.0, Hacku Dumper  
**Propósito:** Buscar, extraer y organizar combinaciones email:contraseña desde fuentes públicas expuestas en internet.

---

## 📑 Índice

1. [¿Qué es DumpFinder?](#-qué-es-dumpfinder)
2. [Arquitectura del Sistema](#-arquitectura-del-sistema)
3. [Pipeline de Búsqueda](#-pipeline-de-búsqueda)
4. [Endpoints de la API](#-endpoints-de-la-api)
5. [Modo Rápido con Cache](#-modo-rápido-con-cache)
6. [Dorks y Fuentes de Datos](#-dorks-y-fuentes-de-datos)
7. [Estructura de Archivos](#-estructura-de-archivos)
8. [Tor y Deep Web](#-tor-y-deep-web)
9. [Cómo Usar](#-cómo-usar)
10. [Solución de Problemas](#-solución-de-problemas)

---

## 🎯 ¿Qué es DumpFinder?

**DumpFinder** es el motor de búsqueda de bases de datos filtradas dentro del Oráculo de Inteligencia. Dada una **palabra clave** (ej: "comcast", "netflix", "verizon"), el sistema:

1. 🔍 **Busca URLs** que contengan dumps de credenciales usando dorking automatizado
2. 📥 **Descarga el contenido** de esas URLs
3. 🔐 **Extrae combinaciones email:contraseña** usando un parser inteligente
4. 📅 **Filtra por fecha** (año, mes, rango personalizado)
5. 💾 **Guarda los resultados** en carpetas organizadas
6. 📦 **Cachea los resultados** en disco para acceso instantáneo en búsquedas repetidas

### ¿Para qué sirve?

- **Auditoría de seguridad:** Verificar si credenciales de un dominio han sido expuestas
- **Threat Intelligence:** Monitorear filtraciones de datos de forma ética
- **Investigación OSINT:** Recopilar información de fuentes públicas

---

## 🏗️ Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                     DUMP FINDER ENGINE                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌────────────────┐    ┌──────────────┐  │
│  │  DorkEngine   │    │ PasteDirect    │    │   URLFetcher  │  │
│  │  · DuckDuckGo │    │ Scraper        │    │  · Stealth    │  │
│  │  · Google     │    │  · Pastebin    │    │  · Retry      │  │
│  │  · Bing       │    │  · Rentry      │    │  · Tor proxy  │  │
│  │  · 44+ dorks  │    │  · Ghostbin    │    │  · Rotación UA│  │
│  └──────┬───────┘    └───────┬────────┘    └───────┬──────┘  │
│         │                    │                      │         │
│         └────────────────────┼──────────────────────┘         │
│                              ▼                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                    ComboParser                             │ │
│  │  Extrae email:password de texto plano con regex           │ │
│  └────────────────────────┬─────────────────────────────────┘ │
│                           ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                    DateFilter                              │ │
│  │  Filtra por año (2023, 2024...) y mes (1-12)             │ │
│  └────────────────────────┬─────────────────────────────────┘ │
│                           ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                    LocalSaver / DiskCache                   │ │
│  │  · Guarda en data/{keyword}/{año}/{mes}/                  │ │
│  │  · Cachea en data/.dump_cache/{md5}.json                  │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │               Hunter.io Connector (fallback)               │ │
│  │  Si el dorking no encuentra nada, busca emails reales     │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Componentes Principales

| Componente | Archivo | Descripción |
|---|---|---|
| `DumpFinder` | `dump_finder.py` | Motor principal — orquesta todo el pipeline |
| `DorkEngine` | `dump_finder.py` | Ejecuta dorks contra buscadores con stealth |
| `PasteDirectScraper` | `dump_finder.py` | Scrapea paste sites directamente (sin Google) |
| `URLFetcher` | `dump_finder.py` | Descarga contenido de URLs con proxy rotation |
| `ComboParser` | `combo_leecher_engine.py` | Extrae email:pass de texto plano |
| `DateFilter` | `dump_finder.py` | Filtra combos por fecha |
| `LocalSaver` | `dump_finder.py` | Guarda resultados en disco |
| `DiskCache` | `dump_finder.py` | Cachea resultados de búsqueda (TTL 1 hora) |
| `API Endpoints` | `api.py` | Interfaz REST para el dashboard |

---

## 🔄 Pipeline de Búsqueda

### Búsqueda Normal (15 dorks, 3 buscadores)

```
1. Seleccionar 15 dorks aleatorios de 44+ disponibles
2. Para cada dork:
   a. DuckDuckGo (intento #1, ~3s)
   b. Google (intento #2 si DDG no dio resultados, ~8s)
   c. Bing (intento #3 si Google no dio resultados, ~5s)
3. Scrapear paste sites (Pastebin, Rentry, Ghostbin, etc.)
4. Descargar contenido de URLs encontradas
5. Extraer email:pass con ComboParser
6. Filtrar por fecha (año, mes, rango)
7. Guardar en disco
8. Cachear resultado

Tiempo estimado: ~77 segundos
```

### Búsqueda Rápida (5 dorks, solo DuckDuckGo)

```
1. ¿Resultado en cache? → Devolver instantáneo (0.01s)
2. Si no:
   a. 5 dorks solo DuckDuckGo (~15s)
   b. Scrapear paste sites (~3s)
   c. Descargar URLs, extraer, filtrar, guardar
3. Cachear resultado

Tiempo estimado: ~15-20 segundos
```

---

## 📡 Endpoints de la API

### Endpoints del DumpFinder

| Método | Endpoint | Descripción | Timeout |
|---|---|---|---|
| `POST` | `/api/dump/search` | Búsqueda con fast-mode + cache | 30s |
| `GET` | `/api/dump/export` | Exportar todos los combos filtrados | 30s |
| `POST` | `/api/dump/cron` | Pre-calentar cache en background | 45s |
| `GET` | `/api/dump/cache` | Listar keywords cacheados | 2s |
| `POST` | `/api/dump/cache/clear` | Limpiar cache | 2s |

### `/api/dump/search` — Búsqueda

```http
POST /api/dump/search
Content-Type: application/json

{
  "keyword": "comcast",
  "year": 2023,
  "month": null,
  "date_from": null,
  "date_to": null,
  "save_to_disk": true
}
```

**Respuesta:**
```json
{
  "success": true,
  "data": {
    "keyword": "comcast",
    "took_seconds": 15.24,
    "dorks_executed": 5,
    "urls_found": 12,
    "urls_fetched": 12,
    "combos_found": 245,
    "filtered_combos_count": 245,
    "top_urls": [...],
    "combos_sample": [...],  // Solo primeros 50
    "stats": {
      "by_source": {"pastebin": 120, "github": 85, "shodan": 40},
      "by_domain": {"comcast.net": 150, "xfinity.com": 95},
      "by_type": {"email:pass": 200, "hash": 45}
    },
    "files_saved": {
      "files_created": ["data/comcast/2026/07/comcast_20260714_full_dump.txt"],
      "total_saved": 245
    },
    "_from_cache": false
  }
}
```

### `/api/dump/export` — Exportar Todo

```http
GET /api/dump/export?keyword=comcast&fmt=txt&year=2023
GET /api/dump/export?keyword=comcast&fmt=csv&year=2023&month=6
GET /api/dump/export?keyword=comcast&fmt=json
```

**Formatos:**
| Formato | MIME | Descripción |
|---|---|---|
| `txt` | `text/plain` | `email:password  #dominio | fuente | fecha` |
| `csv` | `text/csv` | `email,password,dominio,fuente,fecha` |
| `json` | `application/json` | Objeto JSON con stats + combos |

**Ejemplo TXT:**
```
# DumpFinder Export - comcast
# Generated: 2026-07-14 03:32:05
# Total combos: 245
# Export format: email:password

user1234@comcast.net:password123  #comcast.net | pastebin | 2026-06-15
user5678@xfinity.com:qwerty2024   #xfinity.com | github | 2026-07-01
```

### `/api/dump/cron` — Pre-calentar Cache

```http
POST /api/dump/cron
Content-Type: application/json

{"keyword": "comcast"}

# O sin keyword (pre-carga 3 keywords predefinidas):
POST /api/dump/cron
```

**Respuesta:**
```json
{
  "success": true,
  "data": {
    "keyword": "comcast",
    "combos": 245,
    "took_seconds": 15.24,
    "from_cache": false
  }
}
```

---

## ⚡ Modo Rápido con Cache

### ¿Cómo funciona?

1. **Primera búsqueda** (cache miss): Ejecuta 5 dorks solo DuckDuckGo, tarda ~15s. Guarda resultado en `data/.dump_cache/{md5}.json`
2. **Búsquedas subsiguientes** (cache hit): Devuelve resultado instantáneamente (0.01s)
3. **TTL**: 1 hora (3600 segundos). Después de 1 hora expira y se ejecuta búsqueda fresca
4. **Exportación**: El cache guarda la lista COMPLETA de combos (no solo 50 de muestra) para que la exportación funcione desde cache

### DiskCache

```python
Cache structure:
  data/.dump_cache/
    ├── a1b2c3d4e5f6...json  # Cache para "comcast"
    ├── f6e5d4c3b2a1...json  # Cache para "xfinity"
    └── ...

Cada archivo contiene:
{
  "keyword": "comcast",
  "_cached_at": 1723214567.89,  # timestamp UNIX
  "_from_cache": true,
  "_cached_combos": [            # Lista completa de combos
    {"email": "...", "password": "...", "domain": "...", "source": "...", "date": "..."}
  ],
  "filtered_combos_count": 245,
  "took_seconds": 15.24,
  "stats": {...},
  "files_saved": {...}
}
```

---

## 🔍 Dorks y Fuentes de Datos

### 44+ Dorks Organizados por Categoría

| Categoría | Cantidad | Ejemplo |
|---|---|---|
| Paste sites | 10 | `site:pastebin.com "comcast" "email:pass"` |
| File types | 8 | `filetype:txt "comcast" "email" "password"` |
| Index of | 3 | `intitle:"index of" "comcast" "credentials"` |
| Combo-specific | 4 | `"comcast combo" "email:pass"` |
| Telegram | 2 | `site:t.me "comcast" "combo"` |
| Forums | 4 | `site:nulled.to "comcast" "leak"` |
| GitHub | 2 | `site:github.com "comcast" "password"` |
| Discord | 2 | `site:discord.com/channels "comcast" "combo"` |
| Deep web (.onion) | 6 | `inurl:"comcast" ".onion" "email"` |
| Deep web (.i2p) | 2 | `"comcast" ".i2p" "password"` |
| Hidden services | 2 | `"comcast" "hidden" "email:pass"` |

### Fuentes de Scraping Directo

| Fuente | Método |
|---|---|
| Pastebin | DuckDuckGo → raw URL extraction |
| Rentry.co | DuckDuckGo search |
| Ghostbin.co | DuckDuckGo search |
| Archive.is | Búsqueda directa en archivo |
| Cachedview.nl | Búsqueda en caché |

### Motores de Búsqueda

| Motor | Modo Normal | Modo Rápido |
|---|---|---|
| DuckDuckGo | ✅ Siempre | ✅ Siempre |
| Google | ✅ Fallback | ❌ Skip |
| Bing | ✅ Fallback | ❌ Skip |

---

## 📁 Estructura de Archivos

```
oraculo-inteligencia/
├── api.py                    # Flask API con endpoints
├── dump_finder.py            # Motor DumpFinder completo
├── combo_leecher_engine.py   # ComboParser, ComboEntry, ProxyManager
├── intel_connectors.py       # HunterConnector y otras APIs
├── data/                     # Datos guardados (creado por DumpFinder)
│   ├── comcast/
│   │   ├── 2026/
│   │   │   ├── 06/
│   │   │   │   └── comcast_20260615.txt
│   │   │   └── 07/
│   │   │       └── comcast_20260714_full_dump.txt
│   │   └── .../
│   ├── xfinity/
│   │   └── ...
│   └── .dump_cache/          # Cache de resultados (TTL 1 hora)
│       ├── a1b2c3d4...json
│       └── ...
└── static/
    ├── index.html            # Dashboard web
    └── app.js                # Aplicación frontend
```

---

## 🧅 Tor y Deep Web

DumpFinder soporta búsqueda en la **deep web** a través de la red Tor.

### Configuración

1. Instalar Tor Browser o el servicio Tor: `apt install tor`
2. El proxy Tor corre en `socks5h://127.0.0.1:9050` (por defecto)
3. Configurar variable de entorno: `TOR_PROXY=socks5h://127.0.0.1:9050`

### Dorks .onion

```
onion_paste:  site:pastebin.com "comcast" ".onion" ("combo" OR "leak")
onion_creds:  inurl:"comcast" ".onion" ("email" OR "password")
onion_dump:   filetype:txt "comcast" ".onion" ("dump" OR "leak")
onion_db:     "comcast" ".onion" ("database" OR "sql" OR "dump")
onion_breach: "comcast" ".onion" ("breach" OR "leak" OR "compromised")
```

### Dorks .i2p

```
i2p_sites: inurl:"comcast" ".i2p" ("forum" OR "market" OR "creds")
i2p_creds: "comcast" ".i2p" ("password" OR "credentials" OR "dump")
```

### Stealth HTTP Headers

Para evitar detección, todas las requests HTTP usan:

- **User-Agent rotativo**: 8 UAs diferentes (Chrome, Firefox, Edge)
- **Referer rotativo**: 7 referers diferentes (Google, Yahoo, Bing, etc.)
- **Accept-Language**: Español e Inglés
- **Sec-Fetch-***: Headers de seguridad modernos
- **DNT**: Do Not Track = 1
- **Cache-Control**: max-age=0

---

## 🚀 Cómo Usar

### Desde el Dashboard Web

1. Navegar a `https://oraculo-inteligencia.onrender.com`
2. Click en **🗄️ Dump Finder** en el sidebar
3. Ingresar palabra clave (ej: "comcast")
4. Seleccionar año/mes (opcional)
5. Click **🗄️ Buscar Dumps**
6. Ver resultados: KPIs, URLs encontradas, tabla de combos
7. Exportar: **📥 Exportar Todo** (TXT con timestamp) o TXT/CSV/JSON

### Desde la API (curl)

```bash
# Búsqueda
curl -X POST https://oraculo-inteligencia.onrender.com/api/dump/search \
  -H "Content-Type: application/json" \
  -d '{"keyword":"comcast","year":2023,"save_to_disk":true}'

# Exportar todo a TXT
curl -o comcast_2023.txt \
  "https://oraculo-inteligencia.onrender.com/api/dump/export?keyword=comcast&fmt=txt&year=2023"

# Exportar a CSV
curl -o comcast_2023.csv \
  "https://oraculo-inteligencia.onrender.com/api/dump/export?keyword=comcast&fmt=csv&year=2023"

# Pre-calentar cache
curl -X POST https://oraculo-inteligencia.onrender.com/api/dump/cron \
  -H "Content-Type: application/json" \
  -d '{"keyword":"comcast"}'

# Ver cache
curl https://oraculo-inteligencia.onrender.com/api/dump/cache
```

### Con UptimeRobot (mantener activo 24/7)

Configurar un monitor HTTP en UptimeRobot que llame cada 10 minutos a:
```
https://oraculo-inteligencia.onrender.com/api/ping
```

Y un cron job cada 30 minutos para pre-calentar cache:
```
POST https://oraculo-inteligencia.onrender.com/api/dump/cron
```

---

## 🔧 Solución de Problemas

### 502 Bad Gateway en Export

**Causa:** Render free tier corta requests >30 segundos. El export sin cache puede tardar 77s+.

**Soluciones:**
1. ✅ Usar el modo rápido (cache + solo DuckDuckGo) — ya implementado
2. ✅ Pre-calentar cache con cron job — usar `/api/dump/cron`
3. Después del primer cache, el export es instantáneo

### "DumpFinder not available"

**Causa:** El DumpFinder no se inicializó correctamente (timeout de 12s).

**Solución:** Revisar logs del servidor. Verificar que `combo_leecher_engine.py` y dependencias estén instaladas.

### Búsqueda sin resultados

**Causa:** Desde IPs cloud (Render), DuckDuckGo puede devolver resultados limitados.

**Sugerencias:**
1. Probar con keywords más específicas
2. Usar proxies residenciales (configurar ProxyManager)
3. Ejecutar localmente con Tor para mejor anonimato

### Cache no funciona

**Causa:** El directorio `data/.dump_cache/` puede no ser persistente en Render free.

**Solución:** Si Render reinicia el servicio, el cache se pierde. Usar cron job para recargar.

---

## 📊 Estadísticas

| Métrica | Valor |
|---|---|
| Dorks disponibles | 44+ |
| Motores de búsqueda | 3 (DDG, Google, Bing) |
| Categorías de dorks | 10 |
| Stealth User-Agents | 8 |
| Referers rotativos | 7 |
| Tiempo modo normal | ~77s |
| Tiempo modo rápido | ~15s |
| Cache TTL | 1 hora |
| Export formatos | TXT, CSV, JSON |

---

## 📝 Notas Legales y Éticas

DumpFinder es una **herramienta de Threat Intelligence y auditoría de seguridad**. Está diseñada para:

- ✅ **Investigadores de seguridad** que necesitan verificar exposiciones de datos
- ✅ **Equipos de respuesta a incidentes** que buscan credenciales filtradas de su organización
- ✅ **Investigación académica** sobre filtraciones de datos

**NO debe usarse para:**
- ❌ Acceder a cuentas sin autorización
- ❌ Comercializar datos filtrados
- ❌ Cualquier actividad ilegal

---

*DumpFinder v2.0 — Parte del Oráculo de Inteligencia 🔮*
*Construido con Freebuff AI · Julio 2026*
