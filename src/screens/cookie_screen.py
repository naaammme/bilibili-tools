import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QCheckBox, QLabel, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, Qt
from ..api.api_service import ApiService

logger = logging.getLogger(__name__)

class CookieScreen(QWidget):
    # cookie输入登录界面

    login_success = pyqtSignal(object, bool)  # ApiService, aicu_state
    switch_to_qrcode = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        #初始化ui
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 输入cookie
        input_layout = QHBoxLayout()
        self.cookie_input = QLineEdit()
        self.cookie_input.setPlaceholderText("在这里输入cookie")
        self.cookie_input.setMinimumWidth(400)
        self.cookie_input.returnPressed.connect(self.on_submit)

        self.submit_btn = QPushButton("确定")
        self.submit_btn.clicked.connect(self.on_submit)

        input_layout.addWidget(self.cookie_input)
        input_layout.addWidget(self.submit_btn)

        # AICU 复选框
        self.aicu_checkbox = QCheckBox("同时从aicu.cc获取评论")
        self.aicu_checkbox.setChecked(True)

        # 切换到二维码按钮
        self.switch_btn = QPushButton("改为扫描二维码")
        self.switch_btn.clicked.connect(self.switch_to_qrcode.emit)

        # 加入layout
        layout.addLayout(input_layout)
        layout.addWidget(self.aicu_checkbox)
        layout.addWidget(self.switch_btn)

        # Help text
        help_text = QLabel(
            "提示: 点击"
            '<a href="https://www.bilibili.com/opus/846139124598439955">'
            "链接</a>查看获取登录cookie教程"
        )
        help_text.setOpenExternalLinks(True)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        self.setLayout(layout)

    def on_submit(self):
        #处理cookie提交
        cookie = self.cookie_input.text().strip()
        if not cookie:
            QMessageBox.warning(self, "警告", "请输入cookie!")
            return

        try:
            api_service = ApiService.new(cookie)
            aicu_state = self.aicu_checkbox.isChecked()
            self.login_success.emit(api_service, aicu_state)
        except Exception as e:
            logger.error(f"日志含义创建API服务失败: {e}")
            QMessageBox.critical(
                self,
                "错误",
                f"日志含义创建API服务失败: {e}\n\n"
                "确保cookie中含有 'bili_jct' 字段."
            )