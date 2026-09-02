APP_STYLESHEET = """
QWidget {
    color: #f4f1fb;
    font-family: "Segoe UI";
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #191725; }
QLabel {
    background-color: transparent;
    border: none;
}
QCheckBox {
    background-color: transparent;
    border: none;
    spacing: 6px;
}
QCheckBox:disabled {
    background-color: transparent;
    color: #817a91;
}
QScrollArea, QScrollArea > QWidget > QWidget, QAbstractScrollArea::viewport {
    background-color: transparent;
    border: none;
}
QFrame#Sidebar {
    background-color: #242033;
    border: none;
    border-right: 1px solid #332e46;
}
QFrame#ContentArea { background-color: #1d1a2a; border: none; }
QFrame#BrandCard {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 #7a4dff,
        stop: 0.52 #d747c5,
        stop: 1 #18c2cc
    );
    border: none;
    border-radius: 12px;
}
QLabel#BrandTitle {
    color: #ffffff;
    font-size: 21px;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#BrandSubtitle {
    color: #fff8cf;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}
QLabel#SidebarSection {
    color: #8d879e;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 8px 6px 2px 6px;
}
QFrame#TopBar, QFrame#FilterBar {
    background-color: #292638;
    border: 1px solid #373249;
    border-radius: 10px;
}
QGroupBox {
    background-color: #292638;
    border: 1px solid #373249;
    border-radius: 10px;
    margin-top: 16px;
    padding: 18px 12px 12px 12px;
    font-weight: 600;
    color: #b7a9ff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 7px;
    background-color: transparent;
    color: #b7a9ff;
}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget, QTreeWidget {
    background-color: #211e2f;
    color: #e6deee;
    border: 1px solid #3a354d;
    border-radius: 6px;
    padding: 7px;
    selection-background-color: #7a4dff;
    selection-color: #fff1b8;
}
QComboBox QAbstractItemView, QListView {
    background-color: #211e2f;
    color: #ddd5e8;
    border: 1px solid #49425f;
    outline: 0;
    padding: 4px;
    selection-background-color: #6840df;
    selection-color: #fff1b8;
}
QComboBox QAbstractItemView::item, QListView::item {
    min-height: 26px;
    padding: 5px 8px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #18c2cc;
    background-color: #252137;
}
QLineEdit:read-only, QTextEdit:read-only {
    background-color: #242132;
    color: #d7d1e2;
}
QPushButton {
    background-color: #332e47;
    border: 1px solid #49425f;
    border-radius: 6px;
    padding: 8px 13px;
    color: #f4f1fb;
}
QPushButton:hover {
    background-color: #443b61;
    border-color: #7a4dff;
    color: #ffffff;
}
QPushButton:pressed { background-color: #6840df; }
QPushButton:disabled { background-color: #2b2738; border-color: #373245; color: #6f697d; }
QPushButton#accentButton {
    background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0, stop: 0 #7a4dff, stop: 1 #c947c5);
    border: 1px solid #976eff;
    color: #ffffff;
    font-weight: 700;
}
QPushButton#accentButton:hover { border-color: #18c2cc; }
QPushButton#dangerButton {
    background-color: #372539;
    color: #ff7ca9;
    border-color: #f45a91;
}
QPushButton#dangerButton:hover { background-color: #f45a91; color: #201525; }
QPushButton#ModeButton { text-align: left; padding: 10px 12px; }
QPushButton#TopModeButton {
    background-color: #3a344d;
    border-color: #655d79;
    font-weight: 650;
}
QPushButton#TopModeButton:hover { background-color: #7a4dff; border-color: #b99bff; }
QTreeWidget {
    background-color: transparent;
    border: none;
    padding: 2px;
    outline: none;
}
QTreeWidget::item { padding: 7px 6px; border-radius: 5px; }
QTreeWidget::item:hover { background-color: #302b43; }
QTreeWidget::item:selected { background-color: #6e46df; color: #ffffff; }
QHeaderView::section {
    background-color: #312d43;
    color: #c8c1d5;
    padding: 8px;
    border: none;
    border-bottom: 1px solid #443e58;
}
QTabWidget::pane { background-color: #292638; border: 1px solid #373249; border-radius: 8px; }
QTabBar::tab {
    background: #252132;
    color: #918a9f;
    padding: 9px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:hover { color: #ffffff; }
QTabBar::tab:selected { color: #ffffff; border-bottom: 2px solid #9a67ff; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #50486a; min-height: 32px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #7a4dff; }
QScrollBar:add-line:vertical, QScrollBar:sub-line:vertical { height: 0; }
QMenuBar { background-color: #211e2f; color: #d8d2e2; }
QMenuBar::item:selected { background-color: #39334d; }
QMenu { background-color: #292638; border: 1px solid #443e58; }
QMenu::item:selected { background-color: #6e46df; color: #ffffff; }
QToolTip { background: #312d43; color: #ffffff; border: 1px solid #7a4dff; }
QLabel#PageTitle { color: #ffffff; font-size: 18px; font-weight: 700; padding-right: 6px; }
QLabel#ModeStatus {
    color: #18c2cc;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
    padding-right: 6px;
}
QLabel#ModeStatus[admin="true"] { color: #f45a91; }
QLabel#TitleLabel { color: #ffffff; font-size: 22px; font-weight: 750; }
QLabel#SectionTitle { color: #b7a9ff; font-size: 14px; font-weight: 700; }
QLabel#MutedLabel { color: #817a91; }
QCheckBox::indicator { width: 15px; height: 15px; }
QCheckBox::indicator:unchecked { background: #211e2f; border: 1px solid #514a63; border-radius: 3px; }
QCheckBox::indicator:checked { background: #7a4dff; border: 2px solid #b99bff; border-radius: 3px; }
QSplitter#MainSplitter::handle { background-color: #332e46; width: 1px; }
"""
