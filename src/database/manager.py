import sqlite3
import json
import logging
import os
from typing import List, Optional, Dict, Any, Tuple
from contextlib import contextmanager
from .models import CommentRecord, DanmuRecord, NotifyRecord, SyncCursor

logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            try:
                home_dir = os.path.expanduser("~")
                db_dir = os.path.join(home_dir, ".bilibili_tools")
                logger.info(f"数据库目录: {db_dir}")

                if not os.path.exists(db_dir):
                    os.makedirs(db_dir)
                    logger.info(f"创建数据库目录: {db_dir}")

                self.db_path = os.path.join(db_dir, "comments_data.db")
                logger.info(f"数据库文件路径: {self.db_path}")
            except Exception as e:
                logger.error(f"创建数据库目录失败: {e}")
                self.db_path = "comments_data.db"
        else:
            self.db_path = db_path

        # 检查数据库文件是否存在
        if os.path.exists(self.db_path):
            logger.info(f"数据库文件已存在: {self.db_path}")
        else:
            logger.info(f"将创建新的数据库文件: {self.db_path}")

        self.init_database()

    def init_database(self):
        """初始化数据库表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 创建表之前先检查
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            existing_tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"现有数据库表: {existing_tables}")


            # 评论表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY,
                    uid INTEGER NOT NULL,
                    oid INTEGER NOT NULL,
                    type INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    notify_id INTEGER,
                    tp INTEGER,
                    source TEXT DEFAULT 'bilibili',
                    created_time INTEGER DEFAULT 0,
                    synced_time INTEGER DEFAULT 0,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    video_uri TEXT,
                    like_count INTEGER DEFAULT 0,
                    UNIQUE(id, uid) ON CONFLICT REPLACE
                )
            ''')

            # 弹幕表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS danmus (
                    id INTEGER PRIMARY KEY,
                    uid INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    cid INTEGER NOT NULL,
                    notify_id INTEGER,
                    source TEXT DEFAULT 'bilibili',
                    created_time INTEGER DEFAULT 0,
                    synced_time INTEGER DEFAULT 0,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    video_url TEXT,
                    UNIQUE(id, uid) ON CONFLICT REPLACE
                )
            ''')

            # 通知表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifies (
                    id INTEGER PRIMARY KEY,
                    uid INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    tp INTEGER NOT NULL,
                    system_notify_api INTEGER,
                    source TEXT DEFAULT 'bilibili',
                    created_time INTEGER DEFAULT 0,
                    synced_time INTEGER DEFAULT 0,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    UNIQUE(id, uid) ON CONFLICT REPLACE
                )
            ''')

            # 同步游标表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sync_cursors (
                    uid INTEGER NOT NULL,
                    data_type TEXT NOT NULL,
                    cursor_id INTEGER,
                    cursor_time INTEGER,
                    last_sync INTEGER DEFAULT 0,
                    extra_data TEXT DEFAULT '{}',
                    PRIMARY KEY(uid, data_type)
                )
            ''')

            # 检查并添加 video_url 字段到 danmus 表
            cursor.execute("PRAGMA table_info(danmus)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'video_url' not in columns:
                cursor.execute('ALTER TABLE danmus ADD COLUMN video_url TEXT')
                logger.info("已添加 video_url 字段到 danmus 表")
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_uid_time ON comments(uid, created_time DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_danmus_uid_time ON danmus(uid, created_time DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifies_uid_time ON notifies(uid, created_time DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_comments_deleted ON comments(uid, is_deleted)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_danmus_deleted ON danmus(uid, is_deleted)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_notifies_deleted ON notifies(uid, is_deleted)')

            conn.commit()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            final_tables = [row[0] for row in cursor.fetchall()]
            logger.info(f"创建后的数据库表: {final_tables}")
            logger.info(f"数据库初始化完成: {self.db_path}")



    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
        try:
            yield conn
        finally:
            conn.close()

    # ================================== 评论相关操作 =================================
    def save_comments(self, comments: List[CommentRecord]) -> int:
        """批量保存评论"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            saved_count = 0

            for comment in comments:
                cursor.execute('''
                    INSERT OR REPLACE INTO comments 
                    (id, uid, oid, type, content, notify_id, tp, source, created_time, synced_time, is_deleted, video_uri, like_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    comment.id, comment.uid, comment.oid, comment.type, comment.content,
                    comment.notify_id, comment.tp, comment.source, comment.created_time,
                    comment.synced_time, comment.is_deleted, comment.video_uri, comment.like_count
                ))
                saved_count += 1

            conn.commit()
            logger.info(f"保存了 {saved_count} 条评论记录")
            return saved_count

    def get_comments(self, uid: int, limit: int = 1000, offset: int = 0,
                     include_deleted: bool = False) -> List[CommentRecord]:
        """获取评论列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            where_clause = "WHERE uid = ?"
            params = [uid]

            if not include_deleted:
                where_clause += " AND is_deleted = FALSE"

            cursor.execute(f'''
                SELECT * FROM comments {where_clause}
                ORDER BY created_time DESC
                LIMIT ? OFFSET ?
            ''', params + [limit, offset])

            return [CommentRecord.from_dict(dict(row)) for row in cursor.fetchall()]

    def mark_comment_deleted(self, comment_id: int, uid: int) -> bool:
        """标记评论为已删除"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE comments SET is_deleted = TRUE 
                WHERE id = ? AND uid = ?
            ''', (comment_id, uid))
            conn.commit()
            return cursor.rowcount > 0

    def delete_comment_permanently(self, comment_id: int, uid: int) -> bool:
        """永久删除评论记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM comments WHERE id = ? AND uid = ?', (comment_id, uid))
            conn.commit()
            return cursor.rowcount > 0

    def delete_danmu_permanently(self, danmu_id: int, uid: int) -> bool:
        """永久删除弹幕记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM danmus WHERE id = ? AND uid = ?', (danmu_id, uid))
            conn.commit()
            return cursor.rowcount > 0

    def delete_notify_permanently(self, notify_id: int, uid: int) -> bool:
        """永久删除通知记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM notifies WHERE id = ? AND uid = ?', (notify_id, uid))
            conn.commit()
            return cursor.rowcount > 0

    # ============================== 弹幕相关操作 =============================
    def save_danmus(self, danmus: List[DanmuRecord]) -> int:
        """批量保存弹幕"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            saved_count = 0

            for danmu in danmus:
                cursor.execute('''
                    INSERT OR REPLACE INTO danmus 
                    (id, uid, content, cid, notify_id, source, created_time, synced_time, is_deleted, video_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    danmu.id, danmu.uid, danmu.content, danmu.cid, danmu.notify_id,
                    danmu.source, danmu.created_time, danmu.synced_time, danmu.is_deleted, danmu.video_url
                ))
                saved_count += 1

            conn.commit()
            logger.info(f"保存了 {saved_count} 条弹幕记录")
            return saved_count

    def get_danmus(self, uid: int, limit: int = 1000, offset: int = 0,
                   include_deleted: bool = False) -> List[DanmuRecord]:
        """获取弹幕列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            where_clause = "WHERE uid = ?"
            params = [uid]

            if not include_deleted:
                where_clause += " AND is_deleted = FALSE"

            cursor.execute(f'''
                SELECT * FROM danmus {where_clause}
                ORDER BY created_time DESC
                LIMIT ? OFFSET ?
            ''', params + [limit, offset])

            return [DanmuRecord.from_dict(dict(row)) for row in cursor.fetchall()]

    def mark_danmu_deleted(self, danmu_id: int, uid: int) -> bool:
        """标记弹幕为已删除"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE danmus SET is_deleted = TRUE 
                WHERE id = ? AND uid = ?
            ''', (danmu_id, uid))
            conn.commit()
            return cursor.rowcount > 0

    # ==============通知相关操作 ===============
    def save_notifies(self, notifies: List[NotifyRecord]) -> int:
        """批量保存通知"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            saved_count = 0

            for notify in notifies:
                cursor.execute('''
                    INSERT OR REPLACE INTO notifies 
                    (id, uid, content, tp, system_notify_api, source, created_time, synced_time, is_deleted)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    notify.id, notify.uid, notify.content, notify.tp, notify.system_notify_api,
                    notify.source, notify.created_time, notify.synced_time, notify.is_deleted
                ))
                saved_count += 1

            conn.commit()
            logger.info(f"保存了 {saved_count} 条通知记录")
            return saved_count

    def get_notifies(self, uid: int, limit: int = 1000, offset: int = 0,
                     include_deleted: bool = False) -> List[NotifyRecord]:
        """获取通知列表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            where_clause = "WHERE uid = ?"
            params = [uid]

            if not include_deleted:
                where_clause += " AND is_deleted = FALSE"

            cursor.execute(f'''
                SELECT * FROM notifies {where_clause}
                ORDER BY created_time DESC
                LIMIT ? OFFSET ?
            ''', params + [limit, offset])

            return [NotifyRecord.from_dict(dict(row)) for row in cursor.fetchall()]

    def mark_notify_deleted(self, notify_id: int, uid: int) -> bool:
        """标记通知为已删除"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE notifies SET is_deleted = TRUE 
                WHERE id = ? AND uid = ?
            ''', (notify_id, uid))
            conn.commit()
            return cursor.rowcount > 0

    # ============================= 同步游标操作 ===============================
    def save_cursor(self, cursor: SyncCursor):
        """保存同步游标"""
        with self.get_connection() as conn:
            db_cursor = conn.cursor()
            db_cursor.execute('''
                INSERT OR REPLACE INTO sync_cursors 
                (uid, data_type, cursor_id, cursor_time, last_sync, extra_data)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                cursor.uid, cursor.data_type, cursor.cursor_id,
                cursor.cursor_time, cursor.last_sync, cursor.extra_data
            ))
            conn.commit()

    def get_cursor(self, uid: int, data_type: str) -> Optional[SyncCursor]:
        """获取同步游标"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM sync_cursors 
                WHERE uid = ? AND data_type = ?
            ''', (uid, data_type))

            row = cursor.fetchone()
            if row:
                return SyncCursor.from_dict(dict(row))
            return None

    # ======================================== 统计信息 ================================
    def get_stats(self, uid: int) -> Dict[str, Any]:
        """获取用户数据统计"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            # 评论统计
            cursor.execute('SELECT COUNT(*) FROM comments WHERE uid = ? AND is_deleted = FALSE', (uid,))
            stats['total_comments'] = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM comments WHERE uid = ? AND is_deleted = TRUE', (uid,))
            stats['deleted_comments'] = cursor.fetchone()[0]

            # 弹幕统计
            cursor.execute('SELECT COUNT(*) FROM danmus WHERE uid = ? AND is_deleted = FALSE', (uid,))
            stats['total_danmus'] = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM danmus WHERE uid = ? AND is_deleted = TRUE', (uid,))
            stats['deleted_danmus'] = cursor.fetchone()[0]

            # 通知统计
            cursor.execute('SELECT COUNT(*) FROM notifies WHERE uid = ? AND is_deleted = FALSE', (uid,))
            stats['total_notifies'] = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM notifies WHERE uid = ? AND is_deleted = TRUE', (uid,))
            stats['deleted_notifies'] = cursor.fetchone()[0]

            # 最后同步时间
            cursor.execute('''
                SELECT data_type, MAX(last_sync) 
                FROM sync_cursors 
                WHERE uid = ? 
                GROUP BY data_type
            ''', (uid,))

            sync_times = {}
            for row in cursor.fetchall():
                sync_times[row[0]] = row[1]
            stats['last_sync_times'] = sync_times

            return stats

    def clear_user_data(self, uid: int):
        """清除指定用户的所有数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM comments WHERE uid = ?', (uid,))
            cursor.execute('DELETE FROM danmus WHERE uid = ?', (uid,))
            cursor.execute('DELETE FROM notifies WHERE uid = ?', (uid,))
            cursor.execute('DELETE FROM sync_cursors WHERE uid = ?', (uid,))
            conn.commit()
            logger.info(f"已清除用户 {uid} 的所有数据")

    def get_database_path(self) -> str:
        """获取数据库文件路径"""
        return os.path.abspath(self.db_path)

    def get_comments_count(self, uid: int, include_deleted: bool = False) -> int:
        """获取评论总数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            where_clause = "WHERE uid = ?"
            params = [uid]
            if not include_deleted:
                where_clause += " AND is_deleted = FALSE"
            cursor.execute(f'SELECT COUNT(*) FROM comments {where_clause}', params)
            return cursor.fetchone()[0]

    def get_comments_paginated(self, uid: int, page: int = 1, page_size: int = 1000,
                               include_deleted: bool = False) -> List[CommentRecord]:
        """分页获取评论"""
        offset = (page - 1) * page_size
        return self.get_comments(uid, limit=page_size, offset=offset, include_deleted=include_deleted)