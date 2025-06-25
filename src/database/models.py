import sqlite3
import json
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class CommentRecord:
    """评论记录数据模型"""
    id: int  # rpid
    uid: int  # 用户ID
    oid: int  # 对象ID
    type: int  # 评论类型
    content: str  # 评论内容
    notify_id: Optional[int] = None  # 关联通知ID
    tp: Optional[int] = None  # 通知类型
    source: str = "bilibili"  # 数据来源: bilibili/aicu
    created_time: int = 0  # 原始创建时间戳
    synced_time: int = 0  # 同步时间戳
    is_deleted: bool = False  # 是否已删除
    video_uri: Optional[str] = None  # 视频URI
    like_count: int = 0  # 点赞数

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CommentRecord':
        return cls(**data)

@dataclass
class DanmuRecord:
    """弹幕记录数据模型"""
    id: int  # dmid
    uid: int  # 用户ID
    content: str  # 弹幕内容
    cid: int  # 视频CID
    notify_id: Optional[int] = None  # 关联通知ID
    source: str = "bilibili"  # 数据来源
    created_time: int = 0  # 原始创建时间戳
    synced_time: int = 0  # 同步时间戳
    is_deleted: bool = False  # 是否已删除
    video_url: Optional[str] = None
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DanmuRecord':
        return cls(**data)

@dataclass
class NotifyRecord:
    """通知记录数据模型"""
    id: int  # 通知ID
    uid: int  # 用户ID
    content: str  # 通知内容
    tp: int  # 通知类型 (0=点赞, 1=回复, 2=@, 4=系统通知)
    system_notify_api: Optional[int] = None  # 系统通知API类型
    source: str = "bilibili"  # 数据来源
    created_time: int = 0  # 原始创建时间戳
    synced_time: int = 0  # 同步时间戳
    is_deleted: bool = False  # 是否已删除

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NotifyRecord':
        return cls(**data)

@dataclass
class SyncCursor:
    """同步游标数据模型"""
    uid: int  # 用户ID
    data_type: str  # 数据类型: liked/replied/ated/system_notify/aicu_comments/aicu_danmus
    cursor_id: Optional[int] = None  # 游标ID
    cursor_time: Optional[int] = None  # 游标时间
    last_sync: int = 0  # 最后同步时间
    extra_data: str = "{}"  # 额外数据JSON

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncCursor':
        return cls(**data)