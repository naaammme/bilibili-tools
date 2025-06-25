import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from .manager import DatabaseManager
from .models import CommentRecord, DanmuRecord, NotifyRecord, SyncCursor
from ..types import Comment, Danmu, Notify

logger = logging.getLogger(__name__)

class SyncManager:
    """数据同步管理器"""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def convert_comments_to_records(self, comments: Dict[int, Comment], uid: int,
                                    source: str = "bilibili") -> List[CommentRecord]:
        """将Comment对象转换为CommentRecord"""
        records = []
        current_time = int(time.time())

        for comment_id, comment in comments.items():
            # 使用评论对象自身的source属性，如果没有则使用默认值
            actual_source = getattr(comment, 'source', source)

            record = CommentRecord(
                id=comment_id,
                uid=uid,
                oid=comment.oid,
                type=comment.type,
                content=comment.content,
                notify_id=comment.notify_id,
                tp=comment.tp,
                source=actual_source,  # 使用实际的source
                created_time=getattr(comment, 'created_time', current_time),
                synced_time=current_time,
                video_uri = getattr(comment, 'video_uri', None),
                like_count=getattr(comment, 'like_count', 0)
            )
            records.append(record)

        return records
    def convert_danmus_to_records(self, danmus: Dict[int, Danmu], uid: int,
                                  source: str = "bilibili") -> List[DanmuRecord]:
        """将Danmu对象转换为DanmuRecord"""
        records = []
        current_time = int(time.time())

        bilibili_count = 0
        aicu_count = 0

        for danmu_id, danmu in danmus.items():
            # 使用弹幕对象自身的source属性，如果没有则使用默认值
            actual_source = getattr(danmu, 'source', source)

            if actual_source == "bilibili":
                bilibili_count += 1
            elif actual_source == "aicu":
                aicu_count += 1

            record = DanmuRecord(
                id=danmu_id,
                uid=uid,
                content=danmu.content,
                cid=danmu.cid,
                notify_id=danmu.notify_id,
                source=actual_source,  # 使用实际的source
                created_time=getattr(danmu, 'created_time', current_time),
                synced_time=current_time,
                video_url = getattr(danmu, 'video_url', None)
            )
            records.append(record)
        logger.info(f"保存弹幕到数据库: B站={bilibili_count}, AICU={aicu_count}, 总计={len(records)}")
        return records


    def convert_notifies_to_records(self, notifies: Dict[int, Notify], uid: int,
                                    source: str = "bilibili") -> List[NotifyRecord]:
        """将Notify对象转换为NotifyRecord"""
        records = []
        current_time = int(time.time())

        for notify_id, notify in notifies.items():
            # 使用通知对象自身的source属性，如果没有则使用默认值
            actual_source = getattr(notify, 'source', source)

            record = NotifyRecord(
                id=notify_id,
                uid=uid,
                content=notify.content,
                tp=notify.tp,
                system_notify_api=notify.system_notify_api,
                source=actual_source,  # 使用实际的source
                created_time=getattr(notify, 'created_time', current_time),
                synced_time=current_time
            )
            records.append(record)

        return records

    def convert_records_to_objects(self, comments: List[CommentRecord],
                                   danmus: List[DanmuRecord],
                                   notifies: List[NotifyRecord]) -> Tuple[
        Dict[int, Comment], Dict[int, Danmu], Dict[int, Notify]]:
        """将数据库记录转换回原始对象"""
        comment_dict = {}
        for record in comments:
            comment = Comment(
                oid=record.oid,
                type=record.type,
                content=record.content,
                is_selected=True,
                notify_id=record.notify_id,
                tp=record.tp
            )
            # 设置评论的source和时间信息
            comment.source = record.source
            comment.created_time = record.created_time
            comment.synced_time = record.synced_time
            # 恢复video_uri和like_count
            comment.video_uri = record.video_uri
            comment.like_count = record.like_count
            # ID是整数类型
            comment_dict[int(record.id)] = comment

        danmu_dict = {}
        bilibili_count = 0
        aicu_count = 0

        for record in danmus:
            danmu = Danmu(
                content=record.content,
                cid=record.cid,
                is_selected=True,
                notify_id=record.notify_id
            )
            # 重要：设置弹幕的source和时间信息
            danmu.source = record.source
            danmu.created_time = record.created_time
            danmu.synced_time = record.synced_time
            danmu.video_url = record.video_url

            if record.source == "bilibili":
                bilibili_count += 1
            elif record.source == "aicu":
                aicu_count += 1

            danmu_dict[record.id] = danmu

        logger.info(f"从数据库加载弹幕: B站={bilibili_count}, AICU={aicu_count}, 总计={len(danmu_dict)}")

        notify_dict = {}
        for record in notifies:
            notify = Notify(
                content=record.content,
                tp=record.tp,
                is_selected=True,
                system_notify_api=record.system_notify_api
            )
            # 设置通知的source和时间信息
            notify.source = record.source
            notify.created_time = record.created_time
            notify.synced_time = record.synced_time
            notify_dict[record.id] = notify

        return comment_dict, danmu_dict, notify_dict

    def load_from_database(self, uid: int) -> Tuple[Dict[int, Comment], Dict[int, Danmu], Dict[int, Notify]]:
        """从数据库加载数据"""
        logger.info(f"从数据库加载用户 {uid} 的数据")

        comments = self.db.get_comments(uid, limit=10000)
        danmus = self.db.get_danmus(uid, limit=10000)
        notifies = self.db.get_notifies(uid, limit=10000)

        logger.info(f"加载完成: {len(comments)} 评论, {len(danmus)} 弹幕, {len(notifies)} 通知")

        return self.convert_records_to_objects(comments, danmus, notifies)

    def save_to_database(self, uid: int, comments: Dict[int, Comment],
                         danmus: Dict[int, Danmu], notifies: Dict[int, Notify],
                         source: str = "bilibili"):
        """保存数据到数据库"""
        logger.info(f"保存用户 {uid} 的数据到数据库")

        comment_records = self.convert_comments_to_records(comments, uid, source)
        danmu_records = self.convert_danmus_to_records(danmus, uid, source)
        notify_records = self.convert_notifies_to_records(notifies, uid, source)

        self.db.save_comments(comment_records)
        self.db.save_danmus(danmu_records)
        self.db.save_notifies(notify_records)

        logger.info("数据保存完成")

    def mark_deleted(self, uid: int, deleted_ids: Dict[str, List[int]]):
        """标记已删除的项目"""
        for comment_id in deleted_ids.get('comments', []):
            self.db.mark_comment_deleted(comment_id, uid)

        for danmu_id in deleted_ids.get('danmus', []):
            self.db.mark_danmu_deleted(danmu_id, uid)

        for notify_id in deleted_ids.get('notifies', []):
            self.db.mark_notify_deleted(notify_id, uid)

    def update_sync_cursor(self, uid: int, data_type: str, cursor_id: Optional[int] = None,
                           cursor_time: Optional[int] = None, extra_data: Dict[str, Any] = None):
        """更新同步游标"""
        cursor = SyncCursor(
            uid=uid,
            data_type=data_type,
            cursor_id=cursor_id,
            cursor_time=cursor_time,
            last_sync=int(time.time()),
            extra_data=str(extra_data or {})
        )
        self.db.save_cursor(cursor)

    def get_sync_cursor(self, uid: int, data_type: str) -> Optional[SyncCursor]:
        """获取同步游标"""
        return self.db.get_cursor(uid, data_type)

    def parse_time_string(self, time_str: str) -> int:
        """解析时间字符串为时间戳"""
        try:
            # 解析 "2025-05-27 07:01:00" 格式
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            return int(dt.timestamp())
        except Exception as e:
            logger.warning(f"时间字符串解析失败: {time_str}, 错误: {e}")
            return int(time.time())

    def load_from_database_async(self, uid: int, progress_callback=None) -> Tuple[
        Dict[int, Comment], Dict[int, Danmu], Dict[int, Notify]]:
        """异步分批从数据库加载数据"""
        logger.info(f"开始异步加载用户 {uid} 的数据")

        all_comments = {}
        all_danmus = {}
        all_notifies = {}

        # 分批加载评论
        page = 1
        page_size = 1000
        total_comments = self.db.get_comments_count(uid)

        while True:
            if progress_callback:
                progress_callback(f"加载评论: {len(all_comments)}/{total_comments}")

            comments = self.db.get_comments_paginated(uid, page, page_size)
            if not comments:
                break

            comment_dict, _, _ = self.convert_records_to_objects(comments, [], [])
            all_comments.update(comment_dict)
            page += 1

        # 类似地处理弹幕和通知...

        return all_comments, all_danmus, all_notifies