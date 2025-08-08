import json
import logging
import os
import glob
import re
import webbrowser
import time
import random
from datetime import datetime
from typing import Optional, Dict, Any

from curl_cffi import requests
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QFileDialog, QMessageBox, QHeaderView, QFrame,
    QCheckBox, QLineEdit, QDialog, QScrollArea, QGridLayout, QGroupBox, QRadioButton, QSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QSettings
from PyQt6.QtGui import QFont
from ..types import RecordedComment, RecordedDanmu, ImportedData
from ..api.comment import DeleteCommentError
logger = logging.getLogger(__name__)


class LogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.is_valid = True

    def emit(self, record):
        if not self.is_valid or not self.text_widget:
            return

        try:
            msg = self.format(record)
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.text_widget.append(f"[{timestamp}] {msg}")
        except:
            # 如果文本框已被删除，标记为无效
            self.is_valid = False

    def cleanup(self):
        """清理处理器"""
        self.is_valid = False
        self.text_widget = None


class DataImportThread(QThread):
    data_imported = pyqtSignal(object)  # ImportedData
    error_occurred = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            self.log_message.emit(f"开始读取文件: {os.path.basename(self.file_path)}")

            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 解析评论数据
            comments = []
            for comment_data in data.get('comments', []):
                # 保存原始数据供详情窗口使用
                comment = RecordedComment(
                    text=comment_data.get('text', ''),
                    time=comment_data.get('time', ''),
                    timestamp=comment_data.get('timestamp', 0),
                    rpid=comment_data.get('rpid'),
                    status=comment_data.get('status', ''),
                    images=comment_data.get('images', []),
                    video_info=comment_data.get('videoInfo'),
                    video_time=comment_data.get('videoTime', 0),
                    page_type=comment_data.get('pageType', ''),
                    url=comment_data.get('url', '')
                )
                # 保存原始数据
                comment._raw_data = comment_data
                comments.append(comment)

            # 解析弹幕数据
            danmaku = []
            for danmu_data in data.get('danmaku', []):
                danmu = RecordedDanmu(
                    text=danmu_data.get('text', ''),
                    time=danmu_data.get('time', ''),
                    timestamp=danmu_data.get('timestamp', 0),
                    method=danmu_data.get('method', ''),
                    video_info=danmu_data.get('videoInfo'),
                    video_time=danmu_data.get('videoTime', 0),
                    page_type=danmu_data.get('pageType', '')
                )
                # 保存原始数据
                danmu._raw_data = danmu_data
                danmaku.append(danmu)

            imported_data = ImportedData(
                export_time=data.get('exportTime', ''),
                comments=comments,
                danmaku=danmaku,
                summary=data.get('summary')
            )

            self.log_message.emit(f"导入完成: {len(comments)}条评论, {len(danmaku)}条弹幕")
            self.data_imported.emit(imported_data)

        except Exception as e:
            self.error_occurred.emit(f"导入失败: {str(e)}")



class DetailDialog(QDialog):
    """详情对话框"""
    def __init__(self, data: Dict[str, Any], data_type: str, parent=None):
        super().__init__(parent)
        self.data = data
        self.data_type = data_type
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(f"{'评论' if self.data_type == 'comment' else '弹幕'}详情")
        self.resize(600, 500)

        layout = QVBoxLayout(self)

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QGridLayout(scroll_widget)

        # 显示所有有效数据
        row = 0
        for key, value in self.data.items():
            if value is not None and value != "":
                # 标签
                label = QLabel(f"{key}:")
                label.setStyleSheet("font-weight: bold; color: #0ea5e9;")
                scroll_layout.addWidget(label, row, 0, Qt.AlignmentFlag.AlignTop)

                # 值
                if isinstance(value, (list, dict)):
                    value_text = json.dumps(value, ensure_ascii=False, indent=2)
                else:
                    value_text = str(value)

                value_label = QLabel(value_text)
                value_label.setWordWrap(True)
                value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                scroll_layout.addWidget(value_label, row, 1)

                row += 1

        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        # 按钮区域
        button_layout = QHBoxLayout()
        # 跳转原视频按钮
        video_url = self.data.get('url') or (self.data.get('videoInfo', {}).get('url'))
        if video_url:
            jump_video_btn = QPushButton("跳转原视频")
            jump_video_btn.setObjectName("primaryButton")
            jump_video_btn.clicked.connect(self.jump_to_video)
            button_layout.addWidget(jump_video_btn)

        # 跳转原评论按钮（仅评论有）
        if self.data_type == 'comment' and self.data.get('rpid') and self.data.get('oid'):
            jump_comment_btn = QPushButton("跳转原评论")
            jump_comment_btn.setObjectName("primaryButton")
            jump_comment_btn.clicked.connect(self.jump_to_comment)
            button_layout.addWidget(jump_comment_btn)

        button_layout.addStretch()

        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setObjectName("secondaryButton")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def jump_to_video(self):
        """跳转到原视频"""
        url = self.data.get('url') or (self.data.get('videoInfo', {}).get('url'))
        if url:
            webbrowser.open(url)

    def jump_to_comment(self):
        """跳转到原评论"""
        oid = self.data.get('oid')
        rpid = self.data.get('rpid')

        if oid and rpid:
            # 构建评论链接
            comment_url = f"https://www.bilibili.com/video/av{oid}/?vd_source=84720652665df200f207840449fc86f5#reply{rpid}"
            webbrowser.open(comment_url)

