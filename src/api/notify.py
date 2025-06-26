import asyncio
import datetime
import random
import time
from tqdm.asyncio import tqdm_asyncio as tqdm
import logging
from typing import Dict, Optional, Tuple, List, Callable, Union, Any

from ..database.incremental import IncrementalFetcher
from ..types import (
    Notify, Comment, Danmu, FetchProgressState, ActivityInfo,
    LikedRecovery, ReplyedRecovery, AtedRecovery, SystemNotifyRecovery,
    DeleteNotifyError, DeleteSystemNotifyError
)

logger = logging.getLogger(__name__)


class SimpleActivityTracker:
    """简单的活动跟踪器，只显示当前数量和速度"""

    def __init__(self, category: str, message: str, callback: Callable[[Union[str, ActivityInfo]], None]):
        self.category = category
        self.message = message
        self.callback = callback
        self.start_time = time.time()
        self.last_update_time = time.time()
        self.current_count = 0
        self.last_reported = 0
        self.update_interval = 2.0  # 每2秒更新一次，避免太频繁

    def update(self, count: int = 1):
        """更新当前数量"""
        self.current_count += count
        current_time = time.time()

        # 每2秒或每100项更新一次
        if (current_time - self.last_update_time >= self.update_interval or
                self.current_count - self.last_reported >= 100):
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
            logger.debug(f"Activity callback error: {e}")

    def finish(self):
        """完成活动跟踪"""
        # 最终更新，速度设为0表示完成
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
            logger.debug(f"Activity finish callback error: {e}")


def sleep_duration() -> float:#增强的随机延迟
    # 80%概率正常延迟
    if random.random() < 0.8:
        return random.uniform(1.0, 2.0)
    else:
        # 20%概率较长延迟，模拟用户行为
        return random.uniform(2.0, 3.0)

async def remove_notify(notify: Notify, id: int, api_service) -> int:#删除通知

    try:
        if notify.system_notify_api is not None:
            # 系统通知删除逻辑
            csrf = api_service.csrf
            # 根据 api_type 构建不同的请求体
            if notify.system_notify_api == 0:
                json_data = {
                    "csrf": csrf, "ids": [id], "station_ids": [], "type": notify.tp,
                    "build": 8140300, "mobi_app": "android"
                }
            else:
                json_data = {
                    "csrf": csrf, "ids": [], "station_ids": [id], "type": notify.tp,
                    "build": 8140300, "mobi_app": "android"
                }

            url = f"https://message.bilibili.com/x/sys-msg/del_notify_list?build=8140300&mobi_app=android&csrf={csrf}"

            # 直接调用 post_json 方法
            json_res = await api_service.post_json(url, json_data=json_data)

            if json_res.get("code") == 0:
                return id
            else:
                raise DeleteSystemNotifyError(f"删除系统通知失败: {json_res.get('message', '未知错误')}")
        else:
            # 普通通知删除逻辑
            form_data = [
                ("tp", str(notify.tp)),
                ("id", str(id)),
                ("build", "0"),
                ("mobi_app", "web"),
                ("csrf_token", api_service.csrf),
                ("csrf", api_service.csrf)
            ]
            json_res = await api_service.post_form(
                "https://api.bilibili.com/x/msgfeed/del",
                form_data
            )

            if json_res.get("code") == 0:
                return id
            else:
                raise DeleteNotifyError(f"删除通知失败: {json_res.get('message', '未知错误')}")
    except Exception as e:
        # 将底层异常重新抛出，以便上层能获取更详细的信息
        raise DeleteNotifyError(f"删除通知时发生网络或未知错误: {e}") from e


