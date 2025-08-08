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

def get_sidebar_styles():
    """获取侧边栏专用样式"""
    return """
/* =========================================== 侧边栏样式 ============================================= */

/* 侧边栏容器 */
QWidget#sidebarContainer {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #1e293b, stop:1 #0f172a);
    border-right: 2px solid #334155;
}

/* 侧边栏头部 */
QWidget#sidebarHeader {
    background: transparent;
    border-bottom: 1px solid #334155;
}

/* 侧边栏标题 */
QLabel#sidebarTitle {
    color: #67e8f9;
    font-size: 20px;
    font-weight: 700;
    padding-left: 10px;
}

/* 侧边栏分割线 */
QFrame#sidebarSeparator {
    background-color: #334155;
    max-height: 1px;
}

/* 侧边栏滚动区域 */
QScrollArea#sidebarScroll {
    background: transparent;
    border: none;
}

/* 导航项 - 默认状态 */
QWidget#navItem {
    background: transparent;
    border: none;
    border-radius: 8px;
    margin: 5px 10px;
}

QWidget#navItem:hover,
QWidget#navItemHover {
    background: rgba(71, 85, 105, 0.3);
}

/* 导航项 - 选中状态 */
QWidget#navItemSelected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(14, 165, 233, 0.3), 
                stop:1 rgba(2, 132, 199, 0.2));
    border-left: 4px solid #0ea5e9;
    border-radius: 8px;
    margin: 5px 10px;
}

/* 导航项 - 禁用状态 */
QWidget#navItemDisabled {
    background: transparent;
    border: none;
    border-radius: 8px;
    margin: 5px 10px;
    opacity: 0.5;
}

/* 导航项标题 */
QLabel#navItemTitle {
    color: #f1f5f9;
    font-size: 14px; 
    font-weight: 600;
    padding: 0px;     
    margin: 0px;  
}

QLabel#navItemTitle[enabled="false"] {
    color: #64748b;
}

/* 导航项描述 */
QLabel#navItemDesc {
    color: #94a3b8;
    font-size: 11px;  
    padding: 0px;   
    margin: 0px;     
    line-height: 1.2; 
}

QLabel#navItemDesc[enabled="false"] {
    color: #475569;
}

/* 侧边栏底部 */
QWidget#sidebarFooter {
    background: rgba(51, 65, 85, 0.3);
    border-top: 1px solid #334155;
}

/* 侧边栏用户名 */
QLabel#sidebarUsername {
    color: #f1f5f9;
    font-size: 14px;
    font-weight: 600;
}

/* 侧边栏状态 */
QLabel#sidebarStatus {
    color: #34d399;
    font-size: 12px;
}

/* 侧边栏按钮 */
QPushButton#sidebarButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #334155, stop:1 #475569);
    color: #f1f5f9;
    border: 1px solid #64748b;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 13px;
}

QPushButton#sidebarButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #475569, stop:1 #64748b);
    border-color: #94a3b8;
}

/* 侧边栏登录按钮 */
QPushButton#sidebarLoginButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0ea5e9, stop:1 #0284c7);
    color: #ffffff;
    border: none;
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
}

QPushButton#sidebarLoginButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #38bdf8, stop:1 #0ea5e9);
}

/* 侧边栏AICU状态 */
QLabel#sidebarAicuStatus {
    color: #94a3b8;
    font-size: 11px;
    margin-top: 5px;
}

QLabel#sidebarAicuStatus[enabled="true"] {
    color: #34d399;
}

QLabel#sidebarAicuStatus[enabled="false"] {
    color: #f87171;
}

/* 侧边栏版本标签 */
QLabel#sidebarVersionLabel {
    color: #64748b;
    font-size: 11px;
    margin-top: 5px;
}

/* =========================================== 内容区域样式 ============================================= */

/* 内容容器 */
QWidget#contentContainer {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0f172a, stop:1 #1e293b);
}

/* 内容堆栈 */
QStackedWidget#contentStack {
    background: transparent;
}

/* 欢迎页面标题 */
QLabel#welcomeTitle {
    color: #67e8f9;
    font-size: 36px;
    font-weight: 700;
    margin: 30px;
    text-shadow: 0 2px 4px rgba(103, 232, 249, 0.3);
}

/* 欢迎页面副标题 */
QLabel#welcomeSubtitle {
    color: #34d399;
    font-size: 20px;
    font-weight: 600;
    margin: 20px;
}

QLabel#welcomeSubtitleNotLoggedIn {
    color: #f87171;
    font-size: 20px;
    font-weight: 600;
    margin: 20px;
}

/* 欢迎页面提示 */
QLabel#welcomeHint {
    color: #94a3b8;
    font-size: 16px;
    margin: 40px;
}

/* 欢迎页面版本 */
QLabel#welcomeVersion {
    color: #64748b;
    font-size: 12px;
    margin-top: 50px;
}
"""

