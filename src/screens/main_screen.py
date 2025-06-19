import asyncio
import logging
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QPushButton, QLabel, QCheckBox,
    QScrollArea, QLineEdit, QSpinBox, QMessageBox,
    QProgressBar, QStackedWidget,QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices
from typing import Optional, Dict, Callable, List, Union
from ..types import Screen, Comment, Danmu, Notify, FetchProgressState, ActivityInfo
from ..api.api_service import ApiService
from ..api.notify import fetch as fetch_data
from ..utils import fuzzy_search
from .cookie_screen import CookieScreen
from .qrcode_screen import QRCodeScreen

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

    def stop(self):
        self._is_running = False

    def run(self):
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
                tasks = asyncio.all_tasks(loop=loop)
                for task in tasks: task.cancel()
                if tasks: loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                loop.close()
            except Exception as e:
                logger.error(f"Error closing event loop: {e}")

    async def _fetch_with_session(self, progress_callback: Callable[[Union[str, ActivityInfo]], None]):
        async with self.api_service:
            return await fetch_data(self.api_service, self.aicu_state, self.progress_state, progress_callback)


class DeleteThread(QThread):
    item_deleted = pyqtSignal(int)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, api_service, items, item_type, sleep_seconds):
        super().__init__()
        self.api_service, self.items, self.item_type, self.sleep_seconds = api_service, items, item_type, sleep_seconds
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
        # async with self.api_service: <--- 移除这一行
        for item_id, item in self.items:
            if not self._is_running: break
            current += 1
            self.progress.emit(current, total)
            try:
                # 注意：这里删除的是"评论"和"通知"，弹幕删除是通过弹窗提示
                if self.item_type == "评论":
                    from ..api.comment import remove_comment
                    await remove_comment(item, item_id, self.api_service)
                elif self.item_type == "通知":
                    from ..api.notify import remove_notify
                    await remove_notify(item, item_id, self.api_service)

                self.item_deleted.emit(item_id)
                logger.info(f"Deleted {self.item_type} {item_id}")
            except Exception as e:
                logger.error(f"Failed to delete {self.item_type} {item_id}: {e}")
                self.error.emit(f"删除 {self.item_type} (ID: {item_id}) 失败: {e}")

            if self._is_running and current < total: await asyncio.sleep(self.sleep_seconds)
        self.finished.emit()