async def fetch_liked(
        api_service,
        current_notify_data: Dict[int, Notify],
        current_comment_data: Dict[int, Comment],
        current_danmu_data: Dict[int, Danmu],
        recovery_point: Optional[LikedRecovery],
        activity_callback: Callable[[Union[str, ActivityInfo]], None] = None
) -> Tuple[Dict[int, Notify], Dict[int, Comment], Dict[int, Danmu], Optional[LikedRecovery]]:
    #获取喜欢的通知、评论和主题
    from .comment import parse_oid
    from .danmu import extract_cid

    cursor_id = recovery_point.cursor_id if recovery_point else None
    cursor_time = recovery_point.cursor_time if recovery_point else None

    # 使用简单的活动跟踪器
    activity_tracker = SimpleActivityTracker("liked", "正在获取点赞数据", activity_callback or (lambda x: None))

    # 同时保持原有的tqdm，用于控制台输出
    pbar = tqdm(desc="获取点赞", unit="items")

    while True:

        try:
            if cursor_id is None and cursor_time is None:
                url = "https://api.bilibili.com/x/msgfeed/like?platform=web&build=0&mobi_app=web"
            else:
                url = f"https://api.bilibili.com/x/msgfeed/like?platform=web&build=0&mobi_app=web&id={cursor_id}&like_time={cursor_time}"

            response_data = await api_service.fetch_data(url)

            if not isinstance(response_data, dict) or response_data.get("code") != 0:
                logger.error(f"API error or invalid format: {response_data}")
                break

            data = response_data.get("data", {})
            if not data:
                logger.warning("No data in 'liked' response, assuming end.")
                break

            items = data.get("total", {}).get("items", [])
            cursor = data.get("total", {}).get("cursor")

            if not items:
                logger.info("已完全处理点赞的通知 (no items).")
                break

            for item in items:
                try:
                    item_data = item.get("item", {})
                    if not item_data:
                        continue

                    # 创建通知对象
                    notify_id = item["id"]
                    current_notify_data[notify_id] = Notify(
                        content=f"{item_data.get('title', 'Unknown')} (liked)",
                        tp=0 # 点赞类型为0
                    )

                    # 尝试创建关联的评论或弹幕对象
                    if item_data.get("type") == "reply":
                        rpid = item_data.get("item_id")
                        if rpid:
                            try:
                                rpid = int(rpid)  # 确保是整数
                                oid, type_ = parse_oid(item_data)
                                content = item_data.get("title", "")
                                comment = Comment.new_with_notify(
                                    oid=oid, type=type_, content=content, notify_id=notify_id, tp=0
                                )
                                # 设置source属性
                                comment.source = "bilibili"
                                comment.created_time = item.get("like_time", 0)
                                # 保存视频URI
                                comment.video_uri = item_data.get("uri", "")
                                # 保存点赞数
                                comment.like_count = item.get("counts", 0)  # 点赞通知的counts字段
                                logger.debug(
                                    f"存储点赞评论: rpid={rpid}, uri={comment.video_uri}, likes={comment.like_count}")
                                current_comment_data[rpid] = comment
                                comment.synced_time = int(time.time())
                            except Exception as e:
                                logger.warning(f"无法为点赞通知 (ID: {notify_id}) 创建关联评论 (rpid={rpid}): {e}。这可能导致关联删除失败。")
                                logger.warning(f"解析liked评论失败: {e}")

                    elif item_data.get("type") == "danmu":
                        dmid = item_data.get("item_id")
                        if dmid:
                            # 从native_uri中提取cid（用于内部逻辑）
                            native_uri = item_data.get("native_uri", "")
                            cid = extract_cid(native_uri) if native_uri else None
                            # 如果没有cid，尝试其他方式获取
                            if not cid:
                                # 可以尝试从其他字段获取，或者设置一个默认值
                                cid = 0  # 临时设置，主要依赖video_url

                            danmu = Danmu.new_with_notify(
                                item_data.get("title", ""), cid, notify_id
                            )
                            danmu.source = "bilibili"  # 明确设置来源
                            danmu.video_url = item_data.get("uri", "")  # 保存完整的视频链接

                            # 设置正确的时间戳
                            danmu.created_time = item.get("like_time", 0)
                            danmu.synced_time = int(time.time())

                            # 日志
                            logger.debug(
                                f"B站弹幕 dmid={dmid}, cid={cid}, source={danmu.source}, video_url={danmu.video_url}")

                            current_danmu_data[dmid] = danmu

                    # 更新活动
                    activity_tracker.update(1)
                    pbar.update(1)
                except Exception as e:
                    logger.debug(f"Error processing a liked item: {e}")
                    continue

            if cursor and cursor.get("is_end"):
                logger.info("已完全处理点赞的通知 (cursor end).")
                break

            if cursor:
                cursor_id = cursor.get("id")
                cursor_time = cursor.get("time")
            else:
                break
        except Exception as e:
            logger.warning(f"Error fetching liked page: {e}")
            recovery = LikedRecovery(cursor_id, cursor_time) if cursor_id and cursor_time else recovery_point
            activity_tracker.finish()
            pbar.close()
            return current_notify_data, current_comment_data, current_danmu_data, recovery
        await asyncio.sleep(sleep_duration())

    activity_tracker.finish()
    pbar.close()
    return current_notify_data, current_comment_data, current_danmu_data, None


