import logging
import time
from typing import Dict, List, Optional, Tuple, Any, Callable, Union
from datetime import datetime
from .manager import DatabaseManager
from .models import CommentRecord, DanmuRecord, NotifyRecord, SyncCursor
from ..types import Comment, Danmu, Notify, ActivityInfo

logger = logging.getLogger(__name__)

class IncrementalFetcher:
    """增量数据获取器"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def get_last_sync_cursor(self, uid: int, data_type: str) -> Optional[SyncCursor]:
        """获取上次同步的游标"""
        return self.db.get_cursor(uid, data_type)

    def save_sync_cursor(self, uid: int, data_type: str, cursor_id: Optional[int] = None,
                         cursor_time: Optional[int] = None, extra_data: Dict[str, Any] = None):
        """保存同步游标"""
        cursor = SyncCursor(
            uid=uid,
            data_type=data_type,
            cursor_id=cursor_id,
            cursor_time=cursor_time,
            last_sync=int(time.time()),
            extra_data=str(extra_data or {})
        )
        self.db.save_cursor(cursor)

    def extract_time_from_api_data(self, item: Dict[str, Any], data_type: str) -> int:
        """从API数据中提取时间戳"""
        try:
            if data_type == "liked":
                return item.get("like_time", 0)
            elif data_type == "replied":
                return item.get("reply_time", 0)
            elif data_type == "ated":
                return item.get("at_time", 0)
            elif data_type == "system_notify":
                time_str = item.get("time_at", "")
                if time_str:
                    # 解析 "2025-05-27 07:01:00" 格式
                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    return int(dt.timestamp())
                return 0
            elif data_type == "aicu_comments":
                return item.get("time", 0)
            elif data_type == "aicu_danmus":
                return item.get("ctime", 0)
            else:
                return 0
        except Exception as e:
            logger.warning(f"提取时间戳失败: {e}")
            return 0

    def get_latest_timestamp(self, uid: int, data_type: str) -> int:
        """获取数据库中最新的时间戳"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                if data_type in ["liked", "replied", "ated", "system_notify"]:
                    # 通知类数据
                    cursor.execute('''
                        SELECT MAX(created_time) FROM notifies 
                        WHERE uid = ? AND tp = ?
                    ''', (uid, self._get_notify_type(data_type)))
                elif data_type == "aicu_comments":
                    cursor.execute('''
                        SELECT MAX(created_time) FROM comments 
                        WHERE uid = ? AND source = 'aicu'
                    ''', (uid,))
                elif data_type == "aicu_danmus":
                    cursor.execute('''
                        SELECT MAX(created_time) FROM danmus 
                        WHERE uid = ? AND source = 'aicu'
                    ''', (uid,))
                else:
                    return 0

                result = cursor.fetchone()
                return result[0] if result[0] else 0
        except Exception as e:
            logger.error(f"获取最新时间戳失败: {e}")
            return 0

    def _get_notify_type(self, data_type: str) -> int:
        """获取通知类型对应的数字"""
        mapping = {
            "liked": 0,
            "replied": 1,
            "ated": 2,
            "system_notify": 4
        }
        return mapping.get(data_type, 0)

    def filter_new_items(self, items: List[Dict[str, Any]], data_type: str,
                         last_timestamp: int) -> List[Dict[str, Any]]:
        """过滤出新的数据项"""
        new_items = []
        for item in items:
            item_time = self.extract_time_from_api_data(item, data_type)
            if item_time > last_timestamp:
                new_items.append(item)

        logger.info(f"{data_type}: 总数据 {len(items)}, 新数据 {len(new_items)}")
        return new_items

    def should_continue_fetching(self, data_type: str, current_page_data: List[Dict[str, Any]],
                                 last_timestamp: int) -> bool:
        """判断是否应该继续获取数据"""
        if not current_page_data:
            return False

        # 检查当前页是否还有新数据
        has_new_data = False
        for item in current_page_data:
            item_time = self.extract_time_from_api_data(item, data_type)
            if item_time > last_timestamp:
                has_new_data = True
                break

        return has_new_data

    def build_incremental_url(self, base_url: str, data_type: str, cursor: Optional[SyncCursor]) -> str:
        """构建增量获取的URL"""
        if not cursor or not cursor.cursor_id:
            return base_url

        if data_type in ["liked", "replied", "ated"]:
            if cursor.cursor_id and cursor.cursor_time:
                separator = "&" if "?" in base_url else "?"
                return f"{base_url}{separator}id={cursor.cursor_id}&{data_type.rstrip('d')}_time={cursor.cursor_time}"
        elif data_type == "system_notify":
            if cursor.cursor_id:
                separator = "&" if "?" in base_url else "?"
                return f"{base_url}{separator}cursor={cursor.cursor_id}"
        elif data_type in ["aicu_comments", "aicu_danmus"]:
            # AICU API使用page参数
            if cursor.cursor_id:
                separator = "&" if "?" in base_url else "?"
                return f"{base_url}{separator}pn={cursor.cursor_id}"

        return base_url