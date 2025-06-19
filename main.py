import sys
import asyncio
import logging
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtGui import QIcon
from src.screens.main_screen import MainWindow  # 确保 MainWindow 在 main_screen 中
from src.style import get_stylesheet, get_resource_path


# 在没有控制台的GUI应用中，sys.stdout 和 sys.stderr 可能是 None
# tqdm 等库会尝试写入它们，导致 "'NoneType' has no attribute 'write'" 错误
# 我们提供一个假的流对象来捕获这些写入操作
class DummyStream:
    def write(self, text):
        pass # 什么都不做
    def flush(self):
        pass # 什么都不做

if sys.stdout is None:
    sys.stdout = DummyStream()
if sys.stderr is None:
    sys.stderr = DummyStream()



logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class BilibiliCommentCleaning:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("B站评论清理工具")
        icon_path = get_resource_path("assets/1.png")
        self.app.setWindowIcon(QIcon(icon_path))

        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.setIcon(QIcon(icon_path))
        self.tray_icon.show()
        #UI 优化：应用全局样式表
        self.app.setStyleSheet(get_stylesheet())

        self.main_window = MainWindow()
        # 默认窗口尺寸
        self.main_window.resize(1100, 700)
        self.main_window.setWindowTitle("Bilibili 评论清理工具")

    def run(self):
        self.main_window.show()
        # 用于异步集成的Qasync事件循环
        import qasync
        loop = qasync.QEventLoop(self.app)
        asyncio.set_event_loop(loop)

        with loop:
            loop.run_forever()

if __name__ == "__main__":
    app = BilibiliCommentCleaning()
    app.run()