async def fetch_replyed(
        api_service,
        current_notify_data: Dict[int, Notify],
        current_comment_data: Dict[int, Comment],
        recovery_point: Optional[ReplyedRecovery],
        activity_callback: Callable[[Union[str, ActivityInfo]], None] = None
) -> Tuple[Dict[int, Notify], Dict[int, Comment], Optional[ReplyedRecovery]]:
    from .comment import parse_oid
    cursor_id = recovery_point.cursor_id if recovery_point else None
    cursor_time = recovery_point.cursor_time if recovery_point else None
    activity_tracker = SimpleActivityTracker("replyed", "正在获取回复数据", activity_callback or (lambda x: None))
    pbar = tqdm(desc="获取回复", unit="items")
    while True:

        try:
            if cursor_id is None and cursor_time is None:
                url = "https://api.bilibili.com/x/msgfeed/reply?platform=web&build=0&mobi_app=web"
            else:
                url = f"https://api.bilibili.com/x/msgfeed/reply?platform=web&build=0&mobi_app=web&id={cursor_id}&reply_time={cursor_time}"
            response_data = await api_service.fetch_data(url)
            if not isinstance(response_data, dict) or response_data.get("code") != 0:
                logger.error(f"API error or invalid format for replies: {response_data}")
                break

            data = response_data.get("data", {})
            items = data.get("items", [])
            cursor = data.get("cursor")  # The cursor for reply is directly under data

            if not items:
                logger.info("回复的通知已完全处理 (no items).")
                break

            for item in items:
                try:
                    item_data = item.get("item", {})
                    if not item_data: continue
                    notify_id = item["id"]
                    current_notify_data[notify_id] = Notify(content=f"{item_data.get('title', 'Unknown')} (reply)",
                                                            tp=1)
                    if item_data.get("type") == "reply":
                        rpid = item_data.get("target_id")  # 回复通知用target_id
                        if rpid:
                            try:
                                rpid = int(rpid)  # 是整数
                                logger.debug(f"处理回复评论: rpid={rpid}")
                                oid, type_ = parse_oid(item_data)
                                content = item_data.get("target_reply_content") or item_data.get("title", "")
                                comment = Comment.new_with_notify(
                                    oid=oid, type=type_, content=content, notify_id=notify_id, tp=1
                                )
                                comment.source = "bilibili"
                                comment.created_time = item.get("reply_time", 0)
                                # 保存视频URI
                                comment.video_uri = item_data.get("uri", "")
                                # 保存点赞数
                                comment.like_count = item.get("counts", 0)  # 回复通知的counts字段,这里看错了,这个字段是回复数不是点赞数,是固定为1的,因为不影响功能所以不改
                                current_comment_data[rpid] = comment
                                logger.debug(
                                    f"存储回复评论: rpid={rpid}, uri={comment.video_uri}, likes={comment.like_count}")
                            except Exception as e:
                                logger.debug(f"解析回复评论失败: {e}")

                    activity_tracker.update(1)
                    pbar.update(1)
                except Exception as e:
                    logger.debug(f"Error processing a replied item: {e}")
                    continue

            if cursor and cursor.get("is_end"):
                logger.info("Replied notifications processed completely.")
                break

            if cursor and cursor.get("id") and cursor.get("time"):
                cursor_id, cursor_time = cursor.get("id"), cursor.get("time")
            else:
                logger.info("回复的通知已完全处理 (no more cursor).")
                break

        except Exception as e:
            logger.warning(f"Error fetching replied page: {e}")
            recovery = ReplyedRecovery(cursor_id, cursor_time) if cursor_id and cursor_time else recovery_point
            activity_tracker.finish()
            pbar.close()
            return current_notify_data, current_comment_data, recovery
        await asyncio.sleep(sleep_duration())
    activity_tracker.finish()
    pbar.close()
    return current_notify_data, current_comment_data, None



async def fetch_ated(
        api_service,
        current_notify_data: Dict[int, Notify],
        recovery_point: Optional[AtedRecovery],
        activity_callback: Callable[[Union[str, ActivityInfo]], None] = None
) -> Tuple[Dict[int, Notify], Optional[AtedRecovery]]:
    cursor_id = recovery_point.cursor_id if recovery_point else None
    cursor_time = recovery_point.cursor_time if recovery_point else None
    activity_tracker = SimpleActivityTracker("ated", "正在获取@数据", activity_callback or (lambda x: None))
    pbar = tqdm(desc="获取@数据中", unit="items")
    while True:

        try:
            if cursor_id is None and cursor_time is None:
                url = "https://api.bilibili.com/x/msgfeed/at?build=0&mobi_app=web"
            else:
                url = f"https://api.bilibili.com/x/msgfeed/at?build=0&mobi_app=web&id={cursor_id}&at_time={cursor_time}"
            res = (await api_service.fetch_data(url)).get("data", {})
            if not res or not res.get("items"):
                logger.info("@ed通知处理完毕."); break
            for item in res["items"]:
                current_notify_data[item["id"]] = Notify(content=f"{item['item']['title']} (@)", tp=2)
                activity_tracker.update(1); pbar.update(1)
            cursor = res.get("cursor", {})
            if cursor.get("is_end"):
                logger.info("@ed通知处理完毕."); break
            cursor_id, cursor_time = cursor.get("id"), cursor.get("time")
        except Exception as e:
            logger.warning(f"Error fetching @ed page: {e}")
            recovery = AtedRecovery(cursor_id, cursor_time) if cursor_id and cursor_time else recovery_point
            activity_tracker.finish(); pbar.close()
            return current_notify_data, recovery
        await asyncio.sleep(sleep_duration())
    activity_tracker.finish(); pbar.close()
    return current_notify_data, None


