import asyncio
import logging
import random
import requests
from typing import Dict, List, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QCheckBox, QLineEdit, QMessageBox, QHeaderView, QAbstractItemView, QProgressBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QPixmap, QImage
from ..api.api_service import ApiService
from ..utils import fuzzy_search

logger = logging.getLogger(__name__)


class LoadAvatarThread(QThread):
    """加载头像的线程"""
    success = pyqtSignal(QPixmap)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            response = requests.get(self.url, timeout=5)
            if response.status_code == 200:
                img = QImage.fromData(response.content)
                pixmap = QPixmap.fromImage(img)
                self.success.emit(pixmap)
        except Exception as e:
            logger.error(f"获取头像失败: {e}")


class FetchDataThread(QThread):
    """获取数据的线程 - 使用同步请求避免事件循环冲突"""
    success = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, api_service, url, params=None):
        super().__init__()
        self.api_service = api_service
        self.url = url
        self.params = params or {}

    def run(self):
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.2651.86",
                "Cookie": self.api_service.cookie,
                "Referer": "https://www.bilibili.com"
            }

            if self.params:
                # 使用同步请求
                response = requests.get(self.url, headers=headers, params=self.params, timeout=10)
            else:
                response = requests.get(self.url, headers=headers, timeout=10)

            response.raise_for_status()
            result = response.json()
            self.success.emit(result)
        except Exception as e:
            logger.error(f"获取错误: {e}")
            self.error.emit(str(e))


