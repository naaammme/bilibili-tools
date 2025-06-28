import threading
import time
import json
import pickle
import os
import random
import webbrowser
import re
import requests
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QTextEdit, QTextBrowser,
    QCheckBox, QTabWidget, QFrame, QScrollArea, QMessageBox,
    QDialog, QSplitter, QHeaderView, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, pyqtSlot
from PyQt6.QtGui import QFont, QTextCharFormat, QTextCursor, QColor

from ..api.api_service import ApiService
import logging

logger = logging.getLogger(__name__)

#成功了就减少延迟,失败了增加延迟
class SmartDelay:
    def __init__(self):
        self.base_delay = 1.0
        self.failure_count = 0
        self.success_count = 0
        self.last_request_time = 0

    def wait(self):
        # 计算动态延迟
        if self.failure_count > 0:
            delay = self.base_delay * (1.5 ** self.failure_count)
        else:
            # 连续成功可以稍微减少延迟
            delay = self.base_delay * (0.9 ** min(self.success_count, 3))

        # 限制延迟范围
        delay = max(0.5, min(delay, 15))

        # 确保与上次请求的间隔
        time_since_last = time.time() - self.last_request_time
        if time_since_last < delay:
            time.sleep(delay - time_since_last)

        # 添加随机性
        actual_delay = random.uniform(delay * 0.8, delay * 1.2)
        time.sleep(actual_delay)
        self.last_request_time = time.time()

    def on_success(self):
        """请求成功时调用"""
        self.success_count += 1
        self.failure_count = max(0, self.failure_count - 1)

    def on_failure(self):
        """请求失败时调用"""
        self.failure_count += 1
        self.success_count = 0