async def fetch_system_notify_adapted(
        api_service,
        current_data: Dict[int, Notify],
        recovery_point: Optional[SystemNotifyRecovery],
        activity_callback: Callable[[Union[str, ActivityInfo]], None] = None
) -> Tuple[Dict[int, Notify], Optional[SystemNotifyRecovery]]:
    current_cursor = recovery_point.cursor if recovery_point else None
    api_type_to_use = recovery_point.api_type if recovery_point else 0
    activity_tracker = SimpleActivityTracker("system", "正在获取系统通知", activity_callback or (lambda x: None))
    pbar = tqdm(desc="获取系统通知中", unit="items")

    # 标记是否是第一次请求
    is_first_request = current_cursor is None

    while True:
        try:
            if current_cursor is None:
                # 第一次请求，尝试第一个API
                url = (
                    f"https://message.bilibili.com/x/sys-msg/query_user_notify?csrf={api_service.csrf}&page_size=20&build=0&mobi_app=web" if api_type_to_use == 0 else
                    f"https://message.bilibili.com/x/sys-msg/query_unified_notify?csrf={api_service.csrf}&page_size=10&build=0&mobi_app=web")
            else:
                # 分页请求
                url = f"https://message.bilibili.com/x/sys-msg/query_notify_list?csrf={api_service.csrf}&data_type=1&cursor={current_cursor}&build=0&mobi_app=web"

            json_value = await api_service.get_json(url)

            if json_value.get("code") != 0:
                logger.warning(f"系统通知API返回错误: {json_value}")
                break

            # 处理不同的数据结构
            if current_cursor is None:
                # 第一次请求，数据在 data.system_notify_list
                data_obj = json_value.get("data", {})
                items_on_this_page = data_obj.get("system_notify_list", [])

                # 如果第一个API返回空，尝试第二个API
                if not items_on_this_page and is_first_request and api_type_to_use == 0:
                    logger.info("第一个API返回空，尝试备用API...")
                    api_type_to_use = 1
                    await asyncio.sleep(random.uniform(0, 2))
                    url = f"https://message.bilibili.com/x/sys-msg/query_unified_notify?csrf={api_service.csrf}&page_size=10&build=0&mobi_app=web"
                    json_value = await api_service.get_json(url)

                    if json_value.get("code") == 0:
                        data_obj = json_value.get("data", {})
                        items_on_this_page = data_obj.get("system_notify_list", [])
            else:
                # 分页请求，数据直接在 data（是个数组）
                items_on_this_page = json_value.get("data", [])

            if not items_on_this_page:
                logger.info(f"系统通知完全处理。总计: {len(current_data)}")
                break

            # 处理当前页的数据
            new_page_cursor = None
            for item in items_on_this_page:
                # 创建通知对象
                notify_id = item.get("id")
                if notify_id:
                    current_data[notify_id] = Notify.new_system_notify(
                        f"{item.get('title', '')}\n{item.get('content', '')}",
                        item.get("type", 0),
                        api_type_to_use
                    )

                    # 设置时间戳（如果有）
                    time_at = item.get("time_at")
                    if time_at:
                        try:
                            from datetime import datetime
                            dt = datetime.strptime(time_at, "%Y-%m-%d %H:%M:%S")
                            current_data[notify_id].created_time = int(dt.timestamp())
                        except:
                            current_data[notify_id].created_time = int(time.time())

                    activity_tracker.update(1)
                    pbar.update(1)

            # 从最后一条记录获取cursor用于下一页
            if items_on_this_page:
                last_item = items_on_this_page[-1]
                new_page_cursor = last_item.get("cursor")

            # 更新cursor
            current_cursor = new_page_cursor

            # 如果没有新的cursor，说明已经到最后一页
            if current_cursor is None:
                logger.info("系统通知获取完毕（没有更多分页）")
                break

            # 标记不再是第一次请求
            is_first_request = False

            base_delay = random.uniform(0, 2)  # 基础延迟4-6秒

            # 根据已获取的数量增加延迟
            if len(current_data) > 100:
                base_delay += random.uniform(2, 3)  # 获取超过100条后额外延迟
            elif len(current_data) > 200:
                base_delay += random.uniform(3, 5)  # 获取超过200条后更长延迟

            # 添加随机扰动，模拟人类行为
            jitter = random.gauss(0, 1)  # 高斯分布
            delay = max(0, base_delay + jitter)  # 确保最小3秒


        except Exception as e:
            logger.warning(f"获取b站系统通知错误: {e}")
            recovery = SystemNotifyRecovery(current_cursor, api_type_to_use) if current_cursor else None
            activity_tracker.finish()
            pbar.close()
            return current_data, recovery

        await asyncio.sleep(sleep_duration())

    activity_tracker.finish()
    pbar.close()
    return current_data, None


