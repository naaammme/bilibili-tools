import asyncio
import logging
import threading
import time


from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QPushButton, QLabel, QCheckBox,
    QScrollArea, QLineEdit, QSpinBox, QMessageBox,
    QProgressBar, QStackedWidget, QTextEdit, QTableWidgetItem, QAbstractItemView, QTableWidget, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices
from typing import Optional, Dict, Callable, List, Union



from ..types import Screen, Comment, Danmu, Notify, FetchProgressState, ActivityInfo
from ..api.api_service import ApiService
from ..api.notify import fetch as fetch_data
from ..utils import fuzzy_search

from ..database.models import CommentRecord, DanmuRecord, NotifyRecord

# from .tool_selection_screen import ToolSelectionScreen

logger = logging.getLogger(__name__)

class FetchThread(QThread):
    """用于获取数据的线程"""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    status_update = pyqtSignal(str)
    # 活动信息更新信号
    activity_update = pyqtSignal(object)  # ActivityInfo对象

    def __init__(self, api_service, aicu_state, progress_state):
        super().__init__()
        self.api_service = api_service
        self.aicu_state = aicu_state
        self.progress_state = progress_state
        self._is_running = True
        self._stop_flag = threading.Event()

    def stop(self):
        """停止线程"""
        self._is_running = False
        self._stop_flag.set()
        logger.info("FetchThread stop requested")

    def run(self):
        # 创建新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def progress_callback(message_or_info: Union[str, ActivityInfo]):
            if self._is_running:
                if isinstance(message_or_info, ActivityInfo):
                    # 发送活动信息
                    self.activity_update.emit(message_or_info)
                    # 同时发送简化的状态文本
                    self.status_update.emit(str(message_or_info))
                else:
                    # 保持向后兼容性，处理字符串消息
                    self.status_update.emit(message_or_info)

        try:
            result = loop.run_until_complete(self._fetch_with_session(progress_callback))
            if self._is_running:
                self.finished.emit(result)
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            if self._is_running:
                self.error.emit(str(e))
        finally:
            try:
                # 更强力的清理所有挂起的任务
                tasks = asyncio.all_tasks(loop=loop)
                for task in tasks:
                    if not task.done():
                        task.cancel()
                if tasks:
                    try:
                        loop.run_until_complete(
                            asyncio.wait_for(
                                asyncio.gather(*tasks, return_exceptions=True),
                                timeout=2.0  # 2秒超时
                            )
                        )
                    except asyncio.TimeoutError:
                        logger.warning("Some tasks didn't cancel in time")
                    except Exception as e:
                        logger.error(f"Error during task cancellation: {e}")
            except Exception as e:
                logger.error(f"Error cancelling tasks: {e}")
            finally:
                try:
                    if not loop.is_closed():
                        loop.close()
                except Exception as e:
                    logger.error(f"Error closing event loop: {e}")



    async def _fetch_with_session(self, progress_callback: Callable[[Union[str, ActivityInfo]], None]):
        if not self._is_running:
            return None

        def wrapped_callback(message_or_info):
            if self._is_running:
                progress_callback(message_or_info)
        """在新的事件循环中创建新的ApiService实例来避免session冲突"""
        # 创建一个新的ApiService实例，避免session冲突
        temp_api_service = self.api_service.__class__(
            csrf=self.api_service.csrf,
            cookie=self.api_service.cookie
        )

        # 复制用户缓存
        temp_api_service.user_cache = self.api_service.user_cache

        try:
            # 确保在async context中使用临时ApiService
            async with temp_api_service:
                return await fetch_data(temp_api_service, self.aicu_state, self.progress_state, progress_callback)
        finally:
            # 清理临时ApiService
            try:
                await temp_api_service.close()
            except Exception as e:
                logger.debug(f"Error closing temp api_service: {e}")

class DeleteThread(QThread):
    item_deleted = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, api_service, items, item_type, sleep_seconds, delete_db=False, db_manager=None, uid=None):
        super().__init__()
        self.api_service, self.items, self.item_type, self.sleep_seconds = api_service, items, item_type, sleep_seconds
        self.delete_db = delete_db
        self.db_manager = db_manager
        self.uid = uid
        self._is_running = True

    def stop(self): self._is_running = False

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try: loop.run_until_complete(self._delete_items())
        except Exception as e:
            logger.error(f"Delete error: {e}")
            self.error.emit(str(e))
        finally:
            try: loop.close()
            except: pass

    async def _delete_items(self):
        total, current = len(self.items), 0
        for item_id, item in self.items:
            if not self._is_running: break
            current += 1
            self.progress.emit(current, total)
            try:
                if self.item_type == "评论":
                    from ..api.comment import remove_comment
                    await remove_comment(item, item_id, self.api_service)
                elif self.item_type == "通知":
                    from ..api.notify import remove_notify
                    await remove_notify(item, item_id, self.api_service)

                # API删除成功后，检查是否需要删除数据库记录
                if self.delete_db and self.db_manager and self.uid:
                    try:
                        if self.item_type == "评论":
                            self.db_manager.delete_comment_permanently(item_id, self.uid)
                        elif self.item_type == "弹幕":
                            self.db_manager.delete_danmu_permanently(item_id, self.uid)
                        elif self.item_type == "通知":
                            self.db_manager.delete_notify_permanently(item_id, self.uid)
                        logger.info(f"数据库中的 {self.item_type} {item_id} 已永久删除")
                    except Exception as e:
                        logger.error(f"删除数据库记录失败: {e}")

                self.item_deleted.emit(item_id)
                logger.info(f"Deleted {self.item_type} {item_id}")
            except Exception as e:
                logger.error(f"Failed to delete {self.item_type} {item_id}: {e}")
                self.error.emit(f"删除 {self.item_type} (ID: {item_id}) 失败: {e}")
            if self._is_running and current < total:
                logger.info(f"[DeleteThread] sleep {self.sleep_seconds} seconds before next delete...")
                print(f"[DeleteThread] sleep {self.sleep_seconds} seconds before next delete...")
                await asyncio.sleep(self.sleep_seconds)
        self.finished.emit()


