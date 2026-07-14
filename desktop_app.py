"""
╔══════════════════════════════════════════════════════════════╗
║  ORÁCULO DE INTELIGENCIA — Desktop Application              ║
║  PyQt6 · GUI completa · Sistema integrado                   ║
║                                                              ║
║  Uso: python desktop_app.py                                 ║
╚══════════════════════════════════════════════════════════════╝
"""
import sys
import os
import json
import time
import threading
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
        QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
        QGroupBox, QGridLayout, QSplitter, QStatusBar, QMessageBox,
        QProgressBar, QHeaderView, QFrame, QScrollArea,
        QListWidget, QListWidgetItem, QMenu, QMenuBar,
        QFileDialog, QSpinBox, QDialog, QDialogButtonBox,
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
    from PyQt6.QtGui import QFont, QPalette, QColor, QAction, QIcon, QTextCursor
    PYSIDE = False
except ImportError:
    try:
        from PySide6.QtWidgets import *
        from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize
        from PySide6.QtGui import QFont, QPalette, QColor, QAction, QIcon, QTextCursor
        pyqtSignal = Signal
        PYSIDE = True
    except ImportError:
        print("❌ PyQt6 o PySide6 no instalado.")
        print("   pip install PyQt6  o  pip install PySide6")
        sys.exit(1)

# Import project modules
from oracle_engine import OracleEngine, SampleDataGenerator, EnhancedOracleEngine
from combo_leecher_engine import ComboLeecherEngine, ComboParser
from dump_finder import DumpFinder, DiskCache
from proxy_engine import ProxyEngine, detect_vpn
from telegram_scraper import TelegramIntelScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DesktopOracle")

# ─── Global Engine Instances ───
oracle_engine = None
combo_engine = None
dump_finder = None
proxy_engine = None
telegram_scraper = None


def get_oracle():
    global oracle_engine
    if oracle_engine is None:
        oracle_engine = EnhancedOracleEngine()
    return oracle_engine


def get_combo():
    global combo_engine
    if combo_engine is None:
        combo_engine = ComboLeecherEngine(oracle_engine=get_oracle().base_engine if get_oracle() else None)
    return combo_engine


def get_dump():
    global dump_finder
    if dump_finder is None:
        try:
            dump_finder = DumpFinder()
        except Exception as e:
            logger.error(f"DumpFinder init error: {e}")
    return dump_finder


def get_proxy():
    global proxy_engine
    if proxy_engine is None:
        proxy_engine = ProxyEngine()
    return proxy_engine


def get_telegram():
    global telegram_scraper
    if telegram_scraper is None:
        telegram_scraper = TelegramIntelScraper()
    return telegram_scraper


# ═══════════════════════════════════════════════════════════════
#  DARK THEME
# ═══════════════════════════════════════════════════════════════

DARK_STYLE = """
QMainWindow, QDialog {
    background-color: #06060e;
    color: #e0e0f0;
}
QWidget {
    background-color: #06060e;
    color: #e0e0f0;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 12px;
}
QGroupBox {
    border: 1px solid #2a2a4e;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
    font-weight: 600;
    color: #6c5ce7;
}
QGroupBox::title {
    subcontrol-origin: margin;
    padding: 0 8px;
    color: #6c5ce7;
}
QLabel {
    color: #e0e0f0;
    background: transparent;
}
QLabel[class="heading"] {
    font-size: 18px;
    font-weight: 700;
    color: #6c5ce7;
}
QLabel[class="subtitle"] {
    font-size: 11px;
    color: #8888aa;
}
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #0a0a1a;
    border: 1px solid #2a2a4e;
    border-radius: 6px;
    padding: 8px 10px;
    color: #e0e0f0;
    font-size: 12px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #6c5ce7;
}
QPushButton {
    background-color: #6c5ce7;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
    font-size: 11px;
    min-height: 22px;
}
QPushButton:hover {
    background-color: #7c6cf7;
}
QPushButton:pressed {
    background-color: #5c4cd7;
}
QPushButton:disabled {
    background-color: #2a2a4e;
    color: #5a5a7a;
}
QPushButton[class="danger"] {
    background-color: #e17055;
}
QPushButton[class="danger"]:hover {
    background-color: #f18065;
}
QPushButton[class="success"] {
    background-color: #00b894;
}
QPushButton[class="success"]:hover {
    background-color: #00c9a4;
}
QComboBox {
    background-color: #0a0a1a;
    border: 1px solid #2a2a4e;
    border-radius: 6px;
    padding: 6px 10px;
    color: #e0e0f0;
    font-size: 11px;
    min-height: 22px;
}
QComboBox:focus {
    border-color: #6c5ce7;
}
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #0a0a1a;
    border: 1px solid #2a2a4e;
    color: #e0e0f0;
    selection-background-color: #6c5ce7;
}
QCheckBox {
    color: #e0e0f0;
    spacing: 6px;
    font-size: 11px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #2a2a4e;
    border-radius: 3px;
    background-color: #0a0a1a;
}
QCheckBox::indicator:checked {
    background-color: #6c5ce7;
    border-color: #6c5ce7;
}
QTableWidget {
    background-color: #0a0a1a;
    border: 1px solid #2a2a4e;
    border-radius: 6px;
    gridline-color: #1a1a3e;
    font-size: 11px;
}
QTableWidget::item {
    padding: 6px 8px;
    color: #e0e0f0;
}
QTableWidget::item:selected {
    background-color: #6c5ce7;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #12122a;
    color: #6c5ce7;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #2a2a4e;
    font-weight: 600;
    font-size: 10px;
    text-transform: uppercase;
}
QTabWidget::pane {
    border: 1px solid #2a2a4e;
    border-radius: 6px;
    background-color: #06060e;
}
QTabBar::tab {
    background-color: #0a0a1a;
    color: #8888aa;
    padding: 8px 18px;
    border: 1px solid #2a2a4e;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-size: 11px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background-color: #6c5ce7;
    color: #ffffff;
}
QTabBar::tab:hover:!selected {
    background-color: #1a1a3e;
    color: #e0e0f0;
}
QProgressBar {
    border: 1px solid #2a2a4e;
    border-radius: 4px;
    text-align: center;
    font-size: 10px;
    color: #8888aa;
    background-color: #0a0a1a;
    height: 16px;
}
QProgressBar::chunk {
    background-color: #6c5ce7;
    border-radius: 3px;
}
QStatusBar {
    background-color: #0a0a1a;
    border-top: 1px solid #2a2a4e;
    color: #8888aa;
    font-size: 10px;
}
QScrollBar:vertical {
    background: #0a0a1a;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2a2a4e;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #6c5ce7;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QListWidget {
    background-color: #0a0a1a;
    border: 1px solid #2a2a4e;
    border-radius: 6px;
    color: #e0e0f0;
    font-size: 11px;
}
QListWidget::item {
    padding: 6px 10px;
    border-bottom: 1px solid #1a1a3e;
}
QListWidget::item:selected {
    background-color: #6c5ce7;
}
QSplitter::handle {
    background-color: #2a2a4e;
    width: 1px;
}
QFrame[class="card"] {
    background-color: #12122a;
    border: 1px solid #2a2a4e;
    border-radius: 8px;
    padding: 12px;
}
"""