class CommentFinderWorker(QThread):

    log_signal = pyqtSignal(str, str)  # message, level
    comment_found = pyqtSignal(dict)
    progress_signal = pyqtSignal(int, int)  # current, total
    finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.cookie = ""
        self.csrf = ""
        self.searching = True
        self.skip_current = False
        self.task_type = ""
        self.params = {}

        # 创建 session，使用 Chrome 浏览器指纹
        self.session = requests.Session(impersonate="chrome110")

        # 基础请求头,有空再更新`
        self.base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://www.bilibili.com',
            'Referer': 'https://www.bilibili.com',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'sec-ch-ua': '"Chromium";v="110", "Not A(Brand";v="24", "Google Chrome";v="110"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }

    def setup(self, cookie: str, csrf: str, task_type: str, params: dict):
        """设置任务参数"""
        self.cookie = cookie
        self.csrf = csrf
        self.task_type = task_type
        self.params = params
        # 更新 Cookie
        self.session.headers.update({
            'Cookie': self.cookie
        })

    def skip_video(self):
        self.skip_current = True
        self.log_signal.emit("正在跳过当前视频...", "INFO")

    def stop(self):
        """停止搜索"""
        self.searching = False

    def run(self):
        """执行任务"""
        try:
            if self.task_type == "history":
                self.search_from_history()
            elif self.task_type == "video":
                self.search_from_video()
        finally:
            # 关闭 session
            self.session.close()
            self.finished_signal.emit()

    def search_from_history(self):
        """从历史记录查找评论"""
        username = self.params.get('username', '')
        history_count = self.params.get('history_count', 10)
        pages_per_video = self.params.get('pages_per_video', 1)
        smart_search = self.params.get('smart_search', True)
        search_replies = self.params.get('search_replies', False)
        min_watch_time = self.params.get('min_watch_time', 5)

        if not username:
            self.log_signal.emit("请输入用户名", "ERROR")
            return

        self.log_signal.emit("开始获取历史记录...", "INFO")
        history = self.get_history(history_count)

        if not history:
            self.log_signal.emit("未能获取历史记录", "ERROR")
            return

        self.log_signal.emit(f"获取到 {len(history)} 条历史记录", "INFO")

        for i, video in enumerate(history):
            if not self.searching:
                break

            self.progress_signal.emit(i + 1, len(history))

            progress = video.get('progress', 0)
            if progress == 0:
                self.log_signal.emit(f"跳过视频 {video['title']} (秒退)", "INFO")
                continue
            elif progress > 0 and progress < min_watch_time:
                self.log_signal.emit(
                    f"跳过视频 {video['title']} (观看时长 {progress} 秒，小于 {min_watch_time} 秒)",
                    "INFO"
                )
                continue

            self.log_signal.emit(f"[{i + 1}/{len(history)}] 检查视频: {video['title']}", "INFO")

            if smart_search:
                search_pages = self.calculate_search_depth(video, pages_per_video)
            else:
                search_pages = pages_per_video

            if progress == -1:
                self.log_signal.emit(f"视频已看完，查找深度: {search_pages} 页", "INFO")
            else:
                duration = video.get('duration', 0)
                if duration > 0:
                    percentage = (progress / duration) * 100
                    self.log_signal.emit(
                        f"观看进度: {percentage:.1f}% ({progress}秒/{duration}秒)，查找深度: {search_pages} 页",
                        "INFO"
                    )
                else:
                    self.log_signal.emit(f"观看时长: {progress} 秒，查找深度: {search_pages} 页", "INFO")

            comments = self.get_video_comments(
                video['aid'], video['bvid'], video['title'],
                username, search_pages, search_replies
            )

            for comment in comments:
                # 转换为record系统的格式
                record_comment = {
                    'text': comment['comment'],
                    'time': comment['comment_time'],
                    'timestamp': int(time.time()),
                    'rpid': comment.get('rpid'),
                    'status': '已获取ID' if comment.get('rpid') else '未获取',
                    'images': [],
                    'video_info': {'title': comment['video_title'], 'url': comment['video_url']},
                    'video_time': 0,
                    'page_type': '评论查找',
                    'url': comment['video_url'],
                    'source': 'comment_finder',
                    'oid': comment.get('oid'),
                    'type': comment.get('type', 1)
                }
                self.comment_found.emit(record_comment)

            if comments:
                self.log_signal.emit(f"本视频找到 {len(comments)} 条评论", "INFO")

            time.sleep(random.uniform(2, 4))

        self.log_signal.emit("历史记录查找完成", "INFO")

    def search_from_video(self):
        """从指定视频查找评论"""
        video_text = self.params.get('video_url', '')
        target_user = self.params.get('target_user', '')
        pages = self.params.get('pages', 5)
        search_replies = self.params.get('search_replies', False)

        if not video_text or not target_user:
            self.log_signal.emit("请输入视频链接和查找的用户名", "ERROR")
            return

        # 提取BV号
        bvid = self.extract_bvid(video_text)
        if not bvid:
            self.log_signal.emit("无法识别视频链接或BV号", "ERROR")
            return

        self.log_signal.emit(f"识别到BV号: {bvid}", "INFO")

        # 获取视频信息
        video_info = self.get_video_info(bvid)
        if not video_info:
            self.log_signal.emit("无法获取视频信息", "ERROR")
            return

        self.log_signal.emit(f"视频标题: {video_info['title']}", "INFO")
        self.log_signal.emit(f"开始查找用户 {target_user} 的评论...", "INFO")
        self.log_signal.emit(f"查找深度: {pages} 页", "INFO")

        # 查找评论
        comments = self.get_video_comments(
            video_info['aid'], bvid, video_info['title'],
            target_user, pages, search_replies
        )

        for comment in comments:
            # 转换为record系统的格式
            record_comment = {
                'text': comment['comment'],
                'time': comment['comment_time'],
                'timestamp': int(time.time()),
                'rpid': comment.get('rpid'),
                'status': '已获取ID' if comment.get('rpid') else '未获取',
                'images': [],
                'video_info': {'title': comment['video_title'], 'url': comment['video_url']},
                'video_time': 0,
                'page_type': '评论查找',
                'url': comment['video_url'],
                'source': 'comment_finder',
                'oid': comment.get('oid'),
            }
            self.comment_found.emit(record_comment)

        self.log_signal.emit(f"视频查找完成，找到 {len(comments)} 条评论", "INFO")

    def get_history(self, count: int):
        """获取历史记录 - 使用 curl_cffi"""
        url = "https://api.bilibili.com/x/web-interface/history/cursor"
        history_list = []
        view_at = 0

        while len(history_list) < count:
            params = {
                'max': view_at,
                'view_at': view_at,
                'business': ''
            }

            try:
                # 使用 curl_cffi 的 session 发送请求
                headers = self.base_headers.copy()
                headers['Cookie'] = self.cookie

                response = self.session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=10,
                    proxies=None
                )

                data = response.json()

                if data['code'] != 0:
                    self.log_signal.emit(f"获取历史记录失败: {data.get('message', '未知错误')}", "ERROR")
                    break

                items = data['data']['list']
                if not items:
                    break

                for item in items:
                    if item['history']['business'] == 'archive':
                        video_info = {
                            'aid': item['history']['oid'],
                            'bvid': item['history']['bvid'],
                            'title': item['title'],
                            'view_at': item['view_at'],
                            'duration': item.get('duration', 0),
                            'progress': item.get('progress', -1)
                        }
                        history_list.append(video_info)

                        if len(history_list) >= count:
                            break

                view_at = items[-1]['view_at']

                # 随机延迟，模拟人类行为
                time.sleep(random.uniform(1.0, 2.5))

            except Exception as e:
                self.log_signal.emit(f"请求历史记录出错: {str(e)}", "ERROR")
                break

        return history_list

    def extract_bvid(self, text: str):
        """从文本中提取BV号"""
        bv_pattern = r'BV[a-zA-Z0-9]{10}'
        match = re.search(bv_pattern, text)
        if match:
            return match.group(0)

        url_pattern = r'bilibili\.com/video/(BV[a-zA-Z0-9]{10})'
        match = re.search(url_pattern, text)
        if match:
            return match.group(1)

        return None

    def get_video_info(self, bvid: str):
        """获取视频信息 - 使用 curl_cffi"""
        url = "https://api.bilibili.com/x/web-interface/view"
        params = {'bvid': bvid}

        try:
            headers = self.base_headers.copy()
            headers['Cookie'] = self.cookie

            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=10
            )

            data = response.json()

            if data['code'] == 0:
                return {
                    'aid': data['data']['aid'],
                    'bvid': bvid,
                    'title': data['data']['title']
                }
        except Exception as e:
            self.log_signal.emit(f"获取视频信息出错: {str(e)}", "ERROR")

        return None

    def calculate_search_depth(self, video_info: dict, base_pages: int) -> int:
        """根据视频信息计算查找深度"""
        progress = video_info.get('progress', 0)
        duration = video_info.get('duration', 0)

        if progress == -1:
            return min(base_pages + 5, 20)
        elif progress > 0:
            if duration > 0:
                watch_percentage = (progress / duration) * 100
                if watch_percentage >= 80:
                    return min(base_pages + 4, 20)
                elif watch_percentage >= 60:
                    return min(base_pages + 3, 20)
                elif watch_percentage >= 40:
                    return min(base_pages + 2, 20)
                elif watch_percentage >= 20:
                    return min(base_pages + 1, 20)
            else:
                if progress > 300:
                    return min(base_pages + 3, 20)
                elif progress > 180:
                    return min(base_pages + 2, 20)
                elif progress > 60:
                    return min(base_pages + 1, 20)

        return base_pages

    def get_video_comments(self, aid: str, bvid: str, title: str,
                           target_user: str, max_pages: int = 5,
                           search_replies: bool = False):
        """获取视频评论 - 使用 curl_cffi"""
        found_comments = []
        processed_rpids = set()
        url = "https://api.bilibili.com/x/v2/reply/main"
        self.skip_current = False

        params = {
            'csrf': self.csrf,
            'mode': 2,  # 按热度排序
            'oid': aid,
            'type': 1,
            'ps': 20,
            'next': 0
        }

        for page in range(max_pages):
            if not self.searching or self.skip_current:
                return found_comments

            self.log_signal.emit(f"正在查找第 {page + 1}/{max_pages} 页...", "INFO")

            try:
                headers = self.base_headers.copy()
                headers.update({
                    'Cookie': self.cookie,
                    'Referer': f'https://www.bilibili.com/video/{bvid}'
                })

                response = self.session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=10
                )

                data = response.json()

                if data['code'] != 0:
                    self.log_signal.emit(f"获取评论失败: {data.get('message', '未知错误')}", "ERROR")
                    break

                replies = data['data'].get('replies', [])
                if not replies:
                    self.log_signal.emit("没有更多评论了", "INFO")
                    break

                # 查找一级评论
                for reply in replies:
                    if reply['member']['uname'] == target_user and reply['rpid'] not in processed_rpids:
                        comment_data = {
                            'username': target_user,
                            'video_title': title,
                            'video_url': f"https://www.bilibili.com/video/{bvid}",
                            'oid': int(aid),
                            'comment': reply['content']['message'],
                            'comment_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(reply['ctime'])),
                            'type': 1,
                            'rpid': reply['rpid']
                        }
                        found_comments.append(comment_data)
                        processed_rpids.add(reply['rpid'])
                        self.log_signal.emit(f"找到评论: {reply['content']['message'][:30]}...", "INFO")

                    # 查找二级评论
                    if search_replies and reply.get('rcount', 0) > 0:
                        sub_comments = self.get_reply_comments(aid, reply['rpid'], target_user)
                        for sub in sub_comments:
                            if sub['rpid'] not in processed_rpids:
                                sub['video_title'] = title
                                sub['video_url'] = f"https://www.bilibili.com/video/{bvid}"
                                found_comments.append(sub)
                                processed_rpids.add(sub['rpid'])

                # 获取下一页
                if 'cursor' in data['data'] and not data['data']['cursor'].get('is_end', False):
                    params['next'] = data['data']['cursor']['next']
                else:
                    self.log_signal.emit("已到达最后一页", "INFO")
                    break

                # 随机延迟，避免请求过快
                delay = random.uniform(2.0, 4.0)
                time.sleep(delay)

            except Exception as e:
                self.log_signal.emit(f"获取评论出错: {str(e)}", "ERROR")
                break

        return found_comments

    def get_reply_comments(self, oid: str, root: str, target_user: str, max_pages: int = 3):
        """获取二级评论 - 使用 curl_cffi"""
        if self.skip_current:
            return []

        found = []
        url = "https://api.bilibili.com/x/v2/reply/reply"

        for page in range(1, max_pages + 1):
            params = {
                'csrf': self.csrf,
                'oid': oid,
                'type': 1,
                'root': root,
                'ps': 20,
                'pn': page
            }

            try:
                headers = self.base_headers.copy()
                headers['Cookie'] = self.cookie

                response = self.session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=10
                )

                data = response.json()

                if data['code'] != 0:
                    self.log_signal.emit(f"获取二级评论失败: {data.get('message', '未知错误')}", "ERROR")
                    break

                replies = data['data'].get('replies', [])
                if not replies:
                    break

                for reply in replies:
                    if reply['member']['uname'] == target_user:
                        comment_data = {
                            'username': target_user,
                            'oid': int(oid),
                            'comment': reply['content']['message'],
                            'comment_time': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(reply['ctime'])),
                            'type': '二级评论',
                            'rpid': reply['rpid']
                        }
                        found.append(comment_data)
                        self.log_signal.emit(f"找到二级评论: {reply['content']['message'][:30]}...", "INFO")

                if len(replies) < 20:
                    break

                time.sleep(random.uniform(1.5, 2.5))

            except Exception as e:
                self.log_signal.emit(f"获取二级评论出错: {str(e)}", "ERROR")
                break

        return found