class ItemViewer(QWidget):
    delete_requested = pyqtSignal(list, str, int)

    # 定义
    comment_double_clicked = pyqtSignal(int, int, int)  # comment_id, oid, type
    danmu_double_clicked = pyqtSignal(int)  # dmid
    notify_double_clicked = pyqtSignal(int)  # notify_id

    def __init__(self, item_type: str, api_service: ApiService):
        super().__init__()
        self.item_type, self.api_service = item_type, api_service
        self.all_items: Dict[int, any] = {}
        self.items: Dict[int, any] = {}
        self.checkboxes: Dict[int, QCheckBox] = {}
        self.is_deleting = False
        self.init_ui()

    def init_ui(self):
        self.setObjectName("mainPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(f"搜索{self.item_type}...")
        self.search_input.returnPressed.connect(self.filter_items)
        search_layout.addWidget(self.search_input)
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self.filter_items)
        search_layout.addWidget(search_btn)
        layout.addLayout(search_layout)

        header_layout = QHBoxLayout()
        self.header_label = QLabel("0 已选择 / 共 0 项")
        header_layout.addWidget(self.header_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        header_layout.addWidget(self.progress_bar)
        layout.addLayout(header_layout)

        # 使用 QTableWidget 替代滚动区域
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["选择", "内容"])

        # 设置表格属性
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # 双击事件
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.table.itemChanged.connect(self.on_item_changed)

        # 设置objectName
        self.table.setObjectName("commentDataTable")

        layout.addWidget(self.table)

        controls_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        controls_layout.addWidget(self.select_all_btn)
        self.select_all_btn.clicked.connect(self.select_all)
        controls_layout.addStretch()
        controls_layout.addWidget(QLabel("删除间隔:"))
        self.sleep_input = QSpinBox()
        self.sleep_input.setMinimum(0); self.sleep_input.setMaximum(10); self.sleep_input.setValue(3); self.sleep_input.setSuffix(" s")
        controls_layout.addWidget(self.sleep_input)
        self.delete_btn = QPushButton("删除")
        self.delete_btn.setObjectName("deleteButton")
        self.delete_btn.clicked.connect(self.delete_selected)
        controls_layout.addWidget(self.delete_btn)
        layout.addLayout(controls_layout)

    def set_items_async(self, items: Dict[int, any]):
        """异步设置项目"""
        self.all_items = items.copy()
        # 使用QTimer延迟执行，让UI有机会更新
        QTimer.singleShot(0, self.filter_items)

    def set_items(self, items: Dict[int, any]):
        self.all_items = items.copy()
        self.filter_items()

    def filter_items(self):
        search_text = self.search_input.text().strip()
        self.items = {k: v for k, v in self.all_items.items() if
                      not search_text or fuzzy_search(search_text, v.content)}
        self.refresh_display()

    def refresh_display(self):
        """使用表格高效显示数据"""
        # 清空表格
        self.table.setRowCount(0)

        # 批量添加行
        items_list = list(self.items.items())
        row_count = len(items_list)

        # 一次性设置行数
        self.table.setRowCount(row_count)

        # 暂时禁用更新以提高性能
        self.table.setUpdatesEnabled(False)

        try:
            for row, (item_id, item) in enumerate(items_list):
                # 复选框
                checkbox_item = QTableWidgetItem()
                checkbox_item.setCheckState(Qt.CheckState.Checked if item.is_selected else Qt.CheckState.Unchecked)
                checkbox_item.setData(Qt.ItemDataRole.UserRole, item_id)
                self.table.setItem(row, 0, checkbox_item)

                # 内容
                content_display = item.content
                if len(content_display) > 200:  # 限制显示长度
                    content_display = content_display[:200] + "..."

                if self.item_type == "弹幕" and hasattr(item, 'source'):
                    content_display = f"[{item.source.upper()}] {content_display}"

                content_item = QTableWidgetItem(content_display)
                content_item.setData(Qt.ItemDataRole.UserRole, (item_id, item))
                self.table.setItem(row, 1, content_item)

                # 设置行高
                self.table.setRowHeight(row, 40)
        finally:
            # 重新启用更新
            self.table.setUpdatesEnabled(True)

        self.update_header()

    def on_cell_double_clicked(self, row, column):
        """处理表格双击事件"""
        if column == 1:  # 只响应内容列的双击
            content_item = self.table.item(row, 1)
            if content_item:
                item_id, item = content_item.data(Qt.ItemDataRole.UserRole)
                self.handle_double_click(item_id, item)

    def on_item_changed(self, item):
        """处理表格项改变事件"""
        if item.column() == 0:  # 只处理复选框列
            item_id = item.data(Qt.ItemDataRole.UserRole)
            if item_id:
                is_checked = item.checkState() == Qt.CheckState.Checked
                self.toggle_item(item_id, is_checked)

    def handle_double_click(self, item_id: int, item):
        """处理双击事件"""
        logger.info(f"双击 {self.item_type}: ID={item_id}")

        if self.item_type == "评论":
            # 获取主窗口
            main_window = self.window()  # 使用 window() 方法获取顶层窗口
            if isinstance(main_window, CommentCleanScreen):
                main_window.handle_comment_double_click_direct(item_id, item)
            else:
                logger.error("无法找到主窗口")

        elif self.item_type == "弹幕":
            self._handle_danmu_double_click_direct(item_id, item)
        elif self.item_type == "通知":
            self.show_notify_detail(item_id, item)

    def show_notify_detail(self, notify_id: int, notify_item):
        """显示通知的完整内容"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton

        dialog = QDialog(self)
        dialog.setWindowTitle(f"通知详情 - ID: {notify_id}")
        dialog.resize(600, 400)

        layout = QVBoxLayout()

        # 文本框显示完整内容
        text_edit = QTextEdit()
        text_edit.setPlainText(notify_item.content)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)

        dialog.setLayout(layout)
        dialog.exec()

    def _handle_danmu_double_click_direct(self, dmid: int, danmu_item):
        """直接处理弹幕双击事件，避免信号传递问题"""
        logger.info(f"弹幕双击: dmid={dmid}")

        try:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl

            if hasattr(danmu_item, 'source') and danmu_item.source == "aicu":
                # AICU来源的弹幕，跳转到AICU网站
                # 需要通过parent获取api_service
                main_screen = self.parent()
                while main_screen and not hasattr(main_screen, 'api_service'):
                    main_screen = main_screen.parent()

                if main_screen and hasattr(main_screen, 'api_service'):
                    uid, _, _ = main_screen.api_service.get_cached_user_info()
                    if uid:
                        aicu_url = f"https://www.aicu.cc/videodanmu.html?uid={uid}"
                        logger.info(f"打开AICU弹幕链接: {aicu_url}")
                        QDesktopServices.openUrl(QUrl(aicu_url))
                    else:
                        from PyQt6.QtWidgets import QMessageBox
                        QMessageBox.warning(self, "错误", "无法获取用户UID")
                else:
                    from PyQt6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "错误", "无法获取API服务")
            else:
                # B站官方来源的弹幕
                if hasattr(danmu_item, 'video_url') and danmu_item.video_url:
                    # 使用保存的视频链接（包含dmid）
                    logger.info(f"打开B站视频链接: {danmu_item.video_url}")
                    QDesktopServices.openUrl(QUrl(danmu_item.video_url))
                else:
                    # 如果没有video_url，尝试构造链接
                    logger.warning(f"弹幕 {dmid} 没有video_url，尝试其他方式")

                    # 可以尝试通过dmid搜索
                    search_url = f"https://www.bilibili.com/video/BV1rJNjzGEWY?dm_progress=7474&p=1&dmid={dmid}"
                    logger.info(f"使用dmid搜索: {search_url}")
                    QDesktopServices.openUrl(QUrl(search_url))

        except Exception as e:
            logger.error(f"打开弹幕链接失败: {e}")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "打开失败", f"无法打开弹幕链接: {e}")

    def toggle_item(self, item_id: int, checked: bool):
        """切换项目选中状态"""
        if item_id in self.items:
            self.items[item_id].is_selected = checked
        if item_id in self.all_items:
            self.all_items[item_id].is_selected = checked

        self.update_header()

    def update_header(self):
        selected = sum(1 for item in self.items.values() if item.is_selected)
        total = len(self.items)
        self.header_label.setText(f"{selected} 已选择 / 共 {total} 项")

    def select_all(self):
        """全选/取消全选"""
        is_all_selected = all(item.is_selected for item in self.items.values()) if self.items else False
        new_state = not is_all_selected

        # 更新数据
        for item_id in self.items.keys():
            self.items[item_id].is_selected = new_state
            if item_id in self.all_items:
                self.all_items[item_id].is_selected = new_state

        # 更新表格显示
        for row in range(self.table.rowCount()):
            checkbox_item = self.table.item(row, 0)
            if checkbox_item:
                checkbox_item.setCheckState(Qt.CheckState.Checked if new_state else Qt.CheckState.Unchecked)

        self.select_all_btn.setText("取消全选" if new_state else "全选")
        self.update_header()

    def delete_selected(self):
        """删除选中项"""
        if self.item_type == '弹幕':
            asyncio.create_task(self.show_danmu_delete_dialog())
            return

        if self.is_deleting:
            self.stop_deletion()
        else:
            selected_items = [(id, item) for id, item in self.items.items() if item.is_selected]
            if selected_items:
                self.start_deletion(selected_items)
            else:
                QMessageBox.warning(self, "警告", "未选择任何项目！")

    async def show_danmu_delete_dialog(self):
        try:
            uid = await self.api_service.get_uid()
            if not uid:
                QMessageBox.critical(self, "错误", "未能获取到用户UID，无法生成删除链接。")
                return

            url = f"https://www.aicu.cc/videodanmu.html?uid={uid}"

            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setWindowTitle("无法直接删除弹幕")
            msg_box.setTextFormat(Qt.TextFormat.RichText)
            msg_box.setText(f"由于B站官方API限制，本工具无法直接删除您的弹幕。<br><br>"
                            f"如果只需要删除弹幕通知,请在通知窗口搜索关键词删除<br><br>"
                            f"如需删除弹幕本身,请点击链接跳转至第三方网站手动删除：<br>"
                            f"<a href='{url}'>{url}</a>")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

        except Exception as e:
            logger.error(f"显示弹幕删除对话框时出错: {e}")
            QMessageBox.critical(self, "错误", f"出现了一个错误: {e}")

    def start_deletion(self, selected_items):
        self.is_deleting = True
        self.delete_btn.setText("停止")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(selected_items))
        self.progress_bar.setValue(0)
        self.delete_requested.emit(selected_items, self.item_type, self.sleep_input.value())

    def stop_deletion(self):
        self.is_deleting = False
        self.delete_btn.setText("删除")
        self.progress_bar.setVisible(False)
        self.delete_requested.emit([], self.item_type, 0)

    @pyqtSlot(int)
    def on_item_deleted(self, item_id: int):
        self.remove_item(item_id)
        current_value = self.progress_bar.value()
        self.progress_bar.setValue(current_value + 1)

    @pyqtSlot()
    def on_deletion_finished(self):
        self.is_deleting = False
        self.delete_btn.setText("删除")
        self.progress_bar.setVisible(False)

    def remove_item(self, item_id: int):
        """删除项目后更新显示"""
        if item_id in self.all_items:
            del self.all_items[item_id]
        if item_id in self.items:
            del self.items[item_id]

            # 找到并删除表格中的行
            for row in range(self.table.rowCount()):
                checkbox_item = self.table.item(row, 0)
                if checkbox_item and checkbox_item.data(Qt.ItemDataRole.UserRole) == item_id:
                    self.table.removeRow(row)
                    break

            self.update_header()

    def _connect_double_click_signal(self, text_edit, item_id, item):
        """安全地连接双击信号，避免变量捕获问题"""

        def on_double_click():
            self.handle_double_click(item_id, item)

        text_edit.double_clicked.connect(on_double_click)

class CommentCleanScreen(QWidget):
    # 添加返回信号
    back_to_tools = pyqtSignal()
    #打开评论详情
    open_comment_detail = pyqtSignal(object)
    window_closed = pyqtSignal()

    def __init__(self, api_service: ApiService, aicu_state: bool):
        super().__init__()
        self.api_service, self.aicu_state = api_service, aicu_state

        try:
            from ..database import DatabaseManager, SyncManager
            self.db_manager = DatabaseManager()
            self.sync_manager = SyncManager(self.db_manager)
            self.database_enabled = True
            logger.info("数据库功能已启用")
        except ImportError as e:
            logger.warning(f"数据库模块不可用: {e}")
            self.database_enabled = False
            self.db_manager = None
            self.sync_manager = None

        self.progress_state = FetchProgressState()
        self.delete_threads = {}
        self.all_comments, self.all_danmus, self.all_notifies = {}, {}, {}
        # 添加状态变量
        self.is_cascade_delete_enabled = True
        self.is_delete_db_enabled = False
        # 存储各类型的活动信息
        self.activity_stats = {
            "liked": {"count": 0, "speed": 0.0, "active": False},
            "replyed": {"count": 0, "speed": 0.0, "active": False},
            "ated": {"count": 0, "speed": 0.0, "active": False},
            "system": {"count": 0, "speed": 0.0, "active": False},
            "aicu_comments": {"count": 0, "speed": 0.0, "active": False},
            "aicu_danmus": {"count": 0, "speed": 0.0, "active": False}
        }
        self.completed_stages = set()
        self.init_ui()
        self.show_empty_state()

        # 连接双击信号
        self.connect_double_click_signals()

        self._is_closing = False

        self._is_closing = False

    def handle_comment_double_click_direct(self, comment_id: int, comment):
        """直接处理评论双击（绕过信号）"""
        logger.info(f"评论双击（直接调用）: comment_id={comment_id}, oid={comment.oid}, type={comment.type}")

        # 检查登录状态
        if not self.api_service:
            QMessageBox.warning(self, "未登录", "请先登录账号才能查看评论详情。")
            return

        # 创建并显示详情窗口
        try:
            from .comment_detail_screen import CommentDetailScreen
            self.detail_window = CommentDetailScreen(
                self.api_service,
                comment_id,
                comment.oid,
                comment.type,
                comment_data=comment
            )

            self.detail_window.setWindowTitle(f"评论详情 - ID: {comment_id}")
            self.detail_window.resize(800, 600)
            self.detail_window.show()
        except Exception as e:
            logger.error(f"打开评论详情失败: {e}")
            import traceback
            traceback.print_exc()


    def connect_double_click_signals(self):
        """连接双击信号"""
        # 连接评论双击信号
        self.comment_viewer.comment_double_clicked.connect(self.handle_comment_double_click)

        # 连接弹幕双击信号(以已删,)

        # 连接通知双击信号（暂时不处理）
        self.notify_viewer.notify_double_clicked.connect(self.handle_notify_double_click)

    @pyqtSlot(int, int, int)
    def handle_comment_double_click(self, comment_id: int, oid: int, type_: int):
        """处理评论双击事件"""
        logger.info(f"评论双击: comment_id={comment_id}, oid={oid}, type={type_}")

        # 检查登录状态
        if not self.api_service:
            QMessageBox.warning(self, "未登录", "请先登录账号才能查看评论详情。")
            return

        # 根据comment_id从self.all_comments中找到对应的comment对象
        if comment_id not in self.all_comments:
            QMessageBox.warning(self, "错误", "未找到对应的评论信息")
            return

        comment = self.all_comments[comment_id]

        # 创建并显示详情窗口
        try:
            from .comment_detail_screen import CommentDetailScreen
            self.detail_window = CommentDetailScreen(
                self.api_service,
                comment_id,
                oid,
                type_,
                comment_data=comment
            )

            self.detail_window.setWindowTitle(f"评论详情 - ID: {comment_id}")
            self.detail_window.resize(800, 600)
            self.detail_window.show()
        except Exception as e:
            logger.error(f"打开评论详情失败: {e}")
            import traceback
            traceback.print_exc()



    @pyqtSlot(int)
    def handle_notify_double_click(self, notify_id: int):
        """处理通知双击事件（暂时不处理）"""
        logger.info(f"通知双击: notify_id={notify_id}")
        QMessageBox.information(self, "提示", "通知详情功能暂未实现")


    def show_empty_state(self):
        """显示空状态的主界面"""
        # 直接显示主内容页面，但列表为空
        self.stacked_widget.setCurrentWidget(self.main_content_widget)

        # 清空所有列表
        self.comment_viewer.set_items({})
        self.danmu_viewer.set_items({})
        self.notify_viewer.set_items({})

        logger.info("评论清理工具已准备就绪，等待用户操作")

    def init_ui(self):
        self.main_layout = QVBoxLayout(self); self.main_layout.setContentsMargins(10, 10, 10, 10)

        # 添加顶部工具栏
        toolbar_layout = QHBoxLayout()

        # 返回按钮
        back_btn = QPushButton("← 返回工具选择")
        back_btn.clicked.connect(self.safe_back_to_tools)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #7f8c8d;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #95a5a6;
            }
        """)
        toolbar_layout.addWidget(back_btn)

        # 标题
        title_label = QLabel("评论清理工具")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #ecf0f1;")
        toolbar_layout.addWidget(title_label)

        toolbar_layout.addStretch()
        self.main_layout.addLayout(toolbar_layout)

        self.stacked_widget = QStackedWidget(); self.main_layout.addWidget(self.stacked_widget)

        self.loading_widget = QWidget()
        loading_layout = QVBoxLayout(self.loading_widget); loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("正在初始化...")
        font = self.status_label.font(); font.setPointSize(16); self.status_label.setFont(font)
        loading_layout.addWidget(self.status_label)

        # 活动指示器 - 使用不确定进度的进度条
        self.activity_indicator = QProgressBar()
        self.activity_indicator.setRange(0, 0)  # 无限滚动模式
        self.activity_indicator.setMinimumWidth(400)
        self.activity_indicator.setMaximumHeight(20)
        loading_layout.addWidget(self.activity_indicator)

        # 详细活动信息标签
        self.activity_label = QLabel("")
        activity_font = self.activity_label.font(); activity_font.setPointSize(11); self.activity_label.setFont(activity_font)
        self.activity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.activity_label.setStyleSheet("color: #7FB3D3; margin-top: 10px;")
        self.activity_label.setWordWrap(True)
        loading_layout.addWidget(self.activity_label)

        self.stacked_widget.addWidget(self.loading_widget)

        self.main_content_widget = QWidget()
        content_layout = QVBoxLayout(self.main_content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0); content_layout.setSpacing(10)

        # 创建复选框容器
        checkbox_layout = QHBoxLayout()

        self.cascade_delete_checkbox = QCheckBox("删除通知时同时删除关联的评论")
        self.cascade_delete_checkbox.setChecked(False)  # 改为默认不勾选
        # 连接toggled信号到一个新的槽函数
        self.cascade_delete_checkbox.toggled.connect(self.on_cascade_checkbox_toggled)
        checkbox_layout.addWidget(self.cascade_delete_checkbox)

        # 新增数据库删除复选框
        self.delete_db_checkbox = QCheckBox("删除数据时同时删除数据库记录")
        self.delete_db_checkbox.setChecked(False)  # 默认不勾选
        self.delete_db_checkbox.toggled.connect(self.on_delete_db_checkbox_toggled)
        checkbox_layout.addWidget(self.delete_db_checkbox)

        checkbox_layout.addStretch()  # 添加弹性空间
        content_layout.addLayout(checkbox_layout)

        if self.database_enabled:
            db_layout = QHBoxLayout()

            # 从数据库加载按钮
            self.load_from_db_btn = QPushButton("📁 从数据库加载")
            self.load_from_db_btn.clicked.connect(self.load_from_database)
            self.load_from_db_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    padding: 8px 15px;
                    border-radius: 6px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #2ecc71;
                }
            """)
            db_layout.addWidget(self.load_from_db_btn)

            # 获取全量数据按钮
            self.fetch_all_btn = QPushButton("🔄 获取全部数据")
            self.fetch_all_btn.clicked.connect(self.fetch_all_data)
            self.fetch_all_btn.setStyleSheet("""
                 QPushButton {
                     background-color: #3498db;
                     color: white;
                     padding: 8px 15px;
                     border-radius: 6px;
                     font-size: 13px;
                 }
                 QPushButton:hover {
                     background-color: #2980b9;
                 }
             """)
            db_layout.addWidget(self.fetch_all_btn)

            # 获取新数据按钮
            self.fetch_new_btn = QPushButton("🔄 获取新数据")
            self.fetch_new_btn.clicked.connect(self.fetch_new_data)
            self.fetch_new_btn.setStyleSheet("""
                   QPushButton {
                       background-color: #f39c12;
                       color: white;
                       padding: 8px 15px;
                       border-radius: 6px;
                       font-size: 13px;
                   }
                   QPushButton:hover {
                       background-color: #e67e22;
                   }
               """)
            db_layout.addWidget(self.fetch_new_btn)

            # 保存到数据库按钮
            self.save_to_db_btn = QPushButton("💾 保存到数据库")
            self.save_to_db_btn.clicked.connect(self.save_to_database)
            self.save_to_db_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #8e44ad;
                        color: white;
                        padding: 8px 15px;
                        border-radius: 6px;
                        font-size: 13px;
                    }
                    QPushButton:hover {
                        background-color: #9b59b6;
                    }
                """)
            db_layout.addWidget(self.save_to_db_btn)

            # 删除数据库数据按钮
            self.delete_db_btn = QPushButton("🗑️ 清空数据库")
            self.delete_db_btn.clicked.connect(self.delete_database_data)
            self.delete_db_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #e74c3c;
                        color: white;
                        padding: 8px 15px;
                        border-radius: 6px;
                        font-size: 13px;
                    }
                    QPushButton:hover {
                        background-color: #c0392b;
                    }
                """)
            db_layout.addWidget(self.delete_db_btn)

            db_layout.addStretch()
            content_layout.addLayout(db_layout)


        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.comment_viewer = ItemViewer("评论", self.api_service)
        self.comment_viewer.delete_requested.connect(self.handle_delete_request)
        self.comment_viewer.parent_screen = self
        splitter.addWidget(self.comment_viewer)

        self.danmu_viewer = ItemViewer("弹幕", self.api_service)
        self.danmu_viewer.delete_requested.connect(self.handle_delete_request)
        self.danmu_viewer.parent_screen = self
        splitter.addWidget(self.danmu_viewer)

        self.notify_viewer = ItemViewer("通知", self.api_service)
        self.notify_viewer.delete_requested.connect(self.handle_delete_request)
        self.notify_viewer.parent_screen = self
        splitter.addWidget(self.notify_viewer)

        splitter.setSizes([350, 350, 350])
        content_layout.addWidget(splitter)

        self.stacked_widget.addWidget(self.main_content_widget)

    # 删除数据库数据的方法
    def delete_database_data(self):
        """删除当前账号的数据库数据"""
        if not self.database_enabled or not self.api_service:
            return

        try:
            # 获取当前用户UID
            uid, username, _ = self.api_service.get_cached_user_info()
            if not uid:
                QMessageBox.warning(self, "错误", "无法获取用户信息，请先完成登录")
                return

            # 确认删除
            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除账号 '{username}' (UID: {uid}) 的所有数据库数据吗？\n\n"
                f"这将清除：\n"
                f"• 所有评论记录\n"
                f"• 所有弹幕记录\n"
                f"• 所有通知记录\n"
                f"• 所有同步游标\n\n"
                f"此操作不可恢复！",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                # 执行删除
                self.db_manager.clear_user_data(uid)

                # 清空当前界面显示的数据
                self.all_comments.clear()
                self.all_danmus.clear()
                self.all_notifies.clear()

                # 更新UI显示
                self.comment_viewer.set_items(self.all_comments)
                self.danmu_viewer.set_items(self.all_danmus)
                self.notify_viewer.set_items(self.all_notifies)

                QMessageBox.information(
                    self, "删除成功",
                    f"账号 '{username}' 的所有数据库数据已删除"
                )
                logger.info(f"已删除用户 {uid} 的所有数据库数据")

        except Exception as e:
            logger.error(f"删除数据库数据失败: {e}")
            QMessageBox.critical(self, "删除失败", f"删除数据库数据失败: {e}")

    @pyqtSlot(bool)
    def on_delete_db_checkbox_toggled(self, checked):
        """当数据库删除复选框状态改变时，更新内部状态变量"""
        self.is_delete_db_enabled = checked
        logger.debug(f"Delete DB state changed to: {self.is_delete_db_enabled}")

    def safe_back_to_tools(self):
        """安全返回到工具选择界面"""
        if self._is_closing:
            return

        self._is_closing = True
        logger.info("开始安全返回流程...")

        # 停止所有运行中的线程
        threads_to_stop = []

        # 检查获取线程
        if hasattr(self, 'fetch_thread') and self.fetch_thread and self.fetch_thread.isRunning():
            logger.info("停止获取线程...")
            self.fetch_thread.stop()
            threads_to_stop.append(('fetch_thread', self.fetch_thread))

        # 检查删除线程
        for thread_name, thread in self.delete_threads.items():
            if thread and thread.isRunning():
                logger.info(f"停止删除线程: {thread_name}")
                if hasattr(thread, 'stop'):
                    thread.stop()
                threads_to_stop.append((thread_name, thread))

        if threads_to_stop:
            # 显示等待提示
            if hasattr(self, 'status_label'):
                self.status_label.setText("正在安全退出...")

            # 创建定时器来检查线程状态
            self.back_timer = QTimer()
            self.back_timer.timeout.connect(lambda: self.check_back_progress(threads_to_stop))
            self.back_timer.start(100)  # 每100ms检查一次

            # 设置最大等待时间为3秒
            QTimer.singleShot(3000, self.force_back)
        else:
            # 没有运行的线程，直接返回
            self.back_to_tools.emit()

    def check_back_progress(self, threads_to_stop):
        """检查返回进度"""
        still_running = []
        for thread_name, thread in threads_to_stop:
            if thread and thread.isRunning():
                still_running.append((thread_name, thread))

        if not still_running:
            # 所有线程已停止
            if hasattr(self, 'back_timer'):
                self.back_timer.stop()
            logger.info("所有线程已安全停止，执行返回")
            self.back_to_tools.emit()
        else:
            logger.debug(f"仍有 {len(still_running)} 个线程在运行")

    def force_back(self):
        """强制返回（超时处理）"""
        if hasattr(self, 'back_timer'):
            self.back_timer.stop()
        logger.warning("等待超时，强制返回")
        self.back_to_tools.emit()

    #添加新的槽函数来更新状态
    @pyqtSlot(bool)
    def on_cascade_checkbox_toggled(self, checked):
        """当关联删除复选框状态改变时，更新内部状态变量"""
        self.is_cascade_delete_enabled = checked
        logger.debug(f"Cascade delete state changed to: {self.is_cascade_delete_enabled}")

    def start_fetch(self):
        if hasattr(self, 'fetch_thread') and self.fetch_thread.isRunning(): return
        self.stacked_widget.setCurrentWidget(self.loading_widget)
        self.activity_indicator.setVisible(True)

        self.fetch_thread = FetchThread(self.api_service, self.aicu_state, self.progress_state)
        self.fetch_thread.status_update.connect(self.status_label.setText)
        self.fetch_thread.activity_update.connect(self.on_activity_update)
        self.fetch_thread.finished.connect(self.on_fetch_finished)
        self.fetch_thread.error.connect(self.on_fetch_error)
        self.fetch_thread.start()

    @pyqtSlot(object)
    def on_activity_update(self, activity_info: ActivityInfo):
        """处理活动信息更新"""
        try:
            category = activity_info.category
            if category in self.activity_stats:
                self.activity_stats[category] = {
                    "count": activity_info.current_count,
                    "speed": activity_info.speed,
                    "active": True
                }

            # 更新活动信息显示
            active_info = []
            for cat, stats in self.activity_stats.items():
                if stats["active"] and stats["count"] > 0:
                    if stats["speed"] > 0:
                        active_info.append(f"{cat}: {stats['count']} 项 [{stats['speed']:.1f}/s]")
                    else:
                        active_info.append(f"{cat}: {stats['count']} 项")

            # 如果当前阶段结束，标记为完成
            if activity_info.speed == 0 and activity_info.current_count > 0:
                self.completed_stages.add(category)
                if category in self.activity_stats:
                    self.activity_stats[category]["active"] = False

            if active_info:
                self.activity_label.setText(" | ".join(active_info[-2:]))  # 只显示最后2个活跃的
            else:
                self.activity_label.setText("")

        except Exception as e:
            logger.debug(f"Error updating activity display: {e}")

    @pyqtSlot(object)
    def on_fetch_finished(self, result):
        data, progress = result
        if data:
            self.status_label.setText("数据加载完成！")
            self.activity_indicator.setVisible(False)

            self.all_notifies, self.all_comments, self.all_danmus = data

            # 加个调试日志：统计各来源的数据
            bilibili_danmus = sum(1 for d in self.all_danmus.values() if getattr(d, 'source', 'bilibili') == 'bilibili')
            aicu_danmus = sum(1 for d in self.all_danmus.values() if getattr(d, 'source', 'bilibili') == 'aicu')

            logger.info(f"数据统计: B站弹幕={bilibili_danmus}, AICU弹幕={aicu_danmus}, 总弹幕={len(self.all_danmus)}")

            # 打印前几个弹幕的详细信息（用于调试）
            for i, (dmid, danmu) in enumerate(list(self.all_danmus.items())[:5]):
                logger.debug(
                    f"弹幕{i}: dmid={dmid}, source={getattr(danmu, 'source', 'unknown')}, cid={danmu.cid}, video_url={getattr(danmu, 'video_url', 'none')}")

            self.comment_viewer.set_items(self.all_comments)
            self.danmu_viewer.set_items(self.all_danmus)
            self.notify_viewer.set_items(self.all_notifies)
            self.comment_viewer.set_items(self.all_comments)
            self.danmu_viewer.set_items(self.all_danmus)
            self.notify_viewer.set_items(self.all_notifies)
            logger.info(f"进程已完成. C:{len(self.all_comments)}, D:{len(self.all_danmus)}, N:{len(self.all_notifies)}")

            # 显示最终统计信息
            final_stats = []
            for cat, stats in self.activity_stats.items():
                if stats["count"] > 0:
                    final_stats.append(f"{cat}: {stats['count']}")
            if final_stats:
                self.activity_label.setText("获取完成: " + " | ".join(final_stats))

            # 自动保存到数据库
            if self.database_enabled:
                try:
                    uid, _, _ = self.api_service.get_cached_user_info()
                    if uid:
                        self.sync_manager.save_to_database(uid, self.all_comments, self.all_danmus, self.all_notifies)
                        logger.info("数据已自动保存到数据库")
                except Exception as e:
                    logger.warning(f"自动保存到数据库失败: {e}")

            self.stacked_widget.setCurrentWidget(self.main_content_widget)
        elif progress:
            self.progress_state = progress
            self.start_fetch()

    @pyqtSlot(str)
    def on_fetch_error(self, error):
        logger.error(f"Fetch error in UI: {error}")
        self.status_label.setText(f"获取数据失败: {error}")
        self.activity_indicator.setVisible(False)
        QMessageBox.critical(self, "获取错误", f"获取数据失败: {error}")

    @pyqtSlot(str)
    def on_delete_error(self, error_message: str):
        QMessageBox.warning(self, "删除失败", error_message)

    def handle_delete_request(self, items: list, item_type: str, sleep_seconds: int):
        viewer_map = {"评论": self.comment_viewer, "弹幕": self.danmu_viewer, "通知": self.notify_viewer}

        if not items:
            if item_type in self.delete_threads and (thread := self.delete_threads.get(item_type)):
                if thread.isRunning():
                    thread.stop()
                    thread.wait()
                self.delete_threads[item_type] = None
            return

        # 使用状态变量而不是直接读取isChecked()
        if item_type == "通知" and self.is_cascade_delete_enabled:
            cascade_list = self._build_cascade_delete_list(items)
            self.notify_viewer.progress_bar.setMaximum(len(cascade_list))
            self.notify_viewer.progress_bar.setValue(0)

            # 获取当前用户UID
            uid = None
            if self.database_enabled and self.is_delete_db_enabled:
                uid, _, _ = self.api_service.get_cached_user_info()

            thread = CascadeDeleteThread(
                self.api_service, cascade_list, sleep_seconds,
                delete_db=self.is_delete_db_enabled,
                db_manager=self.db_manager if self.database_enabled else None,
                uid=uid
            )
            thread.comment_deleted.connect(self.comment_viewer.on_item_deleted)
            thread.danmu_deleted.connect(self.danmu_viewer.on_item_deleted)
            thread.notify_deleted.connect(self.notify_viewer.on_item_deleted)
            thread.finished.connect(self.notify_viewer.on_deletion_finished)
            thread.progress.connect(lambda c, t: self.notify_viewer.progress_bar.setValue(c))
            thread.error.connect(self.on_delete_error)
        else:
            viewer = viewer_map.get(item_type)
            if not viewer: return
            viewer.progress_bar.setMaximum(len(items))
            viewer.progress_bar.setValue(0)
            # 获取当前用户UID
            uid = None
            if self.database_enabled and self.is_delete_db_enabled:
                uid, _, _ = self.api_service.get_cached_user_info()

            thread = DeleteThread(
                self.api_service, items, item_type, sleep_seconds,
                delete_db=self.is_delete_db_enabled,
                db_manager=self.db_manager if self.database_enabled else None,
                uid=uid
            )
            thread.item_deleted.connect(viewer.on_item_deleted)
            thread.finished.connect(viewer.on_deletion_finished)
            thread.progress.connect(lambda c, t: viewer.progress_bar.setValue(c))
            thread.error.connect(self.on_delete_error)

        self.delete_threads[item_type] = thread
        thread.start()

    def _build_cascade_delete_list(self, notify_items: list) -> list:
        cascade_items = []

        for notify_id, notify in notify_items:
            cascade_items.append(('notify', notify_id, notify))
            logger.debug(f"Building cascade list for notify {notify_id}")

            # 查找关联的评论
            found_comments = 0
            for comment_id, comment in self.all_comments.items():
                if comment.notify_id == notify_id:
                    cascade_items.append(('comment', comment_id, comment))
                    found_comments += 1
                    logger.debug(f"Found associated comment {comment_id} for notify {notify_id}")

            if found_comments == 0:
                logger.debug(f"No associated comments found for notify {notify_id}")

            # 查找关联的弹幕
            found_danmus = 0
            for danmu_id, danmu in self.all_danmus.items():
                if danmu.notify_id == notify_id:
                    cascade_items.append(('danmu', danmu_id, danmu))
                    found_danmus += 1
                    logger.debug(f"Found associated danmu {danmu_id} for notify {notify_id}")

            if found_danmus == 0:
                logger.debug(f"No associated danmus found for notify {notify_id}")

        logger.info(f"Cascade delete list built: {len(cascade_items)} items total")
        return cascade_items

    def load_from_database(self):
        """从数据库加载数据"""
        if not self.database_enabled or not self.api_service:
            return

        try:
            uid, _, _ = self.api_service.get_cached_user_info()
            if not uid:
                QMessageBox.warning(self, "错误", "无法获取用户信息，请先完成登录")
                return

            # 显示加载界面
            self.stacked_widget.setCurrentWidget(self.loading_widget)
            self.status_label.setText("正在从数据库加载数据...")
            self.activity_indicator.setVisible(True)

            # 创建并启动加载线程
            self.db_load_thread = DatabaseLoadThread(self.sync_manager, uid)
            self.db_load_thread.data_loaded.connect(self.on_database_loaded)
            self.db_load_thread.error.connect(self.on_database_load_error)
            self.db_load_thread.progress.connect(self.status_label.setText)
            self.db_load_thread.start()

        except Exception as e:
            logger.error(f"启动数据库加载失败: {e}")
            QMessageBox.critical(self, "加载失败", f"启动数据库加载失败: {e}")

    @pyqtSlot(object, object, object)
    def on_database_loaded(self, comments, danmus, notifies):
        """数据库加载完成"""
        self.all_comments = comments
        self.all_danmus = danmus
        self.all_notifies = notifies

        # 使用延迟加载更新UI
        QTimer.singleShot(0, lambda: self.update_viewers_async())

    @pyqtSlot(str)
    def on_database_load_error(self, error_msg):
        """数据库加载错误"""
        self.activity_indicator.setVisible(False)
        self.stacked_widget.setCurrentWidget(self.main_content_widget)
        QMessageBox.critical(self, "加载失败", f"从数据库加载数据失败: {error_msg}")

    def update_viewers_async(self):
        """异步更新查看器"""
        self.status_label.setText("正在初始化...")

        # 分批更新，避免一次性阻塞
        QTimer.singleShot(0, lambda: self.comment_viewer.set_items_async(self.all_comments))
        QTimer.singleShot(100, lambda: self.danmu_viewer.set_items_async(self.all_danmus))
        QTimer.singleShot(200, lambda: self.notify_viewer.set_items_async(self.all_notifies))

        # 延迟切换界面
        QTimer.singleShot(300, self.finish_database_load)

    def finish_database_load(self):
        """完成数据库加载"""
        self.activity_indicator.setVisible(False)
        self.stacked_widget.setCurrentWidget(self.main_content_widget)

        QMessageBox.information(self, "加载成功",
                                f"已从数据库加载:\n评论: {len(self.all_comments)}\n"
                                f"弹幕: {len(self.all_danmus)}\n通知: {len(self.all_notifies)}")

    def save_to_database(self):
        """保存当前数据到数据库"""
        if not self.database_enabled or not self.api_service:
            return

        try:
            # 使用同步方式获取UID
            uid, _, _ = self.api_service.get_cached_user_info()
            if not uid:
                QMessageBox.warning(self, "错误", "无法获取用户信息，请先完成登录")
                return

            self.sync_manager.save_to_database(uid, self.all_comments, self.all_danmus, self.all_notifies)

            QMessageBox.information(self, "保存成功", "数据已保存到本地数据库")
            logger.info("数据已保存到数据库")

        except Exception as e:
            logger.error(f"保存到数据库失败: {e}")
            QMessageBox.critical(self, "保存失败", f"保存数据到数据库失败: {e}")

    def fetch_all_data(self):
        """获取全量数据"""
        # 检查是否正在获取数据
        if hasattr(self, 'fetch_thread') and self.fetch_thread and self.fetch_thread.isRunning():
            QMessageBox.warning(self, "正在获取", "数据获取正在进行中，请等待完成")
            return

        reply = QMessageBox.question(
            self, "获取全量数据",
            "确定要获取全部数据吗？\n\n这将调用api重新获取所有评论、弹幕和通知数据。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 清空当前数据
            self.all_comments, self.all_danmus, self.all_notifies = {}, {}, {}
            # 重置进度状态
            self.progress_state = FetchProgressState()
            # 开始获取
            self.start_fetch()

    def fetch_new_data(self):
        """获取新数据（增量更新）"""
        if not self.database_enabled:
            QMessageBox.information(self, "功能不可用", "数据库功能未启用，无法进行增量更新")
            return

        # 检查是否正在获取数据
        if hasattr(self,
                   'incremental_fetch_thread') and self.incremental_fetch_thread and self.incremental_fetch_thread.isRunning():
            QMessageBox.warning(self, "正在获取", "增量更新正在进行中，请等待完成")
            return

        # 检查是否有本地数据
        try:
            uid, _, _ = self.api_service.get_cached_user_info()
            if not uid:
                QMessageBox.warning(self, "错误", "无法获取用户信息，请先完成登录")
                return

            stats = self.db_manager.get_stats(uid)
            total_items = stats.get('total_comments', 0) + stats.get('total_danmus', 0) + stats.get('total_notifies', 0)

            if total_items == 0:
                reply = QMessageBox.question(
                    self, "没有本地数据",
                    "本地数据库中没有数据。\n\n是否先进行全量获取？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.fetch_all_data()
                return

            # 确认增量更新
            reply = QMessageBox.question(
                self, "增量更新",
                f"将从服务器获取比本地数据更新的数据。\n\n本地数据库现有:\n评论: {stats.get('total_comments', 0)}\n弹幕: {stats.get('total_danmus', 0)}\n通知: {stats.get('total_notifies', 0)}\n\n确定要进行增量更新吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.start_incremental_fetch()

        except Exception as e:
            logger.error(f"检查本地数据失败: {e}")
            QMessageBox.critical(self, "错误", f"检查本地数据失败: {e}")

    def start_incremental_fetch(self):
        """开始增量获取"""
        logger.info("开始增量获取流程")

        self.stacked_widget.setCurrentWidget(self.loading_widget)
        self.activity_indicator.setVisible(True)
        self.status_label.setText("开始增量获取...")

        self.incremental_fetch_thread = IncrementalFetchThread(self.api_service, self.db_manager, self.aicu_state)
        self.incremental_fetch_thread.status_update.connect(self.status_label.setText)
        self.incremental_fetch_thread.activity_update.connect(self.on_activity_update)
        self.incremental_fetch_thread.finished.connect(self.on_incremental_fetch_finished)
        self.incremental_fetch_thread.error.connect(self.on_fetch_error)
        self.incremental_fetch_thread.start()

        logger.info("增量获取线程已启动")



    @pyqtSlot(object)
    def on_incremental_fetch_finished(self, result):
        """增量获取完成"""
        new_notifies, new_comments, new_danmus = result

        self.status_label.setText("增量获取完成！")
        self.activity_indicator.setVisible(False)

        # 合并新数据到现有数据
        self.all_notifies.update(new_notifies)
        self.all_comments.update(new_comments)
        self.all_danmus.update(new_danmus)

        # 更新UI显示
        self.comment_viewer.set_items(self.all_comments)
        self.danmu_viewer.set_items(self.all_danmus)
        self.notify_viewer.set_items(self.all_notifies)

        # 切换到主内容页面
        self.stacked_widget.setCurrentWidget(self.main_content_widget)

        new_total = len(new_comments) + len(new_danmus) + len(new_notifies)

        if new_total > 0:
            QMessageBox.information(self, "增量更新完成",
                                    f"获取到新数据:\n评论: {len(new_comments)}\n弹幕: {len(new_danmus)}\n通知: {len(new_notifies)}")
        else:
            QMessageBox.information(self, "增量更新完成", "没有发现新数据")

        logger.info(f"增量获取完成，新数据: C:{len(new_comments)}, D:{len(new_danmus)}, N:{len(new_notifies)}")


    def closeEvent(self, event):
        """窗口关闭时的清理操作"""
        self._is_closing = True

        # 打破循环引用
        if hasattr(self, 'comment_viewer'):
            self.comment_viewer.parent_screen = None
        if hasattr(self, 'danmu_viewer'):
            self.danmu_viewer.parent_screen = None
        if hasattr(self, 'notify_viewer'):
            self.notify_viewer.parent_screen = None

        # 停止线程
        if hasattr(self, 'fetch_thread') and self.fetch_thread and self.fetch_thread.isRunning():
            self.fetch_thread.stop()
            self.fetch_thread.wait(2000)

        # 停止删除线程
        for thread in self.delete_threads.values():
            if thread and thread.isRunning():
                if hasattr(thread, 'stop'):
                    thread.stop()
                thread.wait(1000)
        # 清理数据字典以释放内存
        self.all_comments.clear()
        self.all_danmus.clear()
        self.all_notifies.clear()
        # 清理viewer中的数据
        if hasattr(self, 'comment_viewer'):
            self.comment_viewer.all_items.clear()
            self.comment_viewer.items.clear()
            self.comment_viewer.checkboxes.clear()


        if hasattr(self, 'danmu_viewer'):
            self.danmu_viewer.all_items.clear()
            self.danmu_viewer.items.clear()
            self.danmu_viewer.checkboxes.clear()

        if hasattr(self, 'notify_viewer'):
            self.notify_viewer.all_items.clear()
            self.notify_viewer.items.clear()
            self.notify_viewer.checkboxes.clear()

        self.window_closed.emit()  # 发送窗口关闭信号！
        super().closeEvent(event)


class CascadeDeleteThread(QThread):
    comment_deleted, danmu_deleted, notify_deleted = pyqtSignal(int), pyqtSignal(int), pyqtSignal(int)
    finished, progress = pyqtSignal(), pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(self, api_service, cascade_items, sleep_seconds, delete_db=False, db_manager=None, uid=None):
        super().__init__()
        self.api_service, self.cascade_items, self.sleep_seconds = api_service, cascade_items, sleep_seconds
        self.delete_db = delete_db
        self.db_manager = db_manager
        self.uid = uid
        self._is_running = True

    def stop(self): self._is_running = False

    def run(self):
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        try: loop.run_until_complete(self._delete_items())
        except Exception as e:
            logger.error(f"Unexpected error in CascadeDeleteThread: {e}")
            self.error.emit(str(e))
        finally:
            try: loop.close()
            except: pass

    async def _delete_items(self):
        total = len(self.cascade_items)
        for current, (item_type, item_id, item) in enumerate(self.cascade_items, 1):
            if not self._is_running: break
            self.progress.emit(current, total)
            try:
                if item_type == "comment":
                    from ..api.comment import remove_comment
                    await remove_comment(item, item_id, self.api_service)
                    if self.delete_db and self.db_manager and self.uid:
                        try:
                            self.db_manager.delete_comment_permanently(item_id, self.uid)
                            logger.info(f"数据库中的评论 {item_id} 已永久删除")
                        except Exception as e:
                            logger.error(f"删除数据库评论记录失败: {e}")
                    self.comment_deleted.emit(item_id)
                elif item_type == "notify":
                    from ..api.notify import remove_notify
                    await remove_notify(item, item_id, self.api_service)
                    if self.delete_db and self.db_manager and self.uid:
                        try:
                            self.db_manager.delete_notify_permanently(item_id, self.uid)
                            logger.info(f"数据库中的通知 {item_id} 已永久删除")
                        except Exception as e:
                            logger.error(f"删除数据库通知记录失败: {e}")
                    self.notify_deleted.emit(item_id)
                elif item_type == "danmu":
                    logger.warning(f"Skipping cascade delete for danmu {item_id} as it's not supported.")
                    if self.delete_db and self.db_manager and self.uid:
                        try:
                            self.db_manager.delete_danmu_permanently(item_id, self.uid)
                            logger.info(f"数据库中的弹幕 {item_id} 已永久删除")
                        except Exception as e:
                            logger.error(f"删除数据库弹幕记录失败: {e}")
                    self.danmu_deleted.emit(item_id)
                logger.info(f"Successfully processed cascade item: {item_type} {item_id}")
            except Exception as e:
                error_message = f"删除失败: 无法删除 {item_type} (ID: {item_id}).\n原因: {e}"
                logger.error(error_message)
                self.error.emit(error_message)
                if self._is_running:
                    logger.info(f"[CascadeDeleteThread] sleep 5 seconds after error...")
                    print(f"[CascadeDeleteThread] sleep 5 seconds after error...")
                    await asyncio.sleep(5)
            if self._is_running and current < total:
                logger.info(f"[CascadeDeleteThread] sleep {self.sleep_seconds} seconds before next cascade delete...")
                print(f"[CascadeDeleteThread] sleep {self.sleep_seconds} seconds before next cascade delete...")
                await asyncio.sleep(self.sleep_seconds)
        self.finished.emit()


class LoginCacheThread(QThread):
    """登录后缓存用户信息的线程"""
    cache_completed = pyqtSignal()

    def __init__(self, api_service):
        super().__init__()
        self.api_service = api_service

    def run(self):
        """在后台获取并缓存用户信息"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # 获取并缓存用户信息
            loop.run_until_complete(self.api_service.get_user_info())
            logger.info("用户信息已成功缓存")
        except Exception as e:
            logger.error(f"缓存用户信息失败: {e}")
        finally:
            loop.close()
            self.cache_completed.emit()


