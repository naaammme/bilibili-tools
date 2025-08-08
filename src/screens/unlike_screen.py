import time
import random
import re
import urllib.parse
from functools import reduce
from hashlib import md5
from datetime import datetime
from typing import Dict, Tuple, Optional, List
import threading
import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QSpinBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QLineEdit, QFrame,
    QMessageBox, QHeaderView, QAbstractItemView, QSplitter,
    QGroupBox, QTabWidget, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from curl_cffi import requests


logger = logging.getLogger(__name__)


class BilibiliLikeAPI:
    """B站点赞API封装类，使用curl_cffi直接请求"""

    def __init__(self, cookie: str, csrf: str):
        self.cookie = cookie
        self.csrf = csrf

        # 线程本地存储，每个线程独立的session
        self._local = threading.local()

        # WBI签名相关
        self.mixin_key_enc_tab = [
            46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
            33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
            61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
            36, 20, 34, 44, 52
        ]
        self.img_key = None
        self.sub_key = None
        self._user_info = None  # 缓存用户信息

    @property
    def session(self):
        """获取线程本地的session"""
        if not hasattr(self._local, 'session'):
            # 为每个线程创建独立的session
            self._local.session = requests.Session(
                impersonate="chrome110",
                verify=False
            )

            # 设置请求头
            self._local.session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Referer': 'https://www.bilibili.com/',
                'Origin': 'https://www.bilibili.com',
                'Sec-Ch-Ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-site',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Connection': 'keep-alive',
                'Cookie': self.cookie
            })

        return self._local.session

    def parse_cookies(self, cookies_str: str) -> Dict[str, str]:
        """解析完整的cookie字符串"""
        cookies_dict = {}
        for cookie in cookies_str.split('; '):
            if '=' in cookie:
                key, value = cookie.split('=', 1)
                cookies_dict[key] = value
        return cookies_dict

    def set_session_cookies(self):
        """为session设置cookies"""
        cookies_dict = self.parse_cookies(self.cookie)
        self.session.cookies.clear()
        for key, value in cookies_dict.items():
            self.session.cookies.set(key, value)

    def get_mixin_key(self, orig: str) -> str:
        """对 imgKey 和 subKey 进行字符顺序打乱编码"""
        return reduce(lambda s, i: s + orig[i], self.mixin_key_enc_tab, '')[:32]

    def enc_wbi(self, params: dict, img_key: str, sub_key: str) -> dict:
        """为请求参数进行 wbi 签名"""
        mixin_key = self.get_mixin_key(img_key + sub_key)
        curr_time = round(time.time())
        params['wts'] = curr_time
        params = dict(sorted(params.items()))

        # 过滤 value 中的 "!'()*" 字符
        params = {
            k: ''.join(filter(lambda chr: chr not in "!'()*", str(v)))
            for k, v in params.items()
        }

        query = urllib.parse.urlencode(params)
        wbi_sign = md5((query + mixin_key).encode()).hexdigest()
        params['w_rid'] = wbi_sign
        return params

    def get_wbi_keys(self) -> Tuple[str, str]:
        """获取最新的 img_key 和 sub_key"""
        if self.img_key and self.sub_key:
            return self.img_key, self.sub_key

        try:
            resp = self.session.get('https://api.bilibili.com/x/web-interface/nav', timeout=30)
            resp.raise_for_status()
            data = resp.json()

            img_url = data['data']['wbi_img']['img_url']
            sub_url = data['data']['wbi_img']['sub_url']

            self.img_key = img_url.rsplit('/', 1)[1].split('.')[0]
            self.sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]

            return self.img_key, self.sub_key
        except Exception as e:
            raise Exception(f"获取WBI密钥失败: {e}")

    def get_user_info(self) -> Tuple[int, str, str]:
        """获取用户信息"""
        if self._user_info:
            return self._user_info

        try:
            resp = self.session.get('https://api.bilibili.com/x/space/myinfo', timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if data.get('code') != 0:
                raise Exception(f"获取用户信息失败: {data.get('message', 'Unknown error')}")

            user_data = data['data']
            uid = user_data.get('mid')
            username = user_data.get('name', '用户')
            face_url = user_data.get('face', '')

            self._user_info = (uid, username, face_url)
            return self._user_info
        except Exception as e:
            raise Exception(f"获取用户信息失败: {e}")

    def get_user_videos(self, uid: int, pn: int = 1, ps: int = 30) -> Dict:
        """获取用户投稿视频列表（分页）"""
        try:
            img_key, sub_key = self.get_wbi_keys()

            params = {
                'mid': uid,
                'pn': pn,
                'ps': ps,
                'index': 1
            }

            signed_params = self.enc_wbi(params, img_key, sub_key)

            resp = self.session.get(
                'https://api.bilibili.com/x/space/wbi/arc/search',
                params=signed_params,
                timeout=30
            )
            resp.raise_for_status()
            result = resp.json()

            if result['code'] != 0:
                raise Exception(f"获取视频列表失败: {result.get('message', 'Unknown error')}")

            return result['data']
        except Exception as e:
            raise Exception(f"获取用户视频失败: {e}")

    def get_user_likes(self, uid: str, pn: int = 1, ps: int = 30) -> Dict:
        """获取用户点赞视频列表（分页）"""
        try:
            url = 'https://api.bilibili.com/x/space/like/video'
            params = {
                'vmid': uid,
                'pn': pn,
                'ps': ps
            }

            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            result = resp.json()

            if result['code'] != 0:
                raise Exception(f"获取点赞列表失败: {result.get('message', 'Unknown error')}")

            return result['data']
        except Exception as e:
            raise Exception(f"获取用户点赞失败: {e}")

    def cancel_like(self, bvid: str = None, aid: str = None) -> Tuple[bool, str]:
        """取消对指定视频的点赞"""
        try:
            data = {
                'like': '2',  # 2表示取消点赞
                'csrf': self.csrf
            }

            if bvid:
                data['bvid'] = bvid
            elif aid:
                data['aid'] = aid
            else:
                return False, "缺少视频ID"

            resp = self.session.post(
                'https://api.bilibili.com/x/web-interface/archive/like',
                data=data,
                timeout=30
            )
            resp.raise_for_status()
            result = resp.json()

            if result['code'] == 0:
                return True, "成功"
            elif result['code'] == -412:
                return False, "请求被拦截，点赞接口已失效"
            elif result['code'] == 65004:
                return True, "未点赞过，跳过"
            else:
                return False, f"错误码: {result['code']}, {result.get('message', '')}"
        except Exception as e:
            return False, f"请求失败: {str(e)}"

    def random_delay(self, base_delay: float):
        """随机延迟，避免请求过快"""
        delay = base_delay * (random.random() * 0.3 + 0.75)
        time.sleep(delay)


class VideoListWidget(QTableWidget):
    """视频列表组件，支持双击跳转"""

    video_double_clicked = pyqtSignal(str, str)  # bvid, title

    def __init__(self):
        super().__init__()
        self.setObjectName("commentDataTable")  # 使用工具箱的样式
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(['标题', 'BVID', '发布时间', 'UP主'])

        # 设置表格属性
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)

        # 设置列宽
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)

        self.setColumnWidth(1, 120)
        self.setColumnWidth(2, 100)
        self.setColumnWidth(3, 80)

        # 连接信号
        self.itemDoubleClicked.connect(self.on_item_double_clicked)

    def add_video(self, video_info: dict):
        """添加视频到列表"""
        row = self.rowCount()
        self.insertRow(row)

        # 标题
        title_item = QTableWidgetItem(video_info.get('title', ''))
        title_item.setToolTip(video_info.get('title', ''))
        self.setItem(row, 0, title_item)

        # BVID
        bvid_item = QTableWidgetItem(video_info.get('bvid', ''))
        self.setItem(row, 1, bvid_item)

        # 发布时间
        pub_date = video_info.get('created', video_info.get('pubdate', 0))
        if isinstance(pub_date, int):
            time_str = datetime.fromtimestamp(pub_date).strftime('%Y-%m-%d')
        else:
            time_str = str(pub_date)
        time_item = QTableWidgetItem(time_str)
        self.setItem(row, 2, time_item)

        # UP主
        author = video_info.get('author', video_info.get('owner', {}).get('name', ''))
        author_item = QTableWidgetItem(str(author))
        self.setItem(row, 3, author_item)

    def clear_videos(self):
        """清空视频列表"""
        self.setRowCount(0)

    def on_item_double_clicked(self, item):
        """处理双击事件"""
        row = item.row()
        bvid_item = self.item(row, 1)
        title_item = self.item(row, 0)

        if bvid_item and title_item:
            bvid = bvid_item.text()
            title = title_item.text()
            self.video_double_clicked.emit(bvid, title)