class UnfollowScreen(QWidget):
    """批量取关UP主界面"""
    back_to_tools = pyqtSignal()
    window_closed = pyqtSignal()
    def __init__(self, api_service: ApiService):
        super().__init__()
        self.api_service = api_service
        self.userid = None
        self.username = ""
        self.face_url = ""
        self.tagData = []

        self.allUPData = {}  # 存储所有已加载的UP主 {page: [ups...]}
        self.currentPageData = []  # 当前页数据
        self.displayData = []  # 实际显示的数据（搜索后的结果）

        self.current_tagid = 0
        self.current_page = 1
        self.total_pages = 1  # 总页数
        self.is_searching = False  # 是否在搜索状态

        # 添加当前线程引用
        self.current_unfollow_thread = None
        self.is_unfollowing = False

        # 保存所有线程引用
        self.threads = []

        self.init_ui()
        self.load_user_info()  # 加载用户信息

    def init_ui(self):
        #初始化UI
        self.setWindowTitle("批量取关UP主")
        self.resize(800, 1000)

        layout = QVBoxLayout()

        # 顶部工具栏
        self.create_toolbar(layout)

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索UP主:")
        search_layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入UP主名称进行搜索...")
        self.search_input.textChanged.connect(self.filter_ups)
        search_layout.addWidget(self.search_input)

        self.clear_search_btn = QPushButton("清空")
        self.clear_search_btn.clicked.connect(self.clear_search)
        search_layout.addWidget(self.clear_search_btn)

        layout.addLayout(search_layout)

        # 顶部布局
        top_layout = QHBoxLayout()

        # 左侧分组列表
        left_layout = QVBoxLayout()
        left_label = QLabel("分组列表")
        left_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        left_layout.addWidget(left_label)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabel("分组列表")
        self.tree_widget.setMaximumWidth(150)
        self.tree_widget.itemDoubleClicked.connect(self.on_tag_selected)
        left_layout.addWidget(self.tree_widget)

        # 获取按钮
        self.fetch_btn = QPushButton("获取")
        self.fetch_btn.clicked.connect(self.on_tag_selected)
        left_layout.addWidget(self.fetch_btn)

        # 加载全部按钮
        self.load_all_btn = QPushButton("加载全部")
        self.load_all_btn.clicked.connect(self.load_all_pages)
        self.load_all_btn.setEnabled(False)
        left_layout.addWidget(self.load_all_btn)

        # 添加进度标签
        self.progress_label = QLabel("")
        left_layout.addWidget(self.progress_label)

        top_layout.addLayout(left_layout)

        # 右侧UP主列表
        right_layout = QVBoxLayout()
        right_label = QLabel("UP主列表")
        right_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        right_layout.addWidget(right_label)

        self.table_widget = QTableWidget()
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        right_layout.addWidget(self.table_widget)

        # 分页按钮
        page_layout = QHBoxLayout()
        self.prev_btn = QPushButton("上一页")
        self.prev_btn.clicked.connect(self.prev_page)
        self.prev_btn.setEnabled(False)
        page_layout.addWidget(self.prev_btn)

        page_layout.addStretch()

        self.next_btn = QPushButton("下一页")
        self.next_btn.clicked.connect(self.next_page)
        self.next_btn.setEnabled(False)
        page_layout.addWidget(self.next_btn)

        right_layout.addLayout(page_layout)

        top_layout.addLayout(right_layout)

        # 右侧控制按钮
        control_layout = QVBoxLayout()

        # 用户头像
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(80, 80)
        self.avatar_label.setStyleSheet("border: 1px solid #566573; border-radius: 5px;")
        control_layout.addWidget(self.avatar_label)

        # 用户昵称标签
        self.username_label = QLabel("加载中...")
        self.username_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.username_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        control_layout.addWidget(self.username_label)

        control_layout.addStretch()

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self.select_all)
        self.select_all_btn.setEnabled(False)
        control_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("取消全选")
        self.deselect_all_btn.clicked.connect(self.deselect_all)
        self.deselect_all_btn.setEnabled(False)
        control_layout.addWidget(self.deselect_all_btn)

        # 添加进度条
        self.unfollow_progress = QProgressBar()
        self.unfollow_progress.setVisible(False)
        control_layout.addWidget(self.unfollow_progress)

        # 取关按钮（只创建一次）
        self.unfollow_btn = QPushButton("一键取关")
        self.unfollow_btn.setObjectName("deleteButton")
        self.unfollow_btn.clicked.connect(self.unfollow_selected)
        self.unfollow_btn.setEnabled(False)
        control_layout.addWidget(self.unfollow_btn)

        top_layout.addLayout(control_layout)

        layout.addLayout(top_layout)

        # 使用说明
        info_label = QLabel(
            "使用说明:\n"
            "① 双击左侧分组或选中后点击\"获取\"按钮\n"
            "② 单次最多只能获取50个UP，如果数量较多可以分次取关\n"
            "③ 页面跳转会使前一页已勾选项失效\n"
            "④ 使用顶部搜索框可以快速查找UP主"
        )
        info_label.setObjectName("infoLabel")#在style单独设置样式....
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.setLayout(layout)

    def create_toolbar(self, layout):
        """创建顶部工具栏"""
        toolbar_layout = QHBoxLayout()

        # 返回按钮
        back_btn = QPushButton("← 返回工具选择")
        back_btn.clicked.connect(self.back_to_tools.emit)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #7f8c8d;
                color: white;
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
        title_label = QLabel("批量取关")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #ecf0f1;")
        toolbar_layout.addWidget(title_label)

        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)

    def load_user_info(self):
        """加载用户信息 - 优先使用缓存"""
        # 首先尝试从缓存获取
        uid, username, face_url = self.api_service.get_cached_user_info()
        if uid and username:
            self.userid = uid
            self.username = username
            self.face_url = face_url or ""

            # 更新UI
            self.username_label.setText(self.username)
            logger.info(f"从缓存加载用户信息: UID={uid}, 用户名={username}")

            # 如果有头像URL，加载头像
            if self.face_url:
                self.load_avatar(self.face_url)

            # 获取分组信息
            self.get_tags()
        else:
            # 缓存中没有信息，从API获取
            self.get_user_info()

    def clear_search(self):
        """清空搜索"""
        self.search_input.clear()
        self.filter_ups()

    def get_user_info(self):
        """获取用户信息和分组"""
        thread = FetchDataThread(
            self.api_service,
            "https://api.bilibili.com/x/space/myinfo"
        )
        thread.success.connect(self.on_user_info_received)
        thread.error.connect(lambda e: QMessageBox.critical(self, "错误", f"获取用户信息失败: {e}"))
        thread.finished.connect(lambda: self.cleanup_thread(thread))
        thread.start()
        self.threads.append(thread)

    def cleanup_thread(self, thread):
        """清理完成的线程"""
        if thread in self.threads:
            self.threads.remove(thread)

    def on_user_info_received(self, data):
        """处理用户信息"""
        try:
            if data.get("code") == 0:
                user_data = data.get("data", {})
                self.userid = user_data.get("mid")
                self.username = user_data.get("name", "")
                self.face_url = user_data.get("face", "")

                # 用户名显示
                self.username_label.setText(self.username)

                # 缓存用户信息到ApiService
                if self.userid and self.username:
                    self.api_service.user_cache.set_user_info(self.userid, self.username, self.face_url)

                # 加载头像
                if self.face_url:
                    self.load_avatar(self.face_url)

                # 获取分组
                self.get_tags()
        except Exception as e:
            logger.error(f"处理用户信息失败: {e}")

    def load_avatar(self, url):
        """加载用户头像"""
        thread = LoadAvatarThread(url)
        thread.success.connect(self.on_avatar_loaded)
        thread.finished.connect(lambda: self.cleanup_thread(thread))
        thread.start()
        self.threads.append(thread)

    def on_avatar_loaded(self, pixmap):
        """头像加载完成"""
        try:
            self.avatar_label.setPixmap(
                pixmap.scaled(
                    self.avatar_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
            )
        except Exception as e:
            logger.error(f"设置头像失败: {e}")

    def get_tags(self):
        """获取分组列表"""
        thread = FetchDataThread(
            self.api_service,
            "https://api.bilibili.com/x/relation/tags"
        )
        thread.success.connect(self.on_tags_received)
        thread.error.connect(lambda e: QMessageBox.critical(self, "错误", f"获取分组失败: {e}"))
        thread.finished.connect(lambda: self.cleanup_thread(thread))
        thread.start()
        self.threads.append(thread)

    def on_tags_received(self, data):
        """处理分组数据"""
        try:
            if data.get("code") == 0:
                self.tagData = data.get("data", [])
                self.tree_widget.clear()

                for tag in self.tagData:
                    item = QTreeWidgetItem([tag["name"]])
                    self.tree_widget.addTopLevelItem(item)
        except Exception as e:
            logger.error(f"处理分组数据失败: {e}")

    def on_tag_selected(self):
        """选中分组时获取UP主列表"""
        current_item = self.tree_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "提示", "请先选择分组")
            return

        # 查找对应的tagid
        tag_name = current_item.text(0)
        for tag in self.tagData:
            if tag['name'] == tag_name:
                self.current_tagid = tag['tagid']
                break

        self.current_page = 1
        self.allUPData.clear()
        self.search_input.clear()
        self.is_searching = False
        self.load_all_btn.setEnabled(True)

        self.get_ups()

    def get_ups(self, page=None):
        """获取UP主列表"""
        if page is None:
            page = self.current_page

        params = {
            'tagid': self.current_tagid,
            'pn': page,
            'ps': 50,
        }

        thread = FetchDataThread(
            self.api_service,
            "https://api.bilibili.com/x/relation/tag",
            params
        )
        thread.success.connect(lambda data: self.on_ups_received(data, page))
        thread.error.connect(lambda e: QMessageBox.critical(self, "错误", f"获取UP主列表失败: {e}"))
        thread.finished.connect(lambda: self.cleanup_thread(thread))
        thread.start()
        self.threads.append(thread)

    def on_ups_received(self, data, page):
        """处理UP主列表数据"""
        try:
            if data.get("code") == 0:
                ups_data = data.get("data", [])

                # 存储到对应页
                page_data = []
                for up in ups_data:
                    page_data.append({
                        'uname': up.get('uname', ''),
                        'mid': str(up.get('mid', ''))
                    })

                self.allUPData[page] = page_data

                # 如果是当前页，更新显示
                if page == self.current_page and not self.is_searching:
                    self.currentPageData = page_data
                    self.displayData = page_data
                    self.refresh_table()

                # 更新总页数
                if len(ups_data) >= 50:
                    self.total_pages = max(self.total_pages, page + 1)
                else:
                    self.total_pages = page

                # 更新按钮状态
                self.update_button_states()

                # 更新进度
                self.update_progress()

        except Exception as e:
            logger.error(f"处理UP主列表失败: {e}")

    def load_all_pages(self):
        """加载所有页面的数据"""
        reply = QMessageBox.question(
            self, "确认",
            "加载全部数据可能需要一些时间，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.load_all_btn.setEnabled(False)
            self.load_all_btn.setText("加载中...")

            # 从第2页开始加载（第1页已经加载了）
            for page in range(2, self.total_pages + 5):  # +5 是为了探测更多页
                if page not in self.allUPData:
                    self.get_ups(page)
                    # 添加延迟避免请求过快
                    QThread.msleep(500)

    def filter_ups(self):
        """根据搜索内容过滤UP主 - 全局搜索"""
        search_text = self.search_input.text().strip()

        if not search_text:
            # 恢复到当前页显示
            self.is_searching = False
            self.displayData = self.currentPageData
            self.update_button_states()
        else:
            # 搜索所有已加载的数据
            self.is_searching = True
            self.displayData = []

            # 遍历所有页的数据
            for page_data in self.allUPData.values():
                for up in page_data:
                    if fuzzy_search(search_text, up['uname']):
                        self.displayData.append(up)
            # 搜索时禁用分页按钮
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)

        self.refresh_table()

        # 显示搜索结果数量
        if self.is_searching:
            total_loaded = sum(len(page_data) for page_data in self.allUPData.values())
            self.progress_label.setText(f"搜索结果: {len(self.displayData)} / 已加载: {total_loaded}")

    def update_button_states(self):
        """更新按钮状态"""
        if not self.is_searching:
            self.prev_btn.setEnabled(self.current_page > 1)
            self.next_btn.setEnabled(self.current_page < self.total_pages or len(self.currentPageData) >= 50)

        self.select_all_btn.setEnabled(len(self.displayData) > 0)
        self.deselect_all_btn.setEnabled(len(self.displayData) > 0)
        self.unfollow_btn.setEnabled(len(self.displayData) > 0)

    def update_progress(self):
        """更新进度显示"""
        if not self.is_searching:
            total_loaded = sum(len(page_data) for page_data in self.allUPData.values())
            self.progress_label.setText(f"已加载: {total_loaded} UP主 (第{self.current_page}/{self.total_pages}页)")

    def select_all(self):
        """全选"""
        for i in range(self.table_widget.rowCount()):
            checkbox = self.table_widget.cellWidget(i, 0)
            if checkbox:
                checkbox.setChecked(True)

    def deselect_all(self):#取消全选
        for i in range(self.table_widget.rowCount()):
            checkbox = self.table_widget.cellWidget(i, 0)
            if checkbox:
                checkbox.setChecked(False)

    def prev_page(self):
        """上一页"""
        if self.current_page > 1:
            self.current_page -= 1

            # 如果该页已加载，直接显示
            if self.current_page in self.allUPData:
                self.currentPageData = self.allUPData[self.current_page]
                self.displayData = self.currentPageData
                self.refresh_table()
                self.update_button_states()
                self.update_progress()
            else:
                # 否则重新加载
                self.get_ups()

    def next_page(self):
        """下一页"""
        self.current_page += 1

        # 如果该页已加载，直接显示
        if self.current_page in self.allUPData:
            self.currentPageData = self.allUPData[self.current_page]
            self.displayData = self.currentPageData
            self.refresh_table()
            self.update_button_states()
            self.update_progress()
        else:
            # 否则重新加载
            self.get_ups()

    def refresh_table(self):
        """刷新表格显示 - 显示 displayData"""
        self.table_widget.setRowCount(len(self.displayData))
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels(['', '用户名', 'UID'])

        # 设置列宽
        self.table_widget.setColumnWidth(0, 40)
        self.table_widget.setColumnWidth(1, 150)
        self.table_widget.setColumnWidth(2, 100)

        # 隐藏垂直表头
        self.table_widget.verticalHeader().setVisible(False)

        for i, data in enumerate(self.displayData):
            # 复选框
            checkbox = QCheckBox()
            checkbox.setStyleSheet("margin-left: 10px;")
            self.table_widget.setCellWidget(i, 0, checkbox)

            # 用户名
            self.table_widget.setItem(i, 1, QTableWidgetItem(data['uname']))

            # UID
            self.table_widget.setItem(i, 2, QTableWidgetItem(data['mid']))

    def unfollow_selected(self):
        """取关选中的UP主 - 使用 displayData"""
        if self.is_unfollowing:
            # 如果正在取关，则停止
            self.stop_unfollow()
        else:
            # 否则开始取关
            selected_mids = []

            for i in range(self.table_widget.rowCount()):
                checkbox = self.table_widget.cellWidget(i, 0)
                if checkbox and checkbox.isChecked():
                    selected_mids.append(self.displayData[i]['mid'])

            if not selected_mids:
                QMessageBox.information(self, "提示", "请选择要取消关注的UP")
                return

            reply = QMessageBox.question(
                self, "确认",
                f"是否确认取消关注 {len(selected_mids)} 个UP主？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.perform_unfollow(selected_mids)

    def perform_unfollow(self, mids: List[str]):
        """执行取关操作"""
        # 显示进度条
        self.unfollow_progress.setVisible(True)
        self.unfollow_progress.setMaximum(len(mids))
        self.unfollow_progress.setValue(0)

        self.current_unfollow_thread = UnfollowThread(self.api_service, mids)
        self.current_unfollow_thread.progress.connect(self.on_unfollow_progress)
        self.current_unfollow_thread.finished.connect(self.on_unfollow_finished)
        self.current_unfollow_thread.finished.connect(lambda: self.cleanup_thread(self.current_unfollow_thread))
        self.current_unfollow_thread.error.connect(lambda e: QMessageBox.critical(self, "错误", f"取关失败: {e}"))
        self.current_unfollow_thread.start()
        self.threads.append(self.current_unfollow_thread)

        self.is_unfollowing = True
        self.unfollow_btn.setText("停止取关")
        self.unfollow_btn.setEnabled(True)  # 保持按钮可用

        # 禁用其他控制按钮
        self.select_all_btn.setEnabled(False)
        self.deselect_all_btn.setEnabled(False)
        self.fetch_btn.setEnabled(False)
        self.load_all_btn.setEnabled(False)

    def stop_unfollow(self):
        """停止取关操作"""
        if self.current_unfollow_thread and self.current_unfollow_thread.isRunning():
            self.current_unfollow_thread.stop()
            self.unfollow_btn.setText("正在停止...")
            self.unfollow_btn.setEnabled(False)

    def on_unfollow_progress(self, current, total):
        """更新取关进度"""
        self.unfollow_btn.setText(f"停止取关 ({current}/{total})")
        self.unfollow_progress.setValue(current)

    def on_unfollow_finished(self):
        """取关完成"""
        self.is_unfollowing = False
        self.current_unfollow_thread = None

        # 恢复按钮状态
        self.unfollow_btn.setEnabled(True)
        self.unfollow_btn.setText("一键取关")
        self.select_all_btn.setEnabled(True)
        self.deselect_all_btn.setEnabled(True)
        self.fetch_btn.setEnabled(True)
        self.load_all_btn.setEnabled(True)

        # 隐藏进度条
        self.unfollow_progress.setVisible(False)

        QMessageBox.information(self, "完成", "取关操作已完成！")

        # 刷新列表
        self.get_ups()

    #   窗口关闭时清理线程
    def closeEvent(self, event):

        # 停止正在进行的取关操作
        if self.current_unfollow_thread and self.current_unfollow_thread.isRunning():
            self.current_unfollow_thread.stop()

        # 停止所有运行中的线程
        for thread in self.threads:
            if thread.isRunning():
                if hasattr(thread, 'stop'):
                    thread.stop()
                thread.quit()



        # 清空线程列表，打破引用
        self.threads.clear()
        self.current_unfollow_thread = None

        # 清理数据
        self.tagData.clear()
        self.allUPData.clear()
        self.currentPageData.clear()
        self.displayData.clear()

        # 发送窗口关闭信号
        self.window_closed.emit()
        super().closeEvent(event)


class UnfollowThread(QThread):
    """取关操作线程 - 使用独立的事件循环"""
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, api_service: ApiService, mids: List[str]):
        super().__init__()
        self.api_service = api_service
        self.mids = mids
        self._is_running = True

    def stop(self):
        """停止取关操作"""
        self._is_running = False

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._unfollow_all())
            self.finished.emit()
        except Exception as e:
            logger.error(f"Unfollow error: {e}")
            self.error.emit(str(e))
        finally:
            loop.close()

    async def _unfollow_all(self):
        """执行所有取关操作"""
        total = len(self.mids)

        import aiohttp
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.2651.86",
            "Cookie": self.api_service.cookie,
            "Referer": "https://www.bilibili.com"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            for i, mid in enumerate(self.mids):
                # 检查是否需要停止
                if not self._is_running:
                    logger.info(f"取关操作被用户停止，已处理 {i}/{total}")
                    break

                try:
                    data = aiohttp.FormData()
                    data.add_field('fid', mid)
                    data.add_field('act', '2')
                    data.add_field('re_src', '11')
                    data.add_field('csrf', self.api_service.csrf)

                    async with session.post("https://api.bilibili.com/x/relation/modify", data=data) as response:
                        response.raise_for_status()
                        result = await response.json()

                    self.progress.emit(i + 1, total)

                    # 只在未停止时等待
                    if self._is_running:
                        await asyncio.sleep(random.uniform(1.5, 2.5))

                except Exception as e:
                    logger.error(f"取关 {mid} 失败: {e}")
                    # 继续处理其他UP主
                    continue