# 这个MainWindow类应该已经不再需要了，因为我们现在直接使用ImprovedToolSelectionScreen
# 但为了兼容，我们暂时保留它
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.api_service: Optional[ApiService] = None
        self.aicu_state = True
        self.current_screen = Screen.WAIT_SCAN_QRCODE
        # 添加对工具窗口的引用
        self.comment_clean_window = None
        logger.warning("MainWindow is deprecated. Please use ImprovedToolSelectionScreen instead.")
        self.init_ui()

    def init_ui(self):
        self.switch_to_qrcode_screen()

    def switch_to_qrcode_screen(self):
        self.current_screen = Screen.WAIT_SCAN_QRCODE
        from .qrcode_screen import QRCodeScreen
        screen = QRCodeScreen()
        screen.login_success.connect(self.on_login_success)
        screen.switch_to_cookie.connect(self.switch_to_cookie_screen)
        self.setCentralWidget(screen)

    def switch_to_cookie_screen(self):
        self.current_screen = Screen.WAIT_INPUT_COOKIE
        from .cookie_screen import CookieScreen
        screen = CookieScreen()
        screen.login_success.connect(self.on_login_success)
        screen.switch_to_qrcode.connect(self.switch_to_qrcode_screen)
        self.setCentralWidget(screen)

    def switch_to_tool_selection_screen(self):
        """切换到工具选择页面"""
        self.current_screen = Screen.MAIN
        from .tool_selection_screen import ToolSelectionScreen
        screen = ToolSelectionScreen(self.api_service, self.aicu_state)
        screen.open_comment_tool.connect(self.open_comment_clean_tool)
        screen.logout_requested.connect(self.logout)
        self.setCentralWidget(screen)

    def open_comment_clean_tool(self):
        """打开评论清理工具"""
        try:
            # 如果窗口已存在且未关闭，直接显示
            if self.comment_clean_window is not None and not self.comment_clean_window.isHidden():
                self.comment_clean_window.show()
                self.comment_clean_window.raise_()
                self.comment_clean_window.activateWindow()
                return

            # 创建新的评论清理窗口
            self.comment_clean_window = CommentCleanScreen(self.api_service, self.aicu_state)
            self.comment_clean_window.back_to_tools.connect(self.close_comment_tool)

            # 设置为独立窗口
            self.comment_clean_window.setWindowTitle("Bilibili 评论清理工具")
            self.comment_clean_window.resize(1100, 700)
            self.comment_clean_window.show()

        except Exception as e:
            logger.error(f"打开评论清理工具失败: {e}")
            QMessageBox.critical(self, "错误", f"无法打开评论清理工具: {e}")


    def close_comment_tool(self):
        """关闭评论清理工具，返回工具选择页面"""
        if self.comment_clean_window:
            self.comment_clean_window.close()
            self.comment_clean_window = None

    def logout(self):
        """注销登录，返回登录页面"""
        # 关闭所有工具窗口
        if self.comment_clean_window:
            self.comment_clean_window.close()
            self.comment_clean_window = None

        # 清除API服务和缓存
        if self.api_service:
            self.api_service.clear_user_cache()
            self.api_service = None

        # 返回登录页面
        self.switch_to_qrcode_screen()

    @pyqtSlot(object, bool)
    def on_login_success(self, api_service: ApiService, aicu_state: bool):
        """登录成功处理 - 简化版本，移除复杂的缓存线程"""
        self.api_service = api_service
        self.aicu_state = aicu_state

        # 直接切换到工具选择页面，让各个工具自己处理用户信息获取
        self.switch_to_tool_selection_screen()

