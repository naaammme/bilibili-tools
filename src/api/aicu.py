import asyncio
import logging
import time
from typing import Dict, Optional, Tuple, Callable, Union
import random
from tqdm.asyncio import tqdm_asyncio as tqdm
from ..types import Comment, Danmu, AicuCommentRecovery, AicuDanmuRecovery, RequestFailedError, ActivityInfo

logger = logging.getLogger(__name__)


class AicuActivityTracker:
    """AICU专用的活动跟踪器，适应高数据量特点"""

    def __init__(self, category: str, message: str, callback: Callable[[Union[str, ActivityInfo]], None]):
        self.category = category
        self.message = message
        self.callback = callback
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.current_count = 0
        self.last_reported = 0
        self.update_interval = 3.0  # AICU数据量大，每3秒更新一次

    def update(self, count: int = 1):
        """更新当前数量"""
        self.current_count += count
        current_time = time.time()

        # 每3秒或每200项更新一次 (AICU数据通常较多)
        if (current_time - self.last_update_time >= self.update_interval or
                self.current_count - self.last_reported >= 200):
            self._update_activity()
            self.last_update_time = current_time
            self.last_reported = self.current_count

    def _update_activity(self):
        """计算并发送活动信息"""
        current_time = time.time()
        elapsed = current_time - self.start_time

        if elapsed > 0:
            speed = self.current_count / elapsed
        else:
            speed = 0.0

        activity_info = ActivityInfo(
            message=self.message,
            current_count=self.current_count,
            speed=speed,
            elapsed_time=elapsed,
            category=self.category
        )

        try:
            self.callback(activity_info)
        except Exception as e:
            logger.debug(f"AICU activity callback error: {e}")

    def finish(self):
        """完成活动跟踪"""
        current_time = time.time()
        elapsed = current_time - self.start_time

        activity_info = ActivityInfo(
            message=f"{self.message} - 完成",
            current_count=self.current_count,
            speed=0.0,
            elapsed_time=elapsed,
            category=self.category
        )

        try:
            self.callback(activity_info)
        except Exception as e:
            logger.debug(f"AICU activity finish callback error: {e}")


async def fetch_aicu_comments(
        api_service,
        current_comment_data: Dict[int, Comment],
        recovery_point: Optional[AicuCommentRecovery] = None,
        activity_callback: Callable[[Union[str, ActivityInfo]], None] = None
) -> Tuple[Dict[int, Comment], Optional[AicuCommentRecovery]]:
    """从后台线程的AICU API获取评论"""

    uid = None
    current_page = 1
    all_count = 0

    if recovery_point:
        logger.info(
            f"Resuming AICU comment fetch for UID: {recovery_point.uid}, "
            f"from page: {recovery_point.page}, total known: {recovery_point.all_count}"
        )
        uid = recovery_point.uid
        current_page = recovery_point.page
        all_count = recovery_point.all_count
    else:
        logger.info("开始新的AICU评论获取.")
        try:
            uid = await api_service.get_uid()
        except Exception as e:
            logger.error(f"开始新的AICU评论获取: {e}")
            return current_comment_data, None

    if not uid:
        return current_comment_data, None

    # 创建活动跟踪器
    activity_tracker = AicuActivityTracker("aicu_comments", "正在获取AICU评论", activity_callback or (lambda x: None))
    pbar = None
    consecutive_errors = 0
    max_consecutive_errors = 3

    try:
        while True:
            params = {
                "uid": uid,
                "pn": current_page,
                "ps": 500,  # Max page size
                "mode": 0,
                "keyword": ""
            }

            try:
                # 调用包装好的 get_cffi_json 方法，它会在后台运行同步请求
                data = await api_service.get_cffi_json("https://api.aicu.cc/api/v3/search/getreply", params=params)
                consecutive_errors = 0  # 成功时重置错误计数

                if data.get("code") != 0:
                    logger.warning(f"AICU API returned an error: {data.get('message', 'Unknown error')}")
                    break

                if "data" not in data:
                    logger.warning(f"AICU response format error: {data}")
                    break

                # 在第一次成功获取时初始化进度条
                if pbar is None:
                    all_count = data["data"].get("cursor", {}).get("all_count", 0)
                    if all_count == 0:
                        logger.info(f"AICU：没有发现这个UID的评论: {uid}")
                        return current_comment_data, None
                    logger.info(f"AICU comments: Total count {all_count} for UID: {uid}")
                    pbar = tqdm(total=all_count, desc="获取aicu评论", initial=len(current_comment_data))

                replies = data["data"].get("replies", [])
                if not replies:
                    logger.info("AICU comments: No more replies found.")
                    break

                for item in replies:
                    try:
                        rpid = int(item["rpid"])
                        if rpid not in current_comment_data:
                            dyn_data = item.get("dyn", {})
                            if not dyn_data or "oid" not in dyn_data or "type" not in dyn_data:
                                continue

                            comment = Comment(
                                oid=int(dyn_data["oid"]),
                                type=int(dyn_data["type"]),
                                content=item.get("message", ""),
                                is_selected=True,
                                notify_id=None,
                                tp=None
                            )
                            current_comment_data[rpid] = comment
                            activity_tracker.update(1)
                            if pbar:
                                pbar.update(1)
                    except (KeyError, ValueError, TypeError) as e:
                        logger.debug(f"Skipping a comment item due to parsing error: {e}")
                        continue

                if data["data"].get("cursor", {}).get("is_end", False):
                    logger.info("AICU comments: Reached the end.")
                    break

                current_page += 1
                await asyncio.sleep(random.uniform(2.5, 4.0))

            except RequestFailedError as e:
                consecutive_errors += 1
                logger.warning(f"Failed to fetch AICU comments page {current_page} (attempt {consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Reached max consecutive errors for AICU comments. Saving progress.")
                    recovery = AicuCommentRecovery(uid=uid, page=current_page, all_count=all_count)
                    activity_tracker.finish()
                    if pbar:
                        pbar.close()
                    return current_comment_data, recovery
                await asyncio.sleep(random.uniform(5, 8)) # 出现错误后等待更长时间

    finally:
        activity_tracker.finish()
        if pbar:
            pbar.close()

    return current_comment_data, None


