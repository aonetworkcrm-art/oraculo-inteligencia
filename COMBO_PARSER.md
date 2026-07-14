# 🔐 Combo Intelligence Engine — Documentación Técnica

**Versión:** 2.0  \
**Sistema:** Oráculo de Inteligencia — Threat Intelligence OSINT  \
**Archivo:** `combo_leecher_engine.py`  \
**Inspirado en:** Joker Combo Leecher, Hacku Dumper — pero 100% open source

---

## 📑 Índice

1. [Visión General](#-visión-general)
2. [Arquitectura](#-arquitectura)
3. [ComboParser — 7 Patrones Regex](#-comboparser--7-patrones-regex)
   - [Patrón 1: Email:Password Clásico](#patrón-1-emailpassword-clásico)
   - [Patrón 2: URL-based email:pass](#patrón-2-url-based-emailpass)
   - [Patrón 3: URL-based user:pass](#patrón-3-url-based-userpass)
   - [Patrón 4: Username:Password](#patrón-4-usernamepassword)
   - [Patrón 5: JSON Combo](#patrón-5-json-combo)
   - [Patrón 6: CSV Pipe](#patrón-6-csv-pipe)
   - [Patrón 7: Service:email:pass (sin http)](#patrón-7-serviceemailpass-sin-http)
4. [Pipeline de Extracción](#-pipeline-de-extracción)
5. [Data Models](#-data-models)
6. [Validación de Combos](#-validación-de-combos)
7. [Scrapers Multi-Fuente](#-scrapers-multi-fuente)
8. [API Endpoints](#-api-endpoints)
9. [Ejemplos de Uso](#-ejemplos-de-uso)
10. [Pruebas](#-pruebas)

---

## 🎯 Visión General

El **Combo Intelligence Engine** es el módulo de extracción y validación de credenciales del Oráculo de Inteligencia. Está diseñado para:

1. **Extraer** combinaciones email:password de texto plano (pastebins, Telegram, foros)
2. **Soportar múltiples formatos** incluyendo URL-based (`http://servicio:email:pass`)
3. **Validar** si las credenciales son reales (SMTP/HTTP/IMAP)
4. **Indexar** los resultados en el motor de búsqueda
5. **Exportar** en TXT, CSV, JSON

### ¿Por qué 7 patrones?

Los dumps de credenciales en la vida real vienen en MÚLTIPLES formatos. Herramientas como **Joker Combo Leecher** y **Hacku Dumper** solo capturan `email:password` simple. Nuestro engine captura **7 formatos diferentes**, incluyendo los formatos URL-based que son comunes en dumps especializados.

---

## 🏗️ Arquitectura

```
combo_leecher_engine.py
│
├── 📦 DATA MODELS
│   ├── ComboEntry          → Una credencial individual
│   └── LeechResult         → Resultado de una operación de leech
│
├── 🔧 COMBO PARSER
│   ├── PATTERN_URL_COMBO        → http://service:email:pass
│   ├── PATTERN_SERVICE_COMBO    → service.tld:email:pass
│   ├── PATTERN_EMAIL_PASS       → email:pass (clásico)
│   ├── PATTERN_JSON_COMBO       → {"email":"...", "password":"..."}
│   ├── PATTERN_USER_PASS        → user:pass
│   ├── PATTERN_URL_USER_PASS    → http://service:user:pass
│   └── PATTERN_CSV_COMBO        → email | pass
│
├── 🌐 SOURCE SCRAPERS
│   ├── PasteScraper       → Pastebin, Rentry, Ghostbin, Paste.ee
│   ├── TelegramScraper    → Telegram vía Google dorking
│   ├── DiscordScraper     → Discord vía Google + API
│   └── ForumScraper       → 15+ foros de leaks
│
├── ✅ COMBO VALIDATOR
│   ├── SMTP validation    → Login contra MX reales
│   ├── HTTP validation    → POST a login forms
│   └── IMAP validation    → Login IMAP SSL
│
├── 🚀 MAIN ENGINE
│   └── ComboLeecherEngine → Orquesta scraping + parsing + validación
│
└── 📤 EXPORT
    ├── export_txt()
    ├── export_csv()
    └── export_json()
```

---

## 🔧 ComboParser — 7 Patrones Regex

### Patrón 1: Email:Password Clásico

```python
PATTERN_EMAIL_PASS = re.compile(
    r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*[:;|]\s*(\S+)',
    re.IGNORECASE
)
```

**Captura:** `email:password` — el formato más común en dumps.

| Entrada | email | password |
|---------|-------|----------|
| `admin@comcast.net:Welcome2024!` | `admin@comcast.net` | `Welcome2024!` |
| `user@domain.com;secret123` | `user@domain.com` | `secret123` |
| `test@test.com|mypassword` | `test@test.com` | `mypassword` |

---

### Patrón 2: URL-based email:pass

```python
PATTERN_URL_COMBO = re.compile(
    r'(https?://[^\s:]+(?:/[^:]*)?):([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}):(\S+)',
    re.IGNORECASE
)
```

**Captura:** `http://servicio:email:password` — formato usado por Joker Combo Leecher y Hacku Dumper.

| Entrada | service_url | email | password |
|---------|-------------|-------|----------|
| `http://business.comcast.com:slcbiomed@mccmed.com:Mustang` | `http://business.comcast.com` | `slcbiomed@mccmed.com` | `Mustang` |
| `http://business.comcast.com:darek@zmigrodzki.net:f73hGpem` | `http://business.comcast.com` | `darek@zmigrodzki.net` | `f73hGpem` |
| `http://business.comcast.com/account/password-reset/resetpassword:cincoestrellasbakery@yahoo.com:3541STNmtn!` | `http://business.comcast.com/account/password-reset/resetpassword` | `cincoestrellasbakery@yahoo.com` | `3541STNmtn!` |
| `http://business.comcast.com:shardapaperinc@yahoo.com:Sharda` | `http://business.comcast.com` | `shardapaperinc@yahoo.com` | `Sharda` |

**Características:**
- ✅ Extrae el `service_url` completo en `extra_data`
- ✅ Soporta URLs con path: `http://dominio/path:email:pass`
- ✅ Usa `[^:]*` greedy para eficiencia O(n) en paths largos
- ✅ Prioridad máxima en el pipeline — se ejecuta PRIMERO

---

### Patrón 3: URL-based user:pass

```python
PATTERN_URL_USER_PASS = re.compile(
    r'(https?://[^\s:]+(?:/[^:]*)?):([a-zA-Z0-9._-]{4,50}):(\S{4,})',
    re.IGNORECASE
)
```

**Captura:** `http://servicio:username:password` — cuando el combo no tiene email sino username.

| Entrada | service_url | username | password |
|---------|-------------|----------|----------|
| `http://portal.comcast.com:john_doe:Pass123` | `http://portal.comcast.com` | `john_doe` | `Pass123` |

**⚠️ Validación:** Rechaza usernames puramente numéricos (puertos) para evitar falsos positivos como `http://proxy.com:3128:password123`.

---

### Patrón 4: Username:Password

```python
PATTERN_USER_PASS = re.compile(
    r'^([a-zA-Z0-9._-]{4,})\s*[:;|]\s*(\S+)',
    re.MULTILINE
)
```

**Captura:** `username:password` en líneas individuales.

**⚠️ Solo se activa si el keyword coincide** con el username o password. Además, filtra:
- Passwords que contengan `://` o `/` (anti-noise)
- Passwords < 4 o > 80 caracteres
- Usernames con `://` (URL artifacts)

---

### Patrón 5: JSON Combo

```python
PATTERN_JSON_COMBO = re.compile(
    r'"(?:email|user|username|mail|login)"\s*:\s*"([^"]+)"\s*,\s*"(?:pass|password|passwd|pwd)"\s*:\s*"([^"]+)"',
    re.IGNORECASE
)
```

**Captura:** Formatos JSON con pares email/password.

| Entrada | email | password |
|---------|-------|----------|
| `{"email":"user@domain.com","password":"pass123"}` | `user@domain.com` | `pass123` |
| `{"user":"admin","pass":"secret"}` | `admin` | `secret` |
| `{"login":"test","password":"12345"}` | `test` | `12345` |

---

### Patrón 6: CSV Pipe

```python
PATTERN_CSV_COMBO = re.compile(
    r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*[|]\s*(\S+)',
    re.IGNORECASE
)
```

**Captura:** `email | password` con pipe como separador.

| Entrada | email | password |
|---------|-------|----------|
| `user@domain.com | pass123` | `user@domain.com` | `pass123` |
| `admin@test.com\|secret` | `admin@test.com` | `secret` |

---

### Patrón 7: Service:email:pass (sin http)

```python
PATTERN_SERVICE_COMBO = re.compile(
    r'^([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}):([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}):(\S+)$',
    re.MULTILINE
)
```

**Captura:** `servicio.tld:email:password` — el formato compacto sin prefijo `http://`.

| Entrada | service_url | email | password |
|---------|-------------|-------|----------|
| `comcast.net:bob@yahoo.com:Summer2024!` | `http://comcast.net` | `bob@yahoo.com` | `Summer2024!` |
| `xfinity.com:user@gmail.com:Pass123` | `http://xfinity.com` | `user@gmail.com` | `Pass123` |

---

## 🔄 Pipeline de Extracción

### Orden de Procesamiento

```
1. PATTERN_URL_COMBO        ← Máxima prioridad
   Extrae: http://service.tld:email:pass
   Guarda: service_url en extra_data
   Añade: email:password a seen

2. PATTERN_SERVICE_COMBO    ← Segunda prioridad  
   Extrae: service.tld:email:pass
   Convierte: → http://service.tld como service_url
   Añade: email:password a seen

3. PATTERN_EMAIL_PASS       ← Tercera prioridad
   Extrae: email:password
   Dedup: comprueba seen — evita duplicados de pasos 1 y 2

4. PATTERN_JSON_COMBO       ← Cuarta prioridad
   Extrae: {"email":"...", "password":"..."}

5. PATTERN_USER_PASS        ← Quinta prioridad (solo si keyword coincide)
   Extrae: user:password
   Valida: anti-noise (://, /, puertos)
   Filtra: requiere keyword en username o password
```

### Deduplicación Inteligente

```python
seen = set()  # Compartido entre todos los patrones

# Los patrones 1-4 añaden a seen después de validar
# Los patrones 1-2 (URL) se ejecutan ANTES que el patrón 3 (clásico)
# → Si el patrón 3 encuentra el mismo combo, el seen check lo filtra
```

### Filtro Anti-Ruido

La función `_is_valid_combo()` aplica estas validaciones:

```python
# 1. Campos vacíos
if not email or not password: return False

# 2. Longitud mínima
if len(email) < 5 or len(password) < 3: return False

# 3. Password demasiado largo (>100 chars = probablemente no es un password)
if len(password) > 100: return False

# 4. Debe contener @ (email válido)
if "@" not in email: return False

# 5. NO debe contener URL artifacts
if "://" in email or "/" in email or email.count(":") > 0: return False

# 6. No passwords comunes
if password.lower() in COMMON_PASSWORDS: return False

# 7. Regex de email válido
if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email): return False
```

---

## 📦 Data Models

### `ComboEntry`

```python
@dataclass
class ComboEntry:
    email: str = ""                    # Email de la víctima
    username: str = ""                 # Username (si no hay email)
    password: str = ""                 # Contraseña
    domain: str = ""                   # Dominio del email (extraído)
    source_url: str = ""               # URL de origen
    source_type: str = ""              # pastebin, telegram, dorking, api
    record_type: str = "email:pass"    # email:pass, user:pass
    discovered_at: str = ""            # ISO timestamp
    discovered_date: str = ""          # YYYY-MM-DD
    quality: str = "unknown"           # valid, invalid, unknown, checked
    validation_details: dict = field(default_factory=dict)  # Resultado de validación
    extra_data: dict = field(default_factory=dict)          # Datos extra (service_url, etc.)
```

### `ComboEntry.extra_data`

Para combos URL-based, `extra_data` contiene:

```python
entry.extra_data = {
    "service_url": "http://business.comcast.com"  # URL del servicio
}
```

### `LeechResult`

```python
@dataclass
class LeechResult:
    keyword: str = ""
    timestamp: str = ""
    combos: list = field(default_factory=list)
    total: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    sources: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    took_seconds: float = 0.0
```

---

## ✅ Validación de Combos

### SMTP Validation (recomendado)

```python
from combo_leecher_engine import ComboValidator

validator = ComboValidator()
result = validator.validate_smtp("user@domain.com", "password123")

# Resultado:
{
    "success": True,
    "server": "smtp.domain.com",
    "port": 587,
    "method": "SMTP+STARTTLS",
    "latency_ms": 245.3,
    "domain": "domain.com",
    "mx_servers": ["mail.domain.com", "smtp.domain.com"]
}
```

### HTTP Validation

```python
result = validator.validate_http("https://login.domain.com", "user@domain.com", "password123")
```

### IMAP Validation (fallback)

```python
result = validator.validate_imap("user@gmail.com", "password123")
```

---

## 🌐 Scrapers Multi-Fuente

### PasteScraper

```python
scraper = PasteScraper()
combos = scraper.scrape("comcast", max_pastes=10)
# Busca en: Pastebin, Rentry.co, Ghostbin, Paste.ee
# Vía: Google dorking
```

### TelegramScraper

```python
scraper = TelegramScraper()
combos = scraper.scrape("comcast")
# Busca en: 8+ canales de Telegram vía Google dorking
# Canales: combolist, leakbase, leakzone, credentialleaks, etc.
```

### DiscordScraper

```python
scraper = DiscordScraper()
combos = scraper.scrape("comcast")
# Busca en: Discord vía Google dorking
# Si DISCORD_TOKEN configurado: usa la API oficial
```

### ForumScraper

```python
scraper = ForumScraper()
combos = scraper.scrape("comcast")
# 15+ foros: nulled.to, cracked.to, leakzone.xyz, hackforums.net, etc.
```

### ComboLeecherEngine (todo en uno)

```python
from combo_leecher_engine import ComboLeecherEngine

engine = ComboLeecherEngine()
result = engine.leech(
    keyword="comcast",
    sources=["paste", "telegram", "forum", "dorking"],
    validate=True,  # Valida SMTP
    max_per_source=20
)

print(f"Total: {result.total}")
print(f"Válidos: {result.valid_count}")
print(f"Tiempo: {result.took_seconds}s")
```

---

## 📡 API Endpoints

### Combo Leech

```http
POST /api/combo/leech
Content-Type: application/json

{
    "keyword": "comcast",
    "sources": ["paste", "telegram", "dorking"],
    "validate": false,
    "max_per_source": 20
}
```

### Combo Stats

```http
GET /api/combo/stats
```

### Combo Export

```http
GET /api/combo/export/txt?keyword=comcast
GET /api/combo/export/csv?keyword=comcast
GET /api/combo/export/json?keyword=comcast
```

### Combo Validation

```http
POST /api/combo/validate
Content-Type: application/json

{
    "email": "user@domain.com",
    "password": "password123"
}
```

---

## 💻 Ejemplos de Uso

### Desde Python

```python
from combo_leecher_engine import ComboParser

# Parsear texto plano
parser = ComboParser()
text = """
http://business.comcast.com:user@domain.com:Password123
admin@test.com:Welcome2024!
comcast.net:bob@yahoo.com:Summer2024!
"""
combos = parser.parse_text(text, source_type="pastebin", keyword="comcast")

for c in combos:
    svc = c.extra_data.get("service_url", "")
    print(f"{c.email}:{c.password}  [URL={svc}]")
    # Output:
    # user@domain.com:Password123  [URL=http://business.comcast.com]
    # admin@test.com:Welcome2024!
    # bob@yahoo.com:Summer2024!  [URL=http://comcast.net]
```

### Desde la Terminal

```bash
# Leecher completo
python -c "
from combo_leecher_engine import ComboLeecherEngine
engine = ComboLeecherEngine()
result = engine.leech('comcast')
print(f'Total: {result.total}')
for c in result.combos[:5]:
    print(f'  {c.email}:{c.password[:15]}...')
"
```

### Desde el Dashboard Web

1. Ir a la pestaña **🔐 Combo**
2. Ingresar keyword: `comcast`
3. Activar fuentes: Telegram, Foros, Paste
4. Click **Leecher**
5. Ver resultados en tiempo real
6. Exportar a TXT/CSV/JSON

---

## 🧪 Pruebas

### Test Unitario del Parser

```bash
python -c "
from combo_leecher_engine import ComboParser
parser = ComboParser()

# Test URL-based
text = 'http://business.comcast.com:slcbiomed@mccmed.com:Mustang'
combos = parser.parse_text(text)
assert len(combos) == 1
assert combos[0].extra_data['service_url'] == 'http://business.comcast.com'
assert combos[0].email == 'slcbiomed@mccmed.com'
assert combos[0].password == 'Mustang'

# Test Service:email:pass
text2 = 'comcast.net:bob@yahoo.com:Summer2024!'
combos2 = parser.parse_text(text2)
assert len(combos2) == 1
assert combos2[0].extra_data['service_url'] == 'http://comcast.net'

# Test noise filtering
text3 = 'user:password (noise) http://real.com:user@gmail.com:RealPass123!'
combos3 = parser.parse_text(text3)
assert len(combos3) == 1  # Solo el combo válido

print('✅ All tests passed!')
"
```

### Test de los 7 Patrones

```bash
python -c "
from combo_leecher_engine import ComboParser

tests = [
    # (texto, expected_count, description)
    ('admin@test.com:pass123', 1, 'Classic email:pass'),
    ('http://service.com:user@email.com:pass', 1, 'URL-based email:pass'),
    ('http://service.com/path:user@email.com:pass', 1, 'URL with path'),
    ('http://service.com:username:password123', 0, 'URL user:pass (sin keyword)'),
    ('domain.com:user@email.com:pass', 1, 'Service:email:pass'),
    ('{\"email\":\"user@test.com\",\"password\":\"pass\"}', 1, 'JSON format'),
    ('user@test.com | pass123', 1, 'CSV pipe format'),
]

parser = ComboParser()
all_ok = True
for text, expected, desc in tests:
    c = parser.parse_text(text)
    ok = len(c) == expected
    status = '✅' if ok else '❌'
    print(f'  {status} {desc}: {len(c)}/{expected}')
    all_ok = all_ok and ok

print(f'\\n{\"ALL PASS\" if all_ok else \"SOME FAILED\"}')
"
```

---

## 📊 Estadísticas del Engine

```python
engine = ComboLeecherEngine()
stats = engine.get_stats()
print(stats)
# {
#     "total_combos_indexed": 1234,
#     "total_validated": 50,
#     "sources_used": ["paste", "telegram", "dorking"],
#     "proxies_available": 45,
#     "proxies_alive": 12,
#     "last_leech": {
#         "keyword": "comcast",
#         "total": 245,
#         "took_seconds": 15.24
#     },
#     "oracle_stats": {...}
# }
```

---

## 🔧 Solución de Problemas

### Los combos URL-based no se capturan

**Causa:** El `ComboParser` no se usa (se está usando un parser viejo).

**Solución:** Verificar que estás importando `ComboParser` de `combo_leecher_engine.py`:

```python
from combo_leecher_engine import ComboParser  # ✅ Correcto
```

### Duplicados en los resultados

**Causa:** El mismo combo es capturado por el patrón URL y el patrón clásico.

**Solución:** El sistema ya maneja deduplicación automática. Verificar que `seen` set se esté usando correctamente. Si persiste, revisar que `_is_valid_combo` esté recibiendo el parámetro `allow_no_at`.

### Falsos positivos (ruido)

**Causa:** Líneas con formato similar a combos pero que no lo son.

**Solución:** El filtro anti-noise debería atrapar la mayoría. Para casos extremos:
1. Aumentar la lista de `COMMON_PASSWORDS`
2. Agregar patrones específicos al `_is_valid_combo`
3. Usar el validador SMTP para verificar

---

*Combo Intelligence Engine v2.0 — Parte del Oráculo de Inteligencia 🔮*
*Documentación técnica para desarrolladores · Julio 2026*