class ItemViewer(QWidget):
    delete_requested = pyqtSignal(list, str, int)

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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        scroll_widget = QWidget()
        self.items_layout = QVBoxLayout(scroll_widget)
        self.items_layout.setContentsMargins(0, 0, 5, 0)
        self.items_layout.setSpacing(8)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        controls_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("全选")
        controls_layout.addWidget(self.select_all_btn)
        self.select_all_btn.clicked.connect(self.select_all)
        controls_layout.addStretch()
        controls_layout.addWidget(QLabel("删除间隔:"))
        self.sleep_input = QSpinBox()
        self.sleep_input.setMinimum(3); self.sleep_input.setMaximum(10); self.sleep_input.setValue(5); self.sleep_input.setSuffix(" s")
        controls_layout.addWidget(self.sleep_input)
        self.delete_btn = QPushButton("删除")
        self.delete_btn.setObjectName("deleteButton")
        self.delete_btn.clicked.connect(self.delete_selected)
        controls_layout.addWidget(self.delete_btn)
        layout.addLayout(controls_layout)

    def set_items(self, items: Dict[int, any]):
        self.all_items = items.copy()
        self.filter_items()

    def filter_items(self):
        search_text = self.search_input.text().strip()
        self.items = {k: v for k, v in self.all_items.items() if
                      not search_text or fuzzy_search(search_text, v.content)}
        self.refresh_display()

    def refresh_display(self):
        # 清理旧项目
        while (item := self.items_layout.takeAt(0)) is not None:
            if (widget := item.widget()) is not None:
                widget.deleteLater()
        self.checkboxes.clear()

        # 创建新项目
        for item_id, item in self.items.items():
            # 1. 创建一个水平布局的容器控件
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 0, 0)
            item_layout.setSpacing(10)

            # 2. 创建复选框 - 设置顶部对齐
            checkbox = QCheckBox()
            checkbox.setChecked(item.is_selected)
            checkbox.toggled.connect(lambda checked, id=item_id: self.toggle_item(id, checked))
            self.checkboxes[item_id] = checkbox

            # 设置复选框在垂直方向上靠顶部对齐
            checkbox.setStyleSheet("""
                QCheckBox {
                    margin-top: 2px;
                }
            """)

            # 3. 使用 QTextEdit 显示文本，支持多行自适应高度
            from PyQt6.QtWidgets import QTextEdit
            from PyQt6.QtCore import QTimer

            # 保留原始换行符，让文本自然换行
            content_display = item.content  # 不再替换换行符
            text_edit = QTextEdit()
            text_edit.setPlainText(content_display)
            text_edit.setReadOnly(True)

            # 禁用滚动条，让文本框自适应高度
            text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

            # 设置自动换行
            text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

            # 设置样式
            text_edit.setStyleSheet("""
                QTextEdit {
                    background-color: transparent;
                    border: none;
                    padding: 4px;
                    color: #ecf0f1;
                    font-family: "Microsoft YaHei UI", "SimSun", "Arial";
                    font-size: 14px;
                }
            """)

            # 4. 计算并设置合适的高度
            def adjust_text_height():
                # 获取文档高度
                doc = text_edit.document()
                doc_height = doc.size().height()

                # 设置文本框高度为文档高度加上一些边距
                text_edit.setFixedHeight(int(doc_height) + 10)

            # 初始调整高度
            text_edit.document().documentLayout().documentSizeChanged.connect(adjust_text_height)

            # 使用QTimer延迟调整，确保文档已完全加载
            QTimer.singleShot(0, adjust_text_height)

            # 5. 将控件添加到布局
            item_layout.addWidget(checkbox)
            item_layout.addWidget(text_edit)

            # 设置布局对齐方式，让复选框在顶部对齐
            item_layout.setAlignment(checkbox, Qt.AlignmentFlag.AlignTop)

            self.items_layout.addWidget(item_widget)

        self.update_header()

    def toggle_item(self, item_id: int, checked: bool):
        if item_id in self.items: self.items[item_id].is_selected = checked
        if item_id in self.all_items: self.all_items[item_id].is_selected = checked
        self.update_header()

    def update_header(self):
        selected = sum(1 for item in self.items.values() if item.is_selected)
        total = len(self.items)
        self.header_label.setText(f"{selected} 已选择 / 共 {total} 项")

    def select_all(self):
        is_all_selected = all(item.is_selected for item in self.items.values()) if self.items else False
        new_state = not is_all_selected

        for item_id in self.items.keys():
            self.items[item_id].is_selected = new_state
            if item_id in self.all_items:
                self.all_items[item_id].is_selected = new_state
            if item_id in self.checkboxes:
                self.checkboxes[item_id].setChecked(new_state)

        self.select_all_btn.setText("取消全选" if new_state else "全选")
        self.update_header()

    def delete_selected(self):
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
        if item_id in self.all_items: del self.all_items[item_id]
        if item_id in self.items:
            del self.items[item_id]
            if item_id in self.checkboxes:
                widget = self.checkboxes[item_id]
                self.items_layout.removeWidget(widget)
                widget.deleteLater()
                del self.checkboxes[item_id]
            self.update_header()