class WorkerThread(QThread):
    """工作线程基类"""

    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(dict)
    video_loaded_signal = pyqtSignal(list)

    def __init__(self, api: BilibiliLikeAPI):
        super().__init__()
        self.is_running = False
        self.api = api

    def stop(self):
        self.is_running = False


class VideoLoadThread(WorkerThread):
    """视频加载线程"""

    def __init__(self, api: BilibiliLikeAPI, mode: str, uid: int, page: int, page_size: int = 30):
        super().__init__(api)
        self.mode = mode
        self.uid = uid
        self.page = page
        self.page_size = page_size

    def run(self):
        """直接运行同步方法，无需事件循环"""
        try:
            if self.mode == 'uploader':
                data = self.api.get_user_videos(self.uid, self.page, self.page_size)
                videos = data['list']['vlist']
            else:  # likes
                data = self.api.get_user_likes(str(self.uid), self.page, self.page_size)
                videos = data['list']

            self.video_loaded_signal.emit(videos)

        except Exception as e:
            self.log_signal.emit(f"加载第{self.page}页失败: {e}")


class UploaderUnlikeThread(WorkerThread):
    """UP主视频取消点赞线程"""

    def __init__(self, api: BilibiliLikeAPI, uid: int, start_page: int, total_pages: int, delay: float):
        super().__init__(api)
        self.uid = uid
        self.start_page = start_page
        self.total_pages = total_pages
        self.delay = delay

    def run(self):
        """直接运行同步方法，无需事件循环"""
        self.is_running = True
        cancel_count = 0
        error_count = 0
        skip_count = 0

        try:
            self.log_signal.emit(f"开始执行：UID={self.uid}, 起始页={self.start_page}, 总页数={self.total_pages}")

            # 获取总视频数
            first_page = self.api.get_user_videos(self.uid, 1, 30)
            total_videos = first_page['page']['count']
            max_pages = (total_videos + 30 - 1) // 30

            self.log_signal.emit(f"该UP主共有 {total_videos} 个视频，共 {max_pages} 页")

            end_page = min(self.start_page + self.total_pages - 1, max_pages)

            if self.start_page > max_pages:
                self.log_signal.emit(f"起始页 {self.start_page} 超过最大页数 {max_pages}")
                return

            total_videos_to_process = (end_page - self.start_page + 1) * 30
            processed_videos = 0

            for page in range(self.start_page, end_page + 1):
                if not self.is_running:
                    break

                self.log_signal.emit(f"处理第 {page}/{end_page} 页...")

                page_data = self.api.get_user_videos(self.uid, page, 30)
                videos = page_data['list']['vlist']

                for i, video in enumerate(videos):
                    if not self.is_running:
                        break

                    title = video['title']
                    bvid = video['bvid']

                    self.log_signal.emit(f"  [{i+1}/{len(videos)}] {title[:30]}... ({bvid})")

                    success, message = self.api.cancel_like(bvid=bvid)

                    if success:
                        if "未点赞过" in message:
                            self.log_signal.emit(f"→ 跳过")
                            skip_count += 1
                        else:
                            self.log_signal.emit(f"→ ✓ 已取消")
                            cancel_count += 1
                    else:
                        self.log_signal.emit(f"→ ✗ {message}")
                        error_count += 1

                        if "请求被拦截" in message:
                            self.log_signal.emit("接口已失效，请稍后再试")
                            break

                    processed_videos += 1
                    progress = (processed_videos / total_videos_to_process) * 100
                    self.progress_signal.emit(int(progress))

                    # 随机延迟
                    self.api.random_delay(self.delay)

        except Exception as e:
            self.log_signal.emit(f"执行中断: {e}")

        result = {
            'success': error_count == 0,
            'cancel_count': cancel_count,
            'skip_count': skip_count,
            'error_count': error_count
        }

        self.finished_signal.emit(result)


