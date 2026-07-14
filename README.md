# 🛸 Oráculo de Inteligencia — Threat Intelligence OSINT Platform

**Sistema avanzado de inteligencia de amenazas que combina OSINT, dorking automatizado, scraping multi-fuente y extracción de credenciales.**

[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.1-green)](https://flask.palletsprojects.com)
[![License](https://img.shields.io/badge/License-MIT-purple)](LICENSE)
[![Telethon](https://img.shields.io/badge/Telethon-1.34-red)](https://docs.telethon.dev)

---

## 📋 Tabla de Contenidos

- [Arquitectura](#-arquitectura)
- [Características](#-características)
- [Instalación Rápida](#-instalación-rápida)
- [Configuración](#-configuración)
- [Uso](#-uso)
  - [API Server (Web)](#-api-server-web)
  - [Desktop App](#-desktop-app)
  - [CLI (Terminal)](#-cli-terminal)
- [Combo Intelligence Engine](#-combo-intelligence-engine)
  - [Formatos Soportados](#formatos-soportados)
  - [Patrones Regex](#patrones-regex)
  - [Pipeline de Extracción](#pipeline-de-extracción)
- [Módulos](#-módulos)
- [APIs Externas](#-apis-externas)
- [Despliegue](#-despliegue)
- [Documentación Adicional](#-documentación-adicional)
- [Solución de Problemas](#-solución-de-problemas)
- [Notas Éticas y Legales](#-notas-éticas-y-legales)

---

## 🏗️ Arquitectura

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        ORÁCULO DE INTELIGENCIA                            │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ API REST │  │ Desktop  │  │   CLI    │  │Telegram  │  │WebSocket │  │
│  │ (Flask)  │  │ (PyQt6)  │  │ (Terminal)│  │(Telethon)│  │(SocketIO)│  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │              │             │             │              │        │
│       └──────────────┴─────────────┴─────────────┴──────────────┘        │
│                              │                                            │
│              ┌───────────────┼───────────────┐                           │
│              ▼               ▼               ▼                            │
│  ┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐              │
│  │  Oracle Engine    │ │ Dump Finder  │ │Combo Intelligence│              │
│  │  · Dorking (44+)  │ │ · 44+ dorks  │ │· 7 regex patterns│              │
│  │  · Pattern Ext.   │ │ · 3 engines  │ │· URL-based       │              │
│  │  · Indexación     │ │ · Cache      │ │· Service:email:pass │           │
│  │  · APIs externas  │ │ · Tor/Deep   │ │· Classic email:pass│            │
│  └────────┬─────────┘ └──────┬───────┘ │· Validación SMTP  │              │
│           │                  │         └──────────────────┘               │
│           │                  │                 │                          │
│           └──────────────────┼─────────────────┘                          │
│                              ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                    Proxy Engine (30+ fuentes)                      │    │
│  │  · HTTP/HTTPS/SOCKS4/SOCKS5 · Auto-scrape · Auto-test · Rotación  │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │              Elasticsearch / In-Memory Index                       │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Características

| Módulo | Descripción |
|--------|-------------|
| **🔍 OSINT Dorking** | Búsqueda automatizada en Google, Bing y DuckDuckGo con 44+ dorks |
| **🗄️ Dump Finder** | Encuentra bases de datos filtradas con email:pass |
| **🔐 Combo Intelligence** | Scraping multi-fuente con **7 patrones regex** para extracción de credenciales |
| **🌐 URL-based Combos** | Captura `http://servicio:email:password`, `http://servicio/path:email:password`, `dominio:email:password` |
| **💬 Telegram Scraper** | Integración con Telethon para 13+ canales de credenciales |
| **🌐 Proxy Engine** | Scraping automático de 30+ fuentes de proxies gratuitos |
| **🔌 APIs Externas** | Shodan, Hunter.io, HaveIBeenPwned, VirusTotal, Censys |
| **🖥️ Desktop App** | Interfaz gráfica completa con PyQt6 (6 pestañas) |
| **📊 Dashboard Web** | Interfaz web con estadísticas en tiempo real |
| **💾 Exportación** | TXT, CSV, JSON de todos los datos |
| **🧅 Tor Support** | Enrutamiento a través de Tor para deep web |
| **🗄️ Elasticsearch** | Indexación opcional con fallback en memoria |
| **📦 Cache Inteligente** | Resultados cacheados por 1 hora con TTL |

---

## 🚀 Instalación Rápida

### Prerrequisitos

- Python 3.10+
- Pip
- Git (opcional)

### 1. Clonar / Descargar

```bash
git clone https://github.com/tu-usuario/oraculo-inteligencia.git
cd oraculo-inteligencia
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
nano .env   # Editar con tus API keys
```

### 4. Iniciar

**API Web (recomendado):**
```bash
python run.py
# Abrir: http://localhost:8080
```

**Desktop App:**
```bash
pip install PyQt6   # Solo si no está instalado
python run.py --desktop
```

---

## ⚙️ Configuración

### Variables de Entorno (`.env`)

| Variable | Descripción | Obligatorio |
|----------|-------------|:-----------:|
| `PORT` | Puerto del servidor (default: 8080) | No |
| `SECRET_KEY` | Clave secreta de Flask | No |
| `SAMPLE_DATA` | Usar datos de muestra si no hay APIs (`true`/`false`) | No |
| `SHODAN_API_KEY` | API key de Shodan | No* |
| `HUNTER_API_KEY` | API key de Hunter.io | No* |
| `VT_API_KEY` | API key de VirusTotal | No* |
| `HIBP_API_KEY` | API key de HaveIBeenPwned | No* |
| `CENSYS_TOKEN` | API token de Censys | No* |
| `TG_API_ID` | API ID de Telegram ([my.telegram.org](https://my.telegram.org/apps)) | No |
| `TG_API_HASH` | API Hash de Telegram | No |
| `TG_SESSION` | Nombre del archivo de sesión Telethon | No |
| `DISCORD_TOKEN` | Token de bot de Discord (opcional) | No |
| `TOR_PROXY` | Proxy Tor (`socks5h://127.0.0.1:9050`) | No |
| `USE_TOR` | Usar Tor para todas las requests (`true`/`false`) | No |
| `ES_HOSTS` | Hosts de Elasticsearch | No |
| `COMBO_PROXIES` | Lista de proxies separados por coma | No |

*\*El sistema funciona sin APIs externas, pero con funcionalidad limitada.*

---

## 🎮 Uso

### 🌐 API Server (Web)

```bash
python run.py
# Abrir: http://localhost:8080
```

**Endpoints principales:**

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `POST` | `/api/search` | Búsqueda OSINT multi-fuente + DumpFinder |
| `GET` | `/api/stats` | Estadísticas del sistema |
| `POST` | `/api/dump/search` | Búsqueda de dumps filtrados con cache |
| `GET` | `/api/dump/export` | Exportar todos los combos (TXT/CSV/JSON) |
| `POST` | `/api/combo/leech` | Extracción multi-fuente de combos |
| `POST` | `/api/telegram/search` | Búsqueda en Telegram vía Telethon |
| `POST` | `/api/proxy/scrape` | Scraping de proxies (30+ fuentes) |
| `POST` | `/api/proxy/test` | Testear proxies del pool |
| `POST` | `/api/proxy/autopopulate` | Auto-poblar pool (scrape + test) |
| `GET` | `/api/apis/status` | Estado de APIs externas configuradas |
| `GET` | `/api/ping` | Healthcheck ultraligero |
| `POST` | `/api/chat` | Asistente IA del Oráculo |

### 🖥️ Desktop App

```bash
python run.py --desktop
```

La aplicación de escritorio con PyQt6 incluye **6 pestañas**:

| Pestaña | Funcionalidad |
|---------|---------------|
| **🔍 Búsqueda** | OSINT multi-fuente con resultados en tabla |
| **🗄️ Dumps** | DumpFinder con filtros de fecha y KPIs |
| **🔐 Combo** | Combo leecher multi-fuente con validación SMTP |
| **💬 Telegram** | Scraping de canales vía Telethon |
| **🌐 Proxies** | Pool manager con scrape + test automático |
| **📊 Stats** | Estado de todos los motores y APIs |

### 💻 CLI (Terminal)

```bash
# Búsqueda OSINT
python run.py --search "comcast"

# Dump Finder con filtros
python run.py --dump "comcast" --year 2024
python run.py --dump "netflix" --year 2023 --month 6

# Combo Leecher
python run.py --leech "netflix"

# Telegram
python run.py --telegram-login       # Login interactivo
python run.py --telegram-search "comcast"  # Buscar combos

# Proxies
python run.py --proxy-scrape          # Scrape 30+ fuentes
python run.py --proxy-test            # Testear proxies

# Verificar APIs configuradas
python run.py --check-apis
```

---

## 🔐 Combo Intelligence Engine

### Formatos Soportados

El motor de parsing de credenciales soporta **7 formatos diferentes** de combos, incluyendo los formatos URL-based que usan herramientas como Joker Combo Leecher y Hacku Dumper:

| # | Formato | Ejemplo | Origen |
|---|---------|---------|--------|
| 1 | **Classic email:pass** | `admin@comcast.net:Welcome2024!` | Pastebins, dumps |
| 2 | **URL-based email:pass** | `http://business.comcast.com:slcbiomed@mccmed.com:Mustang` | Dumps especializados |
| 3 | **URL-with-path email:pass** | `http://business.comcast.com/account/reset:user@email.com:pass` | Dumps con rutas |
| 4 | **URL-based user:pass** | `http://service.tld:username:password` | Dumps sin email |
| 5 | **Service:email:pass** (sin http) | `comcast.net:bob@yahoo.com:Summer2024!` | Dumps compactos |
| 6 | **JSON combo** | `{"email":"user@domain.com","password":"pass123"}` | APIs |
| 7 | **CSV pipe-separated** | `user@domain.com \| password` | Archivos CSV |

### Patrones Regex

```python
# PATTERN 1: Clásico email:password
r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*[:;|]\s*(\S+)'

# PATTERN 2: URL-based (ej: http://service.tld:email:pass)
r'(https?://[^\s:]+(?:/[^:]*)?):([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}):(\S+)'

# PATTERN 3: URL-based user (ej: http://service.tld:user:pass)
r'(https?://[^\s:]+(?:/[^:]*)?):([a-zA-Z0-9._-]{4,50}):(\S{4,})'

# PATTERN 4: Username:password
r'^([a-zA-Z0-9._-]{4,})\s*[:;|]\s*(\S+)'

# PATTERN 5: JSON format
r'"(?:email|user|username|mail|login)"\s*:\s*"([^"]+)"\s*,\s*"(?:pass|password|passwd|pwd)"\s*:\s*"([^"]+)"'

# PATTERN 6: CSV pipe
r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*[|]\s*(\S+)'

# PATTERN 7: Service:email:pass (sin http)
r'^([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}):([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}):(\S+)$'
```

### Pipeline de Extracción

```
Texto plano (de pastebin, Telegram, foros, etc.)
          │
          ▼
┌─────────────────────────────────┐
│ 1. PATTERN_URL_COMBO             │  ← Prioridad máxima
│    http://service:email:pass     │
└──────────────┬──────────────────┘
               │ (service_url extraído en extra_data)
               ▼
┌─────────────────────────────────┐
│ 2. PATTERN_SERVICE_COMBO        │  ← Sin prefijo http
│    service.tld:email:pass       │
└──────────────┬──────────────────┘
               │ (service_url = http://service.tld)
               ▼
┌─────────────────────────────────┐
│ 3. PATTERN_EMAIL_PASS (clásico) │  ← Con dedup contra seen
│    email:password               │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│ 4. PATTERN_JSON_COMBO           │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│ 5. PATTERN_USER_PASS            │  ← Solo si keyword coincide
│    (con validación anti-noise)  │
└──────────────┬──────────────────┘
               │
               ▼
     ┌───────────────────┐
     │ Deduplicación      │
     │ Filtro anti-ruido  │
     │ (://, /, : en email)│
     └───────────────────┘
               │
               ▼
     Lista de ComboEntry objetos
     con: email, password, domain,
          service_url, source_type, date
```

### Prioridad de Parsing

1. **URL-based primero** → Los formatos URL se procesan **antes** que los clásicos
2. **Service:email:pass** segundo
3. **Classic email:pass** tercero → detecta duplicados del paso 1 y 2
4. **Validación estricta** → Rechaza si email contiene `://`, `/`, o `:` (anti-noise)
5. **Filtro de passwords comunes** → Rechaza `123456`, `password`, etc.

### Ejemplo de Resultado

```python
ComboEntry(
    email="slcbiomed@mccmed.com",
    password="Mustang",
    domain="mccmed.com",
    source_url="https://pastebin.com/raw/ABC123",
    source_type="pastebin",
    record_type="email:pass",
    extra_data={"service_url": "http://business.comcast.com"},  # ← URL tracking
)
```

---

## 📦 Módulos

| Archivo | Descripción | Dependencias |
|---------|-------------|--------------|
| `api.py` | Servidor Flask con WebSocket + 30+ endpoints | Flask, SocketIO |
| `oracle_engine.py` | Motor OSINT con dorking automatizado | requests, bs4 |
| `dump_finder.py` | Buscador de dumps con cache, Tor, 44+ dorks | requests, bs4 |
| `combo_leecher_engine.py` | **ComboParser + ComboValidator + Scrapers multi-fuente** | requests, bs4, dnspython |
| `intel_connectors.py` | Conectores: Shodan, Hunter, HIBP, VT, Censys | requests |
| `proxy_engine.py` | Pool + Scraper de 30+ fuentes de proxies | requests, bs4 |
| `elastic_index.py` | Backend Elasticsearch | elasticsearch-py |
| `telegram_scraper.py` | Scraping Telethon con 13 canales preconfigurados | telethon |
| `desktop_app.py` | Aplicación de escritorio PyQt6 (6 pestañas) | PyQt6 |
| `run.py` | Lanzador unificado (API/Desktop/CLI) | — |
| `local_keys.py` | Gestión de API keys desde `.env` | python-dotenv |

---

## 🔌 APIs Externas

| API | Funcionalidad | Cómo obtenerla |
|-----|---------------|----------------|
| **Shodan** | Búsqueda de servicios expuestos | [shodan.io](https://account.shodan.io/) |
| **Hunter.io** | Descubrimiento de emails por dominio | [hunter.io](https://hunter.io/api-keys) |
| **HaveIBeenPwned** | Brechas de datos verificadas | [hibp](https://haveibeenpwned.com/API/Key) (pago) |
| **VirusTotal** | Análisis de amenazas en dominios/IPs | [virustotal.com](https://www.virustotal.com/gui/my-apikey) |
| **Censys** | Descubrimiento de dispositivos | [censys.io](https://search.censys.io/account/api) |
| **Telegram** | Scraping de canales de credenciales | [my.telegram.org](https://my.telegram.org/apps) |

---

## 🚢 Despliegue

### Render (recomendado — 24/7 gratis)

1. Crear cuenta en [render.com](https://render.com)
2. Conectar repositorio de GitHub
3. Usar **Blueprint** → Render detecta `render.yaml` automáticamente
4. Configurar variables de entorno en el dashboard
5. Healthcheck: `/api/ping`

### Railway

```bash
# railway.json ya incluido
railway up
```

### Docker

```bash
docker build -t oraculo-inteligencia .
docker run -p 8080:8080 oraculo-inteligencia
```

### UptimeRobot (evitar sleep en free tier)

Configurar monitor HTTP cada 5 minutos a `/api/ping`

---

## 📚 Documentación Adicional

| Documento | Descripción |
|-----------|-------------|
| [`COMBO_PARSER.md`](./COMBO_PARSER.md) | Documentación técnica del motor de parsing de combos |
| [`DUMPFINDER_MANUAL.md`](./DUMPFINDER_MANUAL.md) | Manual completo del buscador de dumps |
| [`JOKER_COMBO_LEECHER_ANALISIS.md`](./JOKER_COMBO_LEECHER_ANALISIS.md) | Análisis comparativo con otros sistemas |
| [`DEVELOPMENT.md`](./DEVELOPMENT.md) | Guía para desarrolladores |

---

## 🔧 Solución de Problemas

### Error: "No module named 'PyQt6'"
```bash
pip install PyQt6
```

### Error: "Telegram no configurado"
```bash
# 1. Obtener credenciales en https://my.telegram.org/apps
# 2. Configurar en .env:
TG_API_ID=tu_api_id
TG_API_HASH=tu_api_hash
# 3. Login:
python run.py --telegram-login
```

### Error: "No se encuentran proxies"
```bash
python run.py --proxy-scrape
# O configurar manualmente:
COMBO_PROXIES=http://proxy1:port,http://proxy2:port
```

### Error: "502 Bad Gateway"
Aumentar timeout del servidor:
```bash
gunicorn api:app --timeout 120
```

### Error: Dataset está devolviendo datos de muestra
```bash
# En el dashboard, desmarcar "Datos de muestra"
# O en la API:
POST /api/search {"keyword": "comcast", "sample": false}
```

### Error: Los combos URL-based no se capturan
Verificar que estás usando el `ComboParser` actualizado (v2.0+):
```python
from combo_leecher_engine import ComboParser
parser = ComboParser()
combos = parser.parse_text(text, source_type="test")
# Los combos URL-based tienen extra_data["service_url"]
```

---

## 📝 Notas Éticas y Legales

**Oráculo de Inteligencia** es una herramienta de **Threat Intelligence y auditoría de seguridad**. Está diseñada para:

- ✅ **Investigadores de seguridad** que verifican exposiciones de datos
- ✅ **Equipos de respuesta a incidentes** que buscan credenciales filtradas
- ✅ **Investigación académica** sobre filtraciones de datos
- ✅ **Auditorías de seguridad autorizadas**

**NO debe usarse para:**
- ❌ Acceder a cuentas sin autorización
- ❌ Comercializar datos filtrados
- ❌ Cualquier actividad ilegal

**Todos los datos extraídos son de fuentes públicas.** No se realiza hacking, cracking ni acceso no autorizado a sistemas.

---

## 🛠️ Stack Tecnológico

| Componente | Tecnología | Versión |
|------------|------------|:-------:|
| Backend | Python + Flask | 3.12 / 3.1 |
| WebSocket | Flask-SocketIO + Eventlet | 5.3 |
| Desktop | PyQt6 / PySide6 | 6.11 |
| Cliente Telegram | Telethon | 1.34+ |
| Parsing | Regex (7 patrones) + BeautifulSoup | — |
| Búsqueda | Google, Bing, DuckDuckGo | — |
| Indexación | Elasticsearch / In-Memory | — |
| Proxy | HTTP/HTTPS/SOCKS4/SOCKS5 | 30+ fuentes |
| DB | SQLite (caché) / ES | — |
| Deploy | Render, Railway, Docker | — |

---

*Construido con 🛸 Freebuff AI · Julio 2026*
