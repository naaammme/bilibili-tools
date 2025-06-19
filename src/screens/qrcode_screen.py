import asyncio
import logging
import io
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QCheckBox, QMessageBox
)
from PyQt6.QtCore import pyqtSignal, QTimer, Qt, QThread
from PyQt6.QtGui import QPixmap, QImage
import qrcode
from ..api.api_service import ApiService
from ..api.qr_code import QRData

logger = logging.getLogger(__name__)

class QRCodeFetchThread(QThread):
    #获取二维码线程
    success = pyqtSignal(object)  # 二维码数据
    error = pyqtSignal(str)

    def run(self):
        #运行二维码获取
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            qr_data = loop.run_until_complete(QRData.request_qrcode())
            self.success.emit(qr_data)
        except Exception as e:
            logger.error(f"获取二维码失败: {e}")
            self.error.emit(str(e))
        finally:
            loop.close()


class QRCodeCheckThread(QThread):
    #二维码状态检查线程
    state_changed = pyqtSignal(int, object, object)  # state_code, csrf, cookie
    error = pyqtSignal(str)

    def __init__(self, qr_data: QRData):
        super().__init__()
        self.qr_data = qr_data
        self.api_service = ApiService()

    def run(self):#运行状态检查”
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            async def check():
                async with self.api_service:
                    return await self.qr_data.get_state(self.api_service)

            state_code, csrf, cookie = loop.run_until_complete(check())
            self.state_changed.emit(state_code, csrf, cookie)
        except Exception as e:
            logger.error(f"检查二维码状态失败: {e}")
            self.error.emit(str(e))
        finally:
            loop.close()


class QRCodeScreen(QWidget):#二维码登录页面

    login_success = pyqtSignal(object, bool)  # ApiService, aicu_state
    switch_to_cookie = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.qr_data: Optional[QRData] = None
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_qr_state)
        self.init_ui()
        self.fetch_qr_code()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        #二维码显示
        self.qr_label = QLabel("Loading QR code...")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setMinimumSize(300, 300)
        self.qr_label.setStyleSheet("border: 1px solid #ccc; padding: 10px;")

        # 状态标签
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # AICU 复选框
        self.aicu_checkbox = QCheckBox("同时从aicu.cc获取评论")
        self.aicu_checkbox.setChecked(True)

        # 切换到cookie按钮
        self.switch_btn = QPushButton("改为输入cookie")
        self.switch_btn.clicked.connect(self.switch_to_cookie.emit)

        # Layout
        layout.addWidget(self.qr_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.aicu_checkbox)
        layout.addWidget(self.switch_btn)

        self.setLayout(layout)

    def fetch_qr_code(self):#获取二维码
        self.fetch_thread = QRCodeFetchThread()
        self.fetch_thread.success.connect(self.on_qr_code_fetched)
        self.fetch_thread.error.connect(self.on_fetch_error)
        self.fetch_thread.start()

    def on_qr_code_fetched(self, qr_data: QRData):#处理二维码取回成功
        self.qr_data = qr_data

        # 生成二维码图像
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data.url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        #将PIL图像转换为QPixmap
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        qimage = QImage()
        qimage.loadFromData(buffer.getvalue())
        pixmap = QPixmap.fromImage(qimage)

        # 显示二维码
        self.qr_label.setPixmap(pixmap.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio))

        # 检测状态
        self.check_timer.start(1000)  # 每秒一次

    def on_fetch_error(self, error: str):
        #处理二维码获取错误
        self.qr_label.setText(f"获取二维码失败:\n{error}")
        QMessageBox.critical(self, "Error", f"获取二维码失败: {error}")

    def check_qr_state(self):
       #检测扫描状态
        if not self.qr_data:
            return

        self.check_thread = QRCodeCheckThread(self.qr_data)
        self.check_thread.state_changed.connect(self.on_state_changed)
        self.check_thread.error.connect(lambda e: logger.error(f"状态检查错误: {e}"))
        self.check_thread.start()

    def on_state_changed(self, state_code: int, csrf: Optional[str], cookie: Optional[str]):
        #状态改变
        status_messages = {
            0: "登录成功!",
            86038: "二维码过期",
            86090: "扫描二维码成功，请确认",
            86101: "等待扫码中….."
        }

        status = status_messages.get(state_code, f"未知的状态: {state_code}")
        self.status_label.setText(status)

        if state_code == 0 and csrf and cookie:
            # 登陆成功
            self.check_timer.stop()
            aicu_state = self.aicu_checkbox.isChecked()

            #使用获取的cookie创建ApiService
            api_service = ApiService.new(cookie)
            self.login_success.emit(api_service, aicu_state)
        elif state_code == 86038:
            #QR码过期，重获取
            self.check_timer.stop()
            self.fetch_qr_code()