import sys
import os

def get_resource_path(relative_path):
    """获取资源文件的正确路径，支持开发环境和打包后环境"""
    try:
        # PyInstaller打包后的临时目录
        base_path = sys._MEIPASS
    except Exception:
        # 开发环境下的当前目录
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def get_stylesheet():
    """生成包含正确资源路径的样式表"""

    # 获取对勾图标的正确路径
    check_icon_path = get_resource_path("assets/check.svg").replace("\\", "/")

    return f"""
/* ---- 全局样式 ---- */
QWidget {{
    background-color: #2c3e50; /* 深蓝灰色背景 */
    color: #ecf0f1; /* 浅灰色文字 */
    font-family: "Microsoft YaHei UI", "SimSun", "Arial"; /* 字体 */
    font-size: 14px;
}}

QMainWindow {{
    background-color: #2c3e50;
}}

/* ---- 标签 ---- */
QLabel {{
    color: #ecf0f1;
    padding: 5px;
}}

/* ---- 按钮 ---- */
QPushButton {{
    background-color: #3498db; /* B站蓝 */
    color: #ffffff;
    border: none;
    padding: 10px 15px;
    border-radius: 8px; /* 圆角 */
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: #5dade2; /* 悬停时变亮 */
}}
QPushButton:pressed {{
    background-color: #2e86c1; /* 点击时变暗 */
}}

/* ---- 特殊按钮：删除/停止按钮 ---- */
QPushButton#deleteButton {{
    background-color: #e74c3c; /* 危险红色 */
}}
QPushButton#deleteButton:hover {{
    background-color: #f1948a;
}}
QPushButton#deleteButton:pressed {{
    background-color: #cb4335;
}}


/* ---- 输入框 ---- */
QLineEdit, QSpinBox {{
    background-color: #34495e; /* 较深的输入框背景 */
    border: 1px solid #566573;
    border-radius: 8px;
    padding: 8px;
    color: #ecf0f1;
}}
QLineEdit:focus, QSpinBox:focus {{
    border: 1px solid #3498db; /* 聚焦时边框变蓝 */
}}
QSpinBox::up-button, QSpinBox::down-button {{
    subcontrol-origin: border;
    width: 18px;
    border-radius: 4px;
    background-color: #566573;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: #627282;
}}
QSpinBox::up-arrow, QSpinBox::down-arrow {{
    width: 10px;
    height: 10px;
}}

/* ---- 复选框 ---- */
QCheckBox {{
    spacing: 10px; /* 文字和框的间距 */
}}
QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border-radius: 6px;
    border: 2px solid #566573;
    background-color: #34495e;
}}
QCheckBox::indicator:checked {{
    background-color: #3498db; /* 选中时变蓝 */
    border: 2px solid #3498db;
    image: url({check_icon_path}); /* 使用动态路径的打勾图标 */
}}

/* ---- 进度条 ---- */
QProgressBar {{
    border: 2px solid #566573;
    border-radius: 8px;
    text-align: center;
    background-color: #34495e;
    color: #ecf0f1;
}}
QProgressBar::chunk {{
    background-color: #3498db;
    border-radius: 6px;
}}

/* ---- 滚动区域和滚动条 ---- */
QScrollArea {{
    border: 1px solid #444;
    border-radius: 8px;
}}
QScrollBar:vertical {{
    border: none;
    background: #34495e;
    width: 12px;
    margin: 12px 0 12px 0;
    border-radius: 6px;
}}
QScrollBar::handle:vertical {{
    background: #566573;
    min-height: 20px;
    border-radius: 6px;
}}
QScrollBar::handle:vertical:hover {{
    background: #627282;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* ---- 分割线 ---- */
QSplitter::handle {{
    background-color: #566573; /* 分割条颜色 */
}}
QSplitter::handle:horizontal {{
    width: 4px;
}}
QSplitter::handle:vertical {{
    height: 4px;
}}

/* ---- 面板容器 (通过 objectName 设置) ---- */
QWidget#mainPanel {{
    background-color: #34495e;
    border-radius: 8px;
}}

/* ---- 对话框 ---- */
QMessageBox {{
    background-color: #34495e;
}}
QMessageBox QLabel {{
    color: #ecf0f1;
    font-size: 15px;
}}

"""

# 为了保持向后兼容，保留STYLESHEET变量
STYLESHEET = get_stylesheet()