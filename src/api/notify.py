import asyncio
import random
import time
from tqdm.asyncio import tqdm_asyncio as tqdm
import logging
from typing import Dict, Optional, Tuple, List, Callable, Union
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
                        rpid = item_data.get("target_id") or item_data.get("item_id")
                        if rpid:
                            try:
                                # 注意：这里的解析仍然可能因为信息不足而失败
                                oid, type_ = parse_oid(item_data)
                                content = item_data.get("title", "")
                                current_comment_data[rpid] = Comment.new_with_notify(
                                    oid=oid, type=type_, content=content, notify_id=notify_id, tp=0
                                )
                            except Exception as e:
                                logger.warning(f"无法为点赞通知 (ID: {notify_id}) 创建关联评论 (rpid={rpid}): {e}。这可能导致关联删除失败。")

                    elif item_data.get("type") == "danmu":
                        native_uri = item_data.get("native_uri", "")
                        cid = extract_cid(native_uri) if native_uri else None
                        dmid = item_data.get("item_id")
                        if cid and dmid:
                            current_danmu_data[dmid] = Danmu.new_with_notify(
                                item_data.get("title", ""), cid, notify_id
                            )

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
                logger.error(f"API error or invalid format for replies: {response_data}");
                break

            data = response_data.get("data", {})
            items = data.get("items", [])
            cursor = data.get("cursor")  # The cursor for reply is directly under data

            if not items:
                logger.info("回复的通知已完全处理 (no items).");
                break

            for item in items:
                try:
                    item_data = item.get("item", {})
                    if not item_data: continue
                    notify_id = item["id"]
                    current_notify_data[notify_id] = Notify(content=f"{item_data.get('title', 'Unknown')} (reply)",
                                                            tp=1)
                    if item_data.get("type") == "reply":
                        rpid = item_data.get("target_id")
                        if rpid:
                            try:
                                oid, type_ = parse_oid(item_data)
                                content = item_data.get("target_reply_content") or item_data.get("title", "")
                                current_comment_data[rpid] = Comment.new_with_notify(oid, type_, content, notify_id, 1)
                            except Exception as e:
                                logger.debug(f"Failed to parse replied comment: {e}")
                    activity_tracker.update(1);
                    pbar.update(1)
                except Exception as e:
                    logger.debug(f"Error processing a replied item: {e}");
                    continue

            if cursor and cursor.get("is_end"):
                logger.info("Replied notifications processed completely.");
                break

            if cursor and cursor.get("id") and cursor.get("time"):
                cursor_id, cursor_time = cursor.get("id"), cursor.get("time")
            else:
                logger.info("回复的通知已完全处理 (no more cursor).");
                break

        except Exception as e:
            logger.warning(f"Error fetching replied page: {e}")
            recovery = ReplyedRecovery(cursor_id, cursor_time) if cursor_id and cursor_time else recovery_point
            activity_tracker.finish();
            pbar.close()
            return current_notify_data, current_comment_data, recovery
        await asyncio.sleep(sleep_duration())
    activity_tracker.finish();
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
    while True:
        try:
            if current_cursor is None:
                url = (f"https://message.bilibili.com/x/sys-msg/query_user_notify?csrf={api_service.csrf}&page_size=20&build=0&mobi_app=web" if api_type_to_use == 0 else
                       f"https://message.bilibili.com/x/sys-msg/query_unified_notify?csrf={api_service.csrf}&page_size=10&build=0&mobi_app=web")
            else:
                url = f"https://message.bilibili.com/x/sys-msg/query_notify_list?csrf={api_service.csrf}&data_type=1&cursor={current_cursor}&build=0&mobi_app=web"
            json_value = await api_service.get_json(url)
            data_obj = json_value.get("data", {})
            items_on_this_page = data_obj.get("system_notify_list", []) if current_cursor is None else data_obj
            if not items_on_this_page:
                logger.info(f"系统通知完全处理。总计: {len(current_data)}"); break
            new_page_cursor = None
            for item in items_on_this_page:
                current_data[item["id"]] = Notify.new_system_notify(f"{item['title']}\n{item['content']}", item["type"], api_type_to_use)
                new_page_cursor = item["cursor"]
                activity_tracker.update(1); pbar.update(1)
            current_cursor = new_page_cursor
        except Exception as e:
            logger.warning(f"获取b站系统通知错误: {e}")
            recovery = SystemNotifyRecovery(current_cursor, api_type_to_use) if current_cursor else None
            activity_tracker.finish(); pbar.close()
            return current_data, recovery
        await asyncio.sleep(sleep_duration())
    activity_tracker.finish(); pbar.close()
    return current_data, None



