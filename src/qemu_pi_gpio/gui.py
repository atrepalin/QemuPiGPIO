"""Qt GUI for QEMU Raspberry Pi 3B GPIO with virtual cables."""

from __future__ import annotations

import argparse
import time
from collections import deque

import pyqtgraph as pg
from PySide6.QtCore import QObject, QPointF, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .gpio import BCM2837GPIO, GPIO_COUNT
from .qtest import QTestClient, QTestError

STYLE = """
QMainWindow, QWidget {
    background-color: #111827;
    color: #e5e7eb;
    font-size: 13px;
}

QFrame#Card {
    background-color: #1f2937;
    border: 1px solid #374151;
    border-radius: 12px;
}

QLabel {
    background-color: transparent;
    color: #e5e7eb;
}

QLabel#Title {
    font-size: 23px;
    font-weight: bold;
    color: #f9fafb;
}

QLabel#Metric {
    font-size: 25px;
    font-weight: bold;
    color: #60a5fa;
}

QLabel#Muted {
    color: #9ca3af;
    background-color: transparent;
}

QPushButton {
    background-color: #374151;
    color: #f9fafb;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 9px 15px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #4b5563;
}

QPushButton:pressed {
    background-color: #334155;
}

QPushButton:disabled {
    color: #6b7280;
    background-color: #263244;
}

QPushButton#Primary {
    background-color: #2563eb;
    color: #ffffff;
}

QPushButton#Primary:hover {
    background-color: #1d4ed8;
}

QPushButton#Danger {
    background-color: #991b1b;
    color: #ffffff;
}

QSpinBox, QDoubleSpinBox,
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #1f2937;
    color: #f9fafb;
    border: 1px solid #64748b;
    border-radius: 7px;
    padding: 5px 8px;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QSpinBox, QDoubleSpinBox {
    min-height: 30px;
    padding-right: 32px;
}

QSpinBox::up-button,
QDoubleSpinBox::up-button,
QSpinBox::down-button,
QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    width: 28px;
    background-color: #374151;
    border-left: 1px solid #64748b;
}

QSpinBox::up-button,
QDoubleSpinBox::up-button {
    subcontrol-position: top right;
    border-top-right-radius: 6px;
    border-bottom: 1px solid #64748b;
}

QSpinBox::down-button,
QDoubleSpinBox::down-button {
    subcontrol-position: bottom right;
    border-bottom-right-radius: 6px;
}

QSpinBox::up-button:hover,
QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover,
QDoubleSpinBox::down-button:hover {
    background-color: #2563eb;
}

QCheckBox {
    background-color: transparent;
    color: #e5e7eb;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
}

QCheckBox::indicator:unchecked {
    background-color: #111827;
    border: 1px solid #64748b;
    border-radius: 4px;
}

QCheckBox::indicator:checked {
    background-color: #2563eb;
    border: 1px solid #60a5fa;
    border-radius: 4px;
}

QCheckBox::indicator:disabled {
    border-color: #374151;
    background-color: #263244;
}

QTableWidget {
    background-color: #1f2937;
    alternate-background-color: #243244;
    color: #e5e7eb;
    gridline-color: #374151;
    border: 1px solid #374151;
    border-radius: 8px;
    selection-background-color: #1d4ed8;
    selection-color: #ffffff;
    outline: 0;
}

QTableWidget::item {
    background-color: transparent;
    color: #e5e7eb;
    padding: 4px;
}

QTableWidget::item:alternate {
    background-color: #243244;
    color: #e5e7eb;
}

QTableWidget::item:selected,
QTableWidget::item:selected:active,
QTableWidget::item:selected:!active,
QTableWidget::item:alternate:selected,
QTableWidget::item:alternate:selected:active,
QTableWidget::item:alternate:selected:!active {
    background-color: #1d4ed8;
    color: #ffffff;
}

QHeaderView::section {
    background-color: #374151;
    color: #f9fafb;
    padding: 9px;
    border: none;
    font-weight: bold;
}

QTabWidget::pane {
    background-color: #111827;
    border: 1px solid #374151;
    border-radius: 8px;
}

QTabBar::tab {
    background-color: #1f2937;
    color: #e5e7eb;
    padding: 11px 20px;
    margin-right: 4px;
    border-radius: 6px;
}

QTabBar::tab:selected {
    background-color: #2563eb;
    color: #ffffff;
}
"""


# ---------------------------------------------------------------------------
# Virtual wiring widget
# ---------------------------------------------------------------------------