class RecordCommDanmusScreen(QWidget):
    back_to_tools = pyqtSignal()
    window_closed = pyqtSignal()

    def __init__(self, api_service=None):
        super().__init__()
        self.api_service = api_service
        self.settings = QSettings('BilibiliTools', 'RecordTool')
        self.imported_data: Optional[ImportedData] = None
        self.import_thread: Optional[DataImportThread] = None
        self.log_handler: Optional[LogHandler] = None
        self.selected_folder_path = ""
        self.last_imported_file = ""
        self.filtered_comments = []  # 存储过滤后的评论
        self.filtered_danmaku = []  # 存储过滤后的弹幕
        self.all_comments_dict = {}  # 使用字典存储所有评论，用于去重
        self.all_danmaku_dict = {}  # 使用字典存储所有弹幕，用于去重
        self.cache_file = self._get_cache_file_path()
        self.comment_finder_worker = None
        self.cookie = ""
        self.csrf = ""
        self.delete_worker = None
        # 设置日志
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        self.init_ui()
        self.setup_logging()
        self.load_saved_folder()

    def _get_cache_file_path(self) -> str:
        """获取缓存文件路径"""
        try:
            home_dir = os.path.expanduser("~")
            config_dir = os.path.join(home_dir, ".bilibili_tools")
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            return os.path.join(config_dir, "record_cache.json")
        except Exception:
            return "record_cache.json"

    def load_cache(self):
        """加载缓存数据"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                # 加载评论
                for key, comment_data in cache_data.get('comments', {}).items():
                    try:
                        # 创建RecordedComment对象，只传入构造函数需要的字段
                        comment = RecordedComment(
                            text=comment_data.get('text', ''),
                            time=comment_data.get('time', ''),
                            timestamp=comment_data.get('timestamp', 0),
                            rpid=comment_data.get('rpid'),
                            status=comment_data.get('status', ''),
                            images=comment_data.get('images', []),
                            video_info=comment_data.get('video_info') or comment_data.get('videoInfo'),
                            video_time=comment_data.get('video_time', 0) or comment_data.get('videoTime', 0),
                            page_type=comment_data.get('page_type', '') or comment_data.get('pageType', ''),
                            url=comment_data.get('url', '')
                        )

                        # 保存完整的原始数据
                        comment._raw_data = comment_data
                        comment.source = comment_data.get('source', 'file_import')
                        self.all_comments_dict[key] = comment
                    except Exception as e:
                        self.logger.error(f"加载评论 {key} 失败: {e}")
                        continue

                # 加载弹幕
                for key, danmu_data in cache_data.get('danmaku', {}).items():
                    try:
                        danmu = RecordedDanmu(
                            text=danmu_data.get('text', ''),
                            time=danmu_data.get('time', ''),
                            timestamp=danmu_data.get('timestamp', 0),
                            method=danmu_data.get('method', ''),
                            video_info=danmu_data.get('video_info') or danmu_data.get('videoInfo'),
                            video_time=danmu_data.get('video_time', 0) or danmu_data.get('videoTime', 0),
                            page_type=danmu_data.get('page_type', '') or danmu_data.get('pageType', '')
                        )
                        danmu._raw_data = danmu_data
                        self.all_danmaku_dict[key] = danmu
                    except Exception as e:
                        self.logger.error(f"加载弹幕 {key} 失败: {e}")
                        continue

                # 更新显示
                self.filtered_comments = list(self.all_comments_dict.values())
                self.filtered_danmaku = list(self.all_danmaku_dict.values())
                self.update_tables()

                self.logger.info(
                    f"已从缓存加载 {len(self.all_comments_dict)} 条评论, {len(self.all_danmaku_dict)} 条弹幕")
            else:
                self.logger.info("未找到缓存文件")
        except Exception as e:
            self.logger.error(f"加载缓存失败: {e}")
            import traceback
            traceback.print_exc()

    def save_cache(self):
        """保存缓存数据"""
        try:
            cache_data = {
                'version': '1.0',
                'comments': {},
                'danmaku': {},
                'last_update': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            # 保存评论
            for key, comment in self.all_comments_dict.items():
                # 从_raw_data获取完整数据，如果没有则使用默认值
                raw_data = getattr(comment, '_raw_data', {})
                cache_data['comments'][key] = {
                    'text': comment.text,
                    'time': comment.time,
                    'timestamp': comment.timestamp,
                    'rpid': comment.rpid,
                    'status': comment.status,
                    'images': comment.images,
                    'video_info': comment.video_info,
                    'video_time': comment.video_time,
                    'page_type': comment.page_type,
                    'url': comment.url,
                    # 从_raw_data中获取完整字段
                    'oid': raw_data.get('oid'),
                    'type': raw_data.get('type'),
                    'source': getattr(comment, 'source', 'file_import'),
                    # 保持原始字段名兼容性
                    'videoInfo': comment.video_info,
                    'videoTime': comment.video_time,
                    'pageType': comment.page_type,
                }



            # 保存弹幕
            for key, danmu in self.all_danmaku_dict.items():
                cache_data['danmaku'][key] = {
                    'text': danmu.text,
                    'time': danmu.time,
                    'timestamp': danmu.timestamp,
                    'method': danmu.method,
                    'video_info': danmu.video_info,
                    'video_time': danmu.video_time,
                    'page_type': danmu.page_type,
                    # 保持原始字段名兼容性
                    'videoInfo': danmu.video_info,
                    'videoTime': danmu.video_time,
                    'pageType': danmu.page_type
                }

            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            self.logger.info("缓存已保存")
        except Exception as e:
            self.logger.error(f"保存缓存失败: {e}")

    def _get_comment_key(self, comment) -> str:
        """获取评论的唯一标识"""
        if comment.rpid:
            return f"rpid_{comment.rpid}"
        else:
            return f"ts_{comment.timestamp}_{hash(comment.text)}"

    def _get_danmu_key(self, danmu) -> str:
        """获取弹幕的唯一标识"""
        return f"danmu_ts_{danmu.timestamp}_{danmu.video_time}_{danmu.text[:50]}"

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        # 创建顶部工具栏
        self.create_top_toolbar(layout)

        # 创建主要内容区域
        self.create_main_content(layout)

        # 创建底部操作按钮
        self.create_bottom_buttons(layout)

        # 加载缓存数据
        self.load_cache()

    def create_top_toolbar(self, parent_layout):
        toolbar_frame = QFrame()
        toolbar_frame.setFixedHeight(70)
        toolbar_layout = QHBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(15, 8, 15, 8)

        # 左侧：退出按钮
        self.back_btn = QPushButton("← 返回工具选择")
        self.back_btn.setObjectName("secondaryButton")
        self.back_btn.clicked.connect(self.back_to_tools.emit)
        toolbar_layout.addWidget(self.back_btn)

        # 中间：标题
        title_label = QLabel("评论弹幕记录工具")
        title_label.setObjectName("statsCardTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar_layout.addWidget(title_label)

        toolbar_layout.addStretch()
        # 右侧：监控按钮组
        self.create_monitor_buttons(toolbar_layout)

        parent_layout.addWidget(toolbar_frame)

    def create_monitor_buttons(self, parent_layout):
        self.folder_path_label = QLabel("未选择文件夹")
        self.folder_path_label.setStyleSheet("color: #f87171; font-size: 12px; max-width: 200px;")
        parent_layout.addWidget(self.folder_path_label)

        # 选择文件夹按钮
        self.select_folder_btn = QPushButton("选择文件夹")
        self.select_folder_btn.setObjectName("primaryButton")
        self.select_folder_btn.clicked.connect(self.select_folder)
        parent_layout.addWidget(self.select_folder_btn)

        # 手动刷新按钮
        self.refresh_btn = QPushButton("刷新数据")
        self.refresh_btn.setObjectName("primaryButton")
        self.refresh_btn.clicked.connect(self.manual_refresh)
        self.refresh_btn.setEnabled(False)
        parent_layout.addWidget(self.refresh_btn)
        # 说明按钮
        info_btn = QPushButton("?")
        info_btn.clicked.connect(self.show_info)
        info_btn.setMaximumWidth(25)
        info_btn.setObjectName("infoButton")
        parent_layout.addWidget(info_btn)

    def show_info(self):
        info_text = f"""记录评论功能说明：
        
    1,功能说明
    • 使用本功能前请提前在工具选择页的设置里下载\n   记录评论弹幕脚本
    • 加载数据需要你先选择文件夹并在脚本里导出数据
            
    2,选择文件夹:
    • 作用: 选择一个json数据文件存放的文件夹
    • 这个文件夹是存放记录评论弹幕脚本导出的json数据的
    • 文件夹通常是你的浏览器下载所在的文件夹

    3,刷新数据:
    •点击刷新,会自动从导出的json数据里获取相应的\n   数据显示在列表
    