class MessageCache:
    """消息缓存系统，支持断点续传"""
    def __init__(self, cache_file="message_cache.pkl"):
        self.cache_file = cache_file
        self.messages = []
        self.last_fetch_time = 0
        self.last_processed_session_end_ts = 0
        self.newest_msg_timestamp = 0
        self.session_ack_seqnos = {}  # 存储每个会话的已读位置
        self._ensure_cache_dir()
        self.load_cache()

    def _ensure_cache_dir(self):
        """确保缓存目录存在"""
        try:
            home_dir = os.path.expanduser("~")
            cache_dir = os.path.join(home_dir, ".bilibili_tools")
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
            self.cache_file = os.path.join(cache_dir, "message_cache.pkl")
        except Exception as e:
            logger.error(f"创建缓存目录失败: {e}")

    def load_cache(self):
        """从文件加载缓存"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'rb') as f:
                    data = pickle.load(f)
                    self.messages = data.get('messages', [])
                    self.last_fetch_time = data.get('last_fetch_time', 0)
                    self.last_processed_session_end_ts = data.get('last_processed_session_end_ts', 0)
                    self.newest_msg_timestamp = data.get('newest_msg_timestamp', 0)
                    self.session_ack_seqnos = data.get('session_ack_seqnos', {})

                    # 如果没有记录最新消息时间戳，从现有消息中找出
                    if not self.newest_msg_timestamp and self.messages:
                        self.newest_msg_timestamp = max(msg['timestamp'] for msg in self.messages)
            except Exception as e:
                logger.error(f"加载缓存失败: {e}")

    def save_cache(self):
        """保存缓存到文件"""
        try:
            data = {
                'messages': self.messages,
                'last_fetch_time': self.last_fetch_time,
                'last_processed_session_end_ts': self.last_processed_session_end_ts,
                'newest_msg_timestamp': self.newest_msg_timestamp,
                'session_ack_seqnos': self.session_ack_seqnos
            }
            with open(self.cache_file, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    def add_messages(self, new_messages, update_newest=True):
        """添加新消息，自动去重"""
        existing_seqnos = {msg['msg_seqno'] for msg in self.messages}
        added_count = 0
        for msg in new_messages:
            if msg['msg_seqno'] not in existing_seqnos:
                self.messages.append(msg)
                existing_seqnos.add(msg['msg_seqno'])
                added_count += 1
                # 更新最新消息时间戳
                if update_newest and msg['timestamp'] > self.newest_msg_timestamp:
                    self.newest_msg_timestamp = msg['timestamp']
        self.last_fetch_time = time.time()
        return added_count

    def get_messages(self):
        """获取所有消息"""
        return self.messages

    def clear(self):
        """清空缓存"""
        self.messages = []
        self.last_fetch_time = 0
        self.last_processed_session_end_ts = 0
        self.newest_msg_timestamp = 0
        self.session_ack_seqnos = {}
        self.save_cache()

    def get_formatted_last_time(self):
        """获取格式化的最后处理时间"""
        if self.last_processed_session_end_ts <= 0:
            return None
        try:
            # B站时间戳可能是毫秒级，需要转换为秒
            ts = self.last_processed_session_end_ts
            if ts > 1e10:  # 如果是毫秒级时间戳
                ts = ts / 1000
            return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        except:
            return None

    def update_session_ack_seqno(self, talker_id, ack_seqno):
        """更新会话的已读位置"""
        self.session_ack_seqnos[str(talker_id)] = ack_seqno

    def get_session_ack_seqno(self, talker_id):
        """获取会话的已读位置"""
        return self.session_ack_seqnos.get(str(talker_id), 0)


class MessageFetchThread(QThread):
    """消息获取线程"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    update_ui_signal = pyqtSignal()

    def __init__(self, manager, fetch_type="all"):
        super().__init__()
        self.manager = manager
        self.fetch_type = fetch_type  # "all" 或 "new"
        self.should_stop = False

    def stop(self):
        self.should_stop = True

    def run(self):
        try:
            if self.fetch_type == "all":
                self._fetch_all_messages()
            else:
                self._fetch_new_messages()
        except Exception as e:
            self.log_signal.emit(f"获取消息时发生错误: {e}")
        finally:
            self.finished_signal.emit()

    def _fetch_all_messages(self):
        """获取全部消息"""
        self.log_signal.emit("开始获取会话分页...")
        sessions_processed = 0

        try:
            sessions_processed = self._fetch_all_session_pages()
        except Exception as e:
            self.log_signal.emit(f"获取消息过程中发生错误: {e}")
        finally:
            self.manager.cache.save_cache()

            if self.should_stop:
                log_msg = f"消息获取已中止。本轮处理了 {sessions_processed} 个会话，进度已保存。"
            else:
                log_msg = f"消息获取流程结束。本轮处理了 {sessions_processed} 个会话。"
            self.log_signal.emit(log_msg)

    def _fetch_new_messages(self):
        """获取新消息"""
        try:
            new_messages = []
            page_size = 20
            has_more = True
            current_page_end_ts = 0

            if not self.manager.messages:
                self.log_signal.emit("没有缓存消息，请先使用'获取全部'功能。")
                return

            # 找出最新的消息序列号
            newest_seqno = max(msg['msg_seqno'] for msg in self.manager.messages)
            self.log_signal.emit(f"开始获取新消息（最新缓存消息seqno: {newest_seqno}）...")

            # 获取会话列表
            while has_more and not self.should_stop:
                try:
                    params = {
                        'session_type': 1,
                        'group_fold': 1,
                        'unfollow_fold': 0,
                        'sort_rule': 2,
                        'build': 0,
                        'mobi_app': 'web',
                        'size': page_size
                    }
                    if current_page_end_ts > 0:
                        params['end_ts'] = current_page_end_ts

                    resp = requests.get(
                        f"{self.manager.api_base}/session_svr/v1/session_svr/get_sessions",
                        params=params,
                        headers=self.manager.headers,
                        cookies=self.manager.cookies,
                        timeout=15
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    if data['code'] != 0:
                        self.log_signal.emit(f"获取会话列表失败: {data.get('message', '')}")
                        break

                    sessions = data['data'].get('session_list', [])
                    if not sessions:
                        break

                    for session in sessions:
                        talker_id = session['talker_id']

                        # 更新会话的已读位置
                        current_ack_seqno = session.get('ack_seqno', 0)
                        self.manager.cache.update_session_ack_seqno(talker_id, current_ack_seqno)

                        # 检查是否有新消息
                        last_msg = session.get('last_msg', {})
                        if last_msg.get('msg_seqno', 0) > newest_seqno:
                            # 获取该会话的新消息
                            session_new_messages = self._fetch_session_new_messages(
                                talker_id,
                                newest_seqno,
                                current_ack_seqno
                            )
                            new_messages.extend(session_new_messages)
                            self.manager.smart_delay.wait()

                    current_page_end_ts = sessions[-1]['session_ts']
                    has_more = data['data'].get('has_more', False)

                except Exception as e:
                    self.log_signal.emit(f"获取新消息时出错: {e}")
                    break

            # 添加新消息到缓存
            if new_messages:
                added_count = self.manager.cache.add_messages(new_messages)
                self.manager.messages = self.manager.cache.get_messages()
                self.manager.cache.save_cache()
                self.log_signal.emit(f"获取到 {added_count} 条新消息")
                self.update_ui_signal.emit()
            else:
                self.log_signal.emit("没有新消息")

        except Exception as e:
            self.log_signal.emit(f"获取新消息失败: {e}")

    def _fetch_session_new_messages(self, talker_id, since_seqno, current_ack_seqno):
        """获取特定会话中比指定序列号新的消息"""
        new_messages = []
        has_more = True
        max_seqno = 0

        while has_more and not self.should_stop:
            try:
                params = {
                    'talker_id': talker_id,
                    'session_type': 1,
                    'size': 30,
                    'build': 0,
                    'mobi_app': 'web'
                }
                if max_seqno > 0:
                    params['max_seqno'] = max_seqno

                resp = requests.get(
                    f"{self.manager.api_base}/svr_sync/v1/svr_sync/fetch_session_msgs",
                    params=params,
                    headers=self.manager.headers,
                    cookies=self.manager.cookies,
                    timeout=10
                )
                resp.raise_for_status()
                data = resp.json()

                if data['code'] == 0:
                    messages = data['data'].get('messages', [])
                    has_more = data['data'].get('has_more', False)

                    for msg_json in messages:
                        if msg_json['msg_seqno'] > since_seqno:
                            msg_data = {
                                'msg_seqno': msg_json['msg_seqno'],
                                'talker_id': talker_id,
                                'timestamp': msg_json['timestamp'],
                                'sender_uid': msg_json['sender_uid'],
                                'content': self.manager._parse_message_content(msg_json),
                                'raw_content': msg_json.get('content', ''),
                                'msg_type': msg_json['msg_type'],
                                'msg_status': msg_json.get('msg_status', 0),
                                'is_unread': msg_json['msg_seqno'] > current_ack_seqno
                            }

                            if msg_json['msg_type'] == 2:
                                image_url = self.manager._extract_image_url(msg_json)
                                if image_url:
                                    msg_data['image_url'] = image_url

                            new_messages.append(msg_data)
                        else:
                            has_more = False
                            break

                    if messages:
                        max_seqno = messages[-1]['msg_seqno']
                else:
                    break

            except Exception as e:
                self.log_signal.emit(f"获取会话 {talker_id} 新消息时出错: {e}")
                break

        return new_messages

    def _fetch_all_session_pages(self):
        """获取所有会话分页"""
        session_type = 1
        page_size = 20
        has_more = True
        current_page_end_ts = self.manager.cache.last_processed_session_end_ts
        total_sessions_fetched_this_run = 0
        new_messages_this_run = []

        session_unread_info = {}

        while has_more:
            if self.should_stop:
                self.log_signal.emit("检测到停止信号，中断获取会话分页。")
                break

            try:
                params = {
                    'session_type': session_type,
                    'group_fold': 1,
                    'unfollow_fold': 0,
                    'sort_rule': 2,
                    'build': 0,
                    'mobi_app': 'web',
                    'size': page_size
                }
                if current_page_end_ts > 0:
                    params['end_ts'] = current_page_end_ts

                resp = requests.get(
                    f"{self.manager.api_base}/session_svr/v1/session_svr/get_sessions",
                    params=params,
                    headers=self.manager.headers,
                    cookies=self.manager.cookies,
                    timeout=15
                )
                resp.raise_for_status()
                data = resp.json()

                if data['code'] != 0:
                    self.log_signal.emit(f"获取会话列表失败: {data.get('message', 'Unknown error')} (Code: {data['code']})")
                    has_more = False
                    break

                sessions = data['data'].get('session_list', [])
                has_more = data['data'].get('has_more', False)

                if not sessions:
                    self.log_signal.emit("未获取到更多会话。")
                    has_more = False
                    break

                total_sessions_fetched_this_run += len(sessions)
                self.manager.cache.last_processed_session_end_ts = sessions[-1]['session_ts']
                current_page_end_ts = self.manager.cache.last_processed_session_end_ts

                self.log_signal.emit(f"获取到 {len(sessions)} 个会话，下一页将从 ts: {current_page_end_ts} 开始。")

                for session in sessions:
                    if self.should_stop:
                        break

                    # 保存会话的未读信息
                    talker_id = session['talker_id']
                    session_unread_info[talker_id] = {
                        'unread_count': session.get('unread_count', 0),
                        'ack_seqno': session.get('ack_seqno', 0)
                    }

                    # 获取会话消息
                    messages_from_session = self._fetch_single_session_messages_with_status(
                        talker_id,
                        session_unread_info[talker_id]
                    )
                    new_messages_this_run.extend(messages_from_session)
                    self.manager.smart_delay.wait()

                if self.should_stop:
                    break

                self.manager.smart_delay.on_success()
                self.manager.smart_delay.wait()

            except Exception as e:
                self.log_signal.emit(f"获取会话列表时发生错误: {e}")
                has_more = False
                break

        # 添加新消息到缓存
        self.manager.cache.add_messages(new_messages_this_run)
        self.manager.messages = self.manager.cache.get_messages()
        self.manager.cache.save_cache()

        if not self.should_stop and not has_more:
            self.log_signal.emit("已拉取完所有符合条件的会话。")

        return total_sessions_fetched_this_run

    def _fetch_single_session_messages_with_status(self, talker_id, unread_info):
        """获取单个会话的消息，并标记未读状态"""
        if self.should_stop:
            return []

        messages_for_this_session = []
        ack_seqno = unread_info.get('ack_seqno', 0)

        # 更新缓存中的已读位置
        self.manager.cache.update_session_ack_seqno(talker_id, ack_seqno)

        try:
            params = {
                'talker_id': talker_id,
                'session_type': 1,
                'size': 30,
                'build': 0,
                'mobi_app': 'web'
            }
            resp = requests.get(
                f"{self.manager.api_base}/svr_sync/v1/svr_sync/fetch_session_msgs",
                params=params,
                headers=self.manager.headers,
                cookies=self.manager.cookies,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()

            if data['code'] == 0:
                for msg_json in data['data'].get('messages', []):
                    if self.should_stop:
                        break

                    msg_data = {
                        'msg_seqno': msg_json['msg_seqno'],
                        'talker_id': talker_id,
                        'timestamp': msg_json['timestamp'],
                        'sender_uid': msg_json['sender_uid'],
                        'content': self.manager._parse_message_content(msg_json),
                        'raw_content': msg_json.get('content', ''),
                        'msg_type': msg_json['msg_type'],
                        'msg_status': msg_json.get('msg_status', 0),
                        'is_unread': msg_json['msg_seqno'] > ack_seqno
                    }

                    if msg_json['msg_type'] == 2:
                        image_url = self.manager._extract_image_url(msg_json)
                        if image_url:
                            msg_data['image_url'] = image_url

                    messages_for_this_session.append(msg_data)
                self.manager.smart_delay.on_success()
            else:
                self.log_signal.emit(f"获取会话 {talker_id} 消息失败: {data.get('message', '')}")
                self.manager.smart_delay.on_failure()

        except Exception as e:
            self.log_signal.emit(f"获取会话 {talker_id} 消息时发生错误: {e}")
            self.manager.smart_delay.on_failure()

        return messages_for_this_session


class OperationThread(QThread):
    """操作线程（标记已读、批量删除等）"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    update_ui_signal = pyqtSignal()

    def __init__(self, manager, operation_type, data):
        super().__init__()
        self.manager = manager
        self.operation_type = operation_type
        self.data = data
        self.should_stop = False

    def stop(self):
        self.should_stop = True

    def run(self):
        try:
            if self.operation_type == "mark_read":
                self._mark_as_read(self.data)
            elif self.operation_type == "batch_delete":
                self._batch_delete(self.data)
        except Exception as e:
            self.log_signal.emit(f"操作时发生错误: {e}")
        finally:
            self.finished_signal.emit()

    def _mark_as_read(self, talker_ids_with_seqnos):
        """标记已读的线程方法"""
        if not self.manager.cookies.get('bili_jct'):
            self.log_signal.emit("错误: CSRF token (bili_jct) 未设置，无法标记已读。")
            return

        success_count = 0
        total_to_process = len(talker_ids_with_seqnos)
        processed_count = 0

        for talker_id, ack_seqno in talker_ids_with_seqnos.items():
            if self.should_stop:
                self.log_signal.emit("标记已读操作被中止。")
                break
            try:
                data = {
                    'talker_id': talker_id,
                    'session_type': 1,
                    'ack_seqno': ack_seqno,
                    'build': 0,
                    'mobi_app': 'web',
                    'csrf_token': self.manager.cookies['bili_jct'],
                    'csrf': self.manager.cookies['bili_jct']
                }
                resp = requests.post(
                    f"{self.manager.api_base}/session_svr/v1/session_svr/update_ack",
                    data=data,
                    headers=self.manager.headers,
                    cookies=self.manager.cookies,
                    timeout=10
                )
                resp.raise_for_status()
                result = resp.json()
                if result['code'] == 0:
                    self.log_signal.emit(f"成功标记 UID:{talker_id} 会话已读 (至 seqno:{ack_seqno})")
                    success_count += 1

                    # 更新本地缓存的已读位置
                    self.manager.cache.update_session_ack_seqno(talker_id, ack_seqno)

                    # 更新本地消息的未读状态
                    for msg in self.manager.messages:
                        if msg['talker_id'] == talker_id and msg['msg_seqno'] <= ack_seqno:
                            msg['is_unread'] = False

                    self.manager.smart_delay.on_success()
                else:
                    self.log_signal.emit(f"标记 UID:{talker_id} 会话已读失败: {result.get('message', '')} (Code: {result['code']})")
                    self.manager.smart_delay.on_failure()
                processed_count += 1
                self.manager.smart_delay.wait()
            except Exception as e:
                self.log_signal.emit(f"标记 UID:{talker_id} 会话已读出错: {e}")
                self.manager.smart_delay.on_failure()
                processed_count += 1

        # 保存更新后的缓存
        self.manager.cache.save_cache()
        self.update_ui_signal.emit()

        unprocessed_count = total_to_process - processed_count
        if unprocessed_count > 0:
            self.log_signal.emit(f"标记已读操作完成。成功: {success_count}/{processed_count}，未处理: {unprocessed_count}")
        else:
            self.log_signal.emit(f"标记已读操作完成。成功: {success_count}/{total_to_process}")

    def _batch_delete(self, talker_ids):
        """批量删除的线程方法"""
        if not self.manager.cookies.get('bili_jct'):
            self.log_signal.emit("错误: CSRF token (bili_jct) 未设置，无法删除。")
            return

        self.log_signal.emit(f"开始 API 删除 {len(talker_ids)} 个会话...")
        deleted_count_api = 0
        successfully_deleted_ids = []
        failed_ids_api = []

        for talker_id in talker_ids:
            if self.should_stop:
                self.log_signal.emit("删除操作被中止。")
                break
            try:
                data = {
                    'talker_id': talker_id,
                    'session_type': 1,
                    'csrf_token': self.manager.cookies['bili_jct'],
                    'csrf': self.manager.cookies['bili_jct']
                }
                resp = requests.post(
                    f"{self.manager.api_base}/session_svr/v1/session_svr/remove_session",
                    data=data,
                    headers=self.manager.headers,
                    cookies=self.manager.cookies,
                    timeout=10
                )
                resp.raise_for_status()
                result = resp.json()
                if result['code'] == 0:
                    self.log_signal.emit(f"API: 成功删除与 UID:{talker_id} 的会话。")
                    deleted_count_api += 1
                    successfully_deleted_ids.append(talker_id)
                    self.manager.smart_delay.on_success()
                else:
                    self.log_signal.emit(f"API: 删除 UID:{talker_id} 会话失败: {result.get('message', '')} (Code: {result['code']})")
                    failed_ids_api.append(talker_id)
                    self.manager.smart_delay.on_failure()
                self.manager.smart_delay.wait()
            except requests.exceptions.HTTPError as e_http:
                self.log_signal.emit(f"API: 删除 UID:{talker_id} 会话HTTP错误: {e_http.response.status_code}")
                failed_ids_api.append(talker_id)
                self.manager.smart_delay.on_failure()
            except Exception as e:
                self.log_signal.emit(f"API: 删除 UID:{talker_id} 会话时发生未知错误: {e}")
                failed_ids_api.append(talker_id)
                self.manager.smart_delay.on_failure()

        unprocessed_count = len(talker_ids) - len(successfully_deleted_ids) - len(failed_ids_api)

        self.log_signal.emit(f"API删除操作完成。成功: {deleted_count_api}，失败: {len(failed_ids_api)}，未处理: {unprocessed_count}")
        if failed_ids_api:
            self.log_signal.emit(f"API删除失败的UID: {', '.join(map(str, failed_ids_api))}")

        if successfully_deleted_ids:
            # 只删除成功删除的会话对应的消息
            self.manager.messages = [m for m in self.manager.messages if m['talker_id'] not in successfully_deleted_ids]
            self.manager.cache.messages = self.manager.messages
            self.manager.cache.save_cache()
            self.log_signal.emit(f"本地消息列表已更新，删除了 {len(successfully_deleted_ids)} 个会话的消息。")

        self.update_ui_signal.emit()


class MessageManagerScreen(QWidget):
    """Bilibili 私信管理工具主界面"""

    back_to_tools = pyqtSignal()
    window_closed = pyqtSignal()

    def __init__(self, api_service: ApiService):
        super().__init__()
        self.api_service = api_service
        self.api_base = "https://api.vc.bilibili.com"

        # 设置请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://message.bilibili.com/'
        }

        # 设置cookies
        self.cookies = {}
        if api_service:
            self._setup_cookies()

        # 初始化其他组件
        self.cache = MessageCache()
        self.messages = self.cache.get_messages()
        self.filtered_messages = []  # 用于搜索过滤
        self.smart_delay = SmartDelay()

        # 统计数据
        self.stats_data = defaultdict(lambda: {'sent': 0, 'received': 0, 'total': 0})

        # 线程管理
        self.fetch_thread = None
        self.operation_thread = None

        self.init_ui()
        self.update_message_display()

        logger.info("私信管理界面初始化完成")

    def _setup_cookies(self):
        """设置cookies"""
        try:
            cookie_str = self.api_service.cookie
            for item in cookie_str.split(';'):
                item = item.strip()
                if not item:
                    continue
                parts = item.split('=', 1)
                if len(parts) == 2:
                    self.cookies[parts[0].strip()] = parts[1].strip()

            logger.info("Cookies设置完成")
        except Exception as e:
            logger.error(f"设置cookies失败: {e}")

    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 顶部工具栏
        self.create_toolbar(layout)

        # 主要内容区域
        self.create_main_content(layout)

        # 底部操作区域
        self.create_bottom_area(layout)

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
        title_label = QLabel("私信管理工具")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #ecf0f1;")
        toolbar_layout.addWidget(title_label)

        toolbar_layout.addStretch()

        # 操作按钮
        self.fetch_all_btn = QPushButton("获取全部")
        self.fetch_all_btn.clicked.connect(self.fetch_all_messages)
        self.fetch_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 15px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        toolbar_layout.addWidget(self.fetch_all_btn)

        self.fetch_new_btn = QPushButton("获取新消息")
        self.fetch_new_btn.clicked.connect(self.fetch_new_messages)
        self.fetch_new_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px 15px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        toolbar_layout.addWidget(self.fetch_new_btn)

        self.stop_fetch_btn = QPushButton("停止获取")
        self.stop_fetch_btn.clicked.connect(self.stop_fetch)
        self.stop_fetch_btn.setEnabled(False)
        self.stop_fetch_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 8px 15px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        toolbar_layout.addWidget(self.stop_fetch_btn)

        self.clear_cache_btn = QPushButton("清空缓存")
        self.clear_cache_btn.clicked.connect(self.clear_cache)
        self.clear_cache_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                padding: 8px 15px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        toolbar_layout.addWidget(self.clear_cache_btn)

        layout.addLayout(toolbar_layout)

    def create_main_content(self, layout):
        """创建主要内容区域"""
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(5)

        # 左侧：搜索和消息列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 搜索区域
        search_frame = QFrame()
        search_frame.setObjectName("searchFrame")
        search_frame.setFrameStyle(QFrame.Shape.Box)
        search_layout = QHBoxLayout(search_frame)

        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("搜索消息内容或UID...")
        self.search_entry.returnPressed.connect(self.search_messages)
        search_layout.addWidget(self.search_entry)

        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self.search_messages)
        search_layout.addWidget(search_btn)

        clear_search_btn = QPushButton("清除")
        clear_search_btn.clicked.connect(self.clear_search)
        search_layout.addWidget(clear_search_btn)

        self.search_content_cb = QCheckBox("内容")
        self.search_content_cb.setChecked(True)
        search_layout.addWidget(self.search_content_cb)

        self.search_uid_cb = QCheckBox("UID")
        self.search_uid_cb.setChecked(True)
        search_layout.addWidget(self.search_uid_cb)

        left_layout.addWidget(search_frame)

        # 消息列表
        list_label = QLabel(f"消息列表 (双击查看完整对话) - 共 {len(self.messages)} 条")
        list_label.setStyleSheet("font-weight: bold; color: #ecf0f1; padding: 5px;")
        left_layout.addWidget(list_label)
        self.list_label = list_label

        self.message_tree = QTreeWidget()
        self.message_tree.setHeaderLabels(["时间", "发送者", "内容概要", "状态"])
        self.message_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.message_tree.itemDoubleClicked.connect(self.show_conversation_details)

        # 设置列宽
        header = self.message_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.message_tree.setColumnWidth(0, 200)
        self.message_tree.setColumnWidth(1, 150)
        self.message_tree.setColumnWidth(3, 20)


        left_layout.addWidget(self.message_tree)

        main_layout.addWidget(left_widget, 2)

        # 右侧：日志区域
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0 , 0,0, 0)

        log_label = QLabel("操作日志")
        log_label.setStyleSheet("font-weight: bold; color: #ecf0f1; padding: 5px;")
        right_layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(600)
        self.log_text.setReadOnly(True)
        right_layout.addWidget(self.log_text)

        main_layout.addWidget(right_widget)

        layout.addWidget(main_widget)

    def create_bottom_area(self, layout):
        """创建底部操作区域"""
        bottom_frame = QFrame()
        bottom_frame.setObjectName("bottomControlFrame")
        bottom_frame.setFrameStyle(QFrame.Shape.Box)

        bottom_layout = QHBoxLayout(bottom_frame)

        # 选择操作
        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(self.select_all)
        bottom_layout.addWidget(select_all_btn)

        inverse_select_btn = QPushButton("反选")
        inverse_select_btn.clicked.connect(self.inverse_select)
        bottom_layout.addWidget(inverse_select_btn)

        bottom_layout.addStretch()

        # 批量操作
        mark_read_btn = QPushButton("标记已读")
        mark_read_btn.clicked.connect(self.mark_as_read)
        mark_read_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px 15px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #229954;
            }
        """)
        bottom_layout.addWidget(mark_read_btn)

        batch_delete_btn = QPushButton("批量删除")
        batch_delete_btn.clicked.connect(self.batch_delete)
        batch_delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 8px 15px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        bottom_layout.addWidget(batch_delete_btn)

        self.stop_operation_btn = QPushButton("停止操作")
        self.stop_operation_btn.clicked.connect(self.stop_operation)
        self.stop_operation_btn.setEnabled(False)
        self.stop_operation_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                padding: 8px 15px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        bottom_layout.addWidget(self.stop_operation_btn)

        layout.addWidget(bottom_frame)

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def fetch_all_messages(self):
        """获取全部消息"""
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.log("正在获取消息中，请勿重复点击。")
            return

        # 检查是否有断点
        last_time = self.cache.get_formatted_last_time()
        if last_time:
            reply = QMessageBox.question(
                self, "获取方式",
                f"检测到上次获取进度（{last_time}）。\n\n"
                "是(Yes): 从上次位置继续获取更早的消息\n"
                "否(No): 清空缓存，从最新消息开始重新获取\n"
                "取消(Cancel): 取消操作",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.No:
                self.cache.clear()
                self.messages = []
                self.log("已清空消息缓存，将从最新消息开始获取")
            else:
                self.log(f"将从上次断点（{last_time}）继续获取更早的消息")
        elif self.messages:
            reply = QMessageBox.question(
                self, "提示",
                "看起来您已经获取了所有消息。\n\n是否清空缓存并重新获取？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
            self.cache.clear()
            self.messages = []
            self.log("已清空消息缓存，将重新获取所有消息")

        self.start_fetch_thread("all")

    def fetch_new_messages(self):
        """获取新消息"""
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.log("正在获取消息中，请勿重复点击。")
            return

        if not self.messages:
            self.log("没有缓存消息，请先使用'获取全部'功能。")
            return

        self.start_fetch_thread("new")

    def start_fetch_thread(self, fetch_type):
        """启动获取线程"""
        self.fetch_thread = MessageFetchThread(self, fetch_type)
        self.fetch_thread.log_signal.connect(self.log)
        self.fetch_thread.finished_signal.connect(self.on_fetch_finished)
        self.fetch_thread.update_ui_signal.connect(self.update_message_display)

        # 更新按钮状态
        self.fetch_all_btn.setEnabled(False)
        self.fetch_new_btn.setEnabled(False)
        self.stop_fetch_btn.setEnabled(True)

        self.fetch_thread.start()
        self.log("开始获取消息...")

    def stop_fetch(self):
        """停止获取"""
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetch_thread.stop()
            self.log("发送停止获取信号...")

    def on_fetch_finished(self):
        """获取完成"""
        self.fetch_all_btn.setEnabled(True)
        self.fetch_new_btn.setEnabled(True)
        self.stop_fetch_btn.setEnabled(False)
        self.update_message_display()

    def clear_cache(self):
        """清空缓存"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有消息缓存吗？\n这将删除所有已获取的消息记录。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.cache.clear()
            self.messages = []
            self.update_message_display()
            self.log("已清空所有消息缓存")

    def search_messages(self):
        """搜索消息"""

        keyword = self.search_entry.text().strip()
        if not keyword:
            self.clear_search()
            return

        self.filtered_messages = []
        search_content = self.search_content_cb.isChecked()
        search_uid = self.search_uid_cb.isChecked()

        for msg in self.messages:
            if search_content and keyword.lower() in msg['content'].lower():
                self.filtered_messages.append(msg)
            elif search_uid and keyword in str(msg['sender_uid']):
                self.filtered_messages.append(msg)

        self.log(f"搜索 '{keyword}' 找到 {len(self.filtered_messages)} 条消息")
        self.update_message_display(use_filtered=True)

    def clear_search(self):
        """清除搜索"""
        self.search_entry.clear()
        self.filtered_messages = []
        self.update_message_display()
        self.log("已清除搜索过滤")

    def update_message_display(self, use_filtered=False):
        """更新消息显示"""
        self.message_tree.clear()

        messages_to_show = self.filtered_messages if use_filtered else self.messages

        # 更新标签
        total_count = len(self.messages)
        shown_count = len(messages_to_show)
        if use_filtered:
            self.list_label.setText(f"消息列表 (双击查看完整对话) - 显示 {shown_count}/{total_count} 条")
        else:
            self.list_label.setText(f"消息列表 (双击查看完整对话) - 共 {total_count} 条")

        # 按时间排序
        messages_to_show.sort(key=lambda m: m['timestamp'], reverse=True)
        # 对视频推送消息进行折叠处理
        if not use_filtered:  # 只在非搜索状态下折叠
            collapsed_messages = []
            video_push_latest = {}  # 记录每个UID最新的视频推送消息

            for msg_data in messages_to_show:
                msg_type = msg_data.get('msg_type', 0)
                sender_uid = msg_data.get('sender_uid', 0)

                # 检查是否为视频推送消息
                is_video_push = False
                if msg_type == 11:
                    try:
                        # 使用原始content数据进行判断
                        raw_content = msg_data.get('raw_content', '')
                        if raw_content:
                            content_data = json.loads(raw_content)
                            if 'bvid' in content_data and 'title' in content_data:
                                is_video_push = True
                    except:
                        pass

                if is_video_push:
                    # 对于视频推送消息，只保留每个UID的最新一条
                    if sender_uid not in video_push_latest:
                        video_push_latest[sender_uid] = msg_data
                        collapsed_messages.append(msg_data)
                else:
                    # 非视频推送消息，正常添加
                    collapsed_messages.append(msg_data)

            messages_to_show = collapsed_messages

        for msg_data in messages_to_show:
            try:
                ts = self.normalize_timestamp(msg_data['timestamp'])
                time_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

                # 处理内容摘要
                content_summary = msg_data['content'][:100] + '...' if len(msg_data['content']) > 100 else msg_data['content']

                # 获取消息状态
                msg_status = msg_data.get('msg_status', 0)
                is_unread = msg_data.get('is_unread', False)

                # 构建状态文本
                status_parts = []
                if msg_status != 0:
                    status_parts.append(self._get_status_text(msg_status))
                if is_unread:
                    status_parts.append("未读")

                status_text = " | ".join(status_parts) if status_parts else "已读"

                # 发送者显示
                sender_uid_display = f"UID: {msg_data['sender_uid']}"

                # 创建树形项
                item = QTreeWidgetItem([time_str, sender_uid_display, content_summary, status_text])
                item.setData(0, Qt.ItemDataRole.UserRole, msg_data['msg_seqno'])

                # 标记是否为折叠的视频推送消息
                is_collapsed_video = False
                if msg_data.get('msg_type') == 11:
                    try:
                        content_data = json.loads(msg_data.get('content', '{}'))
                        if 'bvid' in content_data and 'title' in content_data:
                            is_collapsed_video = True
                            # 在内容概要前添加折叠标识
                            current_text = item.text(2)
                            item.setText(2, f"📁 [已折叠] {current_text}")
                    except:
                        pass

                item.setData(1, Qt.ItemDataRole.UserRole, is_collapsed_video)  # 存储折叠标识

                # 设置样式
                if msg_status in [1, 2]:  # 撤回的消息
                    for col in range(4):
                        item.setForeground(col, Qt.GlobalColor.gray)
                elif is_unread:  # 未读消息
                    font = QFont()
                    font.setBold(True)
                    # 设置未读消息为橙色加粗
                    from PyQt6.QtGui import QBrush
                    unread_color = QBrush(QColor(240,230,140))
                    for col in range(4):
                        item.setFont(col, font)
                        item.setForeground(col, unread_color)

                self.message_tree.addTopLevelItem(item)
            except Exception as e:
                logger.error(f"显示消息时出错: {e}")
                continue

        self.log(f"显示 {len(messages_to_show)} 条消息")

    def normalize_timestamp(self, ts):
        """标准化时间戳为秒级"""
        if ts > 1e10:  # 如果是毫秒级时间戳
            return ts / 1000
        return ts

    def select_all(self):
        """全选"""
        for i in range(self.message_tree.topLevelItemCount()):
            item = self.message_tree.topLevelItem(i)
            item.setSelected(True)

    def inverse_select(self):
        """反选"""
        for i in range(self.message_tree.topLevelItemCount()):
            item = self.message_tree.topLevelItem(i)
            item.setSelected(not item.isSelected())

    def mark_as_read(self):
        """标记已读"""
        if self.operation_thread and self.operation_thread.isRunning():
            self.log("正在进行其他操作，请稍后再试。")
            return

        selected_items = self.message_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请先选择要标记的消息所在的会话 (Ctrl+单击可多选)")
            return

        talker_ids_seqnos = {}
        for item in selected_items:
            try:
                seqno = item.data(0, Qt.ItemDataRole.UserRole)
                msg = next((m for m in self.messages if m['msg_seqno'] == seqno), None)
                if msg:
                    tid = msg['talker_id']
                    if tid not in talker_ids_seqnos or seqno > talker_ids_seqnos[tid]:
                        talker_ids_seqnos[tid] = seqno
            except:
                continue

        if not talker_ids_seqnos:
            QMessageBox.warning(self, "提示", "无法从选定项确定会话信息。")
            return

        self.start_operation_thread("mark_read", talker_ids_seqnos)

    def batch_delete(self):
        """批量删除"""
        if self.operation_thread and self.operation_thread.isRunning():
            self.log("正在进行其他操作，请稍后再试。")
            return

        selected_items = self.message_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "提示", "请先选择要删除的消息所在的会话 (Ctrl+单击可多选)")
            return

        talker_ids_to_delete = set()
        for item in selected_items:
            try:
                seqno = item.data(0, Qt.ItemDataRole.UserRole)
                msg = next((m for m in self.messages if m['msg_seqno'] == seqno), None)
                if msg:
                    talker_ids_to_delete.add(msg['talker_id'])
            except:
                continue

        if not talker_ids_to_delete:
            QMessageBox.warning(self, "提示", "无法从选定项确定要删除的会话。")
            return

        num_del = len(talker_ids_to_delete)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除与这 {num_del} 个UID的所有会话记录吗？\n此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.start_operation_thread("batch_delete", list(talker_ids_to_delete))

    def start_operation_thread(self, operation_type, data):
        """启动操作线程"""
        self.operation_thread = OperationThread(self, operation_type, data)
        self.operation_thread.log_signal.connect(self.log)
        self.operation_thread.finished_signal.connect(self.on_operation_finished)
        self.operation_thread.update_ui_signal.connect(self.update_message_display)

        # 更新按钮状态
        self.stop_operation_btn.setEnabled(True)

        self.operation_thread.start()

        if operation_type == "mark_read":
            self.log(f"准备标记 {len(data)} 个会话为已读...")
        elif operation_type == "batch_delete":
            self.log(f"准备通过API删除 {len(data)} 个会话...")

    def stop_operation(self):
        """停止操作"""
        if self.operation_thread and self.operation_thread.isRunning():
            self.operation_thread.stop()
            self.log("发送停止操作信号...")

    def on_operation_finished(self):
        """操作完成"""
        self.stop_operation_btn.setEnabled(False)

    def show_conversation_details(self, item):
        """显示完整对话详情"""
        try:
            msg_seqno_to_find = item.data(0, Qt.ItemDataRole.UserRole)
            is_collapsed_video = item.data(1, Qt.ItemDataRole.UserRole)
        except:
            return

        clicked_message = next((msg for msg in self.messages if msg['msg_seqno'] == msg_seqno_to_find), None)
        if not clicked_message:
            QMessageBox.information(self, "详情", "未找到该消息的详细数据。")
            return

        target_talker_id = clicked_message['talker_id']

        # 如果是折叠的视频推送消息，只显示该UID的视频推送消息
        if is_collapsed_video:
            conversation_messages = []
            for msg in self.messages:
                if msg['talker_id'] == target_talker_id and msg.get('msg_type') == 11:
                    try:
                        # 使用原始content数据进行判断
                        raw_content = msg.get('raw_content', '')
                        if raw_content:
                            content_data = json.loads(raw_content)
                            if 'bvid' in content_data and 'title' in content_data:
                                conversation_messages.append(msg)
                    except:
                        pass
        else:
            # 正常情况，显示所有消息
            conversation_messages = [msg for msg in self.messages if msg['talker_id'] == target_talker_id]

        conversation_messages.sort(key=lambda m: m['timestamp'])

        # 创建对话详情窗口
        detail_dialog = ConversationDetailDialog(self, target_talker_id, conversation_messages)
        detail_dialog.exec()

    def _parse_message_content(self, msg):
        """增强的消息内容解析"""
        msg_type = msg['msg_type']
        content_str = msg.get('content', '')

        # 消息类型处理器
        type_handlers = {
            1: self._parse_text_message,
            2: self._parse_image_message,
            3: self._parse_video_message,
            4: self._parse_emoticon_message,
            5: self._parse_recall_message,
            6: self._parse_share_message,
            7: self._parse_audio_message,
            10: self._parse_official_message,
            11: self._parse_notification_message,
            18: self._parse_interactive_message,
        }

        handler = type_handlers.get(msg_type, self._parse_unknown_message)
        try:
            return handler(content_str, msg)
        except Exception as e:
            logger.error(f"解析消息类型 {msg_type} 时出错: {e}")
            return f"[消息类型 {msg_type} 解析错误]"

    def _parse_text_message(self, content_str, msg):
        """解析文本消息"""
        try:
            data = json.loads(content_str)
            return data.get('content', content_str)
        except:
            return content_str

    def _parse_image_message(self, content_str, msg):
        """增强的图片消息解析"""
        try:
            data = json.loads(content_str)
            width = data.get('width', 0)
            height = data.get('height', 0)
            imageType = data.get('imageType', '')
            size = data.get('size', 0)

            desc_parts = ['[图片']
            if width and height:
                desc_parts.append(f"{width}x{height}")
            if imageType:
                desc_parts.append(f"{imageType.upper()}")
            if size:
                size_mb = size / (1024 * 1024)
                desc_parts.append(f"{size_mb:.1f}MB")

            return ' '.join(desc_parts) + ']'
        except:
            return "[图片消息]"

    def _parse_video_message(self, content_str, msg):
        """解析视频消息"""
        try:
            data = json.loads(content_str)
            title = data.get('title', '视频')
            duration = data.get('duration', 0)
            return f"[视频: {title} ({duration}秒)]"
        except:
            return "[视频消息]"

    def _parse_emoticon_message(self, content_str, msg):
        """解析表情消息"""
        try:
            data = json.loads(content_str)
            text = data.get('text', '')
            return f"[表情: {text}]" if text else "[表情]"
        except:
            return "[表情消息]"

    def _parse_recall_message(self, content_str, msg):
        """解析撤回消息"""
        try:
            if content_str:
                data = json.loads(content_str)
                if 'content' in data:
                    return f"[消息已撤回，原内容: {data['content'][:20]}...]"
        except:
            pass
        return "[该消息已被撤回]"

    def _parse_share_message(self, content_str, msg):
        """解析分享消息"""
        try:
            data = json.loads(content_str)
            title = data.get('title', '')
            return f"[分享: {title}]" if title else "[分享消息]"
        except:
            return "[分享消息]"

    def _parse_audio_message(self, content_str, msg):
        """解析语音消息"""
        try:
            data = json.loads(content_str)
            duration = data.get('duration', 0)
            return f"[语音消息: {duration}秒]"
        except:
            return "[语音消息]"

    def _parse_official_message(self, content_str, msg):
        """解析官方消息"""
        try:
            data = json.loads(content_str)
            title = (data.get('title') or
                     data.get('template', {}).get('title') or
                     data.get('content', {}).get('title') or
                     data.get('card', {}).get('title'))

            desc = (data.get('desc') or
                    data.get('template', {}).get('desc') or
                    data.get('content', {}).get('desc') or
                    data.get('card', {}).get('desc'))

            if title and desc:
                return f"[官方消息: {title} - {desc[:30]}...]"
            elif title:
                return f"[官方消息: {title}]"
            else:
                return "[官方消息]"
        except:
            return "[官方消息]"

    def _parse_notification_message(self, content_str, msg):
        """解析通知消息"""
        try:
            data = json.loads(content_str)

            # 检查是否为视频推送消息（有bvid和title字段）
            if 'bvid' in data and 'title' in data:
                return self._parse_video_push_message(content_str, msg)

            # 普通通知消息
            text = data.get('text', '')
            return f"[通知: {text}]" if text else "[通知消息]"
        except:
            return "[通知消息]"

    def _parse_interactive_message(self, content_str, msg):
        """解析互动消息"""
        try:
            data = json.loads(content_str)
            text = data.get('text', '')
            title = data.get('title', '')
            return f"[互动: {title or text}]" if (title or text) else "[互动消息]"
        except:
            return "[互动消息]"

    def _parse_video_push_message(self, content_str, msg):
        """解析视频推送消息"""
        try:
            data = json.loads(content_str)
            title = data.get('title', '')
            times = data.get('times', 0)
            bvid = data.get('bvid', '')

            # 安全获取可能为None的字段
            desc = data.get('desc', '') or ''
            cover = data.get('cover', '') or ''

            # 修复attach_msg的获取方式
            attach_msg_obj = data.get('attach_msg')
            attach_msg = ''
            if attach_msg_obj and isinstance(attach_msg_obj, dict):
                attach_msg = attach_msg_obj.get('content', '') or ''

            # 格式化时长
            if times > 0:
                if times >= 3600:
                    hours = times // 3600
                    minutes = (times % 3600) // 60
                    seconds = times % 60
                    duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    minutes = times // 60
                    seconds = times % 60
                    duration_str = f"{minutes}:{seconds:02d}"
            else:
                duration_str = "0:00"

            # 构建消息内容 - 重点是文字内容和链接
            result_parts = []
            result_parts.append(f"📺《{title}》({duration_str})")

            if desc:
                desc_display = desc[:60] + "..." if len(desc) > 60 else desc
                result_parts.append(f"📝 {desc_display}")

            if attach_msg:
                result_parts.append(f"💬 {attach_msg}")

            # 视频链接
            if bvid:
                video_url = f"https://www.bilibili.com/video/{bvid}"
                result_parts.append(f"🔗 {video_url}")

            # 封面图片链接
            if cover:
                result_parts.append(f"🖼️ {cover}")

            return "\n".join(result_parts)

        except Exception as e:
            logger.error(f"解析视频推送消息时出错: {e}")
            return "[视频推送消息解析错误]"


    def _parse_unknown_message(self, content_str, msg):
        """解析未知类型消息"""
        msg_type = msg.get('msg_type', 'Unknown')
        try:
            data = json.loads(content_str)
            for key in ['content', 'text', 'title', 'message', 'desc']:
                if key in data and data[key]:
                    return f"[类型{msg_type}: {str(data[key])[:50]}...]"
            return f"[未知消息类型 {msg_type}]"
        except:
            if content_str:
                return f"[类型{msg_type}: {content_str[:30]}...]"
            return f"[未知消息类型 {msg_type}]"

    def _extract_image_url(self, msg_json):
        """尝试从消息数据中提取图片URL"""
        try:
            content_str = msg_json.get('content', '')
            if not content_str:
                return None

            data = json.loads(content_str)

            possible_paths = [
                lambda d: d.get('url'),
                lambda d: d.get('image_url'),
                lambda d: d.get('pic_url'),
                lambda d: d.get('pictures', [{}])[0].get('img_src') if d.get('pictures') else None,
                lambda d: d.get('image', {}).get('url'),
                lambda d: d.get('img', {}).get('src'),
            ]

            for path_func in possible_paths:
                url = path_func(data)
                if url:
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif not url.startswith('http'):
                        url = 'https://' + url
                    return url

        except Exception as e:
            logger.error(f"提取图片URL时出错: {e}")

        return None

    def _get_status_text(self, status):
        """获取消息状态文本"""
        return {
            0: "正常",
            1: "已撤回",
            2: "系统撤回",
            4: "发送中",
            50: "无效图片"
        }.get(status, f"未知({status})")

    def closeEvent(self, event):
        """窗口关闭时清理"""
        # 停止所有线程
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetch_thread.stop()
            self.fetch_thread.wait(2000)

        if self.operation_thread and self.operation_thread.isRunning():
            self.operation_thread.stop()
            self.operation_thread.wait(2000)

        self.window_closed.emit()
        super().closeEvent(event)


class ConversationDetailDialog(QDialog):
    """对话详情对话框"""

    def __init__(self, parent, talker_id, conversation_messages):
        super().__init__(parent)
        self.talker_id = talker_id
        self.conversation_messages = conversation_messages

        self.setWindowTitle(f"与 UID:{talker_id} 的完整对话")
        self.setGeometry(200, 200, 800, 600)

        self.init_ui()
        # 设置窗口属性，防止意外关闭
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setModal(False)  # 设置为非模态对话框
        self.load_conversation()

    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)

        # 对话内容
        # 对话内容 - 使用QTextBrowser支持链接点击
        self.text_area = QTextBrowser()
        self.text_area.setReadOnly(True)
        self.text_area.anchorClicked.connect(self.open_link)
        # 防止链接点击后内容丢失
        self.text_area.setOpenLinks(False)  # 禁用默认链接处理
        self.text_area.setOpenExternalLinks(False)  # 禁用外部链接自动打开

        layout.addWidget(self.text_area)

        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def load_conversation(self):
        """加载对话内容"""
        # 保存当前内容（如果有的话）
        current_content = self.text_area.toHtml() if hasattr(self, 'text_area') else ""
        self.text_area.clear()

        for msg in self.conversation_messages:
            try:
                ts = self.normalize_timestamp(msg['timestamp'])
                time_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
                sender_display = f"UID: {msg['sender_uid']}"

                # 获取消息状态
                status = msg.get('msg_status', 0)
                is_unread = msg.get('is_unread', False)
                status_text = self.get_status_text(status)

                # 显示发送者和时间
                if msg['sender_uid'] == self.talker_id:
                    self.text_area.setTextColor(Qt.GlobalColor.green)
                else:
                    self.text_area.setTextColor(Qt.GlobalColor.blue)

                self.text_area.insertPlainText(f"{sender_display} ")

                self.text_area.setTextColor(Qt.GlobalColor.gray)
                self.text_area.insertPlainText(f"({time_str})")

                # 显示消息状态
                if status != 0:
                    if status in [1, 2]:
                        self.text_area.setTextColor(Qt.GlobalColor.red)
                        self.text_area.insertPlainText(f" [{status_text}]")
                    else:
                        self.text_area.setTextColor(Qt.GlobalColor.gray)
                        self.text_area.insertPlainText(f" [{status_text}]")
                elif is_unread:
                    self.text_area.setTextColor(Qt.GlobalColor.yellow)
                    self.text_area.insertPlainText(" [未读]")

                self.text_area.setTextColor(Qt.GlobalColor.gray)
                self.text_area.insertPlainText(":\n")

                # 处理消息内容
                content = msg['content']
                self.text_area.setTextColor(Qt.GlobalColor.white)

                # 检查是否为视频推送消息
                if msg.get('msg_type') == 11:
                    try:
                        import json
                        data = json.loads(content)
                        if 'bvid' in data and 'title' in data:
                            # 格式化视频推送消息在详情窗口的显示
                            formatted_content = self._format_video_push_for_detail(content)
                            self.text_area.insertHtml(formatted_content + "<br>")
                        else:
                            # 普通通知消息
                            processed_content = self._process_links_in_content(content)
                            self.text_area.insertHtml(processed_content + "<br>")
                    except:
                        processed_content = self._process_links_in_content(content)
                        self.text_area.insertHtml(processed_content + "<br>")
                elif msg.get('msg_type') == 2 or '[图片' in content:
                    # 图片消息
                    self.text_area.insertPlainText(content + "\n")
                    if 'image_url' in msg:
                        image_url = msg['image_url']
                        link_html = f'<a href="{image_url}" style="color: cyan; text-decoration: underline;">🔗 图片链接: {image_url}</a><br>'
                        self.text_area.insertHtml(link_html)
                else:
                    # 普通消息，检查是否包含链接
                    processed_content = self._process_links_in_content(content)
                    self.text_area.insertHtml(processed_content + "<br>")

                self.text_area.insertPlainText("\n")

            except Exception as e:
                logger.error(f"显示对话消息时出错: {e}")
                continue

    def normalize_timestamp(self, ts):
        """标准化时间戳为秒级"""
        if ts > 1e10:
            return ts / 1000
        return ts

    def get_status_text(self, status):
        """获取消息状态文本"""
        return {
            0: "正常",
            1: "已撤回",
            2: "系统撤回",
            4: "发送中",
            50: "无效图片"
        }.get(status, f"未知({status})")

    def _format_video_push_for_detail(self, content):
        """在详情窗口格式化视频推送消息"""
        try:
            import json
            data = json.loads(content)

            title = data.get('title', '')
            times = data.get('times', 0)
            desc = data.get('desc', '')
            cover = data.get('cover', '')
            bvid = data.get('bvid', '')
            attach_msg = data.get('attach_msg', {}).get('content', '')

            # 格式化时长
            if times > 0:
                if times >= 3600:
                    hours = times // 3600
                    minutes = (times % 3600) // 60
                    seconds = times % 60
                    duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                else:
                    minutes = times // 60
                    seconds = times % 60
                    duration_str = f"{minutes}:{seconds:02d}"
            else:
                duration_str = "0:00"

            # 构建HTML格式的内容
            html_parts = []
            html_parts.append(
                '<div style="margin: 8px 0; padding: 8px; background-color: #2c3e50; border-radius: 6px; border-left: 4px solid #3498db;">')
            html_parts.append(f'<p style="color: #3498db; margin: 3px 0; font-weight: bold;">📺 {title}</p>')
            html_parts.append(f'<p style="color: #e74c3c; margin: 3px 0; font-size: 14px;">⏱️ {duration_str}</p>')

            if desc:
                html_parts.append(f'<p style="color: #95a5a6; margin: 3px 0; font-size: 13px;">📝 {desc}</p>')

            if attach_msg:
                html_parts.append(f'<p style="color: #f39c12; margin: 3px 0; font-size: 13px;">💬 {attach_msg}</p>')

            # 重点显示的链接
            if bvid:
                video_url = f"https://www.bilibili.com/video/{bvid}"
                html_parts.append(
                    f'<p style="margin: 3px 0;"><strong style="color: #1abc9c;">🔗 视频:</strong> <a href="{video_url}" style="color: #1abc9c; text-decoration: underline; font-weight: bold;">{video_url}</a></p>')

            if cover:
                html_parts.append(
                    f'<p style="margin: 3px 0;"><strong style="color: #1abc9c;">🖼️ 封面:</strong> <a href="{cover}" style="color: #1abc9c; text-decoration: underline; font-weight: bold;">{cover}</a></p>')

            html_parts.append('</div>')

            return ''.join(html_parts)
        except:
            return f'<p style="color: #e74c3c;">[视频推送消息格式化失败]</p>'

    def _process_links_in_content(self, content):
        """处理消息内容中的链接，将其转换为可点击的HTML链接"""
        import re
        # 定义各种链接的正则表达式
        url_pattern = r'(https?://[^\s\u4e00-\u9fa5]+)'  # 匹配http/https链接，避免匹配中文

        def replace_url(match):
            url = match.group(1)
            # 移除末尾可能的标点符号
            while url and url[-1] in '.,;!?。，；！？':
                url = url[:-1]
            return f'<a href="{url}" style="color: cyan; text-decoration: underline;">{url}</a>'

        # 先转义HTML特殊字符，但保留换行
        content = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # 替换链接
        content = re.sub(url_pattern, replace_url, content)

        # 处理换行
        content = content.replace('\n', '<br>')

        return content

    def open_link(self, url):
        """打开链接"""
        try:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl

            # 确保URL是字符串格式
            if isinstance(url, QUrl):
                url_str = url.toString()
            else:
                url_str = str(url)

            logger.info(f"准备打开链接: {url_str}")

            # 使用QDesktopServices打开链接
            result = QDesktopServices.openUrl(QUrl(url_str))

            if result:
                logger.info(f"成功打开链接: {url_str}")
            else:
                logger.warning(f"打开链接可能失败: {url_str}")

        except Exception as e:
            logger.error(f"打开链接失败: {e}")
            # 显示错误消息但不关闭对话框
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "打开链接失败", f"无法打开链接: {e}")