def get_stylesheet():
    """生成包含正确资源路径的  深蓝色主题样式表"""

    # 获取图标路径
    check_icon_path = get_resource_path("assets/check.svg").replace("\\", "/")
    up_on_path = get_resource_path("assets/up.svg").replace("\\", "/")
    down_on_path = get_resource_path("assets/down.svg").replace("\\", "/")

    return f"""

/*==============================================   深蓝色主题全局样式 ==========================================================*/
QWidget {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                stop:0 #0f172a, stop:1 #1e293b); /* 深蓝到深灰蓝渐变 */
    color: #e2e8f0; /* 浅灰色文字 */
    font-family: "Microsoft YaHei UI", "Segoe UI", "SF Pro Display", "Arial"; 
    font-size: 14px;
    border: none;
}}

QMainWindow {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                stop:0 #0f172a, stop:1 #1e293b);
}}

/* -----------------------   标签样式 --------------------------- */
QLabel {{
    color: #f1f5f9;
    padding: 8px;
    background-color: transparent;
    border: none;
    font-weight: 500;
}}

/*-----------------------   按钮样式 ----------------------- */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0ea5e9, stop:1 #0284c7); /* 蓝色渐变 */
    color: #ffffff;
    border: none;
    padding: 12px 20px;
    border-radius: 16px; 
    font-weight: 600;
    font-size: 14px;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.4);
}}

QPushButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #38bdf8, stop:1 #0ea5e9);
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(14, 165, 233, 0.5);
}}

QPushButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0284c7, stop:1 #0369a1);
    transform: translateY(0px);
    box-shadow: 0 2px 8px rgba(14, 165, 233, 0.3);
}}

/*----------------- 特殊按钮：删除/停止按钮 --------------------- */
QPushButton#deleteButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #ec4899, stop:1 #db2777); /* 粉色渐变 */
    box-shadow: 0 4px 12px rgba(236, 72, 153, 0.4);
}}

QPushButton#deleteButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f472b6, stop:1 #ec4899);
    box-shadow: 0 6px 16px rgba(236, 72, 153, 0.5);
}}

QPushButton#deleteButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #db2777, stop:1 #be185d);
    box-shadow: 0 2px 8px rgba(236, 72, 153, 0.3);
}}

/*----------------- 主要操作按钮：B站蓝色样式 --------------------- */
QPushButton#primaryButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0ea5e9, stop:1 #0284c7); /* B站蓝色渐变 */
    color: #ffffff;
    border: none;
    padding: 8px 15px;
    border-radius: 12px; 
    font-weight: 600;
    font-size: 13px;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.4);
}}

QPushButton#primaryButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #38bdf8, stop:1 #0ea5e9);
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(14, 165, 233, 0.5);
}}

QPushButton#primaryButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0284c7, stop:1 #0369a1);
    transform: translateY(0px);
    box-shadow: 0 2px 8px rgba(14, 165, 233, 0.3);
}}

/*----------------- 危险操作按钮：B站粉色样式 --------------------- */
QPushButton#dangerButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #ec4899, stop:1 #db2777); /* B站粉色渐变 */
    color: #ffffff;
    border: none;
    padding: 8px 15px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 13px;
    box-shadow: 0 4px 12px rgba(236, 72, 153, 0.4);
}}

QPushButton#dangerButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f472b6, stop:1 #ec4899);
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(236, 72, 153, 0.5);
}}

QPushButton#dangerButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #db2777, stop:1 #be185d);
    transform: translateY(0px);
    box-shadow: 0 2px 8px rgba(236, 72, 153, 0.3);
}}

/*----------------- 次要操作按钮：灰色样式 --------------------- */
QPushButton#secondaryButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #64748b, stop:1 #475569); /* 灰色渐变 */
    color: #ffffff;
    border: none;
    padding: 10px 20px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 13px;
    box-shadow: 0 4px 12px rgba(100, 116, 139, 0.4);
}}

QPushButton#secondaryButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #94a3b8, stop:1 #64748b);
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(100, 116, 139, 0.5);
}}

QPushButton#secondaryButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #475569, stop:1 #334155);
    transform: translateY(0px);
    box-shadow: 0 2px 8px rgba(100, 116, 139, 0.3);
}}
/*----------------- 问号按钮小尺寸灰色样式 --------------------- */
QPushButton#infoButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #64748b, stop:1 #475569); /* 灰色渐变 */
    color: #ffffff;
    border: none;
    padding: 6px 8px; /* 更小的内边距 */
    border-radius: 12px;
    font-weight: bold;
    font-size: 12px;
    min-width: 10px; /* 最小宽度 */
    max-width: 20px; /* 最大宽度 */
    min-height: 25px;
    max-height: 25px;
    box-shadow: 0 4px 12px rgba(100, 116, 139, 0.4);
}}

QPushButton#infoButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #94a3b8, stop:1 #64748b);
    transform: translateY(-2px);
    box-shadow: 0 6px 16px rgba(100, 116, 139, 0.5);
}}

QPushButton#infoButton:pressed {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #475569, stop:1 #334155);
    transform: translateY(0px);
    box-shadow: 0 2px 8px rgba(100, 116, 139, 0.3);
}}

/* --------------------------   输入框 ------------------------- */
QLineEdit, QSpinBox {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #334155, stop:1 #475569);
    border: 2px solid #475569;
    border-radius: 12px;
    padding: 12px 16px;
    color: #f1f5f9;
    font-size: 14px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}}

QLineEdit:focus, QSpinBox:focus {{
    border: 2px solid #0ea5e9;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #000000, stop:1 #000000);
    box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.2);
}}

QLineEdit:hover, QSpinBox:hover {{
    border: 2px solid #64748b;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #3f4b5f, stop:1 #52637a);
}}

/*---------------------   SpinBox按钮 ------------------ */
QSpinBox::up-button {{
    subcontrol-origin: border;
    width: 20px;
    border-radius: 8px;
    background:transparent;
    image: url({up_on_path});
    margin: 2px;
}}

QSpinBox::down-button {{
    subcontrol-origin: border;
    width: 20px;
    border-radius: 8px;
    background:transparent;
    image: url({down_on_path});
    margin: 2px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background:transparent;
}}

QSpinBox::up-arrow, QSpinBox::down-arrow {{
    width: 12px;
    height: 12px;
}}

/*---------------------   复选框 ---------------------------  */
QCheckBox {{
    spacing: 12px;
    background-color: transparent;
    font-weight: 500;
    color: #cbd5e1;
}}

QCheckBox::indicator {{
    width: 24px;
    height: 24px;
    border-radius: 8px;
    border: 2px solid #64748b;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #334155, stop:1 #475569);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}}

QCheckBox::indicator:hover {{
    border: 2px solid #0ea5e9;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #808080, stop:1 #808080);
}}

QCheckBox::indicator:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #0ea5e9, stop:1 #0284c7);
    border: 2px solid #38bdf8;
    image: url({check_icon_path});
    box-shadow: 0 4px 8px rgba(14, 165, 233, 0.3);
}}

/* ------------------------   进度条 -----------------------  */
QProgressBar {{
    border: none;
    border-radius: 12px;
    text-align: center;
    background: #f1f5f9;
    color:#1e293b;
    height: 24px;
    font-weight: 600;
}}

QProgressBar::chunk {{
    background: #00A1D6;
    border-radius: 10px;
    margin: 2px;
}}

/* ------------------------   滚动区域和滚动条 -----------------------------*/
QScrollArea {{
    border: none;
    border-radius: 12px;
    background: rgba(51, 65, 85, 0.3);
}}

QScrollBar:vertical {{
    border: none;
    background: rgba(71, 85, 105, 0.5);
    width: 14px;
    margin: 0;
    border-radius: 7px;
}}

QScrollBar::handle:vertical {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #64748b, stop:1 #475569);
    min-height: 30px;
    border-radius: 7px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #94a3b8, stop:1 #64748b);
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* --------------------------   分割线 ----------------------  */
QSplitter::handle {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #64748b, stop:1 #475569);
}}

QSplitter::handle:horizontal {{
    width: 6px;
    border-radius: 3px;
}}

QSplitter::handle:vertical {{
    height: 6px;
    border-radius: 3px;
}}

/* ---------------------   面板容器 ----------------------- */
QWidget#mainPanel {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(51, 65, 85, 0.8), 
                stop:1 rgba(30, 41, 59, 0.8));
    border-radius: 20px;
    border: 1px solid rgba(100, 116, 139, 0.3);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}}

/* -----------------------   对话框 ----------------------------- */
QMessageBox {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #1e293b, stop:1 #334155);
    border-radius: 16px;
}}

QMessageBox QLabel {{
    color: #f1f5f9;
    font-size: 15px;
    background-color: transparent;
    border: none;
    font-weight: 500;
}}

/* ====================================================== 工具选择页面专用样式 ====================================================  */
ToolSelectionScreen {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                stop:0 #0f172a, stop:1 #1e293b);
}}

/*  -------------------------  工具卡片样式 ----------------- */
QFrame#toolCard {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(51, 65, 85, 0.9), 
                stop:1 rgba(30, 41, 59, 0.8));
    border: 2px solid #475569;
    border-radius: 20px;
    padding: 24px;
    margin: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}}

QFrame#toolCard:hover {{
    border-color: #0ea5e9;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(51, 65, 85, 1), 
                stop:1 rgba(30, 41, 59, 0.9));
    box-shadow: 0 12px 32px rgba(14, 165, 233, 0.2);
    transform: translateY(-4px);
}}

QFrame#toolCard QLabel {{
    background-color: transparent;
    border: none;
    color: #f1f5f9;
    font-weight: 500;
}}

/*----------------- 禁用状态的工具卡片 ---------------------- */
QFrame#toolCardDisabled {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(30, 41, 59, 0.4), 
                stop:1 rgba(15, 23, 42, 0.4));
    border: 2px solid #334155;
    border-radius: 20px;
    padding: 24px;
    margin: 12px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}}

QFrame#toolCardDisabled:hover {{
    border-color: #475569;
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(30, 41, 59, 0.5), 
                stop:1 rgba(15, 23, 42, 0.5));
}}

QFrame#toolCardDisabled QLabel {{
    background-color: transparent;
    border: none;
    color: #64748b;
}}

/* -------------------- 堆叠窗口组件 ---------------- */
QStackedWidget {{
    background-color: transparent;
}}

QStackedWidget QWidget {{
    background-color: transparent;
}}

/*--------------    文本编辑框 ------------------- */
QTextEdit {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #334155, stop:1 #475569);
    border: 2px solid #64748b;
    border-radius: 16px;
    color: #f1f5f9;
    selection-background-color: #0ea5e9;
    padding: 16px;
    font-size: 14px;
    line-height: 1.6;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}}

QTextEdit:focus {{
    border: 2px solid #0ea5e9;
    box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.2);
}}

/* -------------- 确保没有意外的背景色 ------------------- */
QVBoxLayout, QHBoxLayout, QGridLayout {{
    background-color: transparent;
}}

/* ============================================== 评论清理页面专用样式 ====================================================  */

/*------------- 评论清理页面的数据列表样式 ---------------------- */
QTableWidget#commentDataTable {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #334155, stop:1 #475569);
    border: 2px solid #0ea5e9;
    border-radius: 16px;
    color: #f1f5f9;
    gridline-color: #64748b;
    font-size: 14px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}}

QTableWidget#commentDataTable::item {{
    padding: 12px;
    border-bottom: 1px solid #64748b;
    border-radius: 4px;
}}

QTableWidget#commentDataTable::item:hover {{
    background: rgba(14, 165, 233, 0.2);
}}

QTableWidget#commentDataTable::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(14, 165, 233, 0.3), 
                stop:1 rgba(2, 132, 199, 0.2));
}}

/*----------------- 评论详情页面的评论内容样式 - B站来源 ---------------*/
QTextEdit#bilibiliCommentContent {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(30, 58, 138, 0.3), 
                stop:1 rgba(37, 99, 235, 0.2));
    border: 2px solid #00a1d6;
    border-radius: 16px;
    padding: 16px;
    color: #bfdbfe;
    font-size: 14px;
    line-height: 1.6;
    box-shadow: 0 4px 12px rgba(0, 161, 214, 0.2);
}}

/*----------- 评论详情页面的评论内容样式 - AICU来源 ---------------- */



QTextEdit#aicuCommentContent {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(190, 24, 93, 0.3), 
                stop:1 rgba(236, 72, 153, 0.2));
    border: 2px solid #ec4899;
    border-radius: 16px;
    padding: 16px;
    color: #fce7f3;
    font-size: 14px;
    line-height: 1.6;
    box-shadow: 0 4px 12px rgba(236, 72, 153, 0.2);
}}

/* ============================================== 批量取关页面专用样式 ============================================ */

/*------------- 使用说明标签 ---------------- */
QLabel#infoLabel {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(34, 197, 94, 0.3), 
                stop:1 rgba(22, 163, 74, 0.2));
    padding: 16px;
    border-radius: 12px;
    color: #bbf7d0;
    border: 1px solid #22c55e;
    font-weight: 500;
    box-shadow: 0 4px 12px rgba(34, 197, 94, 0.2);
}}

/* ======================================= 私信管理页面专用样式 ======================================================== */

/*------------------ 搜索框区域 -------------- */
QFrame#searchFrame {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(51, 65, 85, 0.8), 
                stop:1 rgba(30, 41, 59, 0.6));
    border: 2px solid #475569;
    border-radius: 16px;
    padding: 16px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}}

/*---------------- 底部控制区域 ------------------ */
QFrame#bottomControlFrame {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(51, 65, 85, 0.8), 
                stop:1 rgba(30, 41, 59, 0.6));
    border: 2px solid #ec4899;
    border-radius: 16px;
    padding: 16px;
    box-shadow: 0 4px 12px rgba(236, 72, 153, 0.2);
}}

/* =================================================== 数据统计页面专用样式 ============================================= */


/* ---------------------统计卡片 ----------------------------- */
QFrame#statsCard {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(51, 65, 85, 0.9));
    border: 2px solid #475569;
    border-radius: 20px;
    padding: 20px;
    margin: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}}

QFrame#statsCard:hover {{
    border-color: #0ea5e9;  
    box-shadow: 0 12px 32px rgba(14, 165, 233, 0.2);
    transform: translateY(-2px);
}}

/* ---------------------------卡片标题 ------------------------ */
QLabel#statsCardTitle {{
    color: #F0F0F0;
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 12px;
    text-shadow: 0 1px 2px rgba(103, 232, 249, 0.3);
}}

/*---------------------------- 统计项目框 ------------------------------- */
QFrame#statItem {{
    background:rgba(14, 165, 233, 0.15);
    border: 1px solid #0ea5e9; 
    border-radius: 12px;
    padding: 16px;
    margin: 6px;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.1);
}}

QFrame#statItem:hover {{
    background: rgba(14, 165, 233, 0.25);
    border-color: #38bdf8;
    box-shadow: 0 6px 16px rgba(14, 165, 233, 0.15);
}}

/* ---------------------------------点赞排行榜表格 ------------------------------- */
QTableWidget#likeRankingTable {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #334155, stop:1 #475569);
    border: 2px solid #0ea5e9;
    border-radius: 16px;
    color: #f1f5f9;
    gridline-color: #64748b;
    font-size: 13px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
}}

QTableWidget#likeRankingTable::item {{
    padding: 12px;
    border-bottom: 1px solid #64748b;
    min-height: 24px;
}}

QTableWidget#likeRankingTable::item:hover {{
    background: rgba(14, 165, 233, 0.2);
}}

QTableWidget#likeRankingTable::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(14, 165, 233, 0.3), 
                stop:1 rgba(2, 132, 199, 0.2));
}}

QTableWidget#likeRankingTable QHeaderView::section {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0ea5e9, stop:1 #0284c7);
    color: #ffffff;
    padding: 14px;
    border: none;
    border-bottom: 2px solid #38bdf8;
    font-weight: 700;
    font-size: 14px;
}}

QTableWidget#likeRankingTable QHeaderView::section:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #38bdf8, stop:1 #0ea5e9);
}}


/* ===============---==================================== 全局动画效果 ============================================== */
QPushButton {{
    transition: all 0.3s ease;
}}

QFrame {{
    transition: all 0.3s ease;
}}

QTableWidget::item {{
    transition: background-color 0.2s ease;
}}

/* ============================================== 菜单栏和下拉菜单样式 ======================================================= */
QMenuBar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(51, 65, 85, 0.9), 
                stop:1 rgba(30, 41, 59, 0.8));
    color: #f1f5f9;
    padding: 4px;
    border: none;
    font-weight: 500;
}}

QMenuBar::item {{
    background: transparent;
    padding: 8px 16px;
    border-radius: 8px;
    margin: 2px;
}}

QMenuBar::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0ea5e9, stop:1 #0284c7);
    color: #ffffff;
}}

QMenuBar::item:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(14, 165, 233, 0.3), 
                stop:1 rgba(2, 132, 199, 0.2));
}}

QMenu {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(51, 65, 85, 0.95), 
                stop:1 rgba(30, 41, 59, 0.9));
    border: 2px solid #475569;
    border-radius: 12px;
    padding: 8px;
    color: #f1f5f9;
    font-weight: 500;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}}

QMenu::item {{
    background: transparent;
    padding: 10px 16px;
    border-radius: 8px;
    margin: 2px;
    min-width: 150px;
}}

QMenu::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0ea5e9, stop:1 #0284c7);
    color: #ffffff;
}}

QMenu::item:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(14, 165, 233, 0.4), 
                stop:1 rgba(2, 132, 199, 0.3));
}}

QMenu::item:disabled {{
    background: transparent;
    color: #64748b;
}}

QMenu::separator {{
    height: 1px;
    background: #475569;
    margin: 6px 0;
    border-radius: 1px;
}}

/* =================================== 工具选择页面专用样============================ ========================= */

/*----------------- 应用标题样式---------- */
QLabel#appTitle {{
    color: #67e8f9;
    font-size: 28px;
    font-weight: 700;
    text-shadow: 0 2px 4px rgba(103, 232, 249, 0.3);
}}

/*--------------- 欢迎标签样式--------------- */
QLabel#welcomeLabel {{
    font-size: 16px;
    font-weight: 600;
}}

/* ------------登录状态 - 已登--------------- */
QLabel#welcomeLabel[status="logged_in"] {{
    color: #34d399;
}}

/*---------------- 登录状态 - 未登录--------------- */
QLabel#welcomeLabel[status="not_logged_in"] {{
    color: #f87171;
}}

/*--------------- 提示标签样式 ---------------*/
QLabel#hintLabel {{
    font-size: 14px;
    font-weight: 500;
    color: #cbd5e1;
    margin: 20px 0;
}}

QLabel#hintLabel[status="not_logged_in"] {{
    color: #f87171;
}}

/* -------------登录按钮样式-------------------- */
QPushButton#loginButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f87171, stop:1 #ef4444);
    color: #ffffff;
    padding: 12px 30px;
    border-radius: 12px;
    font-size: 16px;
    font-weight: 700;
    margin-top: 15px;
    box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
}}

QPushButton#loginButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #fca5a5, stop:1 #f87171);
    box-shadow: 0 6px 16px rgba(239, 68, 68, 0.5);
    transform: translateY(-2px);
}}

/*------------------ 账号管理按钮样式----------------------- */
QPushButton#manageButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0ea5e9, stop:1 #0284c7);
    color: #ffffff;
    padding: 10px 20px;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    margin-top: 10px;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
}}

QPushButton#manageButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #38bdf8, stop:1 #0ea5e9);
    box-shadow: 0 6px 16px rgba(14, 165, 233, 0.4);
    transform: translateY(-2px);
}}

/*----------------- 版本信息和底部状态样式----------------------- */
QLabel#versionLabel {{
    color: #94a3b8;
    font-size: 12px;
    font-weight: 500;
}}

QLabel#aicuStatus {{
    font-size: 12px;
    font-weight: 600;
}}

QLabel#aicuStatus[enabled="true"] {{
    color: #34d399;
}}

QLabel#aicuStatus[enabled="false"] {{
    color: #f87171;
}}

QLabel#accountInfo {{
    color: #67e8f9;
    font-size: 12px;
    font-weight: 500;
}}

/* ========================================= 登录对话框样式 =============================================== */

/*-------------------- 对话框标题---------------------- */
QLabel#dialogTitle {{
    color: #67e8f9;
    font-size: 18px;
    font-weight: 700;
    margin: 20px;
    text-shadow: 0 1px 2px rgba(103, 232, 249, 0.3);
}}

/*------------------ 二维码登录按钮------------------- */
QPushButton#qrLoginButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0ea5e9, stop:1 #0284c7);
    color: #ffffff;
    padding: 12px 24px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 700;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.4);
}}

QPushButton#qrLoginButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #38bdf8, stop:1 #0ea5e9);
    box-shadow: 0 6px 16px rgba(14, 165, 233, 0.5);
    transform: translateY(-2px);
}}

/*--------------- Cookie登录按钮------------------- */
QPushButton#cookieLoginButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #34d399, stop:1 #10b981);
    color: #ffffff;
    padding: 12px 24px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 700;
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.4);
}}

QPushButton#cookieLoginButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #6ee7b7, stop:1 #34d399);
    box-shadow: 0 6px 16px rgba(16, 185, 129, 0.5);
    transform: translateY(-2px);
}}

/* ========================= 账号管理对话框样式 ========================= */

/* --------------账号管理对话框标题---------------------- */
QLabel#accountDialogTitle {{
    color: #67e8f9;
    font-size: 18px;
    font-weight: 700;
    margin: 15px;
    text-shadow: 0 1px 2px rgba(103, 232, 249, 0.3);
}}

/*------------------- 账号列表----------------------------- */
QListWidget#accountList {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #334155, stop:1 #475569);
    border: 2px solid #64748b;
    border-radius: 12px;
    color: #f1f5f9;
    padding: 8px;
    font-size: 13px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}}

QListWidget#accountList::item {{
    padding: 12px;
    border-radius: 8px;
    margin: 4px;
    background: transparent;
}}

QListWidget#accountList::item:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(14, 165, 233, 0.2), 
                stop:1 rgba(2, 132, 199, 0.1));
}}

QListWidget#accountList::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgba(14, 165, 233, 0.4), 
                stop:1 rgba(2, 132, 199, 0.3));
}}

/*------------------- 账号管理按钮-------------------------- */
QPushButton#switchAccountButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0ea5e9, stop:1 #0284c7);
    color: #ffffff;
    padding: 8px 16px;
    border-radius: 8px;
    font-weight: 600;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
}}

QPushButton#switchAccountButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #38bdf8, stop:1 #0ea5e9);
    box-shadow: 0 6px 16px rgba(14, 165, 233, 0.4);
}}

QPushButton#removeAccountButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #f87171, stop:1 #ef4444);
    color: #ffffff;
    padding: 8px 16px;
    border-radius: 8px;
    font-weight: 600;
    box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
}}

QPushButton#removeAccountButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #fca5a5, stop:1 #f87171);
    box-shadow: 0 6px 16px rgba(239, 68, 68, 0.4);
}}

QPushButton#cancelButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #64748b, stop:1 #475569);
    color: #ffffff;
    padding: 8px 16px;
    border-radius: 8px;
    font-weight: 600;
    box-shadow: 0 4px 12px rgba(71, 85, 105, 0.3);
}}

QPushButton#cancelButton:hover {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #94a3b8, stop:1 #64748b);
    box-shadow: 0 6px 16px rgba(71, 85, 105, 0.4);
}}
""" + get_sidebar_styles()

# 为了保持兼容，保留STYLESHEET变量
STYLESHEET = get_stylesheet()