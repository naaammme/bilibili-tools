from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any
import asyncio

class Screen(Enum):
    WAIT_SCAN_QRCODE = "wait_scan_qrcode"
    WAIT_INPUT_COOKIE = "wait_input_cookie"
    MAIN = "main"

class Error(Exception):#错误类
    pass

class RequestFailedError(Error):#请求失败的错误
    pass

class ParseIntError(Error):#解析int错误
    pass

class UnrecognizedURIError(Error):
    pass

class DeleteCommentError(Error):
    pass

class DeleteDanmuError(Error):
    pass

class DeleteNotifyError(Error):
    pass

class DeleteSystemNotifyError(Error):
    pass

class CreateApiServiceError(Error):
    pass

class GetUIDError(Error):
    pass

@dataclass
class ActivityInfo:
    """活动信息类，用于显示当前获取状态"""
    message: str
    current_count: int = 0
    speed: float = 0.0  # items per second
    elapsed_time: float = 0.0  # seconds
    category: str = ""  # 数据类型（如 "liked", "replied" 等）

    def __str__(self):
        if self.speed > 0:
            return f"{self.message} - 已获取 {self.current_count} 项 [{self.speed:.1f}/s] ({self.elapsed_time:.0f}s)"
        else:
            return f"{self.message} - 已获取 {self.current_count} 项"

@dataclass
class Comment:
    oid: int
    type: int
    content: str
    is_selected: bool = True
    notify_id: Optional[int] = None
    tp: Optional[int] = None

    @classmethod
    def new_with_notify(cls, oid: int, type: int, content: str, notify_id: int, tp: int):
        return cls(oid=oid, type=type, content=content, notify_id=notify_id, tp=tp)

@dataclass
class Danmu:
    content: str
    cid: int
    is_selected: bool = True
    notify_id: Optional[int] = None

    @classmethod
    def new_with_notify(cls, content: str, cid: int, notify_id: int):
        return cls(content=content, cid=cid, notify_id=notify_id)

@dataclass
class Notify:
    content: str
    tp: int
    is_selected: bool = True
    system_notify_api: Optional[int] = None

    @classmethod
    def new_system_notify(cls, content: str, tp: int, api_type: int):
        return cls(content=content, tp=tp, system_notify_api=api_type)

@dataclass
class LikedRecovery:
    cursor_id: int
    cursor_time: int

@dataclass
class ReplyedRecovery:
    cursor_id: int
    cursor_time: int

@dataclass
class AtedRecovery:
    cursor_id: int
    cursor_time: int

@dataclass
class SystemNotifyRecovery:
    cursor: int
    api_type: int

@dataclass
class AicuCommentRecovery:
    uid: int
    page: int
    all_count: int

@dataclass
class AicuDanmuRecovery:
    uid: int
    page: int
    all_count: int

@dataclass
class FetchProgressState:
    liked_data: Tuple[Dict[int, Notify], Dict[int, Comment], Dict[int, Danmu]] = field(default_factory=lambda: ({}, {}, {}))
    liked_recovery: Optional[LikedRecovery] = None

    replyed_data: Tuple[Dict[int, Notify], Dict[int, Comment]] = field(default_factory=lambda: ({}, {}))
    replyed_recovery: Optional[ReplyedRecovery] = None

    ated_data: Dict[int, Notify] = field(default_factory=dict)
    ated_recovery: Optional[AtedRecovery] = None

    system_notify_data: Dict[int, Notify] = field(default_factory=dict)
    system_notify_recovery: Optional[SystemNotifyRecovery] = None

    aicu_comment_data: Dict[int, Comment] = field(default_factory=dict)
    aicu_comment_recovery: Optional[AicuCommentRecovery] = None

    aicu_danmu_data: Dict[int, Danmu] = field(default_factory=dict)
    aicu_danmu_recovery: Optional[AicuDanmuRecovery] = None

    aicu_enabled_last_run: bool = False