async def fetch_aicu_danmus(
        api_service,
        current_danmu_data: Dict[int, Danmu],
        recovery_point: Optional[AicuDanmuRecovery] = None,
        activity_callback: Callable[[Union[str, ActivityInfo]], None] = None
) -> Tuple[Dict[int, Danmu], Optional[AicuDanmuRecovery]]:
    """从AICU API获取弹幕数据"""

    uid = None
    current_page = 1
    all_count = 0

    if recovery_point:
        logger.info(
            f"Resuming AICU danmu fetch for UID: {recovery_point.uid}, "
            f"from page: {recovery_point.page}, total known: {recovery_point.all_count}"
        )
        uid = recovery_point.uid
        current_page = recovery_point.page
        all_count = recovery_point.all_count
    else:
        logger.info("开始新的AICU弹幕获取.")
        try:
            uid = await api_service.get_uid()
        except Exception as e:
            logger.error(f"获取AICU的UID失败。处理步骤: {e}")
            return current_danmu_data, None

    if not uid:
        return current_danmu_data, None

    # 创建活动跟踪器
    activity_tracker = AicuActivityTracker("aicu_danmus", "正在获取AICU弹幕", activity_callback or (lambda x: None))
    pbar = None
    consecutive_errors = 0
    max_consecutive_errors = 3

    try:
        while True:
            params = {
                "uid": uid,
                "pn": current_page,
                "ps": 500,
                "mode": 0,
                "keyword": ""
            }

            try:
                data = await api_service.get_cffi_json("https://api.aicu.cc/api/v3/search/getvideodm", params=params)
                consecutive_errors = 0

                if data.get("code") != 0:
                    logger.warning(f"AICU danmu API returned an error: {data.get('message', 'Unknown error')}")
                    break

                if "data" not in data:
                    logger.warning(f"AICU danmu response format error: {data}")
                    break

                if pbar is None:
                    all_count = data["data"].get("cursor", {}).get("all_count", 0)
                    if all_count == 0:
                        logger.info(f"AICU：未找到这个UID的弹幕: {uid}")
                        return current_danmu_data, None
                    logger.info(f"AICU danmus: Total count {all_count} for UID: {uid}")
                    pbar = tqdm(total=all_count, desc="Fetching AICU danmus", initial=len(current_danmu_data))

                danmus = data["data"].get("videodmlist", [])
                if not danmus:
                    logger.info("AICU danmus: No more danmus found.")
                    break

                for item in danmus:
                    try:
                        dmid = int(item["id"])
                        # 在弹木API中，"oid"是视频的CID.
                        cid = item.get("oid")
                        if cid and dmid not in current_danmu_data:
                            danmu = Danmu(
                                content=item.get("content", ""),
                                cid=int(cid),
                                is_selected=True,
                                notify_id=None
                            )
                            current_danmu_data[dmid] = danmu
                            activity_tracker.update(1)
                            if pbar:
                                pbar.update(1)
                    except (KeyError, ValueError, TypeError) as e:
                        logger.debug(f"Skipping a danmu item due to parsing error: {e}")
                        continue

                if data["data"].get("cursor", {}).get("is_end", False):
                    logger.info("AICU danmus: Reached the end.")
                    break

                current_page += 1
                await asyncio.sleep(random.uniform(2.5, 4.0))

            except RequestFailedError as e:
                consecutive_errors += 1
                logger.warning(f"Failed to fetch AICU danmus page {current_page} (attempt {consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Reached max consecutive errors for AICU danmus. Saving progress.")
                    recovery = AicuDanmuRecovery(uid=uid, page=current_page, all_count=all_count)
                    activity_tracker.finish()
                    if pbar:
                        pbar.close()
                    return current_danmu_data, recovery
                await asyncio.sleep(random.uniform(5, 8))

    finally:
        activity_tracker.finish()
        if pbar:
            pbar.close()

    return current_danmu_data, None

# 导出
__all__ = ['fetch_aicu_comments', 'fetch_aicu_danmus']