class PersonalUnlikeThread(WorkerThread):
    """个人点赞取消线程"""

    def __init__(self, api: BilibiliLikeAPI, batch_size: int, batch_delay: int, min_delay: int, max_delay: int):
        super().__init__(api)
        self.batch_size = batch_size
        self.batch_delay = batch_delay
        self.min_delay = min_delay
        self.max_delay = max_delay

    def run(self):
        """直接运行同步方法，无需事件循环"""
        self.is_running = True
        cancel_count = 0
        error_count = 0

        try:
            uid, username, _ = self.api.get_user_info()
            self.log_signal.emit(f"开始获取 {username} 的点赞列表...")

            # 分页获取所有点赞视频
            all_videos = []
            page = 1

            while True:
                if not self.is_running:
                    break

                try:
                    like_data = self.api.get_user_likes(str(uid), page, 30)
                    videos = like_data['list']

                    if not videos:
                        break

                    all_videos.extend(videos)
                    self.log_signal.emit(f"已获取第{page}页，累计{len(all_videos)}个视频")
                    page += 1

                    if len(videos) < 30:
                        break

                except Exception as e:
                    self.log_signal.emit(f"获取第{page}页失败: {e}")
                    break

            self.log_signal.emit(f"总共获取到 {len(all_videos)} 个点赞视频")

            for i, video in enumerate(all_videos):
                if not self.is_running:
                    break

                title = video['title']
                aid = video['aid']

                self.log_signal.emit(f"[{i+1}/{len(all_videos)}] {title[:30]}...")

                success, message = self.api.cancel_like(aid=str(aid))

                if success:
                    self.log_signal.emit(f"→ ✓ 已取消")
                    cancel_count += 1
                else:
                    self.log_signal.emit(f"→ ✗ {message}")
                    error_count += 1

                progress = ((i + 1) / len(all_videos)) * 100
                self.progress_signal.emit(int(progress))

                # 批次控制
                if (i + 1) % self.batch_size == 0 and i < len(all_videos) - 1:
                    self.log_signal.emit(f"批次完成，等待 {self.batch_delay} 秒...")
                    for j in range(self.batch_delay):
                        if not self.is_running:
                            break
                        time.sleep(1)
                else:
                    # 随机延时
                    delay = random.uniform(self.min_delay, self.max_delay)
                    time.sleep(delay)

        except Exception as e:
            self.log_signal.emit(f"执行中断: {e}")

        result = {
            'success': error_count == 0,
            'cancel_count': cancel_count,
            'error_count': error_count
        }

        self.finished_signal.emit(result)