class WiringWidget(QWidget):
    """Scrollable GPIO wiring diagram."""

    COLORS = [
        "#60a5fa",
        "#f87171",
        "#4ade80",
        "#fbbf24",
        "#c084fc",
        "#fb923c",
        "#2dd4bf",
        "#f472b6",
        "#a3e635",
        "#e879f9",
    ]

    ROW_HEIGHT = 30
    TOP_MARGIN = 70
    BOTTOM_MARGIN = 35

    def __init__(self, gpio_count: int, parent=None):
        super().__init__(parent)

        self.gpio_count = gpio_count
        self.connections: set[tuple[int, int]] = set()
        self.levels: dict[int, int] = {}
        self.modes: dict[int, str] = {}

        self.setMinimumSize(500, 350)

    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        return self.sizeHintForContents()

    def sizeHintForContents(self):
        return QSize(
            600,
            self.TOP_MARGIN
            + max(1, self.gpio_count) * self.ROW_HEIGHT
            + self.BOTTOM_MARGIN,
        )

    def add_connection(self, pin_a: int, pin_b: int) -> bool:
        if pin_a == pin_b:
            return False

        if not (0 <= pin_a < self.gpio_count and 0 <= pin_b < self.gpio_count):
            return False

        connection = tuple(sorted((pin_a, pin_b)))
        if connection in self.connections:
            return False

        self.connections.add(connection)
        self.update()
        return True

    def remove_connection(self, pin_a: int, pin_b: int):
        self.connections.discard(tuple(sorted((pin_a, pin_b))))
        self.update()

    def clear_connections(self):
        self.connections.clear()
        self.update()

    def set_snapshot(self, snapshot):
        self.levels = {pin: level for pin, _mode, level, _function in snapshot}
        self.modes = {pin: mode for pin, mode, _level, _function in snapshot}
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#111827"))

        width = self.width()

        left_x = 115
        right_x = width - 115

        painter.setPen(QColor("#f9fafb"))
        painter.drawText(18, 25, "VIRTUAL GPIO WIRING")

        painter.setPen(QColor("#9ca3af"))
        painter.drawText(18, 47, "BCM2837 / QEMU")

        painter.setPen(QColor("#60a5fa"))
        painter.drawText(left_x - 32, 58, "PIN A")

        painter.setPen(QColor("#fbbf24"))
        painter.drawText(right_x - 32, 58, "PIN B")

        def position(pin: int, side: int) -> QPointF:
            x = left_x if side == 0 else right_x
            y = self.TOP_MARGIN + pin * self.ROW_HEIGHT
            return QPointF(x, y)

        for index, (pin_a, pin_b) in enumerate(sorted(self.connections)):
            painter.setPen(
                QPen(
                    QColor(self.COLORS[index % len(self.COLORS)]),
                    3,
                )
            )
            painter.drawLine(
                position(pin_b, 0),
                position(pin_a, 1),
            )

        for pin in range(self.gpio_count):
            for side in (0, 1):
                point = position(pin, side)
                mode = self.modes.get(pin, "").lower()
                level = self.levels.get(pin)

                if level == 1:
                    fill = QColor("#16a34a")
                elif level == 0:
                    fill = QColor("#dc2626")
                elif "out" in mode:
                    fill = QColor("#2563eb")
                elif "in" in mode:
                    fill = QColor("#0d9488")
                else:
                    fill = QColor("#475569")

                painter.setPen(QPen(QColor("#cbd5e1"), 1))
                painter.setBrush(fill)
                painter.drawEllipse(point, 5, 5)

                painter.setPen(QColor("#e5e7eb"))

                if side == 0:
                    painter.drawText(
                        int(point.x() - 100),
                        int(point.y() + 5),
                        f"GPIO {pin}",
                    )
                else:
                    painter.drawText(
                        int(point.x() + 12),
                        int(point.y() + 5),
                        f"GPIO {pin}",
                    )

        painter.setPen(QColor("#9ca3af"))
        painter.drawText(
            18,
            self.height() - 10,
            "Green = HIGH | Red = LOW | Blue = output | Teal = input",
        )


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