async def fetch(
        api_service,
        aicu_state: bool,
        progress_state: FetchProgressState,
        activity_callback: Callable[[Union[str, ActivityInfo]], None]
) -> Tuple[Optional[Tuple[Dict[int, Notify], Dict[int, Comment], Dict[int, Danmu]]], Optional[FetchProgressState]]:
    """
    主数据获取函数，负责从多个来源获取通知、评论和弹幕数据
        api_service: API服务实例
        aicu_state: 是否启用AICU数据源
        progress_state: 进度状态，用于断点续传
        activity_callback: 活动回调函数，用于更新UI进度
    """
    local_progress = progress_state
    #  获取点赞通知及相关数据
    # 如果有恢复点或者还没有获取过点赞数据，则执行获取
    if local_progress.liked_recovery is not None or not local_progress.liked_data[0]:
        n, c, d, recovery = await fetch_liked(api_service, local_progress.liked_data[0].copy(), local_progress.liked_data[1].copy(), local_progress.liked_data[2].copy(), local_progress.liked_recovery, activity_callback)
        local_progress.liked_data = (n, c, d); local_progress.liked_recovery = recovery
        # 如果返回了恢复点，说明获取被中断，需要保存进度并退出
        if recovery is not None: return None, local_progress

     #获取回复通知及相关评论
    if local_progress.replyed_recovery is not None or not local_progress.replyed_data[0]:
        n, c, recovery = await fetch_replyed(api_service, local_progress.replyed_data[0].copy(), local_progress.replyed_data[1].copy(), local_progress.replyed_recovery, activity_callback)
        local_progress.replyed_data = (n, c); local_progress.replyed_recovery = recovery
        if recovery is not None: return None, local_progress
    #获取@通知
    if local_progress.ated_recovery is not None or not local_progress.ated_data:
        n, recovery = await fetch_ated(api_service, local_progress.ated_data.copy(), local_progress.ated_recovery, activity_callback)
        local_progress.ated_data = n; local_progress.ated_recovery = recovery
        if recovery is not None: return None, local_progress
    #获取系统通知
    if local_progress.system_notify_recovery is not None or not local_progress.system_notify_data:
        n, recovery = await fetch_system_notify_adapted(api_service, local_progress.system_notify_data.copy(), local_progress.system_notify_recovery, activity_callback)
        local_progress.system_notify_data = n; local_progress.system_notify_recovery = recovery
        if recovery is not None: return None, local_progress
    # 通知合并逻辑部分,后面的会覆盖前面的，优先级依次递增
    combined_notify = {**local_progress.liked_data[0], **local_progress.replyed_data[0], **local_progress.ated_data, **local_progress.system_notify_data}
    # 先放入回复的评论，再用点赞的评论覆盖（因为点赞的评论有更多信息）
    combined_comment = {**local_progress.replyed_data[1], **local_progress.liked_data[1]}
    # 弹幕目前只来自点赞通知
    combined_danmu = {**local_progress.liked_data[2]}

    #  处理AICU第三方数据源的数据
    if aicu_state:
        from .aicu import fetch_aicu_comments, fetch_aicu_danmus
        # 获取AICU评论数据
        if local_progress.aicu_comment_recovery is not None or not local_progress.aicu_comment_data or not local_progress.aicu_enabled_last_run:
            c, recovery = await fetch_aicu_comments(api_service, local_progress.aicu_comment_data.copy(), local_progress.aicu_comment_recovery, activity_callback)
            local_progress.aicu_comment_data = c; local_progress.aicu_comment_recovery = recovery
            if recovery is not None: local_progress.aicu_enabled_last_run = True; return None, local_progress
        # 获取AICU弹幕数据
        if local_progress.aicu_danmu_recovery is not None or not local_progress.aicu_danmu_data or not local_progress.aicu_enabled_last_run:
            d, recovery = await fetch_aicu_danmus(api_service, local_progress.aicu_danmu_data.copy(), local_progress.aicu_danmu_recovery, activity_callback)
            local_progress.aicu_danmu_data = d; local_progress.aicu_danmu_recovery = recovery
            if recovery is not None: local_progress.aicu_enabled_last_run = True; return None, local_progress
        #评论合并, 先创建AICU数据的副本，然后用Bilibili数据覆盖
        temp_comment = local_progress.aicu_comment_data.copy()
        temp_comment.update(combined_comment)
        combined_comment = temp_comment

        #弹幕合并,先创建AICU数据的副本，然后用Bilibili数据覆盖
        temp_danmu = local_progress.aicu_danmu_data.copy()
        temp_danmu.update(combined_danmu)
        combined_danmu = temp_danmu


        local_progress.aicu_enabled_last_run = True
    else:
        # 如果AICU被禁用，但之前启用过，则清理AICU数据
        if local_progress.aicu_enabled_last_run:
            local_progress.aicu_comment_data.clear(); local_progress.aicu_danmu_data.clear()
            local_progress.aicu_comment_recovery = None; local_progress.aicu_danmu_recovery = None
            local_progress.aicu_enabled_last_run = False

    #整合数据返回最终合并结果
    activity_callback("数据整合中...")
    return (combined_notify, combined_comment, combined_danmu), None

__all__ = ['fetch', 'remove_notify', 'fetch_liked', 'fetch_replyed', 'fetch_ated', 'fetch_system_notify_adapted']


