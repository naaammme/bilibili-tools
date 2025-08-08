import hashlib
import json
import random
import time
import logging
import threading
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox,
    QLineEdit, QSpinBox, QMessageBox, QProgressBar,
    QTextEdit, QFrame, QGroupBox, QGridLayout,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSplitter, QComboBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot, QTimer
from PyQt6.QtGui import QFont

try:
    from DrissionPage import ChromiumPage, ChromiumOptions
    DRISSION_AVAILABLE = True
except ImportError:
    DRISSION_AVAILABLE = False

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self):
        home_dir = Path.home()
        cache_dir = home_dir / ".bilibili_tools"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file_path = cache_dir / "aicu_cache.json"

    def _read_cache_file(self) -> Dict:
        if not self.cache_file_path.exists():
            return {}
        try:
            with self.cache_file_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_cache_file(self, data: Dict):
        try:
            with self.cache_file_path.open('w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except IOError as e:
            logger.error(f"写入缓存文件失败: {e}")

    def load_user_data(self, uid: int) -> Dict[str, List]:
        all_data = self._read_cache_file()
        return all_data.get(str(uid), {"comments": [], "danmus": [], "live_danmus": []})

    def save_user_data(self, uid: int, comments: List, danmus: List, live_danmus: List):
        all_data = self._read_cache_file()
        all_data[str(uid)] = {"comments": comments, "danmus": danmus, "live_danmus": live_danmus}
        self._write_cache_file(all_data)

    def clear_user_data(self, uid: int):
        all_data = self._read_cache_file()
        if str(uid) in all_data:
            del all_data[str(uid)]
            self._write_cache_file(all_data)


class HeadlessDrissionClient:
    def __init__(self):
        self.page = None
        self.is_headless = True

    def create_page(self, headless=True):
        co = ChromiumOptions()

        co.set_pref('excludeSwitches', ['enable-automation'])

        if headless:
            co.headless(True)
            co.set_argument('--no-sandbox')
            co.set_argument('--disable-dev-shm-usage')
            co.set_argument('--disable-gpu')
            co.set_argument('--disable-web-security')
            co.set_argument('--disable-features=VizDisplayCompositor')
            co.set_argument('--disable-software-rasterizer')

        co.set_argument('--disable-blink-features=AutomationControlled')

        co.set_user_agent(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36')

        co.set_argument('--window-size=1920,1080')
        co.set_argument('--ignore-certificate-errors')
        co.set_argument('--ignore-ssl-errors')
        co.set_argument('--disable-extensions')
        co.set_argument('--disable-images')
        co.set_argument('--disable-plugins')

        self.page = ChromiumPage(co)

        self.page.set.headers({
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Dnt': '1',
            'Origin': 'https://www.aicu.cc',
            'Sec-Ch-Ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        })
        self.page.run_js("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en-US', 'en']
            });
            window.chrome = {
                runtime: {},
                csi: function() {},
                loadTimes: function() {},
            };
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
            );
        """)
        return self.page
    #这里未来考虑使用网络监听: DrissionPage 提供了强大的网络监听功能 (page.listen.start
    def fetch_api(self, url, timeout=30):
        try:
            if not self.page:
                logger.info("初始化浏览器（无头模式）...")
                self.create_page(headless=self.is_headless)

            logger.info(f"访问URL: {url}")
            self.page.get(url)

            start_time = time.time()
            max_wait = timeout

            while time.time() - start_time < max_wait:
                try:
                    pre_element = self.page.ele('tag:pre')
                    if pre_element:
                        text = pre_element.text
                        if text and (text.startswith('{') or text.startswith('[')):
                            return {'success': True, 'data': text, 'method': 'pre_tag'}
                except:
                    pass

                try:
                    body_text = self.page.ele('tag:body').text
                    if body_text and (body_text.startswith('{') or body_text.startswith('[')):
                        json.loads(body_text)
                        return {'success': True, 'data': body_text, 'method': 'body_text'}
                except:
                    pass

                time.sleep(0.5)

            return {'success': False, 'data': self.page.html, 'error': '未能获取到JSON响应'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def close(self):
        if self.page:
            self.page.quit()
            self.page = None


class DrissionPageWindow(QDialog):
    data_imported = pyqtSignal(dict, dict, dict)

    def __init__(self, uid: int, username: str, parent=None):
        super().__init__(parent)
        self.uid = uid
        self.username = username

        self.drission_client = None
        self.fetch_thread = None
        self.cache_manager = CacheManager()

        self.fetched_comments = []
        self.fetched_danmus = []
        self.fetched_live_danmus = []

        self.init_ui()
        self.setup_drission()
        self.load_from_cache()

        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def init_ui(self):
        self.setWindowTitle(f"DrissionPage备用API - {self.username} (UID: {self.uid})")
        self.resize(1200, 900)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)
        self.create_info_bar(main_layout)
        self.create_tab_widget(main_layout)
        self.create_control_bar(main_layout)

    def create_info_bar(self, parent_layout):
        info_frame = QFrame()
        info_frame.setObjectName("mainPanel")
        info_layout = QHBoxLayout(info_frame)
        user_label = QLabel(f"用户: {self.username}")
        user_label.setStyleSheet("font-weight: bold; color: #4a9eff; font-size: 14px;")
        info_layout.addWidget(user_label)
        uid_label = QLabel(f"UID: {self.uid}")
        uid_label.setStyleSheet("color: #64748b; font-size: 12px;")
        info_layout.addWidget(uid_label)
        info_layout.addStretch()
        self.status_indicator = QLabel("🔴 未连接")
        self.status_indicator.setStyleSheet("color: #ef4444; font-weight: bold;")
        info_layout.addWidget(self.status_indicator)
        parent_layout.addWidget(info_frame)

    def create_tab_widget(self, parent_layout):
        self.tab_widget = QTabWidget()
        config_tab = self.create_config_tab()
        self.tab_widget.addTab(config_tab, "配置")
        log_tab = self.create_log_tab()
        self.tab_widget.addTab(log_tab, "日志")
        preview_tab = self.create_preview_tab()
        self.tab_widget.addTab(preview_tab, "预览")
        parent_layout.addWidget(self.tab_widget)

    def create_config_tab(self):
        config_widget = QWidget()
        layout = QVBoxLayout(config_widget)
        layout.setSpacing(15)

        api_group = QGroupBox("🌐 API配置")
        api_layout = QGridLayout(api_group)
        api_layout.addWidget(QLabel("API地址:"), 0, 0)
        self.api_url_combo = QComboBox()
        self.api_url_combo.addItems([
            "https://api.aicu.cc/api/v3/search",
            "https://apibackup2.aicu.cc:88/api/v3/search"
        ])
        self.api_url_combo.setEditable(True)
        self.api_url_combo.setCurrentText("https://apibackup2.aicu.cc:88/api/v3/search")
        api_layout.addWidget(self.api_url_combo, 0, 1)
        api_layout.addWidget(QLabel("请求超时 (秒):"), 1, 0)
        self.timeout_input = QSpinBox()
        self.timeout_input.setRange(10, 120)
        self.timeout_input.setValue(30)
        api_layout.addWidget(self.timeout_input, 1, 1)
        layout.addWidget(api_group)

        fetch_group = QGroupBox("获取配置")
        fetch_layout = QGridLayout(fetch_group)
        fetch_layout.addWidget(QLabel("每页条数:"), 0, 0)
        self.page_size_input = QSpinBox()
        self.page_size_input.setRange(1, 500)
        self.page_size_input.setValue(500)
        fetch_layout.addWidget(self.page_size_input, 0, 1)
        fetch_layout.addWidget(QLabel("最大页数:"), 0, 2)
        self.max_pages_input = QSpinBox()
        self.max_pages_input.setRange(1, 100)
        self.max_pages_input.setValue(5)
        fetch_layout.addWidget(self.max_pages_input, 0, 3)
        fetch_layout.addWidget(QLabel("页面延迟 (秒):"), 1, 0)
        self.delay_input = QSpinBox()
        self.delay_input.setRange(1, 10)
        self.delay_input.setValue(3)
        fetch_layout.addWidget(self.delay_input, 1, 1)
        layout.addWidget(fetch_group)

        browser_group = QGroupBox("浏览器配置")
        browser_layout = QGridLayout(browser_group)
        self.headless_checkbox = QCheckBox("无头模式 (后台运行)")
        self.headless_checkbox.setChecked(True)
        browser_layout.addWidget(self.headless_checkbox, 0, 0)
        hint_label = QLabel("提示：取消勾选可看到浏览器操作过程，用于调试")
        hint_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        browser_layout.addWidget(hint_label, 1, 0, 1, 2)
        layout.addWidget(browser_group)

        data_group = QGroupBox("数据类型")
        data_layout = QHBoxLayout(data_group)
        self.fetch_comments_checkbox = QCheckBox("获取评论")
        self.fetch_comments_checkbox.setChecked(True)
        data_layout.addWidget(self.fetch_comments_checkbox)
        self.fetch_danmus_checkbox = QCheckBox("获取视频弹幕")
        self.fetch_danmus_checkbox.setChecked(True)
        data_layout.addWidget(self.fetch_danmus_checkbox)
        self.fetch_live_danmus_checkbox = QCheckBox("获取直播弹幕")
        self.fetch_live_danmus_checkbox.setChecked(True)
        data_layout.addWidget(self.fetch_live_danmus_checkbox)
        data_layout.addStretch()
        layout.addWidget(data_group)

        cache_group = QGroupBox("缓存管理")
        cache_layout = QHBoxLayout(cache_group)
        clear_cache_btn = QPushButton("清除此用户缓存")
        clear_cache_btn.setObjectName("dangerButton")
        clear_cache_btn.clicked.connect(self.clear_user_cache)
        cache_layout.addWidget(clear_cache_btn)
        cache_layout.addStretch()
        layout.addWidget(cache_group)

        layout.addStretch()
        return config_widget

    def create_log_tab(self):
        log_widget = QWidget()
        layout = QVBoxLayout(log_widget)
        log_control_layout = QHBoxLayout()
        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.setObjectName("secondaryButton")
        clear_log_btn.clicked.connect(self.clear_log)
        log_control_layout.addWidget(clear_log_btn)
        save_log_btn = QPushButton("保存日志")
        save_log_btn.setObjectName("secondaryButton")
        save_log_btn.clicked.connect(self.save_log)
        log_control_layout.addWidget(save_log_btn)
        log_control_layout.addStretch()
        self.auto_scroll_checkbox = QCheckBox("自动滚动")
        self.auto_scroll_checkbox.setChecked(True)
        log_control_layout.addWidget(self.auto_scroll_checkbox)
        layout.addLayout(log_control_layout)
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        font = QFont("Consolas", 10)
        if not font.exactMatch(): font = QFont("Courier New", 10)
        self.log_display.setFont(font)
        layout.addWidget(self.log_display)
        return log_widget

    def create_preview_tab(self):
        preview_widget = QWidget()
        layout = QVBoxLayout(preview_widget)
        stats_frame = QFrame()
        stats_frame.setObjectName("mainPanel")
        stats_layout = QHBoxLayout(stats_frame)
        self.comments_count_label = QLabel("评论: 0 条")
        self.comments_count_label.setStyleSheet("font-weight: bold; color: #10b981;")
        stats_layout.addWidget(self.comments_count_label)
        self.danmus_count_label = QLabel("视频弹幕: 0 条")
        self.danmus_count_label.setStyleSheet("font-weight: bold; color: #10b981;")
        stats_layout.addWidget(self.danmus_count_label)
        self.live_danmus_count_label = QLabel("直播弹幕: 0 条")
        self.live_danmus_count_label.setStyleSheet("font-weight: bold; color: #10b981;")
        stats_layout.addWidget(self.live_danmus_count_label)
        stats_layout.addStretch()
        refresh_preview_btn = QPushButton("刷新预览")
        refresh_preview_btn.setObjectName("primaryButton")
        refresh_preview_btn.clicked.connect(self.refresh_preview)
        stats_layout.addWidget(refresh_preview_btn)
        layout.addWidget(stats_frame)

        self.preview_tabs = QTabWidget()
        self.comments_table = self.create_preview_table("评论预览", ["ID", "内容", "时间"])
        self.danmus_table = self.create_preview_table("视频弹幕预览", ["ID", "内容", "时间"])
        self.live_danmus_table = self.create_preview_table("直播弹幕预览", ["房间名", "内容", "时间"])

        live_table_widget = self.live_danmus_table.findChild(QTableWidget)#双击跳转功能
        if live_table_widget:
            live_table_widget.cellDoubleClicked.connect(self.on_live_danmu_double_click)
        self.preview_tabs.addTab(self.comments_table, "评论")
        self.preview_tabs.addTab(self.danmus_table, "视频弹幕")
        self.preview_tabs.addTab(self.live_danmus_table, "直播弹幕")
        layout.addWidget(self.preview_tabs)
        return preview_widget

    def create_preview_table(self, title, headers):
        frame = QFrame()
        frame.setObjectName("mainPanel")
        layout = QVBoxLayout(frame)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #f1f5f9;")
        layout.addWidget(title_label)
        table = QTableWidget()
        table.setObjectName("commentDataTable")
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        layout.addWidget(table)
        return frame

    def create_control_bar(self, parent_layout):
        control_frame = QFrame()
        control_frame.setObjectName("mainPanel")
        control_layout = QHBoxLayout(control_frame)
        self.start_btn = QPushButton("开始获取")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.clicked.connect(self.start_fetch)
        control_layout.addWidget(self.start_btn)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("dangerButton")
        self.stop_btn.clicked.connect(self.stop_fetch)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        control_layout.addWidget(self.progress_bar)
        control_layout.addStretch()
        self.import_btn = QPushButton("导入到主界面")
        self.import_btn.setObjectName("primaryButton")
        self.import_btn.clicked.connect(self.import_data)
        self.import_btn.setEnabled(False)
        control_layout.addWidget(self.import_btn)
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.close)
        control_layout.addWidget(close_btn)
        parent_layout.addWidget(control_frame)
        self.status_label = QLabel("就绪 - 等待开始获取数据")
        self.status_label.setStyleSheet("color: #64748b; font-size: 12px; padding: 5px;")
        parent_layout.addWidget(self.status_label)

    def setup_drission(self):
        if not DRISSION_AVAILABLE:
            self.append_log("❌ DrissionPage未安装，无法使用备用API功能", "ERROR")
            self.status_indicator.setText("🔴 DrissionPage不可用")
            return
        try:
            self.drission_client = HeadlessDrissionClient()
            self.append_log("✅ DrissionPage客户端初始化成功", "SUCCESS")
            self.status_indicator.setText("🟢 已初始化")
            self.status_indicator.setStyleSheet("color: #10b981; font-weight: bold;")
        except Exception as e:
            self.append_log(f"❌ DrissionPage客户端初始化失败: {e}", "ERROR")
            self.status_indicator.setText("🔴 初始化失败")

    def append_log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        colors = {"INFO": "#3b82f6", "SUCCESS": "#10b981", "WARNING": "#f59e0b", "ERROR": "#ef4444", "DEBUG": "#6b7280"}
        color = colors.get(level, "#3b82f6")
        formatted_message = f'<span style="color: {color};">[{timestamp}] {message}</span>'
        self.log_display.append(formatted_message)
        if self.auto_scroll_checkbox.isChecked():
            scrollbar = self.log_display.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def clear_log(self):
        self.log_display.clear()
        self.append_log("日志已清空")

    def save_log(self):
        try:
            from PyQt6.QtWidgets import QFileDialog
            file_path, _ = QFileDialog.getSaveFileName(self, "保存日志", f"drission_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", "文本文件 (*.txt)")
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_display.toPlainText())
                self.append_log(f"💾 日志已保存到: {file_path}", "SUCCESS")
        except Exception as e:
            self.append_log(f"❌ 保存日志失败: {e}", "ERROR")

    def load_from_cache(self):
        cached_data = self.cache_manager.load_user_data(self.uid)
        self.fetched_comments = cached_data.get("comments", [])
        self.fetched_danmus = cached_data.get("danmus", [])
        self.fetched_live_danmus = cached_data.get("live_danmus", [])
        if self.fetched_comments or self.fetched_danmus or self.fetched_live_danmus:
            self.append_log(f"从缓存加载了 {len(self.fetched_comments)} 条评论, {len(self.fetched_danmus)} 条视频弹幕, {len(self.fetched_live_danmus)} 条直播弹幕", "SUCCESS")
            self.refresh_preview()
            self.on_data_update(len(self.fetched_comments), len(self.fetched_danmus), len(self.fetched_live_danmus))
            self.import_btn.setEnabled(True)
            self.start_btn.setText("获取新数据")
        else:
            self.start_btn.setText("开始获取")

    def clear_user_cache(self):
        reply = QMessageBox.question(self, "确认清除", f"确定要清除用户 {self.username} (UID: {self.uid}) 的所有本地缓存数据吗？\n此操作不可撤销。", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.cache_manager.clear_user_data(self.uid)
            self.fetched_comments = []
            self.fetched_danmus = []
            self.fetched_live_danmus = []
            self.refresh_preview()
            self.on_data_update(0, 0, 0)
            self.import_btn.setEnabled(False)
            self.start_btn.setText("开始获取")
            self.append_log(f"已清除用户 {self.uid} 的缓存", "SUCCESS")

    def start_fetch(self):
        if not self.drission_client:
            QMessageBox.warning(self, "错误", "DrissionPage客户端未初始化")
            return
        if self.fetch_thread and self.fetch_thread.isRunning():
            QMessageBox.warning(self, "提示", "数据获取正在进行中...")
            return
        if not self.fetch_comments_checkbox.isChecked() and not self.fetch_danmus_checkbox.isChecked() and not self.fetch_live_danmus_checkbox.isChecked():
            QMessageBox.warning(self, "配置错误", "请至少选择一种数据类型")
            return
        fetch_mode = 'full'
        if self.fetched_comments or self.fetched_danmus or self.fetched_live_danmus:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("选择获取模式")
            msg_box.setText("检测到本地已有数据，请选择获取方式：")
            msg_box.setIcon(QMessageBox.Icon.Question)
            new_btn = msg_box.addButton("仅获取新数据", QMessageBox.ButtonRole.YesRole)
            full_btn = msg_box.addButton("补充所有缺失数据", QMessageBox.ButtonRole.NoRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            msg_box.exec()
            if msg_box.clickedButton() == new_btn: fetch_mode = 'incremental'
            elif msg_box.clickedButton() == full_btn: fetch_mode = 'full'
            else: return
        self.update_ui_state(fetching=True)
        config = {
            'uid': self.uid,
            'base_url': self.api_url_combo.currentText(),
            'page_size': self.page_size_input.value(),
            'max_pages': self.max_pages_input.value(),
            'timeout': self.timeout_input.value(),
            'delay': self.delay_input.value(),
            'headless': self.headless_checkbox.isChecked(),
            'fetch_comments': self.fetch_comments_checkbox.isChecked(),
            'fetch_danmus': self.fetch_danmus_checkbox.isChecked(),
            'fetch_live_danmus': self.fetch_live_danmus_checkbox.isChecked(),
            'fetch_mode': fetch_mode
        }
        log_message = "开始增量获取新数据..." if fetch_mode == 'incremental' else "开始全量补充数据..."
        self.append_log(log_message, "SUCCESS")
        self.append_log(f"配置: 页面大小={config['page_size']}, 最大页数={config['max_pages']}")
        self.append_log(f"API基地址: {config['base_url']}")
        cached_comment_ids = {item['rpid'] for item in self.fetched_comments if 'rpid' in item}
        cached_danmu_ids = {item['id'] for item in self.fetched_danmus if 'id' in item}
        cached_live_danmu_ids = {item['id'] for item in self.fetched_live_danmus if 'id' in item}
        self.fetch_thread = DrissionFetchThread(self.drission_client, config, cached_comment_ids, cached_danmu_ids, cached_live_danmu_ids)
        self.fetch_thread.progress_update.connect(self.on_progress_update)
        self.fetch_thread.log_update.connect(self.append_log)
        self.fetch_thread.data_update.connect(self.on_data_update)
        self.fetch_thread.finished.connect(self.on_fetch_finished)
        self.fetch_thread.error.connect(self.on_fetch_error)
        self.fetch_thread.start()

    def stop_fetch(self):
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.append_log("正在停止数据获取...", "WARNING")
            self.fetch_thread.stop()
            if not self.fetch_thread.wait(5000):
                self.append_log("⚠️ 强制停止获取线程", "WARNING")
                self.fetch_thread.terminate()
        self.update_ui_state(fetching=False)

    def update_ui_state(self, fetching=False):
        self.start_btn.setEnabled(not fetching)
        self.stop_btn.setEnabled(fetching)
        if fetching:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.status_indicator.setText("🟢 正在获取")
            self.status_indicator.setStyleSheet("color: #10b981; font-weight: bold;")
        else:
            self.progress_bar.setVisible(False)
            self.status_indicator.setText("🟡 已就绪")
            self.status_indicator.setStyleSheet("color: #f59e0b; font-weight: bold;")
            if self.fetched_comments or self.fetched_danmus or self.fetched_live_danmus:
                self.start_btn.setText("获取新数据")
            else:
                self.start_btn.setText("开始获取")

    def on_progress_update(self, message):
        self.status_label.setText(message)

    def on_data_update(self, comments_count, danmus_count, live_danmus_count):
        self.comments_count_label.setText(f"评论: {comments_count} 条")
        self.danmus_count_label.setText(f"视频弹幕: {danmus_count} 条")
        self.live_danmus_count_label.setText(f"直播弹幕: {live_danmus_count} 条")

    def on_fetch_finished(self, new_comments, new_danmus, new_live_danmus, success=True):
        self.update_ui_state(fetching=False)
        if success:
            if new_comments or new_danmus or new_live_danmus:
                self.append_log(f"获取到 {len(new_comments)} 条新评论, {len(new_danmus)} 条新视频弹幕, {len(new_live_danmus)} 条新直播弹幕", "SUCCESS")
                self.fetched_comments = new_comments + self.fetched_comments
                self.fetched_danmus = new_danmus + self.fetched_danmus
                self.fetched_live_danmus = new_live_danmus + self.fetched_live_danmus
                self.cache_manager.save_user_data(self.uid, self.fetched_comments, self.fetched_danmus, self.fetched_live_danmus)
                self.append_log("数据已更新并保存到缓存", "SUCCESS")
            else:
                self.append_log("ℹ️ 没有获取到新的数据", "INFO")
            comment_count = len(self.fetched_comments)
            danmu_count = len(self.fetched_danmus)
            live_danmu_count = len(self.fetched_live_danmus)
            self.status_label.setText(f"✅ 获取完成 - 评论: {comment_count}, 视频弹幕: {danmu_count}, 直播弹幕: {live_danmu_count}")
            self.on_data_update(comment_count, danmu_count, live_danmu_count)
            self.refresh_preview()
            if self.fetched_comments or self.fetched_danmus or self.fetched_live_danmus:
                self.import_btn.setEnabled(True)
        else:
            self.status_label.setText("获取已停止")
            self.append_log("数据获取已停止", "WARNING")

    def on_fetch_error(self, error_message):
        self.append_log(f"❌ 获取失败: {error_message}", "ERROR")
        self.status_label.setText("❌ 获取失败")
        self.update_ui_state(fetching=False)
        QMessageBox.critical(self, "获取失败", f"数据获取失败:\n{error_message}")

    def refresh_preview(self):
        try:
            comments_table = self.comments_table.findChild(QTableWidget)
            if comments_table: self.update_preview_table(comments_table, self.fetched_comments, "comment")

            danmus_table = self.danmus_table.findChild(QTableWidget)
            if danmus_table: self.update_preview_table(danmus_table, self.fetched_danmus, "danmu")

            live_danmus_table = self.live_danmus_table.findChild(QTableWidget)
            if live_danmus_table: self.update_preview_table(live_danmus_table, self.fetched_live_danmus, "live_danmu")

            self.append_log(" 预览数据已刷新")
        except Exception as e:
            self.append_log(f"❌ 刷新预览失败: {e}", "ERROR")

    def update_preview_table(self, table: QTableWidget, data: list, data_type: str):
        table.setRowCount(0)
        table.setSortingEnabled(False)
        for row, item in enumerate(data):
            table.insertRow(row)
            if data_type == 'comment':
                item_id = str(item.get('rpid', 'N/A'))
                content = item.get('message', '')
                timestamp = item.get('time', 0)
                time_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S') if timestamp else 'N/A'
                table.setItem(row, 0, QTableWidgetItem(item_id))
                table.setItem(row, 1, QTableWidgetItem(content))
                table.setItem(row, 2, QTableWidgetItem(time_str))
            elif data_type == 'danmu':
                item_id = str(item.get('id', 'N/A'))
                content = item.get('content', '')
                timestamp = item.get('ctime', 0)
                time_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S') if timestamp else 'N/A'
                table.setItem(row, 0, QTableWidgetItem(item_id))
                table.setItem(row, 1, QTableWidgetItem(content))
                table.setItem(row, 2, QTableWidgetItem(time_str))
            elif data_type == 'live_danmu':
                room_name = item.get('room_info', {}).get('roomname', 'N/A')
                content = item.get('danmu_info', {}).get('text', '')
                timestamp = item.get('danmu_info', {}).get('ts', 0)
                time_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S') if timestamp else 'N/A'
                table.setItem(row, 0, QTableWidgetItem(room_name))
                table.setItem(row, 1, QTableWidgetItem(content))
                table.setItem(row, 2, QTableWidgetItem(time_str))
        table.setSortingEnabled(True)

    def convert_to_standard_format(self, comments_data, danmus_data, live_danmus_data):
        from ..types import Comment, Danmu
        import time
        converted_comments, converted_danmus, converted_live_danmus = {}, {}, {}
        for item in comments_data:
            try:
                rpid = int(item["rpid"]); dyn_data = item.get("dyn", {})
                if dyn_data and "oid" in dyn_data and "type" in dyn_data:
                    comment = Comment(oid=int(dyn_data["oid"]), type=int(dyn_data["type"]), content=item.get("message", ""), is_selected=True, created_time=item.get("time", 0))
                    comment.source = "aicu"; comment.synced_time = int(time.time()); comment.parent = item.get("parent", None); comment.rank = item.get("rank", 1)
                    converted_comments[rpid] = comment
            except Exception as e: logger.debug(f"转换评论失败: {e}")
        for item in danmus_data:
            try:
                dmid = item["id"]; cid = item.get("oid")
                if cid:
                    danmu = Danmu(content=item.get("content", ""), cid=int(cid), is_selected=True, created_time=item.get("ctime", 0))
                    danmu.source = "aicu"; danmu.synced_time = int(time.time())
                    converted_danmus[dmid] = danmu
            except Exception as e: logger.debug(f"转换弹幕失败: {e}")
        for item in live_danmus_data:
            try:
                dmid = item["id"]; room_info = item.get("room_info", {}); danmu_info = item.get("danmu_info", {}); cid = room_info.get("roomid")
                if cid:
                    danmu = Danmu(content=danmu_info.get("text", ""), cid=int(cid), is_selected=True, created_time=danmu_info.get("ts", 0))
                    danmu.source = "aicu_live"; danmu.synced_time = int(time.time())
                    converted_live_danmus[dmid] = danmu
            except Exception as e: logger.debug(f"转换直播弹幕失败: {e}")
        return converted_comments, converted_danmus, converted_live_danmus

    def import_data(self):
        if not self.fetched_comments and not self.fetched_danmus and not self.fetched_live_danmus:
            QMessageBox.warning(self, "提示", "没有可导入的数据")
            return
        try:
            converted_comments, converted_danmus, converted_live_danmus = self.convert_to_standard_format(self.fetched_comments, self.fetched_danmus, self.fetched_live_danmus)
            self.data_imported.emit(converted_comments, converted_danmus, converted_live_danmus)
            self.append_log(f" 数据已导入到主界面 - 评论: {len(converted_comments)}, 视频弹幕: {len(converted_danmus)}, 直播弹幕: {len(converted_live_danmus)}", "SUCCESS")
            reply = QMessageBox.question(self, "导入完成", f"数据已成功导入到主界面！\n\n评论: {len(converted_comments)} 条\n视频弹幕: {len(converted_danmus)} 条\n直播弹幕: {len(converted_live_danmus)} 条\n\n是否关闭备用API窗口？", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
            if reply == QMessageBox.StandardButton.Yes: self.close()
        except Exception as e:
            self.append_log(f"❌ 导入数据失败: {e}", "ERROR")
            QMessageBox.critical(self, "导入失败", f"导入数据时发生错误:\n{e}")

    def on_live_danmu_double_click(self, row, column):
        try:
            if row < len(self.fetched_live_danmus):
                room_id = self.fetched_live_danmus[row].get('room_info', {}).get('roomid')
                if room_id:
                    import webbrowser
                    url = f"https://live.bilibili.com/{room_id}"
                    webbrowser.open(url)
                    self.append_log(f"🔗 跳转到直播间: {url}", "INFO")
        except Exception as e:
            self.append_log(f"❌ 跳转失败: {e}", "ERROR")
    def closeEvent(self, event):
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetch_thread.stop()
            if not self.fetch_thread.wait(3000): self.fetch_thread.terminate()
        if self.drission_client:
            try: self.drission_client.close()
            except Exception as e: logger.debug(f"关闭DrissionPage客户端时出错: {e}")
        self.append_log(" 备用API窗口已关闭", "INFO")
        super().closeEvent(event)


class DrissionFetchThread(QThread):
    progress_update = pyqtSignal(str)
    log_update = pyqtSignal(str, str)
    data_update = pyqtSignal(int, int, int)
    finished = pyqtSignal(list, list, list, bool)
    error = pyqtSignal(str)

    def __init__(self, drission_client, config, cached_comment_ids: set, cached_danmu_ids: set, cached_live_danmu_ids: set):
        super().__init__()
        self.drission_client = drission_client
        self.config = config
        self.cached_comment_ids = cached_comment_ids
        self.cached_danmu_ids = cached_danmu_ids
        self.cached_live_danmu_ids = cached_live_danmu_ids
        self._is_running = True
        self.fetch_mode = config.get('fetch_mode', 'full')
        self.new_comments_data = []
        self.new_danmus_data = []
        self.new_live_danmus_data = []

    def stop(self):
        self._is_running = False
        logger.info("DrissionFetchThread收到停止信号")

    def run(self):
        try:
            self.log_update.emit(" 正在初始化浏览器...", "INFO")
            self.drission_client.is_headless = self.config.get('headless', True)
            self.log_update.emit("✅ 浏览器初始化完成", "SUCCESS")
            if self.config.get('fetch_comments') and self._is_running:
                self.log_update.emit(" 开始获取新评论数据...", "INFO")
                self.fetch_data_type("getreply", "评论")
            if self.config.get('fetch_danmus') and self._is_running:
                self.log_update.emit(" 开始获取新视频弹幕数据...", "INFO")
                self.fetch_data_type("getvideodm", "视频弹幕")
            if self.config.get('fetch_live_danmus') and self._is_running:
                self.log_update.emit(" 开始获取新直播弹幕数据...", "INFO")
                self.fetch_live_danmu_data()
            if self._is_running:
                self.log_update.emit(" 所有新数据获取完成！", "SUCCESS")
                self.finished.emit(self.new_comments_data, self.new_danmus_data, self.new_live_danmus_data, True)
        except Exception as e:
            error_msg = f"数据获取过程中发生错误: {e}"
            logger.error(error_msg, exc_info=True)
            if self._is_running: self.error.emit(error_msg)

    def fetch_data_type(self, api_endpoint, data_type):
        if not self._is_running: return
        page_count, total_new_items = 0, 0
        max_pages, page_size = self.config.get('max_pages', 5), self.config.get('page_size', 20)
        existing_ids = self.cached_comment_ids if api_endpoint == "getreply" else self.cached_danmu_ids
        id_key = 'rpid' if api_endpoint == "getreply" else 'id'

        for page in range(1, max_pages + 1):
            if not self._is_running: break
            page_count += 1
            self.progress_update.emit(f"正在获取{data_type}第{page}/{max_pages}页...")
            base_url = self.config.get('base_url')
            params = {'uid': self.config['uid'], 'pn': page, 'ps': page_size, 'mode': 0}
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            url = f"{base_url}/{api_endpoint}?{query_string}"
            try:
                self.log_update.emit(f" 请求 {data_type} 第{page}页: {url}", "DEBUG")
                result = self.drission_client.fetch_api(url, self.config.get('timeout', 30))
                if not result['success']: self.log_update.emit(f"❌ {data_type}第{page}页获取失败: {result.get('error', '未知错误')}", "ERROR"); break
                try: data = json.loads(result['data'])
                except json.JSONDecodeError as e: self.log_update.emit(f"❌ {data_type}第{page}页JSON解析失败: {e}", "ERROR"); break
                if data.get('code') != 0: self.log_update.emit(f"❌ {data_type}API返回错误码 {data.get('code')}: {data.get('message', '未知错误')}", "ERROR"); break

                items = data.get('data', {}).get('replies', []) if api_endpoint == "getreply" else data.get('data', {}).get('videodmlist', [])
                if not items: self.log_update.emit(f"ℹ {data_type}第{page}页无数据，停止获取", "INFO"); break

                page_new_items, reached_old = [], False
                for item in items:
                    if item.get(id_key) in existing_ids:
                        if self.fetch_mode == 'incremental': reached_old = True; break
                        else: continue
                    page_new_items.append(item)
                if page_new_items:
                    if api_endpoint == "getreply": self.new_comments_data.extend(page_new_items)
                    else: self.new_danmus_data.extend(page_new_items)
                    total_new_items += len(page_new_items)
                    self.log_update.emit(f"✅ {data_type}第{page}页获取成功: 新增 {len(page_new_items)} 条数据", "SUCCESS")
                    self.data_update.emit(len(self.new_comments_data) + len(self.cached_comment_ids), len(self.new_danmus_data) + len(self.cached_danmu_ids), len(self.new_live_danmus_data) + len(self.cached_live_danmu_ids))
                if reached_old: self.log_update.emit(f" 遇到已缓存的{data_type}数据，停止增量获取", "INFO"); break
                if data.get('data', {}).get('cursor', {}).get('is_end', False): self.log_update.emit(f" {data_type}已到最后一页", "INFO"); break
                if self._is_running and page < max_pages:
                    base_delay = self.config.get('delay', 3)
                    actual_delay = base_delay * random.uniform(0.8, 2.9)
                    self.log_update.emit(f"⏱ 等待 {actual_delay:.1f} 秒后获取下一页...", "DEBUG")
                    for _ in range(int(actual_delay * 2)):
                        if not self._is_running: break
                        time.sleep(0.5)
            except Exception as e:
                self.log_update.emit(f"❌ {data_type}第{page}页处理失败: {e}", "ERROR"); logger.error(f"{data_type}第{page}页处理失败: {e}", exc_info=True); break
        if self._is_running: self.log_update.emit(f" {data_type}获取完成: 共找到 {total_new_items} 条新数据，处理 {page_count} 页", "SUCCESS")

    def fetch_live_danmu_data(self):
        if not self._is_running: return
        page_count, total_new_items = 0, 0
        data_type = "直播弹幕"
        max_pages, page_size = self.config.get('max_pages', 5), self.config.get('page_size', 100)

        for page in range(1, max_pages + 1):
            if not self._is_running: break
            page_count += 1
            self.progress_update.emit(f"正在获取{data_type}第{page}/{max_pages}页...")
            base_url = self.config.get('base_url')
            params = {'uid': self.config['uid'], 'pn': page, 'ps': page_size}
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            url = f"{base_url}/getlivedm?{query_string}"
            try:
                self.log_update.emit(f" 请求 {data_type} 第{page}页: {url}", "DEBUG")
                result = self.drission_client.fetch_api(url, self.config.get('timeout', 30))
                if not result['success']: self.log_update.emit(f"❌ {data_type}第{page}页获取失败: {result.get('error', '未知错误')}", "ERROR"); break
                try: data = json.loads(result['data'])
                except json.JSONDecodeError as e: self.log_update.emit(f"❌ {data_type}第{page}页JSON解析失败: {e}", "ERROR"); break
                if data.get('code') != 0: self.log_update.emit(f"❌ {data_type}API返回错误码 {data.get('code')}: {data.get('message', '未知错误')}", "ERROR"); break

                items = data.get('data', {}).get('list', [])
                if not items: self.log_update.emit(f"ℹ {data_type}第{page}页无数据，停止获取", "INFO"); break

                page_new_items, reached_old = [], False
                for room_item in items:
                    room_info = room_item.get('roominfo', {}); danmus = room_item.get('danmu', []); room_id = room_info.get('roomid')
                    if not room_id: continue
                    for danmu_item in danmus:
                        text, ts = danmu_item.get('text', ''), danmu_item.get('ts', 0)
                        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
                        synthetic_id = f"live_{room_id}_{ts}_{text_hash}"
                        if synthetic_id in self.cached_live_danmu_ids:
                            if self.fetch_mode == 'incremental': reached_old = True; break
                            else: continue
                        page_new_items.append({'id': synthetic_id, 'room_info': room_info, 'danmu_info': danmu_item})
                    if reached_old: break

                if page_new_items:
                    self.new_live_danmus_data.extend(page_new_items)
                    total_new_items += len(page_new_items)
                    self.log_update.emit(f"✅ {data_type}第{page}页获取成功: 新增 {len(page_new_items)} 条数据", "SUCCESS")
                    self.data_update.emit(len(self.new_comments_data) + len(self.cached_comment_ids), len(self.new_danmus_data) + len(self.cached_danmu_ids), len(self.new_live_danmus_data) + len(self.cached_live_danmu_ids))

                if reached_old: self.log_update.emit(f" 遇到已缓存的{data_type}数据，停止增量获取", "INFO"); break
                if data.get('data', {}).get('cursor', {}).get('is_end', False): self.log_update.emit(f" {data_type}已到最后一页", "INFO"); break
                if self._is_running and page < max_pages:
                    base_delay = self.config.get('delay', 3)
                    actual_delay = base_delay * random.uniform(0.8, 2.9)
                    self.log_update.emit(f"⏱ 等待 {actual_delay:.1f} 秒后获取下一页...", "DEBUG")
                    for _ in range(int(actual_delay * 2)):
                        if not self._is_running: break
                        time.sleep(0.5)
            except Exception as e:
                self.log_update.emit(f"❌ {data_type}第{page}页处理失败: {e}", "ERROR"); logger.error(f"{data_type}第{page}页处理失败: {e}", exc_info=True); break
        if self._is_running: self.log_update.emit(f" {data_type}获取完成: 共找到 {total_new_items} 条新数据，处理 {page_count} 页", "SUCCESS")


__all__ = ['DrissionPageWindow', 'HeadlessDrissionClient', 'DRISSION_AVAILABLE']