class GPIOWorker(QObject):
    connected_changed = Signal(bool)
    polling_changed = Signal(bool)
    snapshot_ready = Signal(object, bool)
    error_occurred = Signal(str, str)
    stopped = Signal()

    connect_requested = Signal()
    disconnect_requested = Signal()
    poll_requested = Signal(bool)
    start_polling_requested = Signal(int)
    stop_polling_requested = Signal()
    set_mode_requested = Signal(int, str)
    write_requested = Signal(int, int)
    set_wiring_requested = Signal(object)
    shutdown_requested = Signal()

    UI_INTERVAL_MS = 200
    WIRING_INTERVAL_MS = 50

    def __init__(self, socket_path: str):
        super().__init__()

        self.socket_path = socket_path
        self.client = None
        self.gpio = None

        self.connected = False
        self.polling = False
        self.shutting_down = False

        self.ui_timer = None
        self.poll_timer = None
        self.wiring_timer = None

        self.connections: set[tuple[int, int]] = set()

        self.connect_requested.connect(self.connect_to_qemu)
        self.disconnect_requested.connect(self.disconnect_from_qemu)
        self.poll_requested.connect(self.poll_once)
        self.start_polling_requested.connect(self.start_polling)
        self.stop_polling_requested.connect(self.stop_polling)
        self.set_mode_requested.connect(self.set_mode)
        self.write_requested.connect(self.write_level)
        self.set_wiring_requested.connect(self.set_wiring)
        self.shutdown_requested.connect(self.shutdown)

    @Slot()
    def initialize(self):
        # All timers and GPIO/QTest operations run in this worker thread.
        self.ui_timer = QTimer(self)
        self.ui_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.ui_timer.setInterval(self.UI_INTERVAL_MS)
        self.ui_timer.timeout.connect(self._on_ui_timer)

        self.poll_timer = QTimer(self)
        self.poll_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.poll_timer.timeout.connect(self._on_poll_timer)

        self.wiring_timer = QTimer(self)
        self.wiring_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.wiring_timer.setInterval(self.WIRING_INTERVAL_MS)
        self.wiring_timer.timeout.connect(self._on_wiring_timer)

    def _report_error(self, title: str, exc: Exception):
        self.error_occurred.emit(title, str(exc))

    def _close_client(self):
        if self.client is not None:
            try:
                self.client.close()
            except (OSError, QTestError, RuntimeError):
                pass

        self.client = None
        self.gpio = None

    @Slot()
    def connect_to_qemu(self):
        if self.shutting_down or self.connected:
            return

        try:
            self.client = QTestClient(self.socket_path)
            self.gpio = BCM2837GPIO(self.client)
            self.client.connect()

            self.connected = True
            self.connected_changed.emit(True)

            if self.ui_timer is not None:
                self.ui_timer.start()

            if self.wiring_timer is not None:
                self.wiring_timer.start()

            self.poll_once(False)

        except (OSError, QTestError, ValueError, RuntimeError) as exc:
            self.connected = False

            if self.ui_timer is not None:
                self.ui_timer.stop()

            if self.wiring_timer is not None:
                self.wiring_timer.stop()

            self._close_client()
            self.connected_changed.emit(False)
            self._report_error("Connection failed", exc)

    @Slot()
    def disconnect_from_qemu(self):
        if self.ui_timer is not None:
            self.ui_timer.stop()

        if self.wiring_timer is not None:
            self.wiring_timer.stop()

        self.stop_polling()

        was_connected = self.connected
        self.connected = False
        self._close_client()

        if was_connected:
            self.connected_changed.emit(False)

    @Slot()
    def _on_ui_timer(self):
        if self.connected and not self.shutting_down:
            self.poll_once(False)

    @Slot(int)
    def start_polling(self, interval_ms: int):
        if self.shutting_down:
            return

        if not self.connected or self.poll_timer is None:
            self._report_error(
                "Not connected",
                RuntimeError("Connect to QEMU first."),
            )
            return

        if self.polling:
            return

        self.poll_timer.setInterval(max(50, int(interval_ms)))

        self.polling = True
        self.polling_changed.emit(True)

        self.poll_once(True)
        self.poll_timer.start()

    @Slot()
    def stop_polling(self):
        if self.poll_timer is not None:
            self.poll_timer.stop()

        was_polling = self.polling
        self.polling = False

        if was_polling:
            self.polling_changed.emit(False)

    @Slot()
    def _on_poll_timer(self):
        if self.polling and self.connected:
            self.poll_once(True)

    @Slot(bool)
    def poll_once(self, record_history: bool = False):
        if not self.connected or self.gpio is None:
            return

        record_history = bool(record_history and self.polling)

        try:
            snapshot = []

            for pin in range(GPIO_COUNT):
                state = self.gpio.state(pin)

                snapshot.append(
                    (
                        pin,
                        str(state.mode),
                        state.level,
                        str(state.function),
                    )
                )

            self.snapshot_ready.emit(snapshot, record_history)

        except (
            QTestError,
            OSError,
            ValueError,
            RuntimeError,
        ) as exc:
            self.stop_polling()
            self._report_error("GPIO polling failed", exc)
            self.disconnect_from_qemu()

    @Slot(int, str)
    def set_mode(self, pin: int, mode: str):
        if not self.connected or self.gpio is None:
            self._report_error(
                "Not connected",
                RuntimeError("Connect to QEMU first."),
            )
            return

        try:
            self.gpio.set_mode(pin, mode)
            self.poll_once(False)
        except (
            QTestError,
            OSError,
            ValueError,
            RuntimeError,
        ) as exc:
            self._report_error("GPIO mode change failed", exc)

    @Slot(int, int)
    def write_level(self, pin: int, level: int):
        if not self.connected or self.gpio is None:
            self._report_error(
                "Not connected",
                RuntimeError("Connect to QEMU first."),
            )
            return

        try:
            self.gpio.write(pin, level)
            self.poll_once(False)
        except (
            QTestError,
            OSError,
            ValueError,
            RuntimeError,
        ) as exc:
            self._report_error("GPIO write failed", exc)

    # ------------------------------------------------------------------
    # Virtual cable propagation
    # ------------------------------------------------------------------

    @Slot(object)
    def set_wiring(self, connections):
        """Receive the current cable list from the GUI thread."""
        self.connections = {
            tuple(sorted((int(a), int(b)))) for a, b in connections if int(a) != int(b)
        }

    @staticmethod
    def _is_output(mode: str) -> bool:
        mode = str(mode).strip().lower()
        return mode in ("out", "output") or "gpio_mode_output" in mode

    @staticmethod
    def _is_input(mode: str) -> bool:
        mode = str(mode).strip().lower()
        return mode in ("in", "input") or "gpio_mode_input" in mode

    @Slot()
    def _on_wiring_timer(self):
        """
        Propagate output levels to input pins.

        A cable is active only if exactly one endpoint is an output
        and the other endpoint is an input. The direction is discovered
        from the actual GPIO modes on every timer tick.
        """
        if (
            not self.connected
            or self.gpio is None
            or self.shutting_down
            or not self.connections
        ):
            return

        try:
            # Read each pin at most once during this timer tick.
            states = {}

            for a, b in self.connections:
                for pin in (a, b):
                    if pin not in states:
                        state = self.gpio.state(pin)
                        states[pin] = (
                            str(state.mode),
                            state.level,
                        )

            for pin_a, pin_b in sorted(self.connections):
                mode_a, level_a = states[pin_a]
                mode_b, level_b = states[pin_b]

                a_out = self._is_output(mode_a)
                b_out = self._is_output(mode_b)
                a_in = self._is_input(mode_a)
                b_in = self._is_input(mode_b)

                # Exactly one output and one input are required.
                if a_out and b_in:
                    source_pin, source_level = pin_a, level_a
                    target_pin, target_level = pin_b, level_b
                elif b_out and a_in:
                    source_pin, source_level = pin_b, level_b
                    target_pin, target_level = pin_a, level_a
                else:
                    # Both input, both output, or unknown modes.
                    continue

                if source_level not in (0, 1):
                    continue

                if target_level == source_level:
                    continue

                self.gpio.write(target_pin, int(source_level))

                # Keep the cached state accurate for this tick.
                old_mode, _ = states[target_pin]
                states[target_pin] = (old_mode, int(source_level))

        except (
            QTestError,
            OSError,
            ValueError,
            RuntimeError,
        ) as exc:
            if self.wiring_timer is not None:
                self.wiring_timer.stop()

            self._report_error("Virtual wiring failed", exc)
            self.disconnect_from_qemu()

    @Slot()
    def shutdown(self):
        if self.shutting_down:
            return

        self.shutting_down = True

        if self.ui_timer is not None:
            self.ui_timer.stop()

        if self.wiring_timer is not None:
            self.wiring_timer.stop()

        self.stop_polling()

        was_connected = self.connected
        self.connected = False
        self._close_client()

        if was_connected:
            self.connected_changed.emit(False)

        self.stopped.emit()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class GPIOApp(QMainWindow):
    HISTORY_SIZE = 30000

    def __init__(self, socket_path: str):
        super().__init__()

        self.setWindowTitle("Raspberry Pi 3B | GPIO Monitor")
        self.resize(1200, 820)
        self.setMinimumSize(900, 620)

        self.socket_path = socket_path
        self.connected = False
        self.polling = False
        self.closing = False

        self.started_at = time.monotonic()
        self.samples = 0
        self.selected_pin = 17

        self.history = {
            pin: deque(maxlen=self.HISTORY_SIZE) for pin in range(GPIO_COUNT)
        }

        self._build_ui()
        self._init_worker()
        self._update_status()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(15)

        header = QHBoxLayout()
        title_box = QVBoxLayout()

        title = QLabel("GPIO Monitor")
        title.setObjectName("Title")

        subtitle = QLabel("QEMU Raspberry Pi 3B / BCM2837")
        subtitle.setObjectName("Muted")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        self.status = QLabel("● Disconnected")
        self.status.setStyleSheet("color: #f87171; font-weight: bold;")
        header.addWidget(self.status)

        self.connect_button = QPushButton("Connect")
        self.connect_button.setObjectName("Primary")
        self.connect_button.clicked.connect(self._connect)
        header.addWidget(self.connect_button)

        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.clicked.connect(self._disconnect)
        header.addWidget(self.disconnect_button)

        root.addLayout(header)

        metrics = QHBoxLayout()
        self.pin_metric = self._metric_card("Selected GPIO", "17")
        self.level_metric = self._metric_card("Current level", "—")
        self.samples_metric = self._metric_card("Samples", "0")
        self.rate_metric = self._metric_card("Polling", "Stopped")

        for card in (
            self.pin_metric,
            self.level_metric,
            self.samples_metric,
            self.rate_metric,
        ):
            metrics.addWidget(card)

        root.addLayout(metrics)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        self.tabs.addTab(self._build_overview(), "  GPIO Overview  ")
        self.tabs.addTab(self._build_monitor(), "  Live Monitor  ")
        self.tabs.addTab(self._build_wiring(), "  Virtual Wiring  ")

        self.footer = QLabel(f"QTest socket: {self.socket_path}")
        self.footer.setObjectName("Muted")
        root.addWidget(self.footer)

    def _metric_card(self, caption: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 12, 15, 12)

        label = QLabel(caption)
        label.setObjectName("Muted")

        metric = QLabel(value)
        metric.setObjectName("Metric")

        layout.addWidget(label)
        layout.addWidget(metric)

        card.value_label = metric
        return card

    def _build_overview(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 15, 10, 10)
        layout.setSpacing(12)

        controls = QFrame()
        controls.setObjectName("Card")
        row = QHBoxLayout(controls)

        self.mode_checkbox = QCheckBox("Output mode")
        self.mode_checkbox.setChecked(False)
        row.addWidget(self.mode_checkbox)

        self.apply_button = QPushButton("Apply mode")
        self.apply_button.clicked.connect(self.apply_mode)
        row.addWidget(self.apply_button)

        self.read_button = QPushButton("Read")
        self.read_button.clicked.connect(self.refresh_selected)
        row.addWidget(self.read_button)

        self.low_button = QPushButton("Write 0")
        self.low_button.clicked.connect(lambda: self.write_level(0))
        row.addWidget(self.low_button)

        self.high_button = QPushButton("Write 1")
        self.high_button.setObjectName("Primary")
        self.high_button.clicked.connect(lambda: self.write_level(1))
        row.addWidget(self.high_button)

        row.addStretch()
        layout.addWidget(controls)

        self.table = QTableWidget(GPIO_COUNT, 4)
        self.table.setHorizontalHeaderLabels(["BCM GPIO", "Mode", "Level", "Function"])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.itemSelectionChanged.connect(self._select_table_row)

        for pin in range(GPIO_COUNT):
            self.table.setItem(pin, 0, QTableWidgetItem(str(pin)))
            for col in range(1, 4):
                self.table.setItem(pin, col, QTableWidgetItem("—"))

        layout.addWidget(self.table, 1)
        return page

    def _build_monitor(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 15, 10, 10)
        layout.setSpacing(12)

        controls = QFrame()
        controls.setObjectName("Card")
        row = QHBoxLayout(controls)

        row.addWidget(QLabel("Interval (ms)"))

        self.interval = QSpinBox()
        self.interval.setRange(50, 60000)
        self.interval.setSingleStep(50)
        self.interval.setValue(500)
        row.addWidget(self.interval)

        row.addWidget(QLabel("History (seconds)"))

        self.history_seconds = QDoubleSpinBox()
        self.history_seconds.setRange(5, 3600)
        self.history_seconds.setValue(60)
        self.history_seconds.setSuffix(" s")
        self.history_seconds.valueChanged.connect(self._update_chart)
        row.addWidget(self.history_seconds)

        self.start_button = QPushButton("Start analyzer")
        self.start_button.setObjectName("Primary")
        self.start_button.clicked.connect(self.start_polling)
        row.addWidget(self.start_button)

        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_polling)
        row.addWidget(self.stop_button)

        self.follow_checkbox = QCheckBox("Follow live")
        self.follow_checkbox.setChecked(True)
        self.follow_checkbox.toggled.connect(self._set_follow_live)
        row.addWidget(self.follow_checkbox)

        self.clear_button = QPushButton("Clear history")
        self.clear_button.clicked.connect(self.clear_history)
        row.addWidget(self.clear_button)

        row.addStretch()
        layout.addWidget(controls)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("#111827")
        self.plot.setTitle(
            "GPIO level over time",
            color="#f9fafb",
            size="14pt",
        )
        self.plot.setLabel("left", "Logic level")
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setYRange(-0.2, 1.2, padding=0)
        self.plot.getAxis("left").setTicks([[(0, "LOW (0)"), (1, "HIGH (1)")]])
        self.plot.addLegend()
        self.plot.setClipToView(True)
        self.plot.setDownsampling(auto=True, mode="peak")

        self.curve = self.plot.plot(
            [],
            [],
            name="Selected GPIO",
            pen=pg.mkPen("#60a5fa", width=2),
            stepMode="left",
        )
        self.curve.setClipToView(True)
        self.curve.setDownsampling(auto=True, method="peak")

        self.plot.getViewBox().sigRangeChangedManually.connect(
            self._on_manual_plot_navigation
        )

        layout.addWidget(self.plot, 1)

        self.chart_info = QLabel(
            "Connect to QEMU and start the analyzer to collect samples."
        )
        self.chart_info.setObjectName("Muted")
        layout.addWidget(self.chart_info)

        return page

    def _build_wiring(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 15, 10, 10)
        layout.setSpacing(12)

        controls = QFrame()
        controls.setObjectName("Card")
        row = QHBoxLayout(controls)

        row.addWidget(QLabel("From GPIO"))

        self.wire_from = QComboBox()
        self.wire_from.addItems([str(pin) for pin in range(GPIO_COUNT)])
        self.wire_from.setCurrentText("17")
        row.addWidget(self.wire_from)

        row.addWidget(QLabel("To GPIO"))

        self.wire_to = QComboBox()
        self.wire_to.addItems([str(pin) for pin in range(GPIO_COUNT)])
        self.wire_to.setCurrentText("27")
        row.addWidget(self.wire_to)

        self.add_wire_button = QPushButton("Connect cable")
        self.add_wire_button.setObjectName("Primary")
        self.add_wire_button.clicked.connect(self.add_wire)
        row.addWidget(self.add_wire_button)

        self.remove_wire_button = QPushButton("Disconnect cable")
        self.remove_wire_button.clicked.connect(self.remove_wire)
        row.addWidget(self.remove_wire_button)

        self.clear_wires_button = QPushButton("Remove all")
        self.clear_wires_button.setObjectName("Danger")
        self.clear_wires_button.clicked.connect(self.wiring_clear)
        row.addWidget(self.clear_wires_button)

        layout.addWidget(controls)

        self.wiring_scroll = QScrollArea()
        self.wiring_scroll.setWidgetResizable(False)
        self.wiring_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.wiring_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.wiring_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.wiring_scroll.setWidgetResizable(False)

        self.wiring_view = WiringWidget(GPIO_COUNT)
        self.wiring_view.setFixedSize(
            600,
            WiringWidget.TOP_MARGIN
            + GPIO_COUNT * WiringWidget.ROW_HEIGHT
            + WiringWidget.BOTTOM_MARGIN,
        )

        self.wiring_scroll.setWidget(self.wiring_view)
        layout.addWidget(self.wiring_scroll, 1)

        self.wiring_info = QLabel(
            "Connect two GPIO pins. One must be an output " "and the other an input."
        )
        self.wiring_info.setObjectName("Muted")
        layout.addWidget(self.wiring_info)

        return page

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------

    def _init_worker(self):
        self.thread = QThread(self)
        self.worker = GPIOWorker(self.socket_path)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.initialize)

        self.worker.connected_changed.connect(self._on_connection_changed)
        self.worker.polling_changed.connect(self._on_polling_changed)
        self.worker.snapshot_ready.connect(self._on_snapshot)
        self.worker.error_occurred.connect(self._on_worker_error)

        self.worker.stopped.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)

        self.thread.start()

    # ------------------------------------------------------------------
    # Connection state
    # ------------------------------------------------------------------

    def _connect(self):
        if not self.connected:
            self.connect_button.setEnabled(False)
            self.worker.connect_requested.emit()

    def _disconnect(self):
        self.worker.disconnect_requested.emit()

    @Slot(bool)
    def _on_connection_changed(self, connected: bool):
        self.connected = connected
        self._update_status()

        if not connected:
            self.level_metric.value_label.setText("—")
            self.rate_metric.value_label.setText("Stopped")
            self.footer.setText(f"QTest socket: {self.socket_path}")

    def _update_status(self):
        if self.connected:
            self.status.setText("● Connected")
            self.status.setStyleSheet("color: #4ade80; font-weight: bold;")
        else:
            self.status.setText("● Disconnected")
            self.status.setStyleSheet("color: #f87171; font-weight: bold;")

        self.connect_button.setEnabled(not self.connected)
        self.disconnect_button.setEnabled(self.connected)

        for widget in (
            self.mode_checkbox,
            self.apply_button,
            self.read_button,
            self.low_button,
            self.high_button,
        ):
            widget.setEnabled(self.connected)

        self.add_wire_button.setEnabled(self.connected)
        self.remove_wire_button.setEnabled(self.connected)

    @Slot(str, str)
    def _on_worker_error(self, title: str, message: str):
        if self.closing:
            return

        self._update_status()
        QMessageBox.critical(self, title, message)

    @Slot(bool)
    def _on_polling_changed(self, polling: bool):
        self.polling = polling

        self.start_button.setEnabled(not polling)
        self.stop_button.setEnabled(polling)
        self.interval.setEnabled(not polling)

        self.rate_metric.value_label.setText(
            f"{self.interval.value()} ms" if polling else "Stopped"
        )

    # ------------------------------------------------------------------
    # Snapshots and history
    # ------------------------------------------------------------------

    @Slot(object, bool)
    def _on_snapshot(self, snapshot, record_history: bool):
        self.table.setUpdatesEnabled(False)

        try:
            for pin, mode, level, function in snapshot:
                values = (str(pin), mode, str(level), function)

                for col, value in enumerate(values):
                    item = self.table.item(pin, col)

                    if item is None:
                        self.table.setItem(pin, col, QTableWidgetItem(value))
                    elif item.text() != value:
                        item.setText(value)
        finally:
            self.table.setUpdatesEnabled(True)

        # Update the visual wiring panel.
        self.wiring_view.set_snapshot(snapshot)

        selected = next(
            (entry for entry in snapshot if entry[0] == self.selected_pin),
            None,
        )

        if selected is not None:
            self.level_metric.value_label.setText(str(selected[2]))

        if not record_history or not self.polling:
            return

        elapsed = time.monotonic() - self.started_at

        for pin, _mode, level, _function in snapshot:
            if level in (0, 1):
                self.history[pin].append((elapsed, int(level)))

        self.samples += 1
        self.samples_metric.value_label.setText(str(self.samples))

        self.footer.setText(
            f"QTest socket: {self.socket_path}  |  " f"Elapsed: {elapsed:.1f} s"
        )

        self._update_chart()

    def refresh_selected(self):
        if self.connected:
            self.worker.poll_requested.emit(False)

    def apply_mode(self):
        if not self.connected:
            QMessageBox.warning(self, "Not connected", "Connect to QEMU first.")
            return

        mode = "output" if self.mode_checkbox.isChecked() else "input"

        self.worker.set_mode_requested.emit(self.selected_pin, mode)

    def write_level(self, level: int):
        if not self.connected:
            QMessageBox.warning(self, "Not connected", "Connect to QEMU first.")
            return

        self.worker.write_requested.emit(self.selected_pin, level)

    def _select_table_row(self):
        row = self.table.currentRow()
        if row < 0:
            return

        item = self.table.item(row, 0)
        if item is not None:
            self.selected_pin = int(item.text())
            self.pin_metric.value_label.setText(str(self.selected_pin))
            self._update_chart()

    # ------------------------------------------------------------------
    # Virtual cable controls
    # ------------------------------------------------------------------

    def _send_connections_to_worker(self):
        connections = set(self.wiring_view.connections)
        self.worker.set_wiring_requested.emit(connections)

    def add_wire(self):
        pin_a = int(self.wire_from.currentText())
        pin_b = int(self.wire_to.currentText())

        if pin_a == pin_b:
            QMessageBox.warning(
                self,
                "Invalid connection",
                "Choose two different GPIO pins.",
            )
            return

        if not self.wiring_view.add_connection(pin_a, pin_b):
            QMessageBox.information(
                self,
                "Cable exists",
                f"GPIO {pin_a} and GPIO {pin_b} " "are already connected.",
            )
            return

        self._send_connections_to_worker()

        self.wiring_info.setText(
            f"Cable added: GPIO {pin_a} ↔ GPIO {pin_b}. "
            "Signal direction follows the GPIO modes."
        )

    def remove_wire(self):
        pin_a = int(self.wire_from.currentText())
        pin_b = int(self.wire_to.currentText())

        connection = tuple(sorted((pin_a, pin_b)))

        if connection not in self.wiring_view.connections:
            QMessageBox.information(
                self,
                "No cable",
                f"No cable connects GPIO {pin_a} and GPIO {pin_b}.",
            )
            return

        self.wiring_view.remove_connection(pin_a, pin_b)
        self._send_connections_to_worker()

        self.wiring_info.setText(f"Cable removed: GPIO {pin_a} ↔ GPIO {pin_b}")

    def wiring_clear(self):
        self.wiring_view.clear_connections()
        self._send_connections_to_worker()
        self.wiring_info.setText("All virtual cables removed.")

    # ------------------------------------------------------------------
    # Analyzer controls
    # ------------------------------------------------------------------

    def start_polling(self):
        if not self.connected:
            QMessageBox.warning(
                self,
                "Not connected",
                "Connect to QEMU before starting the analyzer.",
            )
            return

        if self.polling:
            return

        self.history[self.selected_pin].clear()
        self.started_at = time.monotonic()

        self.worker.start_polling_requested.emit(self.interval.value())

    def stop_polling(self):
        self.worker.stop_polling_requested.emit()

    # ------------------------------------------------------------------
    # Plot
    # ------------------------------------------------------------------

    def _on_manual_plot_navigation(self, *_):
        if self.follow_checkbox.isChecked():
            self.follow_checkbox.blockSignals(True)
            self.follow_checkbox.setChecked(False)
            self.follow_checkbox.blockSignals(False)

    def _set_follow_live(self, enabled: bool):
        if enabled:
            self._update_chart()

    def _update_chart(self, *_):
        data = self.history[self.selected_pin]

        if not data:
            self.curve.setData([], [])
            self.chart_info.setText("No samples collected.")
            return

        now = time.monotonic() - self.started_at
        window = self.history_seconds.value()
        cutoff = now - window

        visible = []

        for timestamp, level in reversed(data):
            if timestamp < cutoff:
                break
            visible.append((timestamp, level))

        visible.reverse()

        if not visible:
            self.curve.setData([], [])
            self.chart_info.setText("No samples in the selected time window.")
            return

        x = [point[0] for point in visible]
        y = [point[1] for point in visible]

        self.curve.setData(x, y)

        if self.follow_checkbox.isChecked():
            self.plot.setXRange(
                max(0.0, now - window),
                max(window, now),
                padding=0,
            )

        self.chart_info.setText(
            f"GPIO {self.selected_pin}  |  "
            f"{len(visible)} samples  |  "
            f"Current level: {y[-1]}  |  "
            f"Elapsed: {now:.1f} s"
        )

    def clear_history(self):
        for history in self.history.values():
            history.clear()

        self.samples = 0
        self.samples_metric.value_label.setText("0")
        self.started_at = time.monotonic()

        self.curve.setData([], [])
        self.chart_info.setText("History cleared.")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self.closing = True

        if self.thread.isRunning():
            self.worker.shutdown_requested.emit()

            if not self.thread.wait(3000):
                self.thread.quit()
                self.thread.wait()

        event.accept()


def main():
    parser = argparse.ArgumentParser(description="Qt GPIO monitor for QEMU raspi3b")
    parser.add_argument(
        "--socket",
        default="/tmp/qtest.sock",
        help="QEMU QTest Unix socket",
    )
    args = parser.parse_args()

    app = QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)

    window = GPIOApp(args.socket)
    window.show()

    app.exec()


if __name__ == "__main__":
    main()
