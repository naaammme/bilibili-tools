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
            logger.debug(f"aicu活动回调错误: {e}")

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
            logger.debug(f"AICU 的进程错误r: {e}")


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
            f"再次获取aicu评论,uid: {recovery_point.uid}, "
            f"从第: {recovery_point.page}页, 共: {recovery_point.all_count}"
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
                "ps": 100,
                "mode": 0,
                "keyword": ""
            }

            try:
                # 调用包装好的 get_cffi_json 方法，它会在后台运行同步请求
                data = await api_service.get_cffi_json("https://api.aicu.cc/api/v3/search/getreply", params=params)
                consecutive_errors = 0  # 成功时重置错误计数

                if data.get("code") != 0:
                    logger.warning(f"aicu api调用错误: {data.get('message', 'Unknown error')}")
                    break

                if "data" not in data:
                    logger.warning(f"AICU 格式错误: {data}")
                    break

                # 在第一次成功获取时初始化进度条
                if pbar is None:
                    all_count = data["data"].get("cursor", {}).get("all_count", 0)
                    if all_count == 0:
                        logger.info(f"AICU：没有发现这个UID的评论: {uid}")
                        return current_comment_data, None
                    logger.info(f"AICU 评论: 共{all_count}  UID: {uid}")
                    pbar = tqdm(total=all_count, desc="获取aicu评论", initial=len(current_comment_data))

                replies = data["data"].get("replies", [])
                if not replies:
                    logger.info("AICU 评论未找到.")
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

                            # 设置source
                            comment.source = "aicu"
                            comment.created_time = item.get("time", 0)
                            comment.synced_time = int(time.time())

                            # 保存parent信息
                            parent_info = item.get("parent", {})
                            if parent_info:
                                # 添加parent属性到Comment对象
                                comment.parent = parent_info
                            else:
                                comment.parent = None

                            # 添加rank信息（可能有用）
                            comment.rank = item.get("rank", 1)

                            current_comment_data[rpid] = comment
                            activity_tracker.update(1)
                            if pbar:
                                pbar.update(1)

                            logger.debug(f"评论,,rpid={rpid}, oid={comment.oid}, "
                                         f"parent={comment.parent}, rank={comment.rank}")
                    except (KeyError, ValueError, TypeError) as e:
                        logger.debug(f"由于解析错误而跳过这个评论: {e}")
                        continue

                if data["data"].get("cursor", {}).get("is_end", False):
                    logger.info("aicu评论:已经结束")
                    break

                current_page += 1

                # 基础延迟
                base_delay = random.uniform(3, 5)
                jitter = random.gauss(0, 2)
                delay = max(1, base_delay + jitter)

                # 10%概率触发长暂停（模拟用户去做其他事）
                if random.random() < 0.1:
                    delay += random.uniform(10, 20)


                # 每获取10页后，强制休息
                if current_page % 10 == 0:
                    delay += random.uniform(5, 10)


                await asyncio.sleep(delay)

            except RequestFailedError as e:
                consecutive_errors += 1
                logger.warning(f"获取aicu评论失败 {current_page} (attempt {consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("达到AICU获取评论连续错误的最大值。保存进度.")
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
            f"再次获取aicu弹幕 for UID: {recovery_point.uid}, "
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
                "ps": 100,
                "mode": 0,
                "keyword": ""
            }

            try:
                data = await api_service.get_cffi_json("https://api.aicu.cc/api/v3/search/getvideodm", params=params)
                consecutive_errors = 0

                if data.get("code") != 0:
                    logger.warning(f"AICU弹幕API返回错误: {data.get('message', 'Unknown error')}")
                    break

                if "data" not in data:
                    logger.warning(f"AICU弹幕响应格式错误: {data}")
                    break

                if pbar is None:
                    all_count = data["data"].get("cursor", {}).get("all_count", 0)
                    if all_count == 0:
                        logger.info(f"AICU：未找到这个UID的弹幕: {uid}")
                        return current_danmu_data, None
                    logger.info(f"AICU 弹幕: 共 {all_count}  UID: {uid}")
                    pbar = tqdm(total=all_count, desc="Fetching AICU danmus", initial=len(current_danmu_data))

                danmus = data["data"].get("videodmlist", [])
                if not danmus:
                    logger.info("AICU 找不到更多弹幕.")
                    break

                for item in danmus:
                    try:
                        dmid = int(item["id"])
                        # 在弹幕API中，"oid"是视频的CID
                        cid = item.get("oid")
                        if cid and dmid not in current_danmu_data:
                            danmu = Danmu(
                                content=item.get("content", ""),
                                cid=int(cid),
                                is_selected=True,
                                notify_id=None
                            )
                            danmu.source = "aicu"  # 明确设置来源为aicu

                            # 为AICU弹幕设置创建时间
                            danmu.created_time = item.get("ctime", 0)
                            danmu.synced_time = int(time.time())

                            # 调试日志
                            logger.debug(f"AICU弹幕 dmid={dmid}, cid={cid}, source={danmu.source}")

                            current_danmu_data[dmid] = danmu
                            activity_tracker.update(1)
                            if pbar:
                                pbar.update(1)
                    except (KeyError, ValueError, TypeError) as e:
                        logger.debug(f"由于解析错误而跳过弹幕: {e}")
                        continue

                if data["data"].get("cursor", {}).get("is_end", False):
                    logger.info("aicu弹幕获取结束.")
                    break

                current_page += 1

                # 基础延迟
                base_delay = random.uniform(3, 5)
                # 添加随机扰动
                jitter = random.gauss(0, 2)  # 高斯分布，更自然
                delay = max(1, base_delay + jitter)  # 确保最小1秒

                # 10%概率触发长暂停（模拟用户去做其他事）
                if random.random() < 0.1:
                    delay += random.uniform(10, 20)

                # 每获取10页后，强制休息
                if current_page % 10 == 0:
                    delay += random.uniform(5, 10)
                await asyncio.sleep(delay)

            except RequestFailedError as e:
                consecutive_errors += 1
                logger.warning(f"获取aicu弹幕失败,页数: {current_page} (attempt {consecutive_errors}): {e}")
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("已达到AICU任务连续错误最大值。保存进度.")
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