# 🛠️ Guía para Desarrolladores — Oráculo de Inteligencia

**Guía completa para contribuir, extender y mantener el Oráculo de Inteligencia.**

---

## 📑 Índice

1. [Entorno de Desarrollo](#-entorno-de-desarrollo)
2. [Estructura del Proyecto](#-estructura-del-proyecto)
3. [Flujo de Trabajo Git](#-flujo-de-trabajo-git)
4. [Guía de Estilo](#-guía-de-estilo)
5. [Cómo Agregar un Nuevo Módulo](#-cómo-agregar-un-nuevo-módulo)
6. [Cómo Agregar un Nuevo Patrón Regex](#-cómo-agregar-un-nuevo-patrón-regex)
7. [Cómo Agregar una Nueva API Externa](#-cómo-agregar-una-nueva-api-externa)
8. [Cómo Agregar un Nuevo Scraper](#-cómo-agregar-un-nuevo-scraper)
9. [Testing](#-testing)
10. [Debugging](#-debugging)
11. [Despliegue Local](#-despliegue-local)
12. [Contribuciones](#-contribuciones)

---

## 💻 Entorno de Desarrollo

### Prerrequisitos

| Herramienta | Versión Mínima | Instalación |
|-------------|:--------------:|-------------|
| Python | 3.10+ | [python.org](https://python.org) |
| Git | 2.30+ | [git-scm.com](https://git-scm.com) |
| pip | 21+ | `python -m pip install --upgrade pip` |

### Setup Inicial

```bash
# 1. Clonar
git clone https://github.com/tu-usuario/oraculo-inteligencia.git
cd oraculo-inteligencia

# 2. Virtual environment (recomendado)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Dependencias opcionales
pip install PyQt6      # Desktop app
pip install dnspython  # DNS resolution para validación SMTP
pip install psutil     # Monitoreo de recursos
pip install proxybroker2  # 50+ fuentes de proxies adicionales

# 5. Configurar .env
cp .env.example .env
# Editar .env con tus configuraciones

# 6. Verificar instalación
python -c "
import sys
sys.path.insert(0, '.')
from combo_leecher_engine import ComboParser
from dump_finder import DumpFinder
from proxy_engine import ProxyEngine
print('✅ All modules loaded successfully')
"
```

### Editor Recomendado

**VS Code** con extensiones:
- Python (ms-python.python)
- Pylance (para type hints)
- Python Docstring Generator
- GitLens

---

## 📁 Estructura del Proyecto

```
oraculo-inteligencia/
│
├── api.py                   # 🖥️ Flask API Server (30+ endpoints)
├── oracle_engine.py         # 🔍 OSINT Engine con 44+ dorks
├── dump_finder.py           # 🗄️ Dump Finder con cache + Tor
├── combo_leecher_engine.py  # 🔐 Combo Intelligence Engine (core)
├── intel_connectors.py      # 🔌 Conectores de APIs externas
├── proxy_engine.py          # 🌐 Proxy Manager + Scraper
├── elastic_index.py         # 📦 Elasticsearch backend
├── telegram_scraper.py      # 💬 Telegram Telethon scraper
├── desktop_app.py           # 🖥️ PyQt6 Desktop Application
├── local_keys.py            # 🔑 Gestión de API keys (env vars)
├── run.py                   # 🚀 Launcher unificado
│
├── static/                  # 📊 Dashboard Web
│   ├── index.html           #    Página principal
│   └── app.js               #    Frontend JS
│
├── data/                    # 💾 Datos generados (gitignored)
│   └── .dump_cache/         #    Cache de DumpFinder
│
├── requirements.txt         # 📦 Dependencias Python
├── render.yaml              # 🚢 Render.com Blueprint
├── Dockerfile               # 🐳 Docker image
├── Procfile                 # 📋 Gunicorn process
├── railway.json             # 🚂 Railway config
├── uptimerobot.json         # ⏰ UptimeRobot config
│
├── .env.example             # 📋 Template de variables de entorno
├── .gitignore               # 🚫 Archivos ignorados
│
├── README.md                # 📖 Documentación principal
├── COMBO_PARSER.md          # 📖 Documentación del ComboParser
├── DEVELOPMENT.md           # 📖 Esta guía
├── DUMPFINDER_MANUAL.md     # 📖 Manual de DumpFinder
└── JOKER_COMBO_LEECHER_ANALISIS.md  # 📖 Análisis comparativo
```

---

## 🌿 Flujo de Trabajo Git

### Branches

| Branch | Propósito |
|--------|-----------|
| `main` | Producción — estable y desplegada |
| `develop` | Integración de features |
| `feature/*` | Nuevas funcionalidades |
| `fix/*` | Correcciones de bugs |
| `docs/*` | Documentación |

### Commits Convencionales

```
feat: agregar patrón regex URL-based para combos
fix: corregir deduplicación en ComboParser
docs: actualizar README con formatos soportados
refactor: optimizar backtracking en PATTERN_URL_COMBO
test: agregar test para service:email:pass format
chore: actualizar dependencias en requirements.txt
```

### Proceso

```bash
# 1. Crear branch
git checkout -b feature/nueva-funcionalidad

# 2. Hacer cambios y commit
git add .
git commit -m "feat: agregar nueva funcionalidad"

# 3. Mantener actualizado con develop
git fetch origin
git rebase origin/develop

# 4. Push y crear PR
git push -u origin feature/nueva-funcionalidad
# Crear Pull Request en GitHub
```

---

## 🎨 Guía de Estilo

### Python

- **Type hints** obligatorios en todas las funciones públicas
- **Docstrings** estilo Google para clases y métodos
- **Máximo 100 caracteres** por línea
- **Snake case** para variables y funciones
- **CamelCase** para clases

```python
from typing import Optional, List
from dataclasses import dataclass, field


@dataclass
class ComboEntry:
    """A single credential combo extracted from any source.
    
    Attributes:
        email: Victim email address
        password: Plain-text password
        domain: Email domain (extracted automatically)
        extra_data: Additional metadata (service_url, etc.)
    """
    email: str = ""
    password: str = ""
    domain: str = ""
    extra_data: dict = field(default_factory=dict)


def parse_text(self, text: str, source_type: str = "unknown",
               keyword: str = "") -> List[ComboEntry]:
    """Parse raw text and extract credential combos.
    
    Args:
        text: Raw text to parse
        source_type: Origin of the text (pastebin, telegram, etc.)
        keyword: Search keyword for filtering
    
    Returns:
        List of ComboEntry objects (deduplicated)
    """
    ...
```

### Logging

```python
import logging
logger = logging.getLogger("MiModulo")

logger.debug("Detalle técnico: %s", detalle)
logger.info("Procesando %d combos...", cantidad)
logger.warning("⚠️ No se encontraron proxies")
logger.error("❌ Error al conectar: %s", str(e))
logger.exception("Excepción en pipeline")  # Con traceback
```

### Manejo de Errores

```python
try:
    result = self._operacion_riesgosa()
except requests.exceptions.Timeout:
    logger.warning("Timeout - reintentando...")
    result = self._reintentar()
except requests.exceptions.RequestException as e:
    logger.error(f"Error de red: {e}")
    return {"success": False, "error": str(e)}
except Exception as e:
    logger.exception("Error inesperado")
    return {"success": False, "error": str(e)}
```

---

## 🧩 Cómo Agregar un Nuevo Módulo

### 1. Crear el archivo

```bash
touch oraculo-inteligencia/mi_modulo.py
```

### 2. Estructura básica

```python
"""
╔══════════════════════════════════════════════════════════════╗
║  MI MÓDULO — Descripción                                    ║
║  Parte del Oráculo de Inteligencia                           ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import re
import json
import time
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

import requests

logger = logging.getLogger("MiModulo")


class MiClase:
    """Descripción de la clase."""
    
    def __init__(self):
        self.session = requests.Session()
    
    def hacer_algo(self, param: str) -> Dict[str, Any]:
        """Hacer algo importante."""
        ...
        return {"success": True, "data": ...}
```

### 3. Registrar en `run.py`

```python
# Agregar el comando CLI
def cli_mi_modulo():
    """Ejecutar mi módulo desde CLI."""
    from mi_modulo import MiClase
    m = MiClase()
    result = m.hacer_algo(...)
    print(result)

# Agregar al parser en main()
parser.add_argument("--mi-modulo", action="store_true", help="Ejecutar mi módulo")
```

### 4. Agregar endpoints en `api.py`

```python
@app.route("/api/mi-modulo/accion", methods=["POST"])
def api_mi_modulo_accion():
    """Endpoint para mi módulo."""
    data = request.get_json(silent=True) or {}
    try:
        from mi_modulo import MiClase
        m = MiClase()
        result = m.hacer_algo(data.get("param"))
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

### 5. Agregar tests

```python
# test_mi_modulo.py
from mi_modulo import MiClase

def test_hacer_algo():
    m = MiClase()
    result = m.hacer_algo("test")
    assert result["success"] == True
```

---

## 🔤 Cómo Agregar un Nuevo Patrón Regex

Los patrones regex se definen en `combo_leecher_engine.py` dentro de la clase `ComboParser`:

### 1. Definir el patrón

```python
class ComboParser:
    # ── Nuevo Pattern ──
    PATTERN_MI_FORMATO = re.compile(
        r'(regex_pattern_here)',
        re.IGNORECASE
    )
```

### 2. Agregar la extracción en `parse_text()`

El orden importa — los patrones más específicos van PRIMERO:

```python
def parse_text(self, text, ...):
    # ── NUEVO: Mi formato ──
    for match in self.PATTERN_MI_FORMATO.finditer(full_text):
        grupos = match.groups()
        email, password = self._procesar_grupos(grupos)
        if self._is_valid_combo(email, password, seen):
            entries.append(ComboEntry(
                email=email,
                password=password,
                ...
            ))
            seen.add(f"{email.lower()}:{password}")
    
    # ── 1. URL-based (existente) ──
    # ── 2. Service:email:pass (existente) ──
    # ── 3. Classic email:pass (existente) ──
    # ...
```

### 3. Actualizar contadores

```python
self.stats = {
    "total_lines": 0,
    "parsed_combos": 0,
    "url_based_combos": 0,
    "mi_formato_combos": 0,  # Nuevo contador
    "filtered_duplicates": 0,
    "filtered_noise": 0,
}
```

### 4. Testear

```bash
python -c "
from combo_leecher_engine import ComboParser
p = ComboParser()
c = p.parse_text('test_data')
assert len(c) == expected_count
print('✅ Nuevo patrón funciona')
"
```

---

## 🔌 Cómo Agregar una Nueva API Externa

### 1. Agregar la key en `local_keys.py`

```python
def get_mi_api_key() -> str:
    """Get MiAPI API key from environment."""
    return os.environ.get("MI_API_KEY", "")
```

### 2. Agregar el connector en `intel_connectors.py`

```python
class MiApiConnector:
    """Connector for MiAPI."""
    
    def __init__(self):
        self.api_key = get_mi_api_key()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "OracleIntelligence/2.0",
        })
    
    @property
    def enabled(self) -> bool:
        return bool(self.api_key)
    
    def search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Search MiAPI for a query."""
        if not self.enabled:
            return {"success": False, "error": "API key not configured"}
        try:
            resp = self.session.get(
                f"https://api.miapi.com/v1/search",
                params={"q": query, "limit": limit},
                timeout=10
            )
            if resp.status_code == 200:
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

### 3. Registrar en `IntelOrchestrator`

```python
class IntelOrchestrator:
    def __init__(self):
        self.mi_api = MiApiConnector()
        ...
    
    @property
    def available_apis(self) -> List[str]:
        apis = []
        if self.shodan.enabled: apis.append("shodan")
        ...
        if self.mi_api.enabled: apis.append("mi_api")
        return apis
```

### 4. Agregar endpoints en `api.py`

```python
@app.route("/api/mi-api/search", methods=["POST"])
def api_mi_api_search():
    """Search MiAPI."""
    try:
        from intel_connectors import MiApiConnector
        data = request.get_json(silent=True) or {}
        query = data.get("query", "").strip()
        if not query:
            return jsonify({"success": False, "error": "Query required"}), 400
        connector = MiApiConnector()
        result = connector.search(query)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

### 5. Actualizar `.env.example`

```env
# ─── MiAPI ─────────────────────────────────────
# https://miapi.com/api-keys
MI_API_KEY=
```

---

## 🕷️ Cómo Agregar un Nuevo Scraper

### 1. Crear la clase en `combo_leecher_engine.py`

```python
class MiScraper:
    """Scrapea nuevas fuentes para combos."""
    
    def __init__(self):
        self.session = requests.Session()
        self.parser = ComboParser()
        self.rate_limiter = RateLimiter(requests_per_minute=10)
        self.proxy_mgr = ProxyManager()
    
    def scrape(self, keyword: str, max_results: int = 10) -> List[ComboEntry]:
        """Scrapea mi fuente."""
        all_combos = []
        
        try:
            self.session.headers.update({"User-Agent": random_ua()})
            resp = self.session.get(
                f"https://mifuente.com/search?q={quote_plus(keyword)}",
                timeout=15,
                proxies=self.proxy_mgr.get_random(),
            )
            
            if resp.status_code == 200:
                combos = self.parser.parse_text(
                    resp.text,
                    source_url="https://mifuente.com",
                    source_type="mi_fuente",
                    keyword=keyword,
                )
                all_combos.extend(combos)
        
        except Exception as e:
            logger.debug(f"MiScraper error: {e}")
        
        return all_combos
```

### 2. Registrar en `ComboLeecherEngine`

```python
class ComboLeecherEngine:
    def __init__(self, ...):
        ...
        self.mi_scraper = MiScraper()
    
    def leech(self, keyword, sources=None, ...):
        ...
        if "mi_fuente" in sources:
            try:
                combos = self.mi_scraper.scrape(keyword)
                all_combos.extend(combos)
                used_sources.append("mi_fuente")
            except Exception as e:
                errors.append(f"mi_fuente: {e}")
```

---

## 🧪 Testing

### Tests Manuales Rápidos

```bash
# Test del ComboParser
python -c "
from combo_leecher_engine import ComboParser
p = ComboParser()
assert len(p.parse_text('admin@test.com:pass123')) == 1
assert len(p.parse_text('http://srv.com:user@email.com:pass')) == 1
print('✅ ComboParser OK')
"

# Test del DumpFinder (sin búsqueda real)
python -c "
from dump_finder import DateFilter, LocalSaver
print('✅ DumpFinder modules OK')
"

# Test de importación de todos los módulos
python -c "
modules = ['combo_leecher_engine', 'dump_finder', 'proxy_engine', 
           'intel_connectors', 'oracle_engine', 'local_keys']
for m in modules:
    __import__(m)
    print(f'✅ {m}')
"
```

### Tests de Integración

```bash
# Iniciar servidor
python run.py --port 8080 &
sleep 3

# Test endpoint
curl -s http://localhost:8080/api/ping | python -c "import sys,json; print(json.load(sys.stdin)['data']['status'])"

# Test search
curl -s -X POST http://localhost:8080/api/search \
  -H "Content-Type: application/json" \
  -d '{"keyword":"test","sample":true}' | python -c "import sys,json; d=json.load(sys.stdin); print(f'✅ Search: {d[\"success\"]}')"

# Matar servidor
kill %1
```

---

## 🐛 Debugging

### Logging Niveles

```python
import logging
logging.basicConfig(level=logging.DEBUG)  # Más detalle
logging.basicConfig(level=logging.INFO)   # Normal
logging.basicConfig(level=logging.WARNING) # Solo warnings+
```

### Debug del ComboParser

```python
from combo_leecher_engine import ComboParser
import logging
logging.basicConfig(level=logging.DEBUG)

parser = ComboParser()
combos = parser.parse_text("http://test.com:user@email.com:pass123")
print(f"Stats: {parser.stats}")
# DEBUG log muestra cada patrón ejecutado
```

### Debug de Requests HTTP

```python
import requests
import logging

# Verbose HTTP logging
logging.basicConfig(level=logging.DEBUG)
requests_log = logging.getLogger("urllib3")
requests_log.setLevel(logging.DEBUG)
```

---

## 🚀 Despliegue Local

```bash
# API Server
python run.py --port 8080
# http://localhost:8080

# Desktop App
python run.py --desktop

# CLI Search
python run.py --search "comcast"

# Dump Finder
python run.py --dump "comcast"

# Combo Leecher
python run.py --leech "comcast"

# Proxy Management
python run.py --proxy-scrape
python run.py --proxy-test
python run.py --proxy-test  # Auto-poblar pool

# Telegram
python run.py --telegram-login
python run.py --telegram-search "comcast"

# Check APIs
python run.py --check-apis
```

---

## 🤝 Contribuciones

### Cómo Contribuir

1. **Issues**: Reportar bugs o sugerir features
2. **Pull Requests**: Para código nuevo o correcciones
3. **Documentación**: Mejoras a README, docstrings, guías

### Checklist para PRs

- [ ] Código sigue la guía de estilo
- [ ] Type hints en funciones nuevas
- [ ] Docstrings actualizados
- [ ] Tests agregados/actualizados
- [ ] No rompe funcionalidad existente
- [ ] `python run.py` funciona sin errores
- [ ] README actualizado si aplica

### Código de Conducta

- **Sé respetuoso** con otros contribuidores
- **Enfócate en la calidad** del código
- **Documenta** los cambios importantes
- **Testea** antes de enviar PRs
- **Uso ético**: recordar que es una herramienta de seguridad

---

*Oráculo de Inteligencia — Developer Guide v2.0*
*Construido con 🛸 Freebuff AI · Julio 2026*