"""
        QMessageBox.information(self, "消息获取设置说明", info_text)

    def create_main_content(self, parent_layout):
        search_frame = QFrame()
        search_frame.setFixedHeight(60)
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(10, 5, 10, 5)

        search_label = QLabel("搜索:")
        search_layout.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索评论或弹幕...")
        self.search_input.textChanged.connect(self.on_search_text_changed)
        search_layout.addWidget(self.search_input)

        self.clear_search_btn = QPushButton("清空")
        self.clear_search_btn.setObjectName("secondaryButton")
        self.clear_search_btn.clicked.connect(self.clear_search)
        search_layout.addWidget(self.clear_search_btn)

        parent_layout.addWidget(search_frame)

        # 创建水平分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：数据表格区域
        self.create_data_area(splitter)

        # 右侧：日志区域
        self.create_log_area(splitter)

        # 设置分割比例
        splitter.setSizes([600, 400])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        parent_layout.addWidget(splitter)

    def create_data_area(self, parent_splitter):
        self.tab_widget = QTabWidget()

        self.comments_table = self.create_comments_table()
        self.tab_widget.addTab(self.comments_table, "评论记录")

        self.danmu_table = self.create_danmu_table()
        self.tab_widget.addTab(self.danmu_table, "弹幕记录")

        self.comment_finder_widget = self.create_comment_finder_widget()
        self.tab_widget.addTab(self.comment_finder_widget, "评论查找")
        parent_splitter.addWidget(self.tab_widget)

     #一行行解释这些代码,为什么查找配置和查找方式选择的空间挤在一起
    def create_comment_finder_widget(self):
        """创建评论查找界面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 配置区域
        config_group = QGroupBox("查找配置")
        config_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 14px;
                padding-top: 15px;
                margin-top: 10px;
            }
        """)
        config_layout = QVBoxLayout()
        config_layout.setContentsMargins(15, 20, 15, 15)  # 增加内边距
        config_layout.setSpacing(15)

        # 查找方式选择
        mode_layout = QHBoxLayout()
        self.finder_history_radio = QRadioButton("从历史记录查找")
        self.finder_history_radio.setChecked(True)
        self.finder_video_radio = QRadioButton("从指定视频查找")

        mode_layout.addWidget(self.finder_history_radio)
        mode_layout.addWidget(self.finder_video_radio)
        mode_layout.addStretch()
        config_layout.addLayout(mode_layout)

        # 用户名输入
        username_layout = QHBoxLayout()
        username_layout.addWidget(QLabel("目标用户名:"))
        self.finder_username_input = QLineEdit()
        self.finder_username_input.setPlaceholderText("要查找的用户名")
        username_layout.addWidget(self.finder_username_input)

        # 视频链接输入
        video_layout = QHBoxLayout()
        video_layout.addWidget(QLabel("视频链接/BV号:"))
        self.finder_video_input = QLineEdit()
        self.finder_video_input.setPlaceholderText("https://www.bilibili.com/video/BVxxxxxxxxx")
        video_layout.addWidget(self.finder_video_input)

        config_layout.addLayout(username_layout)
        config_layout.addLayout(video_layout)

        # 参数配置
        params_layout = QHBoxLayout()
        params_layout.addWidget(QLabel("历史条数:"))
        self.finder_history_count = QSpinBox()
        self.finder_history_count.setRange(10, 100)
        self.finder_history_count.setValue(10)
        params_layout.addWidget(self.finder_history_count)

        params_layout.addWidget(QLabel("查找页数:"))
        self.finder_pages = QSpinBox()
        self.finder_pages.setRange(1, 20)
        self.finder_pages.setValue(1)
        params_layout.addWidget(self.finder_pages)
        params_layout.addStretch()

        config_layout.addLayout(params_layout)

        # 高级选项
        options_layout = QHBoxLayout()
        self.finder_smart_search = QCheckBox("智能查找")
        self.finder_smart_search.setChecked(False)
        self.finder_search_replies = QCheckBox("查找二级评论(会增加请求次数)")

        options_layout.addWidget(self.finder_smart_search)
        options_layout.addWidget(self.finder_search_replies)

        options_layout.addWidget(QLabel("观看低于这个秒数自动跳过:"))
        self.finder_min_watch = QSpinBox()
        self.finder_min_watch.setRange(0, 300)
        self.finder_min_watch.setValue(5)
        self.finder_min_watch.setMaximumWidth(80)
        options_layout.addWidget(self.finder_min_watch)

        options_layout.addStretch()
        config_layout.addLayout(options_layout)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 操作按钮
        button_layout = QHBoxLayout()
        self.finder_start_btn = QPushButton("开始查找")
        self.finder_start_btn.setObjectName("primaryButton")
        self.finder_start_btn.clicked.connect(self.start_comment_finder)

        self.finder_stop_btn = QPushButton("停止查找")
        self.finder_stop_btn.setObjectName("dangerButton")
        self.finder_stop_btn.clicked.connect(self.stop_comment_finder)
        self.finder_stop_btn.setEnabled(False)

        self.finder_skip_btn = QPushButton("跳过当前视频")
        self.finder_skip_btn.setObjectName("secondaryButton")
        self.finder_skip_btn.clicked.connect(self.skip_current_video)
        self.finder_skip_btn.setEnabled(False)

        button_layout.addWidget(self.finder_start_btn)
        button_layout.addWidget(self.finder_stop_btn)
        button_layout.addWidget(self.finder_skip_btn)
        button_layout.addStretch()

        layout.addLayout(button_layout)
        layout.addStretch()

        # 使用说明
        info_label = QLabel(
            "使用说明:\n"
            "① 从历史记录查找：自动获取最近观看的视频并查找其中的评论\n"
            "② 从指定视频查找：输入视频链接或BV号查找特定视频的评论\n"
            "③ 智能查找会根据观看进度自动调整查找深度\n    根据观看的进度分别增加1,2,3,4,5页：每页20条数据\n"
            "④ 查找二级评论会增加请求次数，请谨慎使用\n"
            "⑤ 找到的评论会自动保存到缓存，下次打开时自动加载\n"
            "⑥ 本人不保证此工具的安全性,请勿滥用!"
        )
        info_label.setObjectName("infoLabel")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        return widget

    def load_cookie_from_account(self):
        """从账号管理器加载Cookie"""
        try:
            import json
            import os
            config_file = os.path.expanduser("~/.bilibili_tools/accounts.json")

            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 找到活跃账号
                for uid_str, account_data in data.get('accounts', {}).items():
                    if account_data.get('is_active', False):
                        self.cookie = account_data.get('cookie', '')
                        self.csrf = account_data.get('csrf', '')
                        self.logger.info(f"已加载账号: {account_data.get('username', 'Unknown')}")
                        return True

            self.logger.warning("未找到活跃账号")
            return False
        except Exception as e:
            self.logger.error(f"加载Cookie失败: {e}")
            return False

    def start_comment_finder(self):
        """开始评论查找"""
        if not self.load_cookie_from_account():
            self.logger.error("请先登录账号")
            return

        self.finder_start_btn.setEnabled(False)
        self.finder_stop_btn.setEnabled(True)
        self.finder_skip_btn.setEnabled(True)

        # 创建工作线程
        self.comment_finder_worker = CommentFinderWorker()
        self.comment_finder_worker.log_signal.connect(self.handle_finder_log)
        self.comment_finder_worker.comment_found.connect(self.add_found_comment)
        self.comment_finder_worker.progress_signal.connect(self.update_finder_progress)
        self.comment_finder_worker.finished_signal.connect(self.finder_finished)

        # 准备参数
        if self.finder_history_radio.isChecked():
            task_type = "history"
            params = {
                'username': self.finder_username_input.text().strip(),
                'history_count': self.finder_history_count.value(),
                'pages_per_video': self.finder_pages.value(),
                'smart_search': self.finder_smart_search.isChecked(),
                'search_replies': self.finder_search_replies.isChecked(),
                'min_watch_time': self.finder_min_watch.value()
            }
        else:
            task_type = "video"
            params = {
                'video_url': self.finder_video_input.text().strip(),
                'target_user': self.finder_username_input.text().strip(),
                'pages': self.finder_pages.value(),
                'search_replies': self.finder_search_replies.isChecked()
            }

        self.comment_finder_worker.setup(self.cookie, self.csrf, task_type, params)
        self.comment_finder_worker.start()

    def handle_finder_log(self, message: str, level: str = "INFO"):
        """处理评论查找器的日志"""
        if level == "ERROR":
            self.logger.error(message)
        elif level == "WARNING":
            self.logger.warning(message)
        else:
            self.logger.info(message)

    def stop_comment_finder(self):
        """停止评论查找"""
        if self.comment_finder_worker:
            self.comment_finder_worker.stop()
            self.logger.info("正在停止查找...")

    def skip_current_video(self):
        """跳过当前视频"""
        if self.comment_finder_worker:
            self.comment_finder_worker.skip_video()

    def add_found_comment(self, comment_data):
        """添加找到的评论到列表"""
        # 创建RecordedComment对象
        comment = RecordedComment(
            text=comment_data['text'],
            time=comment_data['time'],
            timestamp=comment_data['timestamp'],
            rpid=comment_data.get('rpid'),
            status=comment_data['status'],
            images=comment_data.get('images', []),
            video_info=comment_data.get('video_info'),
            video_time=comment_data.get('video_time', 0),
            page_type=comment_data['page_type'],
            url=comment_data.get('url', '')
        )
        raw_data = comment_data.copy()
        raw_data['oid'] = comment_data.get('oid')
        raw_data['type'] = comment_data.get('type', '一级评论')
        raw_data['videoInfo'] = comment_data.get('video_info')
        raw_data['videoTime'] = comment_data.get('video_time', 0)
        raw_data['pageType'] = comment_data.get('page_type')
        comment._raw_data = comment_data
        comment.source = 'comment_finder'  # 标注来源

        # 添加到评论字典
        key = f"finder_{comment_data.get('rpid', int(time.time()))}"
        if key not in self.all_comments_dict:
            self.all_comments_dict[key] = comment

            # 更新显示
            self.filtered_comments = list(self.all_comments_dict.values())
            self.update_tables()



    def update_finder_progress(self, current, total):
        """更新查找进度"""
        self.logger.info(f"查找进度: {current}/{total}")

    def finder_finished(self):
        """查找完成"""
        self.finder_start_btn.setEnabled(True)
        self.finder_stop_btn.setEnabled(False)
        self.finder_skip_btn.setEnabled(False)

        # 查找完成后统一保存缓存
        if self.comment_finder_worker:
            self.save_cache()
            self.logger.info("已保存查找结果到缓存")

        self.logger.info("评论查找任务完成")

    def create_comments_table(self):
        table = QTableWidget()
        table.setObjectName("commentDataTable")

        # 设置列
        headers = ["选择", "内容", "时间", "状态", "ID", "视频标题", "来源", "页面类型", "图片"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        # 设置表格属性
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSortingEnabled(True)

        # 设置列宽
        header = table.horizontalHeader()
        table.setColumnWidth(0, 50)  # 选择列
        table.setColumnWidth(1, 300)  # 内容列 - 固定宽度
        table.setColumnWidth(2, 150)  # 时间列
        table.setColumnWidth(3, 80)  # 状态列
        table.setColumnWidth(4, 100)  # ID列
        table.setColumnWidth(5, 200)  # 视频标题列
        table.setColumnWidth(6, 100)  # 来源列
        table.setColumnWidth(7, 100)  # 页面类型列
        table.setColumnWidth(8, 60)  # 图片列

        # 设置内容列可以换行
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)

        # 连接单击事件
        table.cellClicked.connect(self.on_cell_clicked)

        # 连接双击事件
        table.itemDoubleClicked.connect(self.on_comment_double_clicked)

        return table

    def create_danmu_table(self):
        table = QTableWidget()
        table.setObjectName("commentDataTable")

        # 设置列
        headers = ["选择", "内容", "时间", "发送方式", "视频标题", "弹幕发送时间", "页面类型"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        # 设置表格属性
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSortingEnabled(True)

        # 设置列宽
        table.setColumnWidth(0, 50)  # 选择列
        table.setColumnWidth(1, 150)  # 内容列 - 固定宽度
        table.setColumnWidth(2, 150)  # 时间列
        table.setColumnWidth(3, 100)  # 发送方式列
        table.setColumnWidth(4, 200)  # 视频标题列
        table.setColumnWidth(5, 120)  # 弹幕发送时间列
        table.setColumnWidth(6, 100)  # 页面类型列

        # 连接单击事件
        table.cellClicked.connect(lambda row, col: self.on_danmu_cell_clicked(row))

        # 连接双击事件
        table.itemDoubleClicked.connect(self.on_danmu_double_clicked)

        # 启用文字换行
        table.setWordWrap(True)

        return table

    def on_danmu_cell_clicked(self, row):
        """弹幕表格单击事件"""
        checkbox = self.danmu_table.cellWidget(row, 0)
        if checkbox and isinstance(checkbox, QCheckBox):
            checkbox.setChecked(not checkbox.isChecked())

    def create_log_area(self, parent_splitter):
        log_frame = QFrame()
        log_frame.setObjectName("mainPanel")
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(10, 10, 10, 10)

        # 日志标题
        log_title = QLabel("操作日志")
        log_title.setObjectName("statsCardTitle")
        log_layout.addWidget(log_title)

        # 日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)

        # 设置等宽字体
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.log_text.setFont(font)

        log_layout.addWidget(self.log_text)

        parent_splitter.addWidget(log_frame)



    def create_bottom_buttons(self, parent_layout):
        button_frame = QFrame()
        button_frame.setFixedHeight(70)
        button_layout = QHBoxLayout(button_frame)
        button_layout.setContentsMargins(15, 8, 15, 8)

        # 左侧按钮组
        # 全选按钮
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setObjectName("secondaryButton")
        self.select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(self.select_all_btn)

        # 反选按钮
        self.select_inverse_btn = QPushButton("反选")
        self.select_inverse_btn.setObjectName("secondaryButton")
        self.select_inverse_btn.clicked.connect(self.select_inverse)
        button_layout.addWidget(self.select_inverse_btn)

        # 删除选中按钮
        self.delete_selected_btn = QPushButton("删除选中")
        self.delete_selected_btn.setObjectName("dangerButton")
        self.delete_selected_btn.clicked.connect(self.delete_selected)
        button_layout.addWidget(self.delete_selected_btn)

        button_layout.addStretch()

        # 右侧按钮组
        # 清空日志按钮
        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.setObjectName("secondaryButton")
        self.clear_log_btn.clicked.connect(self.clear_log)
        button_layout.addWidget(self.clear_log_btn)

        # 清空数据按钮
        self.clear_data_btn = QPushButton("清空数据")
        self.clear_data_btn.setObjectName("dangerButton")
        self.clear_data_btn.clicked.connect(self.clear_data)
        button_layout.addWidget(self.clear_data_btn)

        parent_layout.addWidget(button_frame)

    def setup_logging(self):
        if self.log_handler:
            self.log_handler.cleanup()

        # 创建日志处理器
        self.log_handler = LogHandler(self.log_text)
        self.log_handler.setLevel(logging.INFO)

        # 设置日志格式
        formatter = logging.Formatter('%(levelname)s - %(message)s')
        self.log_handler.setFormatter(formatter)

        # 添加到logger
        self.logger.addHandler(self.log_handler)
        self.logger.setLevel(logging.INFO)

        self.logger.info("评论弹幕记录工具已启动")

    def load_saved_folder(self):
        saved_folder = self.settings.value('monitor_folder_path', '')
        if saved_folder and os.path.exists(saved_folder):
            self.selected_folder_path = saved_folder
            self.folder_path_label.setText(f"...{saved_folder[-30:]}")
            self.folder_path_label.setStyleSheet("color: #34d399; font-size: 12px; max-width: 200px;")
            self.folder_path_label.setToolTip(saved_folder)
            self.refresh_btn.setEnabled(True)
            self.logger.info(f"已加载保存的文件夹: {saved_folder}")

    def select_folder(self):
        # 获取上次使用的目录
        start_dir = self.selected_folder_path if self.selected_folder_path else os.path.expanduser('~/Downloads')

        folder_path = QFileDialog.getExistingDirectory(
            self,
            "选择JS脚本导出文件的文件夹",
            start_dir
        )

        if folder_path:
            self.selected_folder_path = folder_path
            # 永久保存文件夹路径
            self.settings.setValue('monitor_folder_path', folder_path)

            # 更新界面
            self.folder_path_label.setText(f"...{folder_path[-30:]}")
            self.folder_path_label.setStyleSheet("color: #34d399; font-size: 12px; max-width: 200px;")
            self.folder_path_label.setToolTip(folder_path)
            self.refresh_btn.setEnabled(True)

            self.logger.info(f"已选择文件夹: {folder_path}")

            # 立即检查文件
            self.check_for_new_files()

    def manual_refresh(self):
        self.check_for_new_files()

    def check_for_new_files(self):
        if not self.selected_folder_path:
            self.logger.warning("未选择文件夹")
            return

        # 查找匹配的文件
        pattern = os.path.join(self.selected_folder_path, "bili-monitor-data-*.json")
        files = glob.glob(pattern)

        if not files:
            self.logger.info("未找到匹配的文件")
            return

        # 按修改时间排序，获取最新文件
        latest_file = max(files, key=os.path.getmtime)

        # 检查是否是新文件
        if latest_file != self.last_imported_file:
            self.logger.info(f"发现新文件: {os.path.basename(latest_file)}")
            self.import_file(latest_file)
        else:
            self.logger.info("没有新文件")

    def import_file(self, file_path):
        if self.import_thread and self.import_thread.isRunning():
            self.logger.info("正在导入中，请稍候...")
            return

        self.last_imported_file = file_path

        # 启动导入线程
        self.import_thread = DataImportThread(file_path)
        self.import_thread.data_imported.connect(self.on_data_imported)
        self.import_thread.error_occurred.connect(self.on_import_error)
        self.import_thread.log_message.connect(self.logger.info)
        self.import_thread.start()

    def on_data_imported(self, imported_data: ImportedData):
        """处理导入的数据，进行去重"""
        new_comments = 0
        new_danmaku = 0

        # 处理评论去重
        for comment in imported_data.comments:
            key = self._get_comment_key(comment)
            if key not in self.all_comments_dict:
                self.all_comments_dict[key] = comment
                new_comments += 1

        # 处理弹幕去重
        for danmu in imported_data.danmaku:
            key = self._get_danmu_key(danmu)
            if key not in self.all_danmaku_dict:
                self.all_danmaku_dict[key] = danmu
                new_danmaku += 1

        # 更新过滤列表
        self.filtered_comments = list(self.all_comments_dict.values())
        self.filtered_danmaku = list(self.all_danmaku_dict.values())

        # 保存缓存
        self.save_cache()

        # 更新显示
        self.update_tables()

        # 显示导入统计
        msg = f"新增: {new_comments} 条评论, {new_danmaku} 条弹幕"
        msg += f" (总计: {len(self.all_comments_dict)} 条评论, {len(self.all_danmaku_dict)} 条弹幕)"
        self.logger.info(msg)

    def on_import_error(self, error_msg: str):
        """导入错误"""
        self.logger.error(error_msg)

    def update_tables(self):
        if not self.all_comments_dict and not self.all_danmaku_dict:
            return

        # 更新评论表格
        self.update_comments_table()

        # 更新弹幕表格
        self.update_danmu_table()

        # 更新标签页标题
        self.tab_widget.setTabText(0, f"评论记录 ({len(self.filtered_comments)})")
        self.tab_widget.setTabText(1, f"弹幕记录 ({len(self.filtered_danmaku)})")

    def update_comments_table(self):
        table = self.comments_table
        comments = self.filtered_comments

        table.setRowCount(len(comments))

        for row, comment in enumerate(comments):
            # 保存comment对象到表格
            table.setProperty(f"comment_{row}", comment)

            # 选择复选框
            checkbox = QCheckBox()
            checkbox.setStyleSheet("QCheckBox { margin-left: 0px; }")  # 居中显示
            table.setCellWidget(row, 0, checkbox)

            # 内容 - 创建可换行的项
            content_item = QTableWidgetItem(comment.text)
            content_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            table.setItem(row, 1, content_item)

            # 时间
            table.setItem(row, 2, QTableWidgetItem(comment.time))

            # 状态
            status_item = QTableWidgetItem(comment.status)
            if comment.status == "已获取ID":
                status_item.setBackground(Qt.GlobalColor.darkGreen)
            elif comment.status == "等待ID":
                status_item.setBackground(Qt.GlobalColor.darkYellow)
            else:
                status_item.setBackground(Qt.GlobalColor.darkRed)
            table.setItem(row, 3, status_item)

            # ID
            table.setItem(row, 4, QTableWidgetItem(str(comment.rpid) if comment.rpid else "未获取"))

            # 视频标题
            video_title = ""
            if comment.video_info:
                video_title = comment.video_info.get('title', '未知视频')
            table.setItem(row, 5, QTableWidgetItem(video_title))

            # 来源
            source_text = "📁 文件导入" if not hasattr(comment,
                                                      'source') or comment.source != 'comment_finder' else "🔍 实时查找"
            table.setItem(row, 6, QTableWidgetItem(source_text))

            # 页面类型
            table.setItem(row, 7, QTableWidgetItem(comment.page_type))

            # 图片
            image_count = len(comment.images) if comment.images else 0
            image_text = f"📷 {image_count}" if image_count > 0 else ""
            table.setItem(row, 8, QTableWidgetItem(image_text))

            # 设置行高，根据内容长度动态调整
            content_length = len(comment.text)
            if content_length > 100:
                table.setRowHeight(row, 80)
            elif content_length > 50:
                table.setRowHeight(row, 60)
            else:
                table.setRowHeight(row, 45)

        # 启用文字换行
        table.setWordWrap(True)

    def on_cell_clicked(self, row, column):
        """单击任意格子切换选中状态"""
        checkbox = self.comments_table.cellWidget(row, 0)
        if checkbox and isinstance(checkbox, QCheckBox):
            checkbox.setChecked(not checkbox.isChecked())

    def update_danmu_table(self):
        table = self.danmu_table
        danmaku = self.filtered_danmaku

        table.setRowCount(len(danmaku))

        for row, danmu in enumerate(danmaku):
            # 保存danmu对象到表格
            table.setProperty(f"danmu_{row}", danmu)

            # 选择复选框
            checkbox = QCheckBox()
            checkbox.setStyleSheet("QCheckBox { margin-left: 0px; }")
            table.setCellWidget(row, 0, checkbox)

            # 内容
            content_item = QTableWidgetItem(danmu.text)
            content_item.setTextAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            table.setItem(row, 1, content_item)
            # 时间
            table.setItem(row, 2, QTableWidgetItem(danmu.time))
            # 发送方式
            table.setItem(row, 3, QTableWidgetItem(danmu.method))

            # 视频标题
            video_title = ""
            if danmu.video_info:
                video_title = danmu.video_info.get('title', '未知视频')[:50]
            table.setItem(row, 4, QTableWidgetItem(video_title))
            # 视频时间
            table.setItem(row, 5, QTableWidgetItem(f"{danmu.video_time}s"))
            # 页面类型
            table.setItem(row, 6, QTableWidgetItem(danmu.page_type))

            content_length = len(danmu.text)
            if content_length > 100:
                table.setRowHeight(row, 80)
            elif content_length > 50:
                table.setRowHeight(row, 60)
            else:
                table.setRowHeight(row, 45)
            # 启用文字换行
            table.setWordWrap(True)


    def on_comment_double_clicked(self, item):
        """评论双击事件"""
        row = item.row()
        comment = self.comments_table.property(f"comment_{row}")

        if comment and hasattr(comment, '_raw_data'):
            dialog = DetailDialog(comment._raw_data, 'comment', self)
            dialog.exec()

    def on_danmu_double_clicked(self, item):
        """弹幕双击事件"""
        row = item.row()
        danmu = self.danmu_table.property(f"danmu_{row}")

        if danmu and hasattr(danmu, '_raw_data'):
            dialog = DetailDialog(danmu._raw_data, 'danmu', self)
            dialog.exec()

    def on_search_text_changed(self):
        """搜索文本改变时触发"""
        search_text = self.search_input.text().strip().lower()

        if not self.all_comments_dict and not self.all_danmaku_dict:
            return

        if not search_text:
            # 如果搜索框为空，显示所有数据
            self.filtered_comments = list(self.all_comments_dict.values())
            self.filtered_danmaku = list(self.all_danmaku_dict.values())
        else:
            # 过滤评论
            self.filtered_comments = [
                comment for comment in self.all_comments_dict.values()
                if search_text in comment.text.lower()
            ]

            # 过滤弹幕
            self.filtered_danmaku = [
                danmu for danmu in self.all_danmaku_dict.values()
                if search_text in danmu.text.lower()
            ]

        self.update_tables()
        self.logger.info(f"搜索 '{search_text}': 找到 {len(self.filtered_comments)} 条评论, {len(self.filtered_danmaku)} 条弹幕")

    def clear_search(self):
        """清空搜索"""
        self.search_input.clear()

    def select_all(self):
        current_table = self.comments_table if self.tab_widget.currentIndex() == 0 else self.danmu_table
        for row in range(current_table.rowCount()):
            checkbox = current_table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(True)
        self.logger.info("已全选所有项目")

    def select_inverse(self):
        current_table = self.comments_table if self.tab_widget.currentIndex() == 0 else self.danmu_table
        for row in range(current_table.rowCount()):
            checkbox = current_table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(not checkbox.isChecked())
        self.logger.info("已反选所有项目")

    def delete_selected(self):
        """删除选中的评论"""
        if self.tab_widget.currentIndex() != 0:
            self.logger.warning("当前只支持删除评论，不支持删除弹幕")
            return

        # 检查是否有 API 服务
        if not self.api_service:
            self.logger.error("未找到 API 服务，请确保已登录账号")
            return

        # 收集选中的评论
        comments_to_delete = []
        current_table = self.comments_table

        for row in range(current_table.rowCount()):
            checkbox = current_table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                comment = current_table.property(f"comment_{row}")
                if comment:
                    # 找到对应的 key
                    for key, value in self.all_comments_dict.items():
                        if value == comment:
                            comments_to_delete.append((key, comment))
                            break

        if not comments_to_delete:
            self.logger.warning("未选择任何评论")
            return

        # 确认对话框
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(comments_to_delete)} 条评论吗？\n\n"
            "此操作将从B站删除这些评论，不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # 禁用删除按钮
        self.delete_selected_btn.setEnabled(False)

        # 创建并启动删除线程
        self.delete_worker = DeleteWorkerThread(comments_to_delete, self.api_service)
        self.delete_worker.progress_signal.connect(self.on_delete_progress)
        self.delete_worker.log_signal.connect(self.on_delete_log)
        self.delete_worker.deleted_signal.connect(self.on_comments_deleted)
        self.delete_worker.finished_signal.connect(self.on_delete_finished)
        self.delete_worker.start()

        self.logger.info(f"开始删除 {len(comments_to_delete)} 条评论...")

    def on_delete_progress(self, current, total):
        """删除进度更新"""
        self.logger.info(f"删除进度: {current}/{total}")

    def on_delete_log(self, message, level):
        """处理删除日志"""
        if level == "ERROR":
            self.logger.error(message)
        else:
            self.logger.info(message)

    def on_comments_deleted(self, deleted_keys):
        """处理已删除的评论"""
        # 从字典中删除
        for key in deleted_keys:
            if key in self.all_comments_dict:
                del self.all_comments_dict[key]

        # 更新过滤列表
        self.filtered_comments = list(self.all_comments_dict.values())

        # 保存缓存
        self.save_cache()

        # 更新显示
        self.update_tables()

        self.logger.info(f"已从缓存中删除 {len(deleted_keys)} 条评论")

    def on_delete_finished(self):
        """删除任务完成"""
        self.delete_selected_btn.setEnabled(True)
        self.logger.info("删除任务完成")

    def clear_log(self):
        self.log_text.clear()
        self.logger.info("日志已清空")

    def clear_data(self):
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有导入的数据吗？\n\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.imported_data = None
            self.filtered_comments = []
            self.filtered_danmaku = []
            self.all_comments_dict.clear()
            self.all_danmaku_dict.clear()
            # 清除缓存文件
            try:
                if os.path.exists(self.cache_file):
                    os.remove(self.cache_file)
                    self.logger.info("缓存文件已删除")
            except Exception as e:
                self.logger.error(f"删除缓存文件失败: {e}")
            self.last_imported_file = ""
            self.comments_table.setRowCount(0)
            self.danmu_table.setRowCount(0)

            self.tab_widget.setTabText(0, " 评论记录")
            self.tab_widget.setTabText(1, "  弹幕记录")

            self.logger.info("数据已清空")

    def closeEvent(self, event):
        # 停止评论查找线程
        if self.comment_finder_worker and self.comment_finder_worker.isRunning():
            self.comment_finder_worker.stop()
            # 先等待5秒让线程正常结束
            if not self.comment_finder_worker.wait(5000):
                self.logger.warning("评论查找线程未能正常结束，强制终止")
                self.comment_finder_worker.terminate()
                self.comment_finder_worker.wait(2000)

        # 停止导入线程
        if self.import_thread and self.import_thread.isRunning():
            self.import_thread.terminate()
            self.import_thread.wait(1000)

        # 清理日志处理器
        if self.log_handler:
            self.logger.removeHandler(self.log_handler)
            self.log_handler.cleanup()
            self.log_handler = None
        if hasattr(self, 'delete_worker') and self.delete_worker and self.delete_worker.isRunning():
            self.delete_worker.terminate()
            self.delete_worker.wait(1000)
        self.window_closed.emit()
        super().closeEvent(event)


class DeleteWorkerThread(QThread):
    """删除评论的工作线程"""
    progress_signal = pyqtSignal(int, int)
    log_signal = pyqtSignal(str, str)
    deleted_signal = pyqtSignal(list)
    finished_signal = pyqtSignal()

    def __init__(self, comments_to_delete, api_service):
        super().__init__()
        self.comments_to_delete = comments_to_delete
        self.api_service = api_service
        self.deleted_keys = []

    def run(self):
        """执行删除任务"""
        import asyncio
        from ..api.comment import remove_comment
        from ..types import Comment as CommentType

        total = len(self.comments_to_delete)

        async def delete_comments():
            for i, (key, comment) in enumerate(self.comments_to_delete):
                try:
                    # 获取必要的信息
                    raw_data = getattr(comment, '_raw_data', {})
                    oid = raw_data.get('oid')
                    comment_type = raw_data.get('type', 1)  # 默认为视频评论
                    rpid = comment.rpid

                    if not oid or not rpid:
                        self.log_signal.emit(f"评论缺少必要信息: OID={oid}, RPID={rpid}", "ERROR")
                        continue

                    # 创建 Comment 对象 - 只传入必要的参数
                    comment_obj = CommentType(
                        oid=oid,
                        type=comment_type,
                        content=comment.text  # 添加必需的 content 参数
                    )

                    # 调用删除 API
                    await remove_comment(comment_obj, rpid, self.api_service)
                    self.deleted_keys.append(key)
                    self.log_signal.emit(f"成功删除评论: {comment.text[:30]}...", "INFO")

                except DeleteCommentError as e:
                    self.log_signal.emit(str(e), "ERROR")
                except Exception as e:
                    self.log_signal.emit(f"删除评论失败: {str(e)}", "ERROR")

                self.progress_signal.emit(i + 1, total)

                # 添加延迟避免请求过快
                await asyncio.sleep(1.5)

        # 运行异步任务
        asyncio.run(delete_comments())

        self.deleted_signal.emit(self.deleted_keys)
        self.finished_signal.emit()