# ═══════════════════════════════════════════════════════════════
#  WORKER THREADS
# ═══════════════════════════════════════════════════════════════

class SearchWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, keyword, category=None, use_sample=True):
        super().__init__()
        self.keyword = keyword
        self.category = category
        self.use_sample = use_sample

    def run(self):
        try:
            self.progress.emit(f"🔍 Buscando '{self.keyword}'...")
            oracle = get_oracle()
            categories = [self.category] if self.category else None
            result = oracle.search(self.keyword, categories=categories, sample=self.use_sample)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class DumpWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, keyword, year=None, month=None):
        super().__init__()
        self.keyword = keyword
        self.year = year
        self.month = month

    def run(self):
        try:
            self.progress.emit(f"🗄️ Buscando dumps para '{self.keyword}'...")
            finder = get_dump()
            if finder:
                result = finder.search_fast(self.keyword, year=self.year, month=self.month)
                self.finished.emit(result)
            else:
                self.error.emit("DumpFinder no disponible")
        except Exception as e:
            self.error.emit(str(e))


class ComboWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, keyword, sources=None, validate=False):
        super().__init__()
        self.keyword = keyword
        self.sources = sources or ["paste", "telegram", "dorking"]
        self.validate = validate

    def run(self):
        try:
            self.progress.emit(f"🔐 Leeching combos para '{self.keyword}'...")
            engine = get_combo()
            result = engine.leech(self.keyword, sources=self.sources, validate=self.validate)
            self.finished.emit(result.to_dict())
        except Exception as e:
            self.error.emit(str(e))


class ProxyWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, action="scrape"):
        super().__init__()
        self.action = action

    def run(self):
        try:
            engine = get_proxy()
            if self.action == "scrape":
                self.progress.emit("🕸️ Scrapeando proxies de 30+ fuentes...")
                result = engine.scrape_proxies()
            elif self.action == "test":
                self.progress.emit("🧪 Testeando proxies...")
                result = engine.test_proxies()
            elif self.action == "autopopulate":
                self.progress.emit("⚡ Auto-poblando pool de proxies...")
                engine.scrape_proxies()
                result = engine.test_proxies()
            else:
                result = engine.get_stats()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class TelegramWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword

    def run(self):
        try:
            self.progress.emit(f"💬 Buscando en Telegram para '{self.keyword}'...")
            scraper = get_telegram()
            combos = scraper.scrape(self.keyword)
            self.finished.emit(combos)
        except Exception as e:
            self.error.emit(str(e))


# ═══════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════

