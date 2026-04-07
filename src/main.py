#!/usr/bin/env python3
"""STM32F407 UART programmer — application entry."""

import sys

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow

DARK_STYLESHEET = """
QWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
}
QGroupBox {
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin-top: 8px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 4px;
    color: #d4d4d4;
}
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #2d2d2d;
    border: 1px solid #3c3c3c;
    color: #d4d4d4;
    border-radius: 3px;
    padding: 4px;
}
QPushButton {
    background-color: #0e639c;
    color: #ffffff;
    border: none;
    border-radius: 3px;
    padding: 6px 16px;
    min-width: 70px;
}
QPushButton:hover {
    background-color: #1177bb;
}
QPushButton:pressed {
    background-color: #0d5a8c;
}
QPushButton:disabled {
    background-color: #3c3c3c;
    color: #6e6e6e;
}
QComboBox {
    background-color: #2d2d2d;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    padding: 4px;
    color: #d4d4d4;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid #d4d4d4;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    border: 1px solid #3c3c3c;
    color: #d4d4d4;
    selection-background-color: #0e639c;
}
QCheckBox {
    color: #d4d4d4;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #6e6e6e;
    background-color: #2d2d2d;
}
QCheckBox::indicator:checked {
    background-color: #0e639c;
    border-color: #0e639c;
}
QSpinBox {
    background-color: #2d2d2d;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    padding: 4px;
    color: #d4d4d4;
}
QProgressBar {
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    background-color: #2d2d2d;
    text-align: center;
    color: #d4d4d4;
}
QProgressBar::chunk {
    background-color: #0e639c;
    border-radius: 3px;
}
QLabel {
    color: #d4d4d4;
}
QMessageBox {
    background-color: #1e1e1e;
}
QMessageBox QLabel {
    color: #d4d4d4;
}
QMessageBox QPushButton {
    min-width: 80px;
}
"""


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("STM32 UART Programmer")
    app.setStyleSheet(DARK_STYLESHEET)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