class IncrementalFetchThread(QThread):
        """增量获取线程"""
        finished = pyqtSignal(object)
        error = pyqtSignal(str)
        status_update = pyqtSignal(str)
        activity_update = pyqtSignal(object)

        def __init__(self, api_service, db_manager, aicu_state):
            super().__init__()
            self.api_service = api_service
            self.db_manager = db_manager
            self._is_running = True
            self.aicu_state = aicu_state


        def stop(self):
            self._is_running = False
            logger.info("IncrementalFetchThread stop requested")

        def run(self):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            def progress_callback(message_or_info):
                if self._is_running:
                    if isinstance(message_or_info, ActivityInfo):
                        self.activity_update.emit(message_or_info)
                        self.status_update.emit(str(message_or_info))
                    else:
                        self.status_update.emit(message_or_info)

            try:
                logger.info("开始增量获取...")
                result = loop.run_until_complete(self._incremental_fetch_with_session(progress_callback))
                if self._is_running:
                    logger.info("增量获取线程完成")
                    self.finished.emit(result)
            except Exception as e:
                logger.error(f"增量获取错误: {e}")
                import traceback
                traceback.print_exc()
                if self._is_running:
                    self.error.emit(str(e))
            finally:
                try:
                    tasks = asyncio.all_tasks(loop=loop)
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    if tasks:
                        try:
                            loop.run_until_complete(
                                asyncio.wait_for(
                                    asyncio.gather(*tasks, return_exceptions=True),
                                    timeout=2.0
                                )
                            )
                        except asyncio.TimeoutError:
                            logger.warning("Some incremental fetch tasks didn't cancel in time")
                        except Exception as e:
                            logger.error(f"Error during incremental fetch task cancellation: {e}")
                except Exception as e:
                    logger.error(f"Error cancelling incremental fetch tasks: {e}")
                finally:
                    try:
                        if not loop.is_closed():
                            loop.close()
                    except Exception as e:
                        logger.error(f"Error closing incremental fetch event loop: {e}")

        async def _incremental_fetch_with_session(self, progress_callback):
            """执行增量获取的核心逻辑"""
            if not self._is_running:
                return {}, {}, {}

            # 创建临时API服务
            temp_api_service = self.api_service.__class__(
                csrf=self.api_service.csrf,
                cookie=self.api_service.cookie
            )
            temp_api_service.user_cache = self.api_service.user_cache

            try:
                async with temp_api_service:
                    # 获取用户ID
                    uid = await temp_api_service.get_uid()
                    logger.info(f"开始为用户 {uid} 进行增量获取")

                    # 简化版增量获取 - 先实现基本功能
                    return await self._simple_incremental_fetch(temp_api_service, uid, progress_callback)

            finally:
                try:
                    await temp_api_service.close()
                except Exception as e:
                    logger.debug(f"Error closing temp api_service in incremental fetch: {e}")

        async def _simple_incremental_fetch(self, api_service, uid, progress_callback):
            """简化版增量获取"""

            new_danmus = {}
            new_notifies = {}

            try:
                # 获取数据库中最新的时间戳
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()

                    # 获取点赞通知最新时间戳
                    cursor.execute('''
                        SELECT MAX(created_time) FROM notifies WHERE uid = ? AND tp = 0
                    ''', (uid,))
                    last_liked_time = cursor.fetchone()[0] or 0

                    # 获取回复通知最新时间戳
                    cursor.execute('''
                        SELECT MAX(created_time) FROM notifies WHERE uid = ? AND tp = 1
                    ''', (uid,))
                    last_replied_time = cursor.fetchone()[0] or 0

                    # 获取@通知最新时间戳
                    cursor.execute('''
                        SELECT MAX(created_time) FROM notifies WHERE uid = ? AND tp = 2
                    ''', (uid,))
                    last_ated_time = cursor.fetchone()[0] or 0

                    # 获取最新的评论时间戳
                    cursor.execute('''
                        SELECT MAX(created_time) FROM comments WHERE uid = ?
                    ''', (uid,))
                    result = cursor.fetchone()
                    last_comment_time = result[0] if result[0] else 0

                    # 获取最新的弹幕时间戳
                    cursor.execute('''
                        SELECT MAX(created_time) FROM danmus WHERE uid = ?
                    ''', (uid,))
                    result = cursor.fetchone()
                    last_danmu_time = result[0] if result[0] else 0

                logger.info(
                    f"数据库最新时间戳 - 回复通知: {last_replied_time},点赞通知:{last_liked_time},艾特通知:{last_ated_time} 评论: {last_comment_time}, 弹幕: {last_danmu_time}")

                # 分别存储回复和点赞的评论
                replied_comments = {}
                liked_comments = {}

                # 1. 获取新的回复数据
                if self._is_running:
                    progress_callback("获取新的回复数据...")
                    await self._fetch_replied_incremental(api_service, uid, last_replied_time, new_notifies,
                                                          replied_comments)

                # 2. 获取新的点赞数据
                if self._is_running:
                    progress_callback("获取新的点赞数据...")
                    await self._fetch_liked_incremental(api_service, uid, last_liked_time, new_notifies, liked_comments,
                                                        new_danmus)

                #  合并评论数据（点赞覆盖回复，模拟全量获取逻辑）
                new_comments = {**replied_comments, **liked_comments}
                logger.info(
                    f"评论合并结果: 回复={len(replied_comments)}, 点赞={len(liked_comments)}, 最终={len(new_comments)}")

                # 3. 获取新的@数据
                if self._is_running:
                    progress_callback("获取新的@数据...")
                    await self._fetch_ated_incremental(api_service, uid, last_ated_time, new_notifies)

                # AICU增量获取
                if self._is_running and self.aicu_state:
                    progress_callback("获取新的AICU数据...")

                    # 导入AICU增量获取函数
                    from ..api.notify import fetch_aicu_comments_incremental, fetch_aicu_danmus_incremental
                    from ..database.incremental import IncrementalFetcher

                    # 创建增量获取器
                    fetcher = IncrementalFetcher(self.db_manager)

                    # 获取AICU评论
                    try:
                        aicu_comments = await fetch_aicu_comments_incremental(
                            api_service, uid, fetcher, progress_callback
                        )
                        new_comments.update(aicu_comments)
                        logger.info(f"AICU评论增量: {len(aicu_comments)} 项")
                    except Exception as e:
                        logger.error(f"获取AICU评论增量失败: {e}")

                    # 获取AICU弹幕
                    try:
                        aicu_danmus = await fetch_aicu_danmus_incremental(
                            api_service, uid, fetcher, progress_callback
                        )
                        new_danmus.update(aicu_danmus)
                        logger.info(f"AICU弹幕增量: {len(aicu_danmus)} 项")
                    except Exception as e:
                        logger.error(f"获取AICU弹幕增量失败: {e}")

                # 去重：移除已存在于数据库中的数据
                if new_comments or new_danmus or new_notifies:
                    progress_callback("检查重复数据...")
                    new_comments, new_danmus, new_notifies = await self._deduplicate_data(uid, new_comments, new_danmus,
                                                                                          new_notifies)

                logger.info(
                    f"去重后增量数据: 通知 {len(new_notifies)}, 评论 {len(new_comments)}, 弹幕 {len(new_danmus)}")

                # 保存新数据到数据库
                if new_comments or new_danmus or new_notifies:
                    progress_callback("保存新数据到数据库...")
                    await self._save_incremental_data(uid, new_comments, new_danmus, new_notifies)

                return new_notifies, new_comments, new_danmus

            except Exception as e:
                logger.error(f"简化增量获取失败: {e}")
                raise

        async def _deduplicate_data(self, uid, comments, danmus, notifies):
            """去除数据库中已存在的数据"""
            try:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()

                    # 去重评论
                    if comments:
                        comment_ids = list(comments.keys())
                        placeholders = ','.join(['?'] * len(comment_ids))
                        cursor.execute(f'''
                            SELECT id FROM comments WHERE uid = ? AND id IN ({placeholders})
                        ''', [uid] + comment_ids)
                        existing_comments = {row[0] for row in cursor.fetchall()}
                        comments = {k: v for k, v in comments.items() if k not in existing_comments}

                    # 去重通知
                    if notifies:
                        notify_ids = list(notifies.keys())
                        placeholders = ','.join(['?'] * len(notify_ids))
                        cursor.execute(f'''
                            SELECT id FROM notifies WHERE uid = ? AND id IN ({placeholders})
                        ''', [uid] + notify_ids)
                        existing_notifies = {row[0] for row in cursor.fetchall()}
                        notifies = {k: v for k, v in notifies.items() if k not in existing_notifies}

                    # 去重弹幕
                    if danmus:
                        danmu_ids = list(danmus.keys())
                        placeholders = ','.join(['?'] * len(danmu_ids))
                        cursor.execute(f'''
                            SELECT id FROM danmus WHERE uid = ? AND id IN ({placeholders})
                        ''', [uid] + danmu_ids)
                        existing_danmus = {row[0] for row in cursor.fetchall()}
                        danmus = {k: v for k, v in danmus.items() if k not in existing_danmus}

                return comments, danmus, notifies
            except Exception as e:
                logger.error(f"去重失败: {e}")
                return comments, danmus, notifies

        async def _fetch_liked_incremental(self, api_service, uid, last_time, new_notifies, liked_comments, new_danmus):
            """获取新的点赞数据"""
            try:
                # 添加本地计数器
                new_count = 0
                url = "https://api.bilibili.com/x/msgfeed/like?platform=web&build=0&mobi_app=web"
                response_data = await api_service.fetch_data(url)

                if response_data.get("code") != 0:
                    logger.warning(f"点赞API错误: {response_data}")
                    return

                items = response_data.get("data", {}).get("total", {}).get("items", [])


                for item in items:
                    like_time = item.get("like_time", 0)
                    if like_time < last_time:
                        continue  # 跳过旧数据，继续处理后面的

                    # 这是新数据
                    notify_id = item["id"]
                    item_data = item.get("item", {})

                    # 创建通知
                    notify_content = f"{item_data.get('title', 'Unknown')} (liked)"
                    new_notifies[notify_id] = Notify(
                        content=notify_content,
                        tp=0,
                        created_time=like_time
                    )
                    new_count += 1  # 增加计数

                    # 处理关联的评论或弹幕
                    if item_data.get("type") == "reply":
                        rpid = item_data.get("item_id")
                        if rpid:
                            try:
                                from ..api.comment import parse_oid
                                oid, type_ = parse_oid(item_data)
                                content = item_data.get("title", "")
                                liked_comments[rpid] = Comment.new_with_notify(
                                    oid=oid, type=type_, content=content, notify_id=notify_id, tp=0
                                )
                                liked_comments[rpid].created_time = like_time
                                # 设置source
                                liked_comments[rpid].source = "bilibili"
                                # 保存视频URI
                                liked_comments[rpid].video_uri = item_data.get("uri", "")
                                # 保存点赞数
                                liked_comments[rpid].like_count = item.get("counts", 0)
                                # 设置同步时间
                                liked_comments[rpid].synced_time = int(time.time())
                            except Exception as e:
                                logger.debug(f"解析点赞评论失败: {e}")

                    elif item_data.get("type") == "danmu":
                        dmid = item_data.get("item_id")
                        if dmid:
                            try:
                                from ..api.danmu import extract_cid
                                native_uri = item_data.get("native_uri", "")
                                cid = extract_cid(native_uri) if native_uri else None
                                if cid:
                                    new_danmus[dmid] = Danmu.new_with_notify(
                                        item_data.get("title", ""), cid, notify_id
                                    )
                                    new_danmus[dmid].created_time = like_time
                                    # 设置source
                                    new_danmus[dmid].source = "bilibili"
                                    # 保存视频链接
                                    new_danmus[dmid].video_url = item_data.get("uri", "")
                                    # 设置同步时间
                                    new_danmus[dmid].synced_time = int(time.time())
                            except Exception as e:
                                logger.debug(f"解析点赞弹幕失败: {e}")



                logger.info(f"新的点赞数据: {new_count} 项")

            except Exception as e:
                logger.error(f"获取点赞增量数据失败: {e}")

        async def _fetch_replied_incremental(self, api_service, uid, last_time, new_notifies, replied_comments):
            """获取新的回复数据"""
            try:
                # 添加本地计数器
                new_count = 0
                url = "https://api.bilibili.com/x/msgfeed/reply?platform=web&build=0&mobi_app=web"
                response_data = await api_service.fetch_data(url)

                if response_data.get("code") != 0:
                    logger.warning(f"回复API错误: {response_data}")
                    return

                items = response_data.get("data", {}).get("items", [])


                # 改为：
                for item in items:
                    reply_time = item.get("reply_time", 0)
                    if reply_time < last_time:
                        continue  # 跳过旧数据

                    # 这是新数据
                    notify_id = item["id"]
                    item_data = item.get("item", {})

                    # 创建通知
                    notify_content = f"{item_data.get('title', 'Unknown')} (reply)"
                    new_notifies[notify_id] = Notify(
                        content=notify_content,
                        tp=1,
                        created_time=reply_time
                    )
                    new_count += 1

                    # 处理关联的评论
                    if item_data.get("type") == "reply":
                        rpid = item_data.get("target_id")
                        if rpid:
                            try:
                                from ..api.comment import parse_oid
                                oid, type_ = parse_oid(item_data)
                                content = item_data.get("target_reply_content") or item_data.get("title", "")
                                replied_comments [rpid] = Comment.new_with_notify(
                                    oid=oid, type=type_, content=content, notify_id=notify_id, tp=1
                                )
                                replied_comments[rpid].created_time = reply_time
                                # 设置source
                                replied_comments[rpid].source = "bilibili"
                                # 保存视频URI
                                replied_comments[rpid].video_uri = item_data.get("uri", "")
                                # 保存点赞数（注意：回复通知的counts是回复数，不是点赞数）
                                replied_comments[rpid].like_count = item.get("counts", 0)
                                # 设置同步时间
                                replied_comments[rpid].synced_time = int(time.time())
                            except Exception as e:
                                logger.debug(f"解析回复评论失败: {e}")



                logger.info(f"新的回复数据: {new_count} 项")

            except Exception as e:
                logger.error(f"获取回复增量数据失败: {e}")

        async def _fetch_ated_incremental(self, api_service, uid, last_time, new_notifies):
            """获取新的@数据"""
            try:
                # 添加本地计数器
                new_count = 0

                url = "https://api.bilibili.com/x/msgfeed/at?build=0&mobi_app=web"
                response_data = await api_service.fetch_data(url)

                if response_data.get("code") != 0:
                    logger.warning(f"@API错误: {response_data}")
                    return

                items = response_data.get("data", {}).get("items", [])

                for item in items:  # 处理所有项
                    at_time = item.get("at_time", 0)
                    if at_time < last_time:
                        continue  # 继续

                    # 这是新数据
                    notify_id = item["id"]
                    item_data = item.get("item", {})

                    # 创建通知
                    notify_content = f"{item_data.get('title', 'Unknown')} (@)"
                    new_notifies[notify_id] = Notify(
                        content=notify_content,
                        tp=2,
                        created_time=at_time
                    )

                    new_count += 1

                logger.info(f"新的@数据: {new_count} 项")

            except Exception as e:
                logger.error(f"获取@增量数据失败: {e}")

        async def _save_incremental_data(self, uid, new_comments, new_danmus, new_notifies):
            """保存增量数据到数据库"""
            try:
                current_time = int(time.time())

                # 保存评论
                if new_comments:
                    comment_records = []
                    for comment_id, comment in new_comments.items():
                        record = CommentRecord(
                            id=comment_id,
                            uid=uid,
                            oid=comment.oid,
                            type=comment.type,
                            content=comment.content,
                            notify_id=comment.notify_id,
                            tp=comment.tp,
                            source="bilibili",
                            created_time=getattr(comment, 'created_time', current_time),
                            synced_time=current_time,
                            video_uri=getattr(comment, 'video_uri', None),
                            like_count=getattr(comment, 'like_count', 0)

                        )
                        comment_records.append(record)
                    self.db_manager.save_comments(comment_records)

                # 保存弹幕
                if new_danmus:
                    danmu_records = []
                    for danmu_id, danmu in new_danmus.items():
                        record = DanmuRecord(
                            id=danmu_id,
                            uid=uid,
                            content=danmu.content,
                            cid=danmu.cid,
                            notify_id=danmu.notify_id,
                            source=getattr(danmu, 'source', 'bilibili'),
                            created_time=getattr(danmu, 'created_time', current_time),
                            synced_time=current_time
                        )
                        danmu_records.append(record)
                    self.db_manager.save_danmus(danmu_records)

                # 保存通知
                if new_notifies:
                    notify_records = []
                    for notify_id, notify in new_notifies.items():
                        record = NotifyRecord(
                            id=notify_id,
                            uid=uid,
                            content=notify.content,
                            tp=notify.tp,
                            system_notify_api=notify.system_notify_api,
                            source="bilibili",
                            created_time=getattr(notify, 'created_time', current_time),
                            synced_time=current_time,

                        )
                        notify_records.append(record)
                    self.db_manager.save_notifies(notify_records)

                logger.info("增量数据保存完成")

            except Exception as e:
                logger.error(f"保存增量数据失败: {e}")
                raise


class ClickableTextEdit(QTextEdit):
    """支持双击事件的 QTextEdit"""
    double_clicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        """确保单击也能正常工作"""
        super().mousePressEvent(event)

    def enterEvent(self, event):
        """鼠标悬停时改变光标"""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开时恢复光标"""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)


class DatabaseLoadThread(QThread):
    """数据库加载线程"""
    data_loaded = pyqtSignal(object, object, object)  # comments, danmus, notifies
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, sync_manager, uid):
        super().__init__()
        self.sync_manager = sync_manager
        self.uid = uid

    def run(self):
        try:
            self.progress.emit("正在加载评论...")
            comments, danmus, notifies = self.sync_manager.load_from_database(self.uid)
            self.data_loaded.emit(comments, danmus, notifies)
        except Exception as e:
            logger.error(f"数据库加载失败: {e}")
            self.error.emit(str(e))