async def fetch(
        api_service,
        aicu_state: bool,
        progress_state: FetchProgressState,
        activity_callback: Callable[[Union[str, ActivityInfo]], None]
) -> Tuple[Optional[Tuple[Dict[int, Notify], Dict[int, Comment], Dict[int, Danmu]]], Optional[FetchProgressState]]:
    local_progress = progress_state
    if local_progress.liked_recovery is not None or not local_progress.liked_data[0]:
        n, c, d, recovery = await fetch_liked(api_service, local_progress.liked_data[0].copy(), local_progress.liked_data[1].copy(), local_progress.liked_data[2].copy(), local_progress.liked_recovery, activity_callback)
        local_progress.liked_data = (n, c, d); local_progress.liked_recovery = recovery
        if recovery is not None: return None, local_progress
    if local_progress.replyed_recovery is not None or not local_progress.replyed_data[0]:
        n, c, recovery = await fetch_replyed(api_service, local_progress.replyed_data[0].copy(), local_progress.replyed_data[1].copy(), local_progress.replyed_recovery, activity_callback)
        local_progress.replyed_data = (n, c); local_progress.replyed_recovery = recovery
        if recovery is not None: return None, local_progress
    if local_progress.ated_recovery is not None or not local_progress.ated_data:
        n, recovery = await fetch_ated(api_service, local_progress.ated_data.copy(), local_progress.ated_recovery, activity_callback)
        local_progress.ated_data = n; local_progress.ated_recovery = recovery
        if recovery is not None: return None, local_progress
    if local_progress.system_notify_recovery is not None or not local_progress.system_notify_data:
        n, recovery = await fetch_system_notify_adapted(api_service, local_progress.system_notify_data.copy(), local_progress.system_notify_recovery, activity_callback)
        local_progress.system_notify_data = n; local_progress.system_notify_recovery = recovery
        if recovery is not None: return None, local_progress
    combined_notify = {**local_progress.liked_data[0], **local_progress.replyed_data[0], **local_progress.ated_data, **local_progress.system_notify_data}
    combined_comment = {**local_progress.liked_data[1], **local_progress.replyed_data[1]}
    combined_danmu = {**local_progress.liked_data[2]}
    if aicu_state:
        from .aicu import fetch_aicu_comments, fetch_aicu_danmus
        if local_progress.aicu_comment_recovery is not None or not local_progress.aicu_comment_data or not local_progress.aicu_enabled_last_run:
            c, recovery = await fetch_aicu_comments(api_service, local_progress.aicu_comment_data.copy(), local_progress.aicu_comment_recovery, activity_callback)
            local_progress.aicu_comment_data = c; local_progress.aicu_comment_recovery = recovery
            if recovery is not None: local_progress.aicu_enabled_last_run = True; return None, local_progress
        if local_progress.aicu_danmu_recovery is not None or not local_progress.aicu_danmu_data or not local_progress.aicu_enabled_last_run:
            d, recovery = await fetch_aicu_danmus(api_service, local_progress.aicu_danmu_data.copy(), local_progress.aicu_danmu_recovery, activity_callback)
            local_progress.aicu_danmu_data = d; local_progress.aicu_danmu_recovery = recovery
            if recovery is not None: local_progress.aicu_enabled_last_run = True; return None, local_progress
        combined_comment.update(local_progress.aicu_comment_data)
        combined_danmu.update(local_progress.aicu_danmu_data)
        local_progress.aicu_enabled_last_run = True
    else:
        if local_progress.aicu_enabled_last_run:
            local_progress.aicu_comment_data.clear(); local_progress.aicu_danmu_data.clear()
            local_progress.aicu_comment_recovery = None; local_progress.aicu_danmu_recovery = None
            local_progress.aicu_enabled_last_run = False
    activity_callback("数据整合中...")
    return (combined_notify, combined_comment, combined_danmu), None

__all__ = ['fetch', 'remove_notify', 'fetch_liked', 'fetch_replyed', 'fetch_ated', 'fetch_system_notify_adapted']