class OracleDesktop(QMainWindow):
    """Main desktop application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("🛸 Oráculo de Inteligencia — Desktop v1.0")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        self.current_worker = None
        self.combo_data = []
        self.dump_data = []
        self.search_data = []

        self._init_ui()
        self._show_startup_info()

    def _init_ui(self):
        """Initialize the UI."""
        self.setStyleSheet(DARK_STYLE)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # ─── Header ───
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 8)

        title = QLabel("🛸 Oráculo de Inteligencia — Desktop")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #6c5ce7;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.status_label = QLabel("🟢 Sistema Activo")
        self.status_label.setStyleSheet("font-size: 11px; color: #00b894; background: transparent;")
        header_layout.addWidget(self.status_label)

        main_layout.addWidget(header)

        # ─── Tabs ───
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Create all tabs
        self._create_search_tab()
        self._create_dump_tab()
        self._create_combo_tab()
        self._create_telegram_tab()
        self._create_proxy_tab()
        self._create_stats_tab()

        # ─── Progress Bar ───
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # ─── Status Bar ───
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("🛸 Listo para operar")

        # ─── Timer for clock ───
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_clock)
        self.timer.start(1000)

    def _update_clock(self):
        """Update the clock in the status bar."""
        now = datetime.now().strftime("%H:%M:%S")
        self.status_bar.showMessage(f"🛸 Listo para operar  ·  {now}")

    def _show_startup_info(self):
        """Show startup info dialog."""
        QMessageBox.information(
            self,
            "🛸 Oráculo de Inteligencia",
            "Bienvenido al Oráculo de Inteligencia Desktop v1.0\n\n"
            "🔍 Busca inteligencia de amenazas en múltiples fuentes\n"
            "🗄️ Encuentra bases de datos filtradas\n"
            "🔐 Extrae y valida credenciales\n"
            "💬 Scrapea Telegram y Discord\n"
            "🌐 Gestiona proxies automáticamente\n\n"
            "¡Comienza por la pestaña '🔍 Búsqueda'!"
        )

    # ══════════════════════════════════════════════════════════
    #  SEARCH TAB
    # ══════════════════════════════════════════════════════════

    def _create_search_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # ── Input ──
        input_group = QGroupBox("🔍 Búsqueda de Inteligencia")
        input_layout = QHBoxLayout(input_group)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Ej: comcast, xfinity, verizon, "password"')
        self.search_input.returnPressed.connect(self._do_search)
        input_layout.addWidget(self.search_input, 3)

        self.search_category = QComboBox()
        self.search_category.addItems([
            "🌐 Todas", "🔑 Credenciales", "🔍 Logs",
            "🗄️ Bases de datos", "⚙️ Configuraciones",
            "📋 Paste sites", "💻 Repositorios"
        ])
        input_layout.addWidget(self.search_category, 1)

        self.search_btn = QPushButton("🔍 Buscar")
        self.search_btn.clicked.connect(self._do_search)
        input_layout.addWidget(self.search_btn)

        layout.addWidget(input_group)

        # ── Results ──
        results_group = QGroupBox("📊 Resultados")
        results_layout = QVBoxLayout(results_group)

        self.search_table = QTableWidget()
        self.search_table.setColumnCount(7)
        self.search_table.setHorizontalHeaderLabels(["Severidad", "Tipo", "Email", "Dominio", "Contenido", "Fuente", "Fecha"])
        self.search_table.horizontalHeader().setStretchLastSection(False)
        self.search_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.search_table.setAlternatingRowColors(True)
        self.search_table.setSortingEnabled(True)
        self.search_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        results_layout.addWidget(self.search_table)

        # ── Search info ──
        self.search_info = QLabel("Ejecuta una búsqueda para ver resultados")
        self.search_info.setStyleSheet("color: #8888aa; font-size: 11px; padding: 4px 0;")
        results_layout.addWidget(self.search_info)

        # ── Export ──
        export_layout = QHBoxLayout()
        export_btn = QPushButton("📥 Exportar CSV")
        export_btn.setStyleSheet("QPushButton { background-color: #00b894; }")
        export_btn.clicked.connect(self._export_search)
        export_layout.addWidget(export_btn)
        export_layout.addStretch()
        results_layout.addLayout(export_layout)

        layout.addWidget(results_group)

        self.tabs.addTab(tab, "🔍 Búsqueda")

    def _do_search(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "⚠️ Campo requerido", "Ingresa una palabra clave para buscar.")
            return

        self.search_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        self.current_worker = SearchWorker(keyword)
        self.current_worker.finished.connect(self._on_search_finished)
        self.current_worker.error.connect(self._on_worker_error)
        self.current_worker.progress.connect(self.status_bar.showMessage)
        self.current_worker.start()

    def _on_search_finished(self, result):
        self.progress_bar.setVisible(False)
        self.search_btn.setEnabled(True)

        # Extract records
        all_records = result.get("all_records", [])
        dorking = result.get("dorking", {})
        dorking_records = dorking.get("records", [])
        api_intel = result.get("api_intel", {})

        # Combine
        records = all_records if all_records else dorking_records
        self.search_data = records

        # Update table
        self.search_table.setRowCount(len(records))
        for i, rec in enumerate(records[:500]):
            sev = rec.get("severity", "info")
            self.search_table.setItem(i, 0, QTableWidgetItem(f"● {sev.upper()}"))
            self.search_table.setItem(i, 1, QTableWidgetItem(rec.get("record_type", "")))
            self.search_table.setItem(i, 2, QTableWidgetItem(rec.get("email", rec.get("username", ""))))
            self.search_table.setItem(i, 3, QTableWidgetItem(rec.get("domain", "")))
            preview = rec.get("content_preview", "")[:80]
            self.search_table.setItem(i, 4, QTableWidgetItem(preview))
            self.search_table.setItem(i, 5, QTableWidgetItem(rec.get("source_type", "")))
            self.search_table.setItem(i, 6, QTableWidgetItem(rec.get("discovered_date", "")))

        # Color severity
        for i in range(len(records[:500])):
            sev = records[i].get("severity", "info")
            color = "#e17055" if sev == "critical" else "#e67e22" if sev == "high" else \
                    "#fdcb6e" if sev == "medium" else "#0984e3" if sev == "low" else "#8888aa"
            self.search_table.item(i, 0).setForeground(QColor(color))
            self.search_table.item(i, 0).setFont(QFont("", 10, QFont.Weight.Bold))

        summary = result.get("summary", {})
        total = summary.get("total_records", len(records))
        sources = summary.get("sources", [])
        critical = summary.get("critical_count", 0)

        self.search_info.setText(
            f"📊 {total} registros encontrados  ·  "
            f"🔴 {critical} críticos  ·  "
            f"📡 Fuentes: {', '.join(sources[:5]) or 'N/A'}  ·  "
            f"⏱️ {result.get('timestamp', '')[:19]}"
        )
        self.status_bar.showMessage(f"✅ Búsqueda completada: {total} registros")

    # ══════════════════════════════════════════════════════════
    #  DUMP FINDER TAB
    # ══════════════════════════════════════════════════════════

    def _create_dump_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # ── Input ──
        input_group = QGroupBox("🗄️ Dump Finder")
        input_layout = QHBoxLayout(input_group)

        self.dump_input = QLineEdit()
        self.dump_input.setPlaceholderText("Ej: comcast, verizon, netflix")
        self.dump_input.returnPressed.connect(self._do_dump)
        input_layout.addWidget(self.dump_input, 3)

        self.dump_year = QComboBox()
        self.dump_year.addItems(["Todos", "2023", "2024", "2025", "2026"])
        input_layout.addWidget(self.dump_year)

        self.dump_month = QComboBox()
        self.dump_month.addItems(["Todos", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                                   "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"])
        input_layout.addWidget(self.dump_month)

        self.dump_btn = QPushButton("🗄️ Buscar Dumps")
        self.dump_btn.clicked.connect(self._do_dump)
        input_layout.addWidget(self.dump_btn)

        layout.addWidget(input_group)

        # ── KPIs ──
        kpi_group = QGroupBox("📊 KPIs")
        kpi_layout = QHBoxLayout(kpi_group)

        self.dump_kpis = {}
        for key, label, color in [
            ("dorks", "Dorks", "#6c5ce7"), ("urls", "URLs", "#e17055"),
            ("fetched", "Fetchados", "#fdcb6e"), ("combos", "Combos", "#00b894"),
            ("time", "Tiempo", "#0984e3")
        ]:
            kpi = QLabel(f"{label}: 0")
            kpi.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {color}; padding: 6px 12px; "
                              f"background: #12122a; border-radius: 6px; border: 1px solid #2a2a4e;")
            kpi_layout.addWidget(kpi)
            self.dump_kpis[key] = kpi

        layout.addWidget(kpi_group)

        # ── Results ──
        results_group = QGroupBox("🔗 URLs Encontradas")
        results_layout = QVBoxLayout(results_group)
        self.dump_urls_list = QListWidget()
        results_layout.addWidget(self.dump_urls_list)
        layout.addWidget(results_group)

        # ── Combo Table ──
        combo_group = QGroupBox("🔐 Combos Encontrados (sample)")
        combo_layout = QVBoxLayout(combo_group)

        self.dump_table = QTableWidget()
        self.dump_table.setColumnCount(5)
        self.dump_table.setHorizontalHeaderLabels(["Email", "Contraseña", "Dominio", "Fuente", "Fecha"])
        self.dump_table.horizontalHeader().setStretchLastSection(True)
        self.dump_table.setAlternatingRowColors(True)
        combo_layout.addWidget(self.dump_table)

        # Export
        export_layout = QHBoxLayout()
        for fmt in ["TXT", "CSV", "JSON"]:
            btn = QPushButton(f"📥 Exportar {fmt}")
            btn.setStyleSheet("QPushButton { background-color: #00b894; }")
            btn.clicked.connect(lambda checked, f=fmt.lower(): self._export_dump(f))
            export_layout.addWidget(btn)
        export_layout.addStretch()
        combo_layout.addLayout(export_layout)

        layout.addWidget(combo_group)

        self.tabs.addTab(tab, "🗄️ Dumps")

    def _do_dump(self):
        keyword = self.dump_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "⚠️ Campo requerido", "Ingresa una palabra clave.")
            return

        year = self.dump_year.currentText()
        month = self.dump_month.currentText()

        year_val = int(year) if year.isdigit() else None
        month_val = self.dump_month.currentIndex() if month != "Todos" else None

        self.dump_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.current_worker = DumpWorker(keyword, year_val, month_val)
        self.current_worker.finished.connect(self._on_dump_finished)
        self.current_worker.error.connect(self._on_worker_error)
        self.current_worker.progress.connect(self.status_bar.showMessage)
        self.current_worker.start()

    def _on_dump_finished(self, result):
        self.progress_bar.setVisible(False)
        self.dump_btn.setEnabled(True)

        self.dump_data = result.get("combos_sample", [])

        # KPIs
        self.dump_kpis["dorks"].setText(f"📝 Dorks: {result.get('dorks_executed', 0)}")
        self.dump_kpis["urls"].setText(f"🔗 URLs: {result.get('urls_found', 0)}")
        self.dump_kpis["fetched"].setText(f"📥 Fetchados: {result.get('urls_fetched', 0)}")
        self.dump_kpis["combos"].setText(f"🔐 Combos: {result.get('filtered_combos_count', 0)}")
        self.dump_kpis["time"].setText(f"⏱️ Time: {result.get('took_seconds', 0)}s")

        # URLs
        self.dump_urls_list.clear()
        for u in result.get("top_urls", [])[:20]:
            item = QListWidgetItem(f"  {u.get('url', '')[:80]}  [{u.get('source', '')}]")
            self.dump_urls_list.addItem(item)

        # Combos table
        combos = self.dump_data
        self.dump_table.setRowCount(len(combos))
        for i, c in enumerate(combos):
            self.dump_table.setItem(i, 0, QTableWidgetItem(c.get("email", "")))
            pw = c.get("password", "")
            pw_display = pw[:15] + "***" if len(pw) > 15 else pw
            self.dump_table.setItem(i, 1, QTableWidgetItem(pw_display))
            self.dump_table.setItem(i, 2, QTableWidgetItem(c.get("domain", "")))
            self.dump_table.setItem(i, 3, QTableWidgetItem(c.get("source", c.get("source_type", ""))))
            self.dump_table.setItem(i, 4, QTableWidgetItem(c.get("date", c.get("discovered_date", ""))))

        self.status_bar.showMessage(f"✅ Dump completado: {result.get('filtered_combos_count', 0)} combos")

    # ══════════════════════════════════════════════════════════
    #  COMBO TAB
    # ══════════════════════════════════════════════════════════

    def _create_combo_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # ── Input ──
        input_group = QGroupBox("🔐 Combo Intelligence — Multi-source Leecher")
        input_layout = QHBoxLayout(input_group)

        self.combo_input = QLineEdit()
        self.combo_input.setPlaceholderText("Ej: comcast, netflix, spotify")
        self.combo_input.returnPressed.connect(self._do_combo)
        input_layout.addWidget(self.combo_input, 2)

        self.combo_sources = QComboBox()
        self.combo_sources.addItems(["🌐 Todas", "📋 Paste", "💬 Telegram", "💬 Discord", "📢 Foros", "🔍 Dorking"])
        input_layout.addWidget(self.combo_sources)

        self.combo_validate = QCheckBox("🔐 Validar SMTP")
        input_layout.addWidget(self.combo_validate)

        self.combo_btn = QPushButton("🔐 Leecher")
        self.combo_btn.setStyleSheet("QPushButton { background-color: #a855f7; }")
        self.combo_btn.clicked.connect(self._do_combo)
        input_layout.addWidget(self.combo_btn)

        layout.addWidget(input_group)

        # ── KPIs ──
        kpi_group = QGroupBox("📊 KPIs")
        kpi_layout = QHBoxLayout(kpi_group)
        for key, label, color in [
            ("total", "Total", "#6c5ce7"), ("valid", "Válidos", "#00b894"),
            ("invalid", "Inválidos", "#e17055"), ("sources", "Fuentes", "#fdcb6e"),
        ]:
            kpi = QLabel(f"{label}: 0")
            kpi.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {color}; padding: 6px 12px;"
                              f"background: #12122a; border-radius: 6px; border: 1px solid #2a2a4e;")
            kpi_layout.addWidget(kpi)
            self.__dict__[f"combo_kpi_{key}"] = kpi

        layout.addWidget(kpi_group)

        # ── Table ──
        table_group = QGroupBox("📋 Resultados")
        table_layout = QVBoxLayout(table_group)

        self.combo_table = QTableWidget()
        self.combo_table.setColumnCount(6)
        self.combo_table.setHorizontalHeaderLabels(["Estado", "Email", "Contraseña", "Dominio", "Fuente", "Calidad"])
        self.combo_table.horizontalHeader().setStretchLastSection(True)
        self.combo_table.setAlternatingRowColors(True)
        table_layout.addWidget(self.combo_table)

        export_layout = QHBoxLayout()
        for fmt in ["TXT", "CSV", "JSON"]:
            btn = QPushButton(f"📥 Exportar {fmt}")
            btn.setStyleSheet("QPushButton { background-color: #a855f7; }")
            btn.clicked.connect(lambda checked, f=fmt.lower(): self._export_combo(f))
            export_layout.addWidget(btn)
        export_layout.addStretch()
        table_layout.addLayout(export_layout)

        layout.addWidget(table_group)

        self.tabs.addTab(tab, "🔐 Combo")

    def _do_combo(self):
        keyword = self.combo_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "⚠️ Campo requerido", "Ingresa una palabra clave.")
            return

        source_map = {
            "🌐 Todas": ["paste", "telegram", "discord", "forum", "dorking"],
            "📋 Paste": ["paste"],
            "💬 Telegram": ["telegram"],
            "💬 Discord": ["discord"],
            "📢 Foros": ["forum"],
            "🔍 Dorking": ["dorking"],
        }
        sources = source_map.get(self.combo_sources.currentText(), ["paste", "telegram", "dorking"])
        validate = self.combo_validate.isChecked()

        self.combo_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.current_worker = ComboWorker(keyword, sources=sources, validate=validate)
        self.current_worker.finished.connect(self._on_combo_finished)
        self.current_worker.error.connect(self._on_worker_error)
        self.current_worker.progress.connect(self.status_bar.showMessage)
        self.current_worker.start()

    def _on_combo_finished(self, result):
        self.progress_bar.setVisible(False)
        self.combo_btn.setEnabled(True)

        combos = result.get("combos", [])
        total = result.get("total", 0)
        valid = result.get("valid_count", 0)
        invalid = result.get("invalid_count", 0)
        sources = result.get("sources", [])

        self.combo_kpi_total.setText(f"📦 Total: {total}")
        self.combo_kpi_valid.setText(f"✅ Válidos: {valid}")
        self.combo_kpi_invalid.setText(f"❌ Inválidos: {invalid}")
        self.combo_kpi_sources.setText(f"📡 Fuentes: {', '.join(sources)}")

        self.combo_table.setRowCount(len(combos))
        for i, c in enumerate(combos):
            q = c.get("quality", "unknown")
            status = "✅" if q == "valid" else ("❌" if q == "invalid" else "❓")
            self.combo_table.setItem(i, 0, QTableWidgetItem(status))
            self.combo_table.setItem(i, 1, QTableWidgetItem(c.get("email", c.get("username", ""))))
            pw = c.get("password", "")
            pw_display = pw[:12] + "***" if len(pw) > 12 else pw
            self.combo_table.setItem(i, 2, QTableWidgetItem(pw_display))
            self.combo_table.setItem(i, 3, QTableWidgetItem(c.get("domain", "")))
            self.combo_table.setItem(i, 4, QTableWidgetItem(c.get("source_type", "")))
            self.combo_table.setItem(i, 5, QTableWidgetItem(q))

        self.status_bar.showMessage(f"✅ Combo leech completado: {total} combos de {len(sources)} fuentes")

    # ══════════════════════════════════════════════════════════
    #  TELEGRAM TAB
    # ══════════════════════════════════════════════════════════

    def _create_telegram_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # ── Input ──
        input_group = QGroupBox("💬 Telegram Intelligence (Telethon)")
        input_layout = QHBoxLayout(input_group)

        self.tg_input = QLineEdit()
        self.tg_input.setPlaceholderText("Ej: comcast, netflix, 'email:pass'")
        self.tg_input.returnPressed.connect(self._do_telegram)
        input_layout.addWidget(self.tg_input, 3)

        self.tg_btn = QPushButton("💬 Buscar en Telegram")
        self.tg_btn.setStyleSheet("QPushButton { background-color: #0088cc; }")
        self.tg_btn.clicked.connect(self._do_telegram)
        input_layout.addWidget(self.tg_btn)

        # Status
        self.tg_status = QLabel("📡 Telegram: Configurar TG_API_ID y TG_API_HASH en .env")
        self.tg_status.setStyleSheet("color: #8888aa; font-size: 11px; padding: 4px 0;")
        input_layout.addWidget(self.tg_status)

        layout.addWidget(input_group)

        # ── Results ──
        results_group = QGroupBox("📊 Resultados de Telegram")
        results_layout = QVBoxLayout(results_group)

        self.tg_table = QTableWidget()
        self.tg_table.setColumnCount(5)
        self.tg_table.setHorizontalHeaderLabels(["Email", "Contraseña", "Dominio", "Fuente", "Calidad"])
        self.tg_table.horizontalHeader().setStretchLastSection(True)
        self.tg_table.setAlternatingRowColors(True)
        results_layout.addWidget(self.tg_table)

        self.tg_info = QLabel("💬 Scrapea canales de Telegram en busca de credenciales filtradas")
        self.tg_info.setStyleSheet("color: #8888aa; font-size: 11px; padding: 4px 0;")
        results_layout.addWidget(self.tg_info)

        layout.addWidget(results_group)

        self.tabs.addTab(tab, "💬 Telegram")

    def _do_telegram(self):
        keyword = self.tg_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "⚠️ Campo requerido", "Ingresa una palabra clave.")
            return

        scraper = get_telegram()
        if not scraper.enabled:
            QMessageBox.warning(
                self, "⚠️ Telegram no configurado",
                "Configura TG_API_ID y TG_API_HASH en el archivo .env\n"
                "y ejecuta: python telegram_scraper.py --login"
            )
            return

        self.tg_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.current_worker = TelegramWorker(keyword)
        self.current_worker.finished.connect(self._on_telegram_finished)
        self.current_worker.error.connect(self._on_worker_error)
        self.current_worker.progress.connect(self.status_bar.showMessage)
        self.current_worker.start()

    def _on_telegram_finished(self, combos):
        self.progress_bar.setVisible(False)
        self.tg_btn.setEnabled(True)

        self.tg_table.setRowCount(len(combos))
        for i, c in enumerate(combos):
            self.tg_table.setItem(i, 0, QTableWidgetItem(c.email))
            pw = c.password[:15] + "***" if len(c.password) > 15 else c.password
            self.tg_table.setItem(i, 1, QTableWidgetItem(pw))
            self.tg_table.setItem(i, 2, QTableWidgetItem(c.domain))
            self.tg_table.setItem(i, 3, QTableWidgetItem(c.source_type))
            self.tg_table.setItem(i, 4, QTableWidgetItem(c.quality))

        self.tg_info.setText(f"✅ {len(combos)} combos encontrados en Telegram para '{self.tg_input.text()}'")
        self.status_bar.showMessage(f"✅ Telegram completo: {len(combos)} combos")

    # ══════════════════════════════════════════════════════════
    #  PROXY TAB
    # ══════════════════════════════════════════════════════════

    def _create_proxy_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # ── KPIs ──
        kpi_group = QGroupBox("🌐 Proxy Pool")
        kpi_layout = QHBoxLayout(kpi_group)

        for key, label, color in [
            ("total", "Total", "#6c5ce7"), ("alive", "Vivos", "#00b894"),
            ("dead", "Muertos", "#e17055"), ("untested", "Sin testear", "#fdcb6e"),
        ]:
            kpi = QLabel(f"{label}: 0")
            kpi.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {color}; padding: 6px 12px;"
                              f"background: #12122a; border-radius: 6px; border: 1px solid #2a2a4e;")
            kpi_layout.addWidget(kpi)
            self.__dict__[f"proxy_kpi_{key}"] = kpi

        layout.addWidget(kpi_group)

        # ── Actions ──
        actions_group = QGroupBox("⚙️ Acciones")
        actions_layout = QHBoxLayout(actions_group)

        scrape_btn = QPushButton("🕸️ Scrapear Proxies")
        scrape_btn.clicked.connect(lambda: self._do_proxy("scrape"))
        actions_layout.addWidget(scrape_btn)

        test_btn = QPushButton("🧪 Testear Proxies")
        test_btn.clicked.connect(lambda: self._do_proxy("test"))
        actions_layout.addWidget(test_btn)

        auto_btn = QPushButton("⚡ Auto-poblar Pool")
        auto_btn.setStyleSheet("QPushButton { background-color: #a855f7; }")
        auto_btn.clicked.connect(lambda: self._do_proxy("autopopulate"))
        actions_layout.addWidget(auto_btn)

        vpn_btn = QPushButton("🔍 Detectar VPN")
        vpn_btn.clicked.connect(self._detect_vpn)
        actions_layout.addWidget(vpn_btn)

        actions_layout.addStretch()
        layout.addWidget(actions_group)

        # ── Log ──
        log_group = QGroupBox("📋 Log")
        log_layout = QVBoxLayout(log_group)
        self.proxy_log = QTextEdit()
        self.proxy_log.setReadOnly(True)
        self.proxy_log.setMaximumHeight(200)
        log_layout.addWidget(self.proxy_log)
        layout.addWidget(log_group)

        self.tabs.addTab(tab, "🌐 Proxies")

    def _do_proxy(self, action):
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.current_worker = ProxyWorker(action)
        self.current_worker.finished.connect(lambda r: self._on_proxy_finished(r, action))
        self.current_worker.error.connect(self._on_worker_error)
        self.current_worker.progress.connect(lambda m: self.proxy_log.append(m))
        self.current_worker.start()

    def _on_proxy_finished(self, result, action):
        self.progress_bar.setVisible(False)

        if isinstance(result, dict):
            if "pool" in result or "alive" in result:
                pool = result if "alive" in result else result.get("pool", {})
                self.proxy_kpi_total.setText(f"📦 Total: {pool.get('total', 0)}")
                self.proxy_kpi_alive.setText(f"✅ Vivos: {pool.get('alive', 0)}")
                self.proxy_kpi_dead.setText(f"💀 Muertos: {pool.get('dead', 0)}")
                self.proxy_kpi_untested.setText(f"❓ Sin testear: {pool.get('untested', 0)}")

        action_msg = {"scrape": "Scrapeo completado", "test": "Test completado",
                      "autopopulate": "Pool auto-poblado"}.get(action, "Completado")
        self.proxy_log.append(f"✅ {action_msg}")
        self.status_bar.showMessage(f"✅ {action_msg}")

    def _detect_vpn(self):
        try:
            info = detect_vpn()
            msg = (f"🌐 VPN Detection:\n"
                   f"   IP: {info.get('ip', 'N/A')}\n"
                   f"   País: {info.get('country', 'N/A')}\n"
                   f"   ISP: {info.get('isp', 'N/A')}\n"
                   f"   VPN: {'🔒 SÍ' if info.get('vpn') else '🔓 NO'}\n"
                   f"   Hosting: {'🏢 SÍ' if info.get('hosting') else '🏠 NO'}")
            self.proxy_log.append(msg)
        except Exception as e:
            self.proxy_log.append(f"❌ VPN detection error: {e}")

    # ══════════════════════════════════════════════════════════
    #  STATS TAB
    # ══════════════════════════════════════════════════════════

    def _create_stats_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        # ── System Info ──
        sys_group = QGroupBox("💻 Información del Sistema")
        sys_layout = QVBoxLayout(sys_group)

        info_lines = [
            f"🐍 Python: {sys.version.split()[0]}",
            f"🏗️ Plataforma: {sys.platform}",
            f"🕐 Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        for line in info_lines:
            lbl = QLabel(line)
            lbl.setStyleSheet("color: #e0e0f0; font-size: 11px; padding: 2px 0; font-family: monospace;")
            sys_layout.addWidget(lbl)

        layout.addWidget(sys_group)

        # ── Engine Status ──
        engine_group = QGroupBox("⚙️ Estado de Motores")
        engine_layout = QVBoxLayout(engine_group)

        self.engine_info = QLabel("Cargando información de motores...")
        self.engine_info.setStyleSheet("color: #8888aa; font-size: 11px;")
        engine_layout.addWidget(self.engine_info)

        refresh_btn = QPushButton("🔄 Refrescar Estado")
        refresh_btn.clicked.connect(self._refresh_engine_stats)
        engine_layout.addWidget(refresh_btn)

        layout.addWidget(engine_group)

        # ── API Status ──
        api_group = QGroupBox("🔌 APIs de Inteligencia")
        api_layout = QVBoxLayout(api_group)

        self.api_info = QLabel("Verificando APIs configuradas...")
        self.api_info.setStyleSheet("color: #8888aa; font-size: 11px;")
        api_layout.addWidget(self.api_info)

        check_btn = QPushButton("🔍 Verificar APIs")
        check_btn.clicked.connect(self._check_apis)
        api_layout.addWidget(check_btn)

        layout.addWidget(api_group)
        layout.addStretch()

        self.tabs.addTab(tab, "📊 Stats")

        # Load initial info
        QTimer.singleShot(500, self._refresh_engine_stats)
        QTimer.singleShot(1000, self._check_apis)

    def _refresh_engine_stats(self):
        try:
            oracle = get_oracle()
            stats = oracle.base_engine.get_index_stats() if oracle else {"total_records": 0}

            tg = get_telegram()
            tg_stats = tg.get_stats() if tg else {}

            self.engine_info.setText(
                f"📦 Oracle Engine: {stats.get('total_records', 0)} registros indexados\n"
                f"🔑 Keywords: {stats.get('total_keywords', 0)}\n"
                f"🔄 Búsquedas: {stats.get('total_searches', 0)}\n"
                f"🗄️ Index mode: {'Elasticsearch' if stats.get('using_elasticsearch') else 'Memoria'}\n"
                f"💬 Telegram: {'✅ Conectado' if tg_stats.get('connected') else '❌ No conectado'}\n"
                f"📡 Mensajes escaneados: {tg_stats.get('messages_scanned', 0)}"
            )
            self.status_bar.showMessage("🔄 Estado actualizado")
        except Exception as e:
            self.engine_info.setText(f"❌ Error: {e}")

    def _check_apis(self):
        try:
            from intel_connectors import IntelOrchestrator
            orch = IntelOrchestrator()
            apis = orch.available_apis

            if apis:
                self.api_info.setText(
                    "✅ APIs configuradas:\n" +
                    "\n".join(f"   • {api}" for api in apis)
                )
            else:
                self.api_info.setText(
                    "⚠️ Ninguna API externa configurada.\n"
                    "   Configura las keys en el archivo .env\n"
                    "   Las APIs disponibles son: Shodan, Hunter.io,\n"
                    "   HaveIBeenPwned, VirusTotal, Censys"
                )
        except Exception as e:
            self.api_info.setText(f"❌ Error al verificar APIs: {e}")

    # ══════════════════════════════════════════════════════════
    #  EXPORT FUNCTIONS
    # ══════════════════════════════════════════════════════════

    def _export_search(self):
        if not self.search_data:
            QMessageBox.warning(self, "⚠️ Sin datos", "No hay datos de búsqueda para exportar.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Guardar CSV", "oraculo_search.csv", "CSV (*.csv)")
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("severidad,tipo,email,dominio,contenido,fuente,fecha\n")
                for r in self.search_data:
                    f.write(f'"{r.get("severity","")}","{r.get("record_type","")}",'
                            f'"{r.get("email","")}","{r.get("domain","")}",'
                            f'"{r.get("content_preview","").replace(chr(34),chr(34)+chr(34))}",'
                            f'"{r.get("source_type","")}","{r.get("discovered_date","")}"\n')
            QMessageBox.information(self, "✅ Exportado", f"Datos exportados a:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"Error al exportar: {e}")

    def _export_dump(self, fmt):
        if not self.dump_data:
            QMessageBox.warning(self, "⚠️ Sin datos", "No hay datos de dump para exportar.")
            return

        ext = {"txt": "TXT (*.txt)", "csv": "CSV (*.csv)", "json": "JSON (*.json)"}
        path, _ = QFileDialog.getSaveFileName(self, "Guardar archivo", f"dump.{fmt}", ext.get(fmt, "All (*.*)"))
        if not path:
            return

        try:
            keyword = self.dump_input.text().strip() or "dump"
            ts = datetime.now().strftime("%Y%m%d")

            if fmt == "txt":
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# Dump Finder - {keyword} - {ts}\n# Format: email:password\n\n")
                    for c in self.dump_data:
                        f.write(f"{c.get('email','')}:{c.get('password','')}  #{c.get('domain','')}\n")

            elif fmt == "csv":
                with open(path, "w", encoding="utf-8") as f:
                    f.write("email,password,dominio,fuente,fecha\n")
                    for c in self.dump_data:
                        f.write(f'"{c.get("email","")}","{c.get("password","")}",'
                                f'"{c.get("domain","")}","{c.get("source","")}","{c.get("date","")}"\n')

            elif fmt == "json":
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"keyword": keyword, "ts": ts, "combos": self.dump_data}, f, indent=2)

            QMessageBox.information(self, "✅ Exportado", f"Datos exportados a:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"Error al exportar: {e}")

    def _export_combo(self, fmt):
        """Export combo data."""
        QMessageBox.information(self, "ℹ️ Exportar",
                                f"Exportar en formato {fmt.upper()}. "
                                f"Usa la API REST para exportaciones completas o "
                                f"revisa la carpeta 'data/' para archivos guardados.")

    # ══════════════════════════════════════════════════════════
    #  ERROR HANDLER
    # ══════════════════════════════════════════════════════════

    def _on_worker_error(self, error_msg):
        self.progress_bar.setVisible(False)
        # Re-enable all operation buttons
        for btn_name in ['search_btn', 'dump_btn', 'combo_btn', 'tg_btn']:
            btn = getattr(self, btn_name, None)
            if isinstance(btn, QPushButton):
                btn.setEnabled(True)

        QMessageBox.critical(self, "❌ Error", f"Error en la operación:\n{error_msg}")
        self.status_bar.showMessage(f"❌ Error: {error_msg}")


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    """Launch the desktop application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Oráculo de Inteligencia Desktop")
    app.setApplicationVersion("1.0.0")

    # Set app icon if available
    try:
        app.setWindowIcon(QIcon())
    except Exception:
        pass

    window = OracleDesktop()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