class MainScreen(QWidget):
    def __init__(self, api_service: ApiService, aicu_state: bool):
        super().__init__()
        self.api_service, self.aicu_state = api_service, aicu_state
        self.progress_state = FetchProgressState()
        self.delete_threads = {}
        self.all_comments, self.all_danmus, self.all_notifies = {}, {}, {}
        # 添加状态变量
        self.is_cascade_delete_enabled = True
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
        self.start_fetch()

    def init_ui(self):
        self.main_layout = QVBoxLayout(self); self.main_layout.setContentsMargins(10, 10, 10, 10)
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

        self.cascade_delete_checkbox = QCheckBox("删除通知时同时删除关联的评论")
        self.cascade_delete_checkbox.setChecked(self.is_cascade_delete_enabled)
        # 连接toggled信号到一个新的槽函数
        self.cascade_delete_checkbox.toggled.connect(self.on_cascade_checkbox_toggled)
        content_layout.addWidget(self.cascade_delete_checkbox)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.comment_viewer = ItemViewer("评论", self.api_service)
        self.comment_viewer.delete_requested.connect(self.handle_delete_request)
        splitter.addWidget(self.comment_viewer)

        self.danmu_viewer = ItemViewer("弹幕", self.api_service)
        self.danmu_viewer.delete_requested.connect(self.handle_delete_request)
        splitter.addWidget(self.danmu_viewer)

        self.notify_viewer = ItemViewer("通知", self.api_service)
        self.notify_viewer.delete_requested.connect(self.handle_delete_request)
        splitter.addWidget(self.notify_viewer)

        splitter.setSizes([350, 350, 350])
        content_layout.addWidget(splitter)

        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.unfollow_btn = QPushButton("批量取关工具")
        self.unfollow_btn.clicked.connect(self.open_unfollow_screen)
        bottom_layout.addWidget(self.unfollow_btn)
        content_layout.addLayout(bottom_layout)

        self.stacked_widget.addWidget(self.main_content_widget)

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
            thread = CascadeDeleteThread(self.api_service, cascade_list, sleep_seconds)
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
            thread = DeleteThread(self.api_service, items, item_type, sleep_seconds)
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
            # 添加调试日志
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
    def open_unfollow_screen(self):
        """打开批量取关界面"""
        try:
            from .unfollow_screen import UnfollowScreen
            self.unfollow_window = UnfollowScreen(self.api_service)
            self.unfollow_window.show()
        except Exception as e:
            logger.error(f"打开批量取关界面失败: {e}")
            QMessageBox.critical(self, "错误", f"无法打开批量取关界面: {e}")

    def closeEvent(self, event):
        if hasattr(self, 'fetch_thread') and self.fetch_thread.isRunning(): self.fetch_thread.stop(); self.fetch_thread.wait()
        for thread in self.delete_threads.values():
            if thread and thread.isRunning(): thread.stop(); thread.wait()
        super().closeEvent(event)


class CascadeDeleteThread(QThread):
    comment_deleted, danmu_deleted, notify_deleted = pyqtSignal(int), pyqtSignal(int), pyqtSignal(int)
    finished, progress = pyqtSignal(), pyqtSignal(int, int)
    error = pyqtSignal(str)

    def __init__(self, api_service, cascade_items, sleep_seconds):
        super().__init__()
        self.api_service, self.cascade_items, self.sleep_seconds = api_service, cascade_items, sleep_seconds
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
        # async with self.api_service: <--- 移除这一行
        for current, (item_type, item_id, item) in enumerate(self.cascade_items, 1):
            if not self._is_running: break
            self.progress.emit(current, total)
            try:
                if item_type == "comment":
                    from ..api.comment import remove_comment
                    await remove_comment(item, item_id, self.api_service)
                    self.comment_deleted.emit(item_id)
                elif item_type == "notify":
                    from ..api.notify import remove_notify
                    await remove_notify(item, item_id, self.api_service)
                    self.notify_deleted.emit(item_id)
                elif item_type == "danmu":
                    # 弹幕无法直接删除，但我们在这里记录一下日志
                    logger.warning(f"Skipping cascade delete for danmu {item_id} as it's not supported.")
                    self.danmu_deleted.emit(item_id)  # 仍然发射信号，让UI移除它

                logger.info(f"Successfully processed cascade item: {item_type} {item_id}")
            except Exception as e:
                error_message = f"删除失败: 无法删除 {item_type} (ID: {item_id}).\n原因: {e}"
                logger.error(error_message)
                self.error.emit(error_message)
                # 遇到错误时，可以多等一会，给服务器和网络喘息的时间
                if self._is_running:
                    await asyncio.sleep(5)

            if self._is_running and current < total: await asyncio.sleep(self.sleep_seconds)
        self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.api_service: Optional[ApiService] = None
        self.aicu_state = True
        self.current_screen = Screen.WAIT_SCAN_QRCODE
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

    def switch_to_main_screen(self):
        self.current_screen = Screen.MAIN
        screen = MainScreen(self.api_service, self.aicu_state)
        self.setCentralWidget(screen)

    @pyqtSlot(object, bool)
    def on_login_success(self, api_service: ApiService, aicu_state: bool):
        self.api_service = api_service
        self.aicu_state = aicu_state
        self.switch_to_main_screen()