async def fetch_incremental_data( #这个方法应该没啥用了,留着吧哎
        api_service,
        uid: int,
        db_manager,
        activity_callback: Callable[[Union[str, ActivityInfo]], None] = None
) -> Tuple[Dict[int, Notify], Dict[int, Comment], Dict[int, Danmu]]:
    """增量获取所有类型的数据"""
    from ..database.incremental import IncrementalFetcher

    fetcher = IncrementalFetcher(db_manager)

    all_notifies = {}
    all_comments = {}
    all_danmus = {}

    # 获取各类型的增量数据
    data_types = ["liked", "replied", "ated", "system_notify"]

    for data_type in data_types:
        try:
            if activity_callback:
                activity_callback(f"获取新的{data_type}数据...")

            # 获取增量数据
            notifies, comments, danmus = await fetch_incremental_by_type(
                api_service, uid, data_type, fetcher, activity_callback
            )

            # 合并数据
            all_notifies.update(notifies)
            all_comments.update(comments)
            all_danmus.update(danmus)

        except Exception as e:
            logger.error(f"获取{data_type}增量数据失败: {e}")
            continue

    # 获取AICU增量数据
    if activity_callback:
        activity_callback("获取AICU增量数据...")

    try:
        aicu_comments = await fetch_aicu_comments_incremental(
            api_service, uid, fetcher, activity_callback
        )
        all_comments.update(aicu_comments)

        aicu_danmus = await fetch_aicu_danmus_incremental(
            api_service, uid, fetcher, activity_callback
        )
        all_danmus.update(aicu_danmus)

    except Exception as e:
        logger.error(f"获取AICU增量数据失败: {e}")

    return all_notifies, all_comments, all_danmus


async def fetch_incremental_by_type(
        api_service, uid: int, data_type: str, fetcher: IncrementalFetcher,
        activity_callback: Callable[[Union[str, ActivityInfo]], None] = None
) -> Tuple[Dict[int, Notify], Dict[int, Comment], Dict[int, Danmu]]:
    """按类型获取增量数据"""

    # 获取上次同步的游标和最新时间戳
    last_cursor = fetcher.get_last_sync_cursor(uid, data_type)
    last_timestamp = fetcher.get_latest_timestamp(uid, data_type)

    notifies = {}
    comments = {}
    danmus = {}

    # 构建API URL
    base_urls = {
        "liked": "https://api.bilibili.com/x/msgfeed/like?platform=web&build=0&mobi_app=web",
        "replied": "https://api.bilibili.com/x/msgfeed/reply?platform=web&build=0&mobi_app=web",
        "ated": "https://api.bilibili.com/x/msgfeed/at?build=0&mobi_app=web",
        "system_notify": f"https://message.bilibili.com/x/sys-msg/query_user_notify?csrf={api_service.csrf}&page_size=20&build=0&mobi_app=web"
    }

    if data_type not in base_urls:
        return notifies, comments, danmus

    base_url = base_urls[data_type]
    current_cursor_id = last_cursor.cursor_id if last_cursor else None
    current_cursor_time = last_cursor.cursor_time if last_cursor else None

    new_items_count = 0
    max_pages = 10  # 限制最大页数，避免无限循环
    page_count = 0

    while page_count < max_pages:
        try:
            # 构建URL
            if current_cursor_id and current_cursor_time and data_type in ["liked", "replied", "ated"]:
                if data_type == "liked":
                    url = f"{base_url}&id={current_cursor_id}&like_time={current_cursor_time}"
                elif data_type == "replied":
                    url = f"{base_url}&id={current_cursor_id}&reply_time={current_cursor_time}"
                elif data_type == "ated":
                    url = f"{base_url}&id={current_cursor_id}&at_time={current_cursor_time}"
            elif current_cursor_id and data_type == "system_notify":
                url = f"https://message.bilibili.com/x/sys-msg/query_notify_list?csrf={api_service.csrf}&data_type=1&cursor={current_cursor_id}&build=0&mobi_app=web"
            else:
                url = base_url

            # 获取数据
            response_data = await api_service.fetch_data(url)

            if response_data.get("code") != 0:
                logger.warning(f"{data_type}增量获取API错误: {response_data}")
                break

            # 解析数据
            data = response_data.get("data", {})
            if data_type == "system_notify":
                items = data.get("system_notify_list", []) if current_cursor_id is None else data
            else:
                items = data.get("items", []) if data_type != "liked" else data.get("total", {}).get("items", [])

            if not items:
                logger.info(f"{data_type}增量获取完成：没有更多数据")
                break

            # 过滤新数据
            new_items = fetcher.filter_new_items(items, data_type, last_timestamp)

            if not new_items:
                logger.info(f"{data_type}增量获取完成：没有新数据")
                break

            # 处理新数据
            for item in new_items:
                try:
                    if data_type in ["liked", "replied", "ated"]:
                        # 处理点赞、回复、@通知
                        await process_notify_item(item, data_type, notifies, comments, danmus)
                    elif data_type == "system_notify":
                        # 处理系统通知
                        await process_system_notify_item(item, notifies)

                    new_items_count += 1

                except Exception as e:
                    logger.debug(f"处理{data_type}项目失败: {e}")
                    continue

            # 更新游标
            cursor_info = data.get("cursor", {})
            if data_type == "liked":
                cursor_info = data.get("total", {}).get("cursor", {})

            if cursor_info:
                current_cursor_id = cursor_info.get("id")
                current_cursor_time = cursor_info.get("time")

                if cursor_info.get("is_end"):
                    logger.info(f"{data_type}增量获取完成：到达末尾")
                    break
            else:
                break

            page_count += 1

            # 更新进度
            if activity_callback:
                activity_info = ActivityInfo(
                    message=f"获取新的{data_type}数据",
                    current_count=new_items_count,
                    speed=0.0,
                    elapsed_time=0.0,
                    category=f"{data_type}_incremental"
                )
                activity_callback(activity_info)

            await asyncio.sleep(1)  # 限制请求频率

        except Exception as e:
            logger.error(f"获取{data_type}增量数据页面失败: {e}")
            break

    # 保存最新的游标
    if current_cursor_id:
        fetcher.save_sync_cursor(uid, data_type, current_cursor_id, current_cursor_time)

    logger.info(f"{data_type}增量获取完成，新数据: {new_items_count}")
    return notifies, comments, danmus


