import logging
import requests
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFrame, QGridLayout, QMessageBox, QDialog,
    QMenuBar, QMainWindow, QMenu, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QPixmap, QIcon, QAction
from ..api.api_service import ApiService
from ..style import get_resource_path

logger = logging.getLogger(__name__)



class UsernameThread(QThread):
    """用户名获取线程"""
    username_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_service):
        super().__init__()
        self.setObjectName("UsernameThread")  # 添加这行
        self.api_service = api_service
        self._is_running = True

    def stop(self):
        self._is_running = False

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
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #3498db; margin: 15px;")
        layout.addWidget(title)

        # 账号列表
        self.account_list = QListWidget()
        self.refresh_account_list()
        self.account_list.itemDoubleClicked.connect(self.on_account_selected)
        layout.addWidget(QLabel("双击切换账号:"))
        layout.addWidget(self.account_list)

        # 按钮区域
        button_layout = QHBoxLayout()

        # 切换账号按钮
        switch_btn = QPushButton("切换到此账号")
        switch_btn.clicked.connect(self.on_account_selected)
        switch_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 16px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        button_layout.addWidget(switch_btn)

        # 删除账号按钮
        remove_btn = QPushButton("删除账号")
        remove_btn.clicked.connect(self.remove_account)
        remove_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 8px 16px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        button_layout.addWidget(remove_btn)

        button_layout.addStretch()

        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #7f8c8d;
                color: white;
                padding: 8px 16px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #95a5a6;
            }
        """)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def refresh_account_list(self):
        """刷新账号列表"""
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
    """简化的登录对话框 - 移除AICU选择"""
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
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 20px; color: #3498db;")
        layout.addWidget(title)

        # 登录方式选择
        method_layout = QHBoxLayout()

        self.qr_btn = QPushButton("扫码登录")
        self.qr_btn.clicked.connect(self.show_qr_login)
        self.qr_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        method_layout.addWidget(self.qr_btn)

        self.cookie_btn = QPushButton("Cookie登录")
        self.cookie_btn.clicked.connect(self.show_cookie_login)
        self.cookie_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
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


class ToolSelectionScreen(QMainWindow):

    # 信号定义
    open_comment_tool = pyqtSignal()
    open_unfollow_tool = pyqtSignal()
    open_comment_stats_tool = pyqtSignal()
    open_message_tool = pyqtSignal()
    open_message_tool = pyqtSignal()

    def __init__(self, api_service: ApiService, aicu_state: bool):
        super().__init__()
        self.api_service = api_service
        self.aicu_state = aicu_state
        self.username = "未登录"
        self.username_thread = None  # 保存线程引用

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
        # 创建菜单栏
        self.create_menu_bar()

        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(25)

        # 顶部区域
        self.create_header_area(main_layout)

        # 工具区域
        self.create_tools_area(main_layout)

        # 底部区域
        self.create_footer_area(main_layout)

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
                manage_action = QAction('   管理账号...', self)
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

        aicu_action = QAction('AICU数据源(第三方数据源,会披露您的uid)', self)
        aicu_action.setCheckable(True)
        aicu_action.setChecked(self.aicu_state)
        aicu_action.triggered.connect(self.toggle_aicu_state)
        settings_menu.addAction(aicu_action)

        settings_menu.addSeparator()
        clear_cache_action = QAction('清除本地缓存', self)
        clear_cache_action.triggered.connect(self.clear_local_cache)
        settings_menu.addAction(clear_cache_action)

    def clear_local_cache(self):
        """清除本地缓存"""
        if not self.account_manager:
            QMessageBox.information(self, "提示", "账号管理器不可用")
            return

        cache_dir = self.account_manager.get_cache_directory()
        reply = QMessageBox.question(
            self, "确认清除",
            f"确定要清除所有本地缓存吗？\n\n这将删除：\n- 所有保存的账号信息\n- 所有缓存数据\n\n缓存位置：{cache_dir}",
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

    def create_header_area(self, main_layout):
        """创建顶部区域"""
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 应用标题
        app_title = QLabel("Bilibili 工具集")
        app_font = QFont()
        app_font.setPointSize(28)
        app_font.setBold(True)
        app_title.setFont(app_font)
        app_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_title.setStyleSheet("color: #3498db; margin-bottom: 15px;")
        header_layout.addWidget(app_title)

        # 账号状态区域
        status_layout = QHBoxLayout()
        status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 状态图标和文字
        if self.api_service:
            status_text = f"🟢 欢迎, {self.username}"
            status_color = "#27ae60"
        else:
            status_text = "🔴 未登录"
            status_color = "#e74c3c"

        self.welcome_label = QLabel(status_text)
        welcome_font = QFont()
        welcome_font.setPointSize(16)
        self.welcome_label.setFont(welcome_font)
        self.welcome_label.setStyleSheet(f"color: {status_color};")
        status_layout.addWidget(self.welcome_label)

        header_layout.addLayout(status_layout)

        # 登录/账号管理按钮
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if not self.api_service:
            # 未登录时显示登录按钮
            login_btn = QPushButton("点击登录")
            login_btn.clicked.connect(self.show_login_dialog)
            login_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    padding: 12px 30px;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: bold;
                    margin-top: 15px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
            """)
            button_layout.addWidget(login_btn)
        else:
            # 已登录时显示账号管理按钮（如果有多个账号）
            if self.account_manager and len(self.account_manager.get_all_accounts()) > 1:
                manage_btn = QPushButton("切换账号")
                manage_btn.clicked.connect(self.show_account_management)
                manage_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #3498db;
                        color: white;
                        padding: 10px 20px;
                        border-radius: 6px;
                        font-size: 14px;
                        margin-top: 10px;
                    }
                    QPushButton:hover {
                        background-color: #2980b9;
                    }
                """)
                button_layout.addWidget(manage_btn)

        header_layout.addLayout(button_layout)
        main_layout.addLayout(header_layout)

    def create_tools_area(self, main_layout):
        """创建工具区域"""
        # 提示文字
        if self.api_service:
            hint_text = "请选择你要使用的工具:"
            hint_color = "#bdc3c7"
        else:
            hint_text = "登录后即可使用以下工具:"
            hint_color = "#e74c3c"

        hint_label = QLabel(hint_text)
        hint_font = QFont()
        hint_font.setPointSize(14)
        hint_label.setFont(hint_font)
        hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint_label.setStyleSheet(f"color: {hint_color}; margin: 20px 0;")
        main_layout.addWidget(hint_label)

        # 工具网格
        tools_layout = QHBoxLayout()
        tools_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tools_layout.setSpacing(40)

        # 工具卡片
        tools = [
            {
                "title": "评论清理工具",
                "description": "清理你的评论、弹幕和通知\n支持批量删除和搜索过滤\n双击评论可查看完整对话",  # 更新描述
                "enabled": bool(self.api_service),
                "callback": self.open_comment_tool.emit
            },
            {
                "title": "批量取关工具",
                "description": "批量管理你关注的UP主\n支持分组浏览和搜索\n一键取消关注多个UP主",
                "enabled": bool(self.api_service),
                "callback": self.open_unfollow_tool.emit
            },
            {
                "title": "数据统计中心",  # 更新标题
                "description": "查看你的数据统计概览\n评论、弹幕、私信、通知统计\n数据来源和时间分布",  # 更新描述
                "enabled": bool(self.api_service),
                "callback": self.open_comment_stats_tool.emit
            },
            {
                "title": "私信管理工具",
                "description": "管理你的B站私信\n批量删除和搜索过滤\n双击查看对话详情",
                "enabled": bool(self.api_service),
                "callback":self.open_message_tool.emit
            }
        ]

        for tool in tools:
            card = self.create_clean_tool_card(
                tool["title"],
                tool["description"],
                tool["enabled"],
                tool["callback"]
            )
            tools_layout.addWidget(card)

        main_layout.addLayout(tools_layout)

    def create_clean_tool_card(self, title: str, description: str, enabled: bool, callback):
        """创建简洁的工具卡片"""
        card = QFrame()
        card.setFrameStyle(QFrame.Shape.Box)
        card.setLineWidth(1)
        card.setObjectName("toolCard")

        if enabled:
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.mousePressEvent = lambda event: callback() if event.button() == Qt.MouseButton.LeftButton else None
        else:
            # 未登录时点击弹出登录提示
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.mousePressEvent = lambda event: self.show_login_prompt() if event.button() == Qt.MouseButton.LeftButton else None

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)

        # 图标区域
        if enabled:
            icon_label = QLabel("🛠️")
            icon_color = "#3498db"
        else:
            icon_label = QLabel("🔒")
            icon_color = "#7f8c8d"

        icon_label.setStyleSheet(f"font-size: 48px; margin-bottom: 10px; color: {icon_color};")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        # 标题
        title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # 描述
        desc_label = QLabel(description)
        desc_font = QFont()
        desc_font.setPointSize(12)
        desc_label.setFont(desc_font)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setMinimumHeight(80)
        layout.addWidget(desc_label)

        card.setLayout(layout)
        card.setFixedSize(320, 280)

        # 设置样式
        if enabled:
            card.setStyleSheet("""
                QFrame#toolCard {
                    background-color: #34495e;
                    border: 3px solid #566573;
                    border-radius: 15px;
                }
                QFrame#toolCard:hover {
                    border-color: #3498db;
                    background-color: #3c4a5a;
                }
                QFrame#toolCard QLabel {
                    background-color: transparent;
                    border: none;
                    color: #ecf0f1;
                }
            """)
        else:
            card.setStyleSheet("""
                QFrame#toolCard {
                    background-color: #2c3e50;
                    border: 3px solid #34495e;
                    border-radius: 15px;
                }
                QFrame#toolCard:hover {
                    border-color: #7f8c8d;
                    background-color: #34495e;
                }
                QFrame#toolCard QLabel {
                    background-color: transparent;
                    border: none;
                    color: #7f8c8d;
                }
            """)

        return card

    def create_footer_area(self, main_layout):
        """创建底部区域"""
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 30, 0, 0)

        # AICU状态
        aicu_status = QLabel(f"AICU数据源: {'启用' if self.aicu_state else '禁用'}")
        aicu_status.setStyleSheet(f"""
            color: {'#27ae60' if self.aicu_state else '#e74c3c'}; 
            font-size: 12px;
            font-weight: bold;
        """)
        footer_layout.addWidget(aicu_status)

        footer_layout.addStretch()

        # 账号信息
        if self.account_manager and self.account_manager.has_accounts():
            account_count = len(self.account_manager.accounts)
            account_info = QLabel(f"已保存 {account_count} 个账号")
            account_info.setStyleSheet("color: #3498db; font-size: 12px;")
            footer_layout.addWidget(account_info)

        # 版本信息
        version_label = QLabel("版本: 1.4.10")
        version_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        footer_layout.addWidget(version_label)

        main_layout.addLayout(footer_layout)

    def show_login_prompt(self):
        """显示登录提示"""
        QMessageBox.information(
            self, "需要登录",
            "请先登录账号才能使用此工具。\n\n点击上方的'点击登录'按钮或使用菜单栏登录。"
        )

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
        logger.info(f"=== 开始切换账号到 UID: {uid} ===")

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
                QMessageBox.critical(self, "切换失败", "账号切换失败，请查看日志")

        except Exception as e:
            logger.error(f"切换账号异常: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "切换失败", f"发生异常: {e}")

        logger.info("=== 切换账号流程结束 ===")

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
        if hasattr(self, 'welcome_label'):
            self.welcome_label.setText(f"🟢 欢迎, {username}")
        self.statusBar().showMessage(f"已登录: {username}")

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
        """刷新界面"""
        self.menuBar().clear()
        self.init_ui()

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