import logging
import requests
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QMessageBox, QDialog,
    QMainWindow, QListWidget, QListWidgetItem,
    QStackedWidget, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer, QPropertyAnimation, QEasingCurve, QUrl
from PyQt6.QtGui import QAction, QDesktopServices
from ..api.api_service import ApiService
logger = logging.getLogger(__name__)


class UsernameThread(QThread):
    """用户名获取线程"""
    username_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_service):
        super().__init__()
        self.setObjectName("UsernameThread")
        self.api_service = api_service
        self._is_running = True

    def stop(self):
        self._is_running = False
        self.requestInterruption()

    def run(self):
        if not self._is_running:
            return

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Cookie": self.api_service.cookie,
                "Referer": "https://www.bilibili.com"
            }
            response = requests.get("https://api.bilibili.com/x/space/myinfo", headers=headers, timeout=10)

            if not self._is_running:
                return

            data = response.json()
            if data.get("code") == 0:
                username = data["data"]["name"]
                if self._is_running:
                    self.username_received.emit(username)
            else:
                if self._is_running:
                    self.error_occurred.emit(f"API错误: {data.get('message', '未知错误')}")
        except Exception as e:
            if self._is_running:
                self.error_occurred.emit(str(e))


class AccountSelectionDialog(QDialog):
    """账号选择对话框"""
    account_selected = pyqtSignal(str)  # 发送选中的UID
    account_removed = pyqtSignal(str)  # 发送要删除的UID

    def __init__(self, account_manager, parent=None):
        super().__init__(parent)
        self.account_manager = account_manager
        self.parent_window = parent  # 保存父窗口引用
        self.setWindowTitle("账号管理")
        self.setFixedSize(450, 350)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 标题
        title = QLabel("账号管理")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("accountDialogTitle")
        layout.addWidget(title)

        # 账号列表
        self.account_list = QListWidget()
        self.account_list.setObjectName("accountList")
        self.refresh_account_list()
        self.account_list.itemDoubleClicked.connect(self.on_account_selected)
        layout.addWidget(QLabel("双击切换账号:"))
        layout.addWidget(self.account_list)

        # 按钮区域
        button_layout = QHBoxLayout()

        # 切换账号按钮
        switch_btn = QPushButton("切换到此账号")
        switch_btn.clicked.connect(self.on_account_selected)
        switch_btn.setObjectName("switchAccountButton")
        button_layout.addWidget(switch_btn)

        # 删除账号按钮
        remove_btn = QPushButton("删除账号")
        remove_btn.clicked.connect(self.remove_account)
        remove_btn.setObjectName("removeAccountButton")
        button_layout.addWidget(remove_btn)

        button_layout.addStretch()

        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setObjectName("cancelButton")
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def refresh_account_list(self):
        self.account_list.clear()

        # 重新获取最新的账号列表
        accounts = self.account_manager.get_all_accounts()
        current_account = self.account_manager.get_current_account()

        for account in accounts:
            item = QListWidgetItem()

            # 设置显示文本
            is_current = (current_account and current_account.uid == account.uid)
            status = " 🟢 [当前]" if is_current else ""
            text = f"{account.username}{status}\nUID: {account.uid}\n最后登录: {account.last_login}"
            item.setText(text)
            item.setData(Qt.ItemDataRole.UserRole, str(account.uid))

            # 高亮当前账号
            if is_current:
                item.setBackground(Qt.GlobalColor.darkCyan)

            self.account_list.addItem(item)

    def on_account_selected(self):
        """选择账号进行切换"""
        current_item = self.account_list.currentItem()
        if current_item:
            uid = int(current_item.data(Qt.ItemDataRole.UserRole))

            # 检查是否选择了当前账号
            current_account = self.account_manager.get_current_account()
            if current_account and current_account.uid == uid:
                QMessageBox.information(self, "提示", "这已经是当前账号")
                return

            # 先关闭对话框
            self.accept()

            # 然后发送切换信号
            self.account_selected.emit(str(uid))

    def remove_account(self):
        """删除选中的账号"""
        current_item = self.account_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选择要删除的账号")
            return

        uid = int(current_item.data(Qt.ItemDataRole.UserRole))

        # 获取账号信息
        account = None
        for acc in self.account_manager.get_all_accounts():
            if acc.uid == uid:
                account = acc
                break

        if account:
            # 检查是否只剩一个账号
            if len(self.account_manager.get_all_accounts()) == 1:
                reply = QMessageBox.question(
                    self, "确认删除",
                    f"这是最后一个账号，删除后将退出登录。\n\n确定要删除账号 '{account.username}' 吗？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
            else:
                reply = QMessageBox.question(
                    self, "确认删除",
                    f"确定要删除账号 '{account.username}' 吗？\n\n这将清除该账号的登录信息。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )

            if reply == QMessageBox.StandardButton.Yes:
                # 发送删除信号
                self.account_removed.emit(str(uid))

                # 刷新列表
                self.refresh_account_list()

                # 如果没有账号了，关闭对话框
                if not self.account_manager.has_accounts():
                    QMessageBox.information(self, "提示", "所有账号已删除，返回登录页面")
                    self.accept()


class SimpleLoginDialog(QDialog):
    """登录对话框 """
    login_success = pyqtSignal(object, bool)  # ApiService, aicu_state

    def __init__(self, aicu_state: bool, parent=None):
        super().__init__(parent)
        self.aicu_state = aicu_state  # 从父窗口传入，不再让用户选择
        self.setWindowTitle("账号登录")
        self.setFixedSize(500, 550)
        self._is_closing = False
        self.qr_screen = None
        self.cookie_screen = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # 标题
        title = QLabel("登录 Bilibili 账号")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("dialogTitle")
        layout.addWidget(title)

        # 登录方式选择
        method_layout = QHBoxLayout()

        self.qr_btn = QPushButton("扫码登录")
        self.qr_btn.clicked.connect(self.show_qr_login)
        self.qr_btn.setObjectName("qrLoginButton")
        method_layout.addWidget(self.qr_btn)

        self.cookie_btn = QPushButton("Cookie登录")
        self.cookie_btn.clicked.connect(self.show_cookie_login)
        self.cookie_btn.setObjectName("cookieLoginButton")
        method_layout.addWidget(self.cookie_btn)

        layout.addLayout(method_layout)

        # 登录内容区域
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        layout.addWidget(self.content_widget)

        # 默认显示二维码登录
        self.show_qr_login()

        self.setLayout(layout)

    def show_qr_login(self):
        """显示二维码登录"""
        self.clear_content()

        try:
            from .qrcode_screen import QRCodeScreen
            self.qr_screen = QRCodeScreen()
            # 连接登录成功信号
            self.qr_screen.login_success.connect(self.on_login_success)
            self.content_layout.addWidget(self.qr_screen)
        except ImportError as e:
            logger.error(f"无法导入QRCodeScreen: {e}")
            error_label = QLabel("二维码登录功能不可用")
            error_label.setStyleSheet("color: #e74c3c; text-align: center; padding: 20px;")
            self.content_layout.addWidget(error_label)

    def show_cookie_login(self):
        """显示Cookie登录"""
        self.clear_content()

        try:
            from .cookie_screen import CookieScreen
            self.cookie_screen = CookieScreen()
            # 连接登录成功信号
            self.cookie_screen.login_success.connect(self.on_login_success)
            self.content_layout.addWidget(self.cookie_screen)
        except ImportError as e:
            logger.error(f"无法导入CookieScreen: {e}")
            error_label = QLabel("Cookie登录功能不可用")
            error_label.setStyleSheet("color: #e74c3c; text-align: center; padding: 20px;")
            self.content_layout.addWidget(error_label)

    def on_login_success(self, api_service, _):
        """处理登录成功"""
        if self._is_closing:
            return

        # 停止QR屏幕的线程（如果有的话）
        if self.qr_screen:
            self.qr_screen.stop_all_threads()

        # 发送登录成功信号
        self.login_success.emit(api_service, self.aicu_state)

        # 使用QTimer延迟关闭，给线程时间清理
        QTimer.singleShot(500, self.accept)  # 延迟500毫秒关闭

    def clear_content(self):
        """清空内容区域"""
        # 如果有QR屏幕，先停止其线程
        if self.qr_screen:
            self.qr_screen.stop_all_threads()
            self.qr_screen.deleteLater()

        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.qr_screen = None
        self.cookie_screen = None

    def closeEvent(self, event):
        """对话框关闭时清理资源"""
        self._is_closing = True

        # 清理QR屏幕
        if self.qr_screen:
            self.qr_screen.stop_all_threads()

        super().closeEvent(event)


class ToolNavigationItem(QWidget):
    """侧边栏工具导航项"""
    clicked = pyqtSignal()

    def __init__(self, icon: str, title: str, description: str, enabled: bool = True):
        super().__init__()
        self.title = title
        self.enabled = enabled
        self.selected = False
        self.init_ui(icon, title, description)

    def init_ui(self, icon: str, title: str, description: str):
        self.setFixedHeight(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.enabled else Qt.CursorShape.ForbiddenCursor)

        layout = QHBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)


        # 文本区域
        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        # 标题
        self.title_label = QLabel(title)
        self.title_label.setObjectName("navItemTitle")
        self.title_label.setProperty("enabled", "true" if self.enabled else "false")
        text_layout.addWidget(self.title_label)

        # 描述
        desc_label = QLabel(description)
        desc_label.setObjectName("navItemDesc")
        desc_label.setProperty("enabled", "true" if self.enabled else "false")
        desc_label.setWordWrap(True)
        text_layout.addWidget(desc_label)

        layout.addLayout(text_layout)
        layout.addStretch()

        # 状态指示器
        if not self.enabled:
            lock_label = QLabel("🔒")
            lock_label.setStyleSheet("font-size: 20px;")
            layout.addWidget(lock_label)

        self.setLayout(layout)
        self.update_style()

    def update_style(self):
        if self.selected and self.enabled:
            self.setObjectName("navItemSelected")
        elif self.enabled:
            self.setObjectName("navItem")
        else:
            self.setObjectName("navItemDisabled")
        self.setStyleSheet(self.styleSheet())  # 触发样式更新

    def set_selected(self, selected: bool):
        self.selected = selected
        self.update_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.enabled:
            self.clicked.emit()

    def enterEvent(self, event):
        if self.enabled and not self.selected:
            self.setObjectName("navItemHover")
            self.setStyleSheet(self.styleSheet())

    def leaveEvent(self, event):
        self.update_style()


class ToolSelectionScreen(QMainWindow):

    # 信号定义
    open_comment_tool = pyqtSignal()
    open_unfollow_tool = pyqtSignal()
    open_comment_stats_tool = pyqtSignal()
    open_message_tool = pyqtSignal()
    open_record_tool = pyqtSignal()
    open_unlike_tool = pyqtSignal()

    def __init__(self, api_service: ApiService, aicu_state: bool):
        super().__init__()
        self.api_service = api_service
        self.aicu_state = aicu_state
        self.username = "未登录"
        self.username_thread = None  # 保存线程引用
        self.tool_items = []  # 保存工具导航项引用

        # 初始化账号管理器
        try:
            from ..api.account_manager import AccountManager
            self.account_manager = AccountManager()
            logger.info("账号管理器初始化成功")

            # 如果没有提供api_service，尝试从账号管理器获取
            if not self.api_service:
                self.api_service = self.account_manager.get_current_api_service()
                if self.api_service:
                    current_account = self.account_manager.get_current_account()
                    if current_account:
                        self.username = current_account.username
                        logger.info(f"自动登录: {self.username}")
        except ImportError:
            self.account_manager = None
            logger.warning("账号管理器不可用")

        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        # 应用样式表（包含侧边栏样式）
        from ..style import get_stylesheet
        self.setStyleSheet(get_stylesheet())

        # 创建菜单栏
        self.create_menu_bar()

        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # 主布局 - 水平布局
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 创建侧边栏
        self.create_sidebar(main_layout)

        # 创建内容区域
        self.create_content_area(main_layout)

        # 状态栏
        status_message = f"已登录: {self.username}" if self.api_service else "未登录"
        self.statusBar().showMessage(status_message)

    def create_menu_bar(self):
        """创建的菜单栏"""
        menubar = self.menuBar()

        # 账号菜单
        account_menu = menubar.addMenu('账号')

        if not self.api_service:
            # 未登录状态
            login_action = QAction('登录账号', self)
            login_action.triggered.connect(self.show_login_dialog)
            account_menu.addAction(login_action)
        else:
            # 已登录状态
            current_user_action = QAction(f'当前: {self.username}', self)
            current_user_action.setEnabled(False)  # 只显示，不可点击
            account_menu.addAction(current_user_action)

            account_menu.addSeparator()

            # 账号管理子菜单
            if self.account_manager and self.account_manager.has_accounts():
                manage_action = QAction('管理账号', self)
                manage_action.triggered.connect(self.show_account_management)
                account_menu.addAction(manage_action)

            # 添加新账号
            add_account_action = QAction('添加新账号', self)
            add_account_action.triggered.connect(self.show_login_dialog)
            account_menu.addAction(add_account_action)

            account_menu.addSeparator()

            # 退出当前账号
            logout_current_action = QAction('退出当前账号', self)
            logout_current_action.triggered.connect(self.logout_current)
            account_menu.addAction(logout_current_action)

            # 清除所有账号
            if self.account_manager and len(self.account_manager.get_all_accounts()) > 1:
                logout_all_action = QAction('清除所有账号', self)
                logout_all_action.triggered.connect(self.logout_all)
                account_menu.addAction(logout_all_action)

        # 设置菜单
        settings_menu = menubar.addMenu('设置')

        aicu_action = QAction('AICU数据源(使用前请使用手机热点网络,否则会风控!!!)', self)
        aicu_action.setCheckable(True)
        aicu_action.setChecked(self.aicu_state)
        aicu_action.triggered.connect(self.toggle_aicu_state)
        settings_menu.addAction(aicu_action)

        settings_menu.addSeparator()
        clear_cache_action = QAction('清除本地缓存', self)
        clear_cache_action.triggered.connect(self.clear_local_cache)
        settings_menu.addAction(clear_cache_action)

        script_action = QAction('安装评论记录脚本', self)
        script_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://scriptcat.org/zh-CN/users/174969")))
        settings_menu.addAction(script_action)


    def create_sidebar(self, main_layout):
        """创建侧边栏"""
        # 侧边栏容器
        self.sidebar_container = QWidget()
        self.sidebar_container.setObjectName("sidebarContainer")
        self.sidebar_container.setFixedWidth(300)

        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # 侧边栏头部
        header_widget = QWidget()
        header_widget.setObjectName("sidebarHeader")
        header_widget.setFixedHeight(80)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 0, 20, 0)

        # Logo和标题
        logo_label = QLabel("📺")
        logo_label.setStyleSheet("font-size: 32px;")
        header_layout.addWidget(logo_label)

        title_label = QLabel("B站工具集")
        title_label.setObjectName("sidebarTitle")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        sidebar_layout.addWidget(header_widget)

        # 分割线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setObjectName("sidebarSeparator")
        sidebar_layout.addWidget(separator)

        # 工具列表滚动区域
        scroll_area = QScrollArea()
        scroll_area.setObjectName("sidebarScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 工具列表容器
        tools_widget = QWidget()
        tools_layout = QVBoxLayout(tools_widget)
        tools_layout.setContentsMargins(0, 10, 0, 10)
        tools_layout.setSpacing(5)

        # 工具列表
        tools = [
            {
                "icon": "",
                "title": "评论清理工具",
                "description": "清理评论、弹幕和通知",
                "enabled": bool(self.api_service),
                "callback": self.open_comment_tool.emit
            },
            {
                "icon": "",
                "title": "批量取关工具",
                "description": "管理关注的UP主",
                "enabled": bool(self.api_service),
                "callback": self.open_unfollow_tool.emit
            },
            {
                "icon": "",
                "title": "批量取消点赞",
                "description": "批量取消视频点赞",
                "enabled": bool(self.api_service),
                "callback": self.open_unlike_tool.emit
            },
            {
                "icon": "",
                "title": "数据统计中心",
                "description": "查看各项数据统计",
                "enabled": bool(self.api_service),
                "callback": self.open_comment_stats_tool.emit
            },
            {
                "icon": "",
                "title": "私信管理工具",
                "description": "管理B站私信",
                "enabled": bool(self.api_service),
                "callback": self.open_message_tool.emit
            },
            {
                "icon": "",
                "title": "评论弹幕记录",
                "description": "记录最新发的评论弹幕",
                "enabled": bool(self.api_service),
                "callback": self.open_record_tool.emit
            }
        ]


        for i, tool in enumerate(tools):
            item = ToolNavigationItem(
                tool["icon"],
                tool["title"],
                tool["description"],
                tool["enabled"]
            )

            if tool["enabled"]:
                item.clicked.connect(lambda checked=False, idx=i: self.on_tool_selected(idx))
            else:
                item.clicked.connect(self.show_login_prompt)

            tools_layout.addWidget(item)
            self.tool_items.append(item)

        tools_layout.addStretch()

        scroll_area.setWidget(tools_widget)
        sidebar_layout.addWidget(scroll_area)

        # 底部用户信息
        self.create_sidebar_footer(sidebar_layout)

        main_layout.addWidget(self.sidebar_container)

        # 默认选中第一个工具（如果已登录）
        if self.api_service and self.tool_items:
            self.tool_items[0].set_selected(True)

    def create_sidebar_footer(self, sidebar_layout):
        """创建侧边栏底部"""
        footer_widget = QWidget()
        footer_widget.setObjectName("sidebarFooter")
        footer_layout = QVBoxLayout(footer_widget)
        footer_layout.setContentsMargins(20, 15, 20, 15)

        # 用户信息区域
        if self.api_service:
            # 已登录
            user_info_layout = QHBoxLayout()
            # 用户头像占位
            avatar_label = QLabel("🦕")
            avatar_label.setStyleSheet("font-size: 28px;")
            user_info_layout.addWidget(avatar_label)

            # 用户名和状态
            user_text_layout = QVBoxLayout()
            username_label = QLabel(self.username)
            username_label.setObjectName("sidebarUsername")
            user_text_layout.addWidget(username_label)

            status_label = QLabel("在线")
            status_label.setObjectName("sidebarStatus")
            user_text_layout.addWidget(status_label)

            user_info_layout.addLayout(user_text_layout)
            user_info_layout.addStretch()

            footer_layout.addLayout(user_info_layout)

            # 操作按钮
            if self.account_manager and len(self.account_manager.get_all_accounts()) > 1:
                switch_btn = QPushButton("切换账号")
                switch_btn.setObjectName("sidebarButton")
                switch_btn.clicked.connect(self.show_account_management)
                footer_layout.addWidget(switch_btn)
        else:
            # 未登录
            login_btn = QPushButton("登录账号")
            login_btn.setObjectName("sidebarLoginButton")
            login_btn.clicked.connect(self.show_login_dialog)
            footer_layout.addWidget(login_btn)

        # AICU状态和版本信息 - 放在同一行
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(0, 10, 0, 0)

        # AICU状态
        aicu_label = QLabel(f"AICU: {'启用' if self.aicu_state else '禁用'}")
        aicu_label.setObjectName("sidebarAicuStatus")
        aicu_label.setProperty("enabled", "true" if self.aicu_state else "false")
        aicu_label.setStyleSheet(f"""
            color: {'#34d399' if self.aicu_state else '#f87171'};
            font-size: 12px;
            font-weight: 500;
        """)
        info_layout.addWidget(aicu_label)

        # 分隔符
        separator_label = QLabel("•")
        separator_label.setStyleSheet("color: #475569; margin: 0 8px;")
        info_layout.addWidget(separator_label)

        # 版本信息
        version_label = QLabel("版本:1.6.19")
        version_label.setObjectName("sidebarVersionLabel")
        version_label.setStyleSheet("""
            color: #64748b;
            font-size: 12px;
            font-weight: 500;
        """)
        info_layout.addWidget(version_label)

        info_layout.addStretch()

        footer_layout.addLayout(info_layout)

        sidebar_layout.addWidget(footer_widget)

    def create_content_area(self, main_layout):
        """创建内容区域"""
        # 内容区域容器
        content_container = QWidget()
        content_container.setObjectName("contentContainer")

        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # 内容堆栈
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")

        # 欢迎页面
        self.create_welcome_page()

        content_layout.addWidget(self.content_stack)
        main_layout.addWidget(content_container)

    def create_welcome_page(self):
        """创建欢迎页面"""
        welcome_widget = QWidget()
        welcome_layout = QVBoxLayout(welcome_widget)
        welcome_layout.setContentsMargins(40, 40, 40, 40)
        welcome_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 大标题
        welcome_title = QLabel("欢迎使用 Bilibili 工具集")
        welcome_title.setObjectName("welcomeTitle")
        welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(welcome_title)

        # 副标题
        if self.api_service:
            subtitle = QLabel(f"你好，{self.username}！")
            subtitle.setObjectName("welcomeSubtitle")
        else:
            subtitle = QLabel("请先登录后使用")
            subtitle.setObjectName("welcomeSubtitleNotLoggedIn")

        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(subtitle)

        # 提示文字
        hint = QLabel("请从左侧选择要使用的工具")
        hint.setObjectName("welcomeHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(hint)

        self.content_stack.addWidget(welcome_widget)


    def on_tool_selected(self, index):
        # 更新选中状态
        for i, item in enumerate(self.tool_items):
            item.set_selected(i == index)

        # 触发对应的信号
        tools = [
            self.open_comment_tool,
            self.open_unfollow_tool,
            self.open_unlike_tool,
            self.open_comment_stats_tool,
            self.open_message_tool,
            self.open_record_tool
        ]

        if 0 <= index < len(tools):
            tools[index].emit()

    def show_login_prompt(self):
        """显示登录提示"""
        QMessageBox.information(
            self, "需要登录",
            "请先登录账号才能使用此工具。\n\n点击侧边栏底部的'登录账号'按钮或使用菜单栏登录。"
        )

    def clear_local_cache(self):
        """清除本地缓存"""
        if not self.account_manager:
            QMessageBox.information(self, "提示", "账号管理器不可用")
            return

        cache_dir = self.account_manager.get_cache_directory()
        reply = QMessageBox.question(
            self, "确认清除",
            f"确定要清除所有本地缓存吗？\n\n这将删除：\n1, 所有保存的账号信息\n2, 所有缓存数据\n\n缓存位置：{cache_dir}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            if self.account_manager.clear_all_cache():
                self.api_service = None
                self.username = "未登录"
                # 重新初始化账号管理器
                try:
                    from ..api.account_manager import AccountManager
                    self.account_manager = AccountManager()
                except ImportError:
                    self.account_manager = None
                self.refresh_ui()
                QMessageBox.information(self, "清除成功", "本地缓存已清除，所有账号信息已删除")
            else:
                QMessageBox.critical(self, "清除失败", "清除缓存时发生错误")

    def show_login_dialog(self):
        """显示登录对话框"""
        dialog = SimpleLoginDialog(self.aicu_state, self)
        dialog.login_success.connect(self.on_login_success)
        dialog.exec()

    def show_account_management(self):
        """显示账号管理对话框 """
        if not self.account_manager or not self.account_manager.has_accounts():
            QMessageBox.information(self, "提示", "没有已保存的账号")
            return

        # 创建对话框
        dialog = AccountSelectionDialog(self.account_manager, self)

        # 连接信号
        dialog.account_selected.connect(self.on_dialog_account_selected)
        dialog.account_removed.connect(self.on_dialog_account_removed)

        # 显示对话框
        result = dialog.exec()

        # 对话框关闭后，如果账号有变化，刷新界面
        if result == QDialog.DialogCode.Accepted:
            logger.info("账号管理对话框关闭，可能有账号变化")

    def on_dialog_account_selected(self, uid: str):  # 参数类型改为str
        """处理对话框中的账号选择"""
        uid = int(uid)  # 转换回整数
        logger.info(f"对话框请求切换到账号 UID: {uid}")
        self.switch_account(uid)

    def on_dialog_account_removed(self, uid: str):  # 参数类型改为str
        """处理对话框中的账号删除"""
        uid = int(uid)  # 转换回整数
        logger.info(f"对话框请求删除账号 UID: {uid}")
        self.remove_account(uid)

    def switch_account(self, uid: int):
        """切换账号"""
        logger.info(f"切换账号到 UID: {uid} ")

        if not self.account_manager:
            logger.error("账号管理器不存在")
            QMessageBox.critical(self, "错误", "账号管理器未初始化")
            return

        try:
            # 使用账号管理器切换账号
            if self.account_manager.switch_to_account(uid):
                logger.info("账号管理器切换成功")

                # 获取新的API服务
                api_service = self.account_manager.get_current_api_service()
                if api_service:
                    logger.info("API服务创建成功")
                    self.api_service = api_service

                    # 获取当前账号信息
                    account = self.account_manager.get_current_account()
                    if account:
                        self.username = account.username
                        logger.info(f"切换完成: {self.username}")

                        # 刷新主界面
                        self.refresh_ui()

                        # 显示成功消息
                        QMessageBox.information(
                            self,
                            "切换成功",
                            f"已切换到账号: {self.username}"
                        )
                    else:
                        logger.error("获取当前账号信息失败")
                        QMessageBox.critical(self, "切换失败", "无法获取账号信息")
                else:
                    logger.error("API服务创建失败")
                    QMessageBox.critical(self, "切换失败", "无法创建API服务，请检查账号信息是否完整")
            else:
                logger.error("账号管理器切换失败")
                QMessageBox.critical(self, "切换失败", "账号切换失败,原因未知 ")

        except Exception as e:
            logger.error(f"切换账号异常: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "切换失败", f"发生异常: {e}")

        logger.info("切换账号流程结束")

    def remove_account(self, uid: int):
        """删除账号"""
        logger.info(f"=== 开始删除账号 UID: {uid} ===")

        if not self.account_manager:
            return

        # 获取要删除的账号信息
        account_to_remove = None
        for acc in self.account_manager.get_all_accounts():
            if acc.uid == uid:
                account_to_remove = acc
                break

        if not account_to_remove:
            logger.error(f"未找到账号 UID: {uid}")
            return

        # 检查是否是当前账号
        is_current_account = (self.account_manager.current_account and
                              self.account_manager.current_account.uid == uid)

        # 执行删除
        if self.account_manager.remove_account(uid):
            logger.info(f"账号 {account_to_remove.username} 已从管理器中删除")

            # 如果删除的是当前账号，需要处理切换
            if is_current_account:
                self.api_service = None
                self.username = "未登录"

                # 获取剩余账号
                remaining_accounts = self.account_manager.get_all_accounts()

                if remaining_accounts:
                    # 自动切换到第一个账号
                    first_account = remaining_accounts[0]
                    logger.info(f"自动切换到账号: {first_account.username}")

                    # 使用账号管理器的切换方法
                    if self.account_manager.switch_to_account(first_account.uid):
                        self.api_service = self.account_manager.get_current_api_service()
                        if self.api_service:
                            self.username = first_account.username
                            logger.info(f"成功切换到: {self.username}")
                        else:
                            logger.error("创建API服务失败")
                    else:
                        logger.error("切换账号失败")
                else:
                    logger.info("没有剩余账号，退到未登录状态")

            # 刷新主界面
            self.refresh_ui()

            # 返回成功，让对话框刷新列表
            logger.info("=== 删除账号完成 ===")
        else:
            logger.error(f"删除账号 {uid} 失败")

    def logout_current(self):
        """退出当前账号"""
        if self.account_manager and self.account_manager.current_account:
            current_username = self.account_manager.current_account.username
            current_uid = self.account_manager.current_account.uid

            reply = QMessageBox.question(
                self, "确认退出",
                f"确定要退出账号 '{current_username}' 吗？\n\n账号信息仍会保存，可以随时重新登录。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                # 设置当前账号为非活跃
                self.account_manager.current_account.is_active = False
                self.account_manager.save_accounts()

                # 查找其他可用账号
                other_accounts = [acc for acc in self.account_manager.accounts.values()
                                  if acc.uid != current_uid]

                if other_accounts:
                    # 有其他账号，自动切换到第一个
                    first_account = other_accounts[0]
                    logger.info(f"退出账号 '{current_username}'，自动切换到 '{first_account.username}'")

                    # 设置为活跃并切换
                    first_account.is_active = True
                    self.account_manager.current_account = first_account
                    self.account_manager.save_accounts()

                    # 创建新的API服务
                    self.api_service = self.account_manager.get_current_api_service()
                    if self.api_service:
                        self.username = first_account.username
                        self.refresh_ui()
                        QMessageBox.information(
                            self, "已退出",
                            f"已退出账号 '{current_username}'\n\n自动切换到账号 '{first_account.username}'"
                        )
                    else:
                        # API服务创建失败，退到未登录状态
                        self.account_manager.current_account = None
                        self.api_service = None
                        self.username = "未登录"
                        self.refresh_ui()
                        QMessageBox.warning(
                            self, "已退出",
                            f"已退出账号 '{current_username}'\n\n切换账号失败，请重新登录"
                        )
                else:
                    # 没有其他账号，退到未登录状态
                    self.account_manager.current_account = None
                    self.api_service = None
                    self.username = "未登录"
                    self.refresh_ui()
                    QMessageBox.information(self, "已退出", f"已退出账号 '{current_username}'")
        else:
            # 不应该发生的情况
            QMessageBox.warning(self, "错误", "当前没有登录的账号")

    def logout_all(self):
        """清除所有账号"""
        if self.account_manager:
            reply = QMessageBox.question(
                self, "确认清除",
                "确定要清除所有保存的账号吗？\n\n这将删除所有登录信息，下次需要重新登录。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.account_manager.clear_all_accounts()
                self.api_service = None
                self.username = "未登录"

                self.refresh_ui()
                QMessageBox.information(self, "已清除", "所有账号信息已清除")

    def on_login_success(self, api_service, aicu_state):
        """登录成功处理"""
        self.api_service = api_service
        self.aicu_state = aicu_state

        # 保存账号信息
        if self.account_manager:
            try:
                # 获取用户信息
                uid, username, face_url = api_service.get_cached_user_info()

                # 如果缓存中没有用户信息，同步获取
                if not username:
                    logger.info("缓存中没有用户信息，尝试同步获取")
                    uid, username, face_url = self.account_manager.get_complete_user_info_sync(api_service)

                if username:
                    # 有用户名，直接保存并刷新
                    self.username = username

                    # 保存到账号管理器
                    if self.account_manager.add_account(api_service, username, face_url):
                        logger.info(f"账号已保存: {username}")

                        # 立即刷新界面
                        self.refresh_ui()
                        QMessageBox.information(self, "登录成功",
                                                f"欢迎, {username}!\n\n账号信息已保存，下次启动将自动登录。")
                    else:
                        # 即使保存失败，也更新当前状态
                        self.refresh_ui()
                        QMessageBox.warning(self, "部分成功", "登录成功，但保存账号信息失败")
                else:
                    # 没有用户名，异步获取
                    self.username = "获取中..."
                    self.refresh_ui()
                    self.fetch_username_async(api_service)

                    # 先保存账号（用户名稍后更新）
                    self.account_manager.add_account(api_service, "获取中...", "")
                    QMessageBox.information(self, "登录成功", "登录成功！正在获取用户信息...")

            except Exception as e:
                logger.error(f"保存账号失败: {e}")
                # 即使保存失败，也让用户能正常使用
                self.username = "未知用户"
                self.refresh_ui()
                QMessageBox.warning(self, "部分成功", f"登录成功，但保存账号信息失败: {e}")
        else:
            # 没有账号管理器，直接使用
            self.username = "已登录"
            self.refresh_ui()
            QMessageBox.information(self, "登录成功", "登录成功！")

    def fetch_username_async(self, api_service):
        """异步获取用户名"""
        # 如果已有线程在运行，先停止它
        if self.username_thread and self.username_thread.isRunning():
            self.username_thread.stop()
            self.username_thread.wait(1000)

        self.username_thread = UsernameThread(api_service)
        self.username_thread.username_received.connect(self.on_username_received)
        self.username_thread.error_occurred.connect(self.on_username_error)
        self.username_thread.start()

    def on_username_received(self, username):
        """收到用户名时更新界面"""
        self.username = username
        self.statusBar().showMessage(f"已登录: {username}")

        # 更新侧边栏的用户名显示
        self.refresh_ui()

        # 更新账号管理器中的用户名
        if self.account_manager and self.account_manager.current_account:
            # 更新当前账号的用户名
            self.account_manager.current_account.username = username

            # 同时更新accounts字典中的信息
            uid = self.account_manager.current_account.uid
            if uid in self.account_manager.accounts:
                self.account_manager.accounts[uid].username = username

            # 保存更新
            self.account_manager.save_accounts()
            logger.info(f"已更新账号用户名: {username}")

    def on_username_error(self, error):
        """用户名获取失败"""
        logger.error(f"获取用户名失败: {error}")

    def closeEvent(self, event):
        """窗口关闭时清理资源"""
        # 停止用户名获取线程
        if self.username_thread and self.username_thread.isRunning():
            self.username_thread.stop()
            self.username_thread.wait(1000)

        super().closeEvent(event)

    def refresh_ui(self):
        # 保存当前的工具选中状态
        current_selected = -1
        for i, item in enumerate(self.tool_items):
            if item.selected:
                current_selected = i
                break

        # 正确清理旧的widget
        # 1. 断开信号连接并删除工具项
        for item in self.tool_items:
            try:
                item.clicked.disconnect()  # 断开所有连接
            except:
                pass
            item.deleteLater()  # 标记删除
        self.tool_items.clear()

        # 2. 清理菜单栏
        self.menuBar().clear()

        # 3. 删除主widget（这会级联删除所有子widget）
        old_central = self.centralWidget()
        if old_central:
            old_central.deleteLater()

        # 重新应用样式表
        from ..style import get_stylesheet
        self.setStyleSheet(get_stylesheet())

        # 重新初始化UI
        self.init_ui()

        # 恢复选中状态
        if current_selected >= 0 and current_selected < len(self.tool_items):
            self.tool_items[current_selected].set_selected(True)

    def toggle_aicu_state(self, checked: bool):
        """切换AICU状态"""
        self.aicu_state = checked
        logger.info(f"AICU数据源: {'启用' if checked else '禁用'}")
        # 刷新底部状态显示
        self.refresh_ui()

    def get_current_api_service(self):
        """获取当前API服务"""
        return self.api_service

    def get_aicu_state(self) -> bool:
        """获取AICU状态"""
        return self.aicu_state