async def process_notify_item(item: Dict[str, Any], data_type: str,
                              notifies: Dict[int, Notify], comments: Dict[int, Comment],
                              danmus: Dict[int, Danmu]):
    """处理通知类数据项"""
    from .comment import parse_oid
    from .danmu import extract_cid

    try:
        notify_id = item["id"]
        item_data = item.get("item", {})

        # 创建通知
        tp_mapping = {"liked": 0, "replied": 1, "ated": 2}
        tp = tp_mapping.get(data_type, 0)

        notify_content = f"{item_data.get('title', 'Unknown')} ({data_type})"
        notifies[notify_id] = Notify(
            content=notify_content,
            tp=tp,
            created_time=item.get(f"{data_type.rstrip('d')}_time", 0)
        )

        # 处理关联的评论或弹幕
        if item_data.get("type") == "reply":
            rpid = item_data.get("target_id") or item_data.get("item_id")
            if rpid:
                try:
                    oid, type_ = parse_oid(item_data)
                    content = item_data.get("title", "")
                    comments[rpid] = Comment.new_with_notify(
                        oid=oid, type=type_, content=content,
                        notify_id=notify_id, tp=tp
                    )
                    comments[rpid].created_time = item.get(f"{data_type.rstrip('d')}_time", 0)
                    # 设置source
                    comments[rpid].source = "bilibili"
                    # 保存视频URI
                    comments[rpid].video_uri = item_data.get("uri", "")
                    # 保存点赞数
                    comments[rpid].like_count = item.get("counts", 0)
                    # 设置同步时间
                    comments[rpid].synced_time = int(time.time())

                except Exception as e:
                    logger.debug(f"解析评论失败: {e}")

        elif item_data.get("type") == "danmu":
            native_uri = item_data.get("native_uri", "")
            cid = extract_cid(native_uri) if native_uri else None
            dmid = item_data.get("item_id")
            if cid and dmid:
                danmus[dmid] = Danmu.new_with_notify(
                    item_data.get("title", ""), cid, notify_id
                )
                danmus[dmid].created_time = item.get(f"{data_type.rstrip('d')}_time", 0)

    except Exception as e:
        logger.debug(f"处理通知项目失败: {e}")


async def process_system_notify_item(item: Dict[str, Any], notifies: Dict[int, Notify]):
    """处理系统通知项目"""
    try:
        notify_id = item["id"]
        content = f"{item['title']}\n{item['content']}"

        # 解析时间
        time_str = item.get("time_at", "")
        created_time = 0
        if time_str:
            try:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                created_time = int(dt.timestamp())
            except:
                created_time = int(time.time())

        notifies[notify_id] = Notify.new_system_notify(content, item["type"], 0)
        notifies[notify_id].created_time = created_time

    except Exception as e:
        logger.debug(f"处理系统通知项目失败: {e}")