class UnlikeScreen(QWidget):
    """B站批量取消点赞工具屏幕"""

    back_to_tools = pyqtSignal()
    window_closed = pyqtSignal()

    def __init__(self, api_service):
        super().__init__()
        self.api_service = api_service

        # 调试：检查api_service的属性
        print(f"=== API Service 调试信息 ===")
        print(f"api_service类型: {type(api_service)}")
        print(f"api_service属性: {dir(api_service)}")

        cookie = None
        csrf = None

        try:
            cookie = getattr(api_service, 'cookie', '')
            csrf = getattr(api_service, 'csrf', '')
            print(f"方法1 - cookie长度: {len(cookie) if cookie else 0}, csrf长度: {len(csrf) if csrf else 0}")
        except Exception as e:
            print(f"方法1失败: {e}")

        # 创建API实例
        try:
            if not cookie or not csrf:
                raise Exception(f"无法获取登录信息 - cookie: {bool(cookie)}, csrf: {bool(csrf)}")

            self.api = BilibiliLikeAPI(cookie, csrf)
            print(f"✅ API初始化成功，Cookie长度: {len(cookie)}")

            # 测试API是否真的可用
            try:
                user_info = self.api.get_user_info()
                print(f"✅ API测试成功，用户信息: {user_info}")
            except Exception as test_e:
                print(f"⚠️ API测试失败: {test_e}")

        except Exception as e:
            self.api = None
            print(f"❌ API初始化失败: {e}")
            import traceback
            traceback.print_exc()

        self.uploader_data = {'page': 0, 'uid': None, 'has_more': True, 'videos': []}
        self.personal_data = {'page': 0, 'has_more': True, 'videos': []}
        self.worker_thread = None
        self.load_thread = None
        self.setup_ui()

    def setup_ui(self):
        self.setObjectName("mainPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(10)

        # 顶部标题栏
        header_widget = QWidget()
        header_widget.setMaximumHeight(60)
        header_layout = QHBoxLayout(header_widget)

        # 返回按钮 - 最左对齐
        back_btn = QPushButton("← 返回工具选择")
        back_btn.setObjectName("secondaryButton")
        back_btn.clicked.connect(self.back_to_tools.emit)
        header_layout.addWidget(back_btn)

        # 标题
        title_label = QLabel("批量取消点赞工具")
        title_label.setObjectName("statsCardTitle")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        layout.addWidget(header_widget)

        # 搜索区域（仅在UP主模式显示）
        self.search_widget = QWidget()
        self.search_widget.setMaximumHeight(60)
        search_layout = QHBoxLayout(self.search_widget)
        search_layout.setContentsMargins(0, 5, 0, 5)
        search_layout.setSpacing(8)
        search_layout.addWidget(QLabel("搜索:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入UP主UID或空间URL")
        search_layout.addWidget(self.search_input)

        self.search_btn = QPushButton("搜索")
        self.search_btn.setObjectName("primaryButton")
        self.search_btn.clicked.connect(self.search_videos)
        search_layout.addWidget(self.search_btn)

        layout.addWidget(self.search_widget)

        # 主内容区域
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：标签页区域
        # 创建标签页
        self.tab_widget = QTabWidget()

        # UP主视频取消点赞标签页
        self.uploader_widget = self.create_uploader_tab()
        self.tab_widget.addTab(self.uploader_widget, "UP主视频取消点赞")

        # 个人点赞管理标签页
        self.personal_widget = self.create_personal_tab()
        self.tab_widget.addTab(self.personal_widget, "个人点赞管理")

        # 连接标签切换信号
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        # 右侧：操作日志
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_layout.addWidget(QLabel("操作日志"))

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumWidth(350)
        right_layout.addWidget(self.log_text)

        # 添加到分割器
        splitter.addWidget(self.tab_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([1000, 350])

        layout.addWidget(splitter)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 底部控制按钮区域
        bottom_layout = QHBoxLayout()

        # 加载更多按钮
        self.load_more_btn = QPushButton("开始获取")
        self.load_more_btn.setObjectName("secondaryButton")
        self.load_more_btn.clicked.connect(self.load_more_videos)
        self.load_more_btn.setEnabled(False)
        bottom_layout.addWidget(self.load_more_btn)

        # 刷新列表按钮
        self.refresh_btn = QPushButton("刷新列表")
        self.refresh_btn.setObjectName("primaryButton")
        self.refresh_btn.clicked.connect(self.refresh_current_tab)
        bottom_layout.addWidget(self.refresh_btn)

        bottom_layout.addStretch()

        # 开始取消点赞按钮
        self.start_btn = QPushButton("开始取消点赞")
        self.start_btn.setObjectName("dangerButton")
        self.start_btn.clicked.connect(self.start_unlike)
        self.start_btn.setEnabled(False)
        bottom_layout.addWidget(self.start_btn)

        # 停止按钮
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("secondaryButton")
        self.stop_btn.clicked.connect(self.stop_unlike)
        self.stop_btn.setEnabled(False)
        bottom_layout.addWidget(self.stop_btn)

        layout.addLayout(bottom_layout)

        # 检查API初始化状态
        if not self.api:
            self.log("⚠️ API初始化失败，请检查登录状态")
            self.start_btn.setEnabled(False)
        else:
            self.log("✅ API初始化成功，可以开始使用")

    def create_uploader_tab(self):
        """创建UP主视频取消点赞标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(5)

        # 参数设置区域 - 更紧凑的布局
        params_widget = QWidget()
        params_widget.setMaximumHeight(50)
        params_layout = QHBoxLayout(params_widget)
        params_layout.setContentsMargins(0, 5, 0, 5)
        params_layout.setSpacing(8)

        params_layout.addWidget(QLabel("参数设置:"))

        params_layout.addWidget(QLabel("起始页:"))
        self.start_page_spin = QSpinBox()
        self.start_page_spin.setMinimum(1)
        self.start_page_spin.setMaximum(9999)
        self.start_page_spin.setValue(1)
        self.start_page_spin.setMaximumWidth(80)
        params_layout.addWidget(self.start_page_spin)

        params_layout.addWidget(QLabel("执行页数:"))
        self.total_pages_spin = QSpinBox()
        self.total_pages_spin.setMinimum(1)
        self.total_pages_spin.setMaximum(100)
        self.total_pages_spin.setValue(2)
        self.total_pages_spin.setMaximumWidth(80)
        params_layout.addWidget(self.total_pages_spin)

        params_layout.addWidget(QLabel("请求延迟:"))
        self.delay_spin = QSpinBox()
        self.delay_spin.setMinimum(500)
        self.delay_spin.setMaximum(5000)
        self.delay_spin.setValue(800)
        self.delay_spin.setSuffix(" ms")
        self.delay_spin.setMaximumWidth(100)
        params_layout.addWidget(self.delay_spin)

        params_layout.addStretch()
        layout.addWidget(params_widget)

        # 视频列表
        self.uploader_video_list = VideoListWidget()
        self.uploader_video_list.video_double_clicked.connect(self.open_video)
        layout.addWidget(self.uploader_video_list)

        return widget

    def create_personal_tab(self):
        """创建个人点赞管理标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 参数设置区域
        params_widget = QWidget()
        params_widget.setMaximumHeight(60)
        params_layout = QHBoxLayout(params_widget)
        params_layout.setContentsMargins(0, 5, 0, 5)
        params_layout.setSpacing(6)

        params_layout.addWidget(QLabel("参数设置:"))

        params_layout.addWidget(QLabel("每批次:"))
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setMinimum(1)
        self.batch_size_spin.setMaximum(20)
        self.batch_size_spin.setValue(20)
        self.batch_size_spin.setMaximumWidth(80)
        params_layout.addWidget(self.batch_size_spin)

        params_layout.addWidget(QLabel("批次间隔:"))
        self.batch_delay_spin = QSpinBox()
        self.batch_delay_spin.setMinimum(5)
        self.batch_delay_spin.setMaximum(300)
        self.batch_delay_spin.setValue(5)
        self.batch_delay_spin.setSuffix(" s")
        self.batch_delay_spin.setMaximumWidth(80)
        params_layout.addWidget(self.batch_delay_spin)

        params_layout.addWidget(QLabel("延时范围:"))
        self.min_delay_spin = QSpinBox()
        self.min_delay_spin.setMinimum(1)
        self.min_delay_spin.setMaximum(30)
        self.min_delay_spin.setValue(1)
        self.min_delay_spin.setSuffix(" s")
        self.min_delay_spin.setMaximumWidth(70)
        params_layout.addWidget(self.min_delay_spin)

        params_layout.addWidget(QLabel("-"))
        self.max_delay_spin = QSpinBox()
        self.max_delay_spin.setMinimum(1)
        self.max_delay_spin.setMaximum(60)
        self.max_delay_spin.setValue(3)
        self.max_delay_spin.setSuffix(" s")
        self.max_delay_spin.setMaximumWidth(70)
        params_layout.addWidget(self.max_delay_spin)

        params_layout.addStretch()
        layout.addWidget(params_widget)

        # 视频列表
        self.personal_video_list = VideoListWidget()
        self.personal_video_list.video_double_clicked.connect(self.open_video)
        layout.addWidget(self.personal_video_list)

        return widget

    def on_tab_changed(self, index):
        """处理标签页切换"""
        if index == 0:  # UP主模式
            self.search_widget.setVisible(True)
            # 重新加载UP主数据
            if self.uploader_data['videos']:
                self.uploader_video_list.clear_videos()
                for video in self.uploader_data['videos']:
                    self.uploader_video_list.add_video(video)
                self.load_more_btn.setEnabled(self.uploader_data['uid'] is not None and self.uploader_data['has_more'])
                self.start_btn.setEnabled(self.uploader_video_list.rowCount() > 0 and self.api is not None)
            else:
                self.load_more_btn.setEnabled(False)
                self.start_btn.setEnabled(False)
        else:  # 个人模式
            self.search_widget.setVisible(False)
            # 重新加载个人数据
            if self.personal_data['videos']:
                self.personal_video_list.clear_videos()
                for video in self.personal_data['videos']:
                    self.personal_video_list.add_video(video)
                self.load_more_btn.setEnabled(self.personal_data['has_more'])
                self.start_btn.setEnabled(self.personal_video_list.rowCount() > 0 and self.api is not None)
            else:
                self.load_more_btn.setEnabled(True if self.api else False)
                self.start_btn.setEnabled(False)

    def get_current_video_list(self):
        if self.tab_widget.currentIndex() == 0:
            return self.uploader_video_list
        else:
            return self.personal_video_list

    def search_videos(self):
        """搜索UP主视频"""
        if not self.api:
            QMessageBox.warning(self, "警告", "API未初始化，请重新登录")
            return

        uid_input = self.search_input.text().strip()
        if not uid_input:
            QMessageBox.warning(self, "警告", "请输入UP主UID")
            return

        # 解析UID
        uid_match = re.search(r'/(\d+)(?:[#/?]|$)', uid_input)
        if uid_match:
            uid = int(uid_match.group(1))
        elif uid_input.isdigit():
            uid = int(uid_input)
        else:
            QMessageBox.critical(self, "错误", "UID格式不正确")
            return

        # 重置UP主数据
        self.uploader_data = {'page': 0, 'uid': uid, 'has_more': True, 'videos': []}
        self.uploader_video_list.clear_videos()
        self.load_more_videos()

    def refresh_current_tab(self):
        """刷新当前标签页"""
        if not self.api:
            QMessageBox.warning(self, "警告", "API未初始化，请重新登录")
            return

        if self.tab_widget.currentIndex() == 0:  # UP主模式
            if self.uploader_data['uid']:
                self.uploader_data = {'page': 0, 'uid': self.uploader_data['uid'], 'has_more': True, 'videos': []}
                self.uploader_video_list.clear_videos()
                self.load_more_videos()
            else:
                QMessageBox.warning(self, "提示", "请先搜索UP主")
        else:  # 个人模式
            self.personal_data = {'page': 0, 'has_more': True, 'videos': []}
            self.personal_video_list.clear_videos()
            self.load_more_videos()

    def load_more_videos(self):
        """加载更多视频"""
        if not self.api:
            self.log("API未初始化，无法加载视频")
            return

        if self.tab_widget.currentIndex() == 0:  # UP主模式
            if not self.uploader_data['uid'] or not self.uploader_data['has_more']:
                return

            self.uploader_data['page'] += 1
            self.log(f"正在加载UP主视频第{self.uploader_data['page']}页...")

            self.load_more_btn.setEnabled(False)
            self.load_thread = VideoLoadThread(self.api, 'uploader', self.uploader_data['uid'], self.uploader_data['page'])
            self.load_thread.video_loaded_signal.connect(self.on_uploader_videos_loaded)
            self.load_thread.log_signal.connect(self.log)
            self.load_thread.finished.connect(lambda: self.load_more_btn.setEnabled(self.uploader_data['has_more']))
            self.load_thread.start()

        else:  # 个人模式
            if not self.personal_data['has_more']:
                return

            self.personal_data['page'] += 1
            self.log(f"正在加载个人点赞第{self.personal_data['page']}页...")

            self.load_more_btn.setEnabled(False)

            # 获取当前用户UID（同步方式）
            try:
                uid, _, _ = self.api.get_user_info()
                if uid:
                    self.load_thread = VideoLoadThread(self.api, 'likes', uid, self.personal_data['page'])
                    self.load_thread.video_loaded_signal.connect(self.on_personal_videos_loaded)
                    self.load_thread.log_signal.connect(self.log)
                    self.load_thread.finished.connect(lambda: self.load_more_btn.setEnabled(self.personal_data['has_more']))
                    self.load_thread.start()
                else:
                    self.log("获取用户信息失败")
                    self.load_more_btn.setEnabled(True)
            except Exception as e:
                self.log(f"加载失败: {e}")
                self.load_more_btn.setEnabled(True)

    def on_uploader_videos_loaded(self, videos: list):
        """处理UP主视频加载结果"""
        if videos:
            self.uploader_data['videos'].extend(videos)
            for video in videos:
                self.uploader_video_list.add_video(video)

            self.log(f"第{self.uploader_data['page']}页加载完成，获取到 {len(videos)} 个视频")
            self.uploader_data['has_more'] = len(videos) == 30
            self.start_btn.setEnabled(self.api is not None)
        else:
            self.log("没有更多视频了")
            self.uploader_data['has_more'] = False

        self.load_more_btn.setEnabled(
            self.uploader_data['uid'] is not None and
            self.uploader_data['has_more']
        )

    def on_personal_videos_loaded(self, videos: list):
        """处理个人点赞加载结果"""
        if videos:
            self.personal_data['videos'].extend(videos)
            for video in videos:
                self.personal_video_list.add_video(video)

            self.log(f"第{self.personal_data['page']}页加载完成，获取到 {len(videos)} 个视频")
            self.personal_data['has_more'] = len(videos) == 30
            self.start_btn.setEnabled(self.api is not None)
        else:
            self.log("没有更多点赞了")
            self.personal_data['has_more'] = False

        self.load_more_btn.setEnabled(self.personal_data['has_more'])

    def start_unlike(self):
        """开始取消点赞"""
        if not self.api:
            QMessageBox.warning(self, "警告", "API未初始化，请重新登录")
            return

        current_list = self.get_current_video_list()
        if current_list.rowCount() == 0:
            QMessageBox.warning(self, "警告", "请先加载视频列表")
            return

        # 确认对话框
        if self.tab_widget.currentIndex() == 0:
            message = f"即将取消对 UID {self.uploader_data['uid']} 的所有点赞\n\n此操作不可撤销！是否继续？"
        else:
            message = f"即将取消所有个人点赞视频\n\n此操作不可撤销！是否继续？"

        reply = QMessageBox.question(
            self, "确认操作", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # 清空日志
        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        # 启动工作线程
        if self.tab_widget.currentIndex() == 0:  # UP主模式
            start_page = self.start_page_spin.value()
            total_pages = self.total_pages_spin.value()
            delay = self.delay_spin.value() / 1000.0

            self.worker_thread = UploaderUnlikeThread(self.api, self.uploader_data['uid'], start_page, total_pages, delay)
        else:  # 个人模式
            batch_size = self.batch_size_spin.value()
            batch_delay = self.batch_delay_spin.value()
            min_delay = self.min_delay_spin.value()
            max_delay = self.max_delay_spin.value()

            self.worker_thread = PersonalUnlikeThread(self.api, batch_size, batch_delay, min_delay, max_delay)

        self.worker_thread.log_signal.connect(self.log)
        self.worker_thread.progress_signal.connect(self.progress_bar.setValue)
        self.worker_thread.finished_signal.connect(self.on_finished)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.worker_thread.start()

    def stop_unlike(self):
        """停止取消点赞"""
        if self.worker_thread:
            self.worker_thread.stop()
            self.log("正在停止...")

            # 等待线程结束后隐藏进度条
            if not self.worker_thread.isRunning():
                self.progress_bar.setVisible(False)

    def on_finished(self, result: dict):
        """处理完成"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        if self.tab_widget.currentIndex() == 0:  # UP主模式
            message = f"执行完成！\n\n成功取消点赞: {result['cancel_count']} 个\n"
            message += f"跳过(未点赞): {result['skip_count']} 个\n"
            message += f"失败: {result['error_count']} 个"
        else:  # 个人模式
            message = f"执行完成！\n\n成功取消点赞: {result['cancel_count']} 个\n"
            message += f"失败: {result['error_count']} 个"

        if result['success']:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "完成", message + "\n\n建议等待1小时后再试")

    def open_video(self, bvid: str, title: str):
        """打开视频页面"""
        url = f"https://www.bilibili.com/video/{bvid}"
        QDesktopServices.openUrl(QUrl(url))

    def log(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.append(f"[{timestamp}] {message}")

    def closeEvent(self, event):
        """窗口关闭事件"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.worker_thread.wait(1000)

        if self.load_thread and self.load_thread.isRunning():
            self.load_thread.stop()
            self.load_thread.wait(1000)

        self.progress_bar.setVisible(False)
        self.window_closed.emit()
        super().closeEvent(event)