async def fetch_aicu_comments_incremental(
        api_service, uid: int, fetcher: IncrementalFetcher,
        activity_callback: Callable[[Union[str, ActivityInfo]], None] = None
) -> Dict[int, Comment]:
    """增量获取AICU评论"""

    last_cursor = fetcher.get_last_sync_cursor(uid, "aicu_comments")
    last_timestamp = fetcher.get_latest_timestamp(uid, "aicu_comments")

    comments = {}
    current_page = last_cursor.cursor_id if last_cursor else 1
    new_items_count = 0
    max_pages = 20  # 限制最大页数

    for page in range(current_page, current_page + max_pages):
        try:
            params = {
                "uid": uid,
                "pn": page,
                "ps": 500,
                "mode": 0,
                "keyword": ""
            }

            data = await api_service.get_cffi_json("https://api.aicu.cc/api/v3/search/getreply", params=params)

            if data.get("code") != 0:
                logger.warning(f"AICU评论增量获取API错误: {data}")
                break

            replies = data["data"].get("replies", [])
            if not replies:
                logger.info("AICU评论增量获取完成：没有更多数据")
                break

            # 过滤新数据
            new_replies = fetcher.filter_new_items(replies, "aicu_comments", last_timestamp)

            if not new_replies:
                logger.info("AICU评论增量获取完成：没有新数据")
                break

            # 处理新评论
            for item in new_replies:
                try:
                    rpid = int(item["rpid"])
                    dyn_data = item.get("dyn", {})
                    if dyn_data and "oid" in dyn_data and "type" in dyn_data:
                        comment = Comment(
                            oid=int(dyn_data["oid"]),
                            type=int(dyn_data["type"]),
                            content=item.get("message", ""),
                            is_selected=True,
                            created_time=item.get("time", 0)
                        )
                        comments[rpid] = comment
                        new_items_count += 1

                except Exception as e:
                    logger.debug(f"处理AICU评论项目失败: {e}")
                    continue

            # 检查是否到达末尾
            if data["data"].get("cursor", {}).get("is_end", False):
                logger.info("AICU评论增量获取完成：到达末尾")
                break

            # 更新进度
            if activity_callback:
                activity_info = ActivityInfo(
                    message="获取新的AICU评论",
                    current_count=new_items_count,
                    speed=0.0,
                    elapsed_time=0.0,
                    category="aicu_comments_incremental"
                )
                activity_callback(activity_info)

            await asyncio.sleep(2)  # AICU请求间隔

        except Exception as e:
            logger.error(f"获取AICU评论页面失败: {e}")
            break

    # 保存游标
    if new_items_count > 0:
        fetcher.save_sync_cursor(uid, "aicu_comments", current_page)

    logger.info(f"AICU评论增量获取完成，新数据: {new_items_count}")
    return comments


async def fetch_aicu_danmus_incremental(
        api_service, uid: int, fetcher: IncrementalFetcher,
        activity_callback: Callable[[Union[str, ActivityInfo]], None] = None
) -> Dict[int, Danmu]:
    """增量获取AICU弹幕"""

    last_cursor = fetcher.get_last_sync_cursor(uid, "aicu_danmus")
    last_timestamp = fetcher.get_latest_timestamp(uid, "aicu_danmus")

    danmus = {}
    current_page = last_cursor.cursor_id if last_cursor else 1
    new_items_count = 0
    max_pages = 20

    for page in range(current_page, current_page + max_pages):
        try:
            params = {
                "uid": uid,
                "pn": page,
                "ps": 500,
                "mode": 0,
                "keyword": ""
            }

            data = await api_service.get_cffi_json("https://api.aicu.cc/api/v3/search/getvideodm", params=params)

            if data.get("code") != 0:
                logger.warning(f"AICU弹幕增量获取API错误: {data}")
                break

            videodmlist = data["data"].get("videodmlist", [])
            if not videodmlist:
                logger.info("AICU弹幕增量获取完成：没有更多数据")
                break

            # 过滤新数据
            new_danmus_list = fetcher.filter_new_items(videodmlist, "aicu_danmus", last_timestamp)

            if not new_danmus_list:
                logger.info("AICU弹幕增量获取完成：没有新数据")
                break

            # 处理新弹幕
            for item in new_danmus_list:
                try:
                    dmid = int(item["id"])
                    cid = item.get("oid")
                    if cid:
                        danmu = Danmu(
                            content=item.get("content", ""),
                            cid=int(cid),
                            is_selected=True,
                            created_time=item.get("ctime", 0)
                        )
                        danmus[dmid] = danmu
                        new_items_count += 1

                except Exception as e:
                    logger.debug(f"处理AICU弹幕项目失败: {e}")
                    continue

            # 检查是否到达末尾
            if data["data"].get("cursor", {}).get("is_end", False):
                logger.info("AICU弹幕增量获取完成：到达末尾")
                break

            # 更新进度
            if activity_callback:
                activity_info = ActivityInfo(
                    message="获取新的AICU弹幕",
                    current_count=new_items_count,
                    speed=0.0,
                    elapsed_time=0.0,
                    category="aicu_danmus_incremental"
                )
                activity_callback(activity_info)

            await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"获取AICU弹幕页面失败: {e}")
            break

    # 保存游标
    if new_items_count > 0:
        fetcher.save_sync_cursor(uid, "aicu_danmus", current_page)

    logger.info(f"AICU弹幕增量获取完成，新数据: {new_items_count}")
    return danmus


# 导出新函数
__all__.extend(['fetch_incremental_data', 'fetch_incremental_by_type',
                'fetch_aicu_comments_incremental', 'fetch_aicu_danmus_incremental'])