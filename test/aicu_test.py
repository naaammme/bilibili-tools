#!/usr/bin/env python3
"""
aicu.cc API 客户端
使用 curl_cffi 绕过 Cloudflare 检测
"""
from asyncio import timeout
from datetime import datetime
from pathlib import Path
from time import sleep

from curl_cffi import requests
import time
from typing import List, Dict, Optional, Generator
import json

class AicuClient:
    """aicu.cc API 客户端"""

    def __init__(self, bilibili_cookie: Optional[str] = None):
        """
        初始化客户端

        Args:
            bilibili_cookie: B站 Cookie（可选，主要用于获取 UID）
        """
        self.session = requests.Session()
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.2651.86"

        # 设置请求头
        headers = {"User-Agent": self.ua}
        if bilibili_cookie:
            headers["Cookie"] = bilibili_cookie

        self.session.headers.update(headers)

    def get_comments(self, uid: int, page_size: int = 500, raw_json: bool = False) -> Generator[Dict, None, None]:
        """
        获取用户的所有评论

        Args:
            uid: 用户 UID
            page_size: 每页大小（最大 500）

        Yields:
            评论数据字典
        """
        page = 1
        total_count = None
        fetched_count = 0

        while True:
            url = f"https://api.aicu.cc/api/v3/search/getreply"
            params = {
                "uid": uid,
                "pn": page,
                "ps": page_size,
                "mode": 0,
                "keyword": ""
            }

            print(f"正在获取第 {page} 页评论...")

            try:
                # 使用 curl_cffi，模拟 Edge 浏览器
                resp = self.session.get(
                    url,
                    params=params,
                    impersonate="edge99",  # 模拟 Edge 浏览器
                    timeout=300
                )

                if resp.status_code != 200:
                    print(f"请求失败: {resp.status_code}")
                    break

                data = resp.json()

                if "data" not in data:
                    print(f"响应格式错误: {data}")
                    break
                if raw_json:
                    yield data  # 如果需要原始数据，直接 yield 整个 data
                    # 为了防止无限循环，我们需要在获取后跳出或翻页
                    if data["data"]["cursor"]["is_end"]:
                        print("所有评论获取完成")
                        break
                    page += 1
                    time.sleep(3)
                    continue  # 继续下一次循环

                # 获取总数
                if total_count is None:
                    total_count = data["data"]["cursor"]["all_count"]
                    print(f"总评论数: {total_count}")

                # 获取评论列表
                replies = data["data"]["replies"]
                if not replies:
                    print("没有更多评论了")
                    break

                for reply in replies:
                    yield {
                        "rpid": reply["rpid"],
                        "message": reply["message"],
                        "oid": reply["dyn"]["oid"],
                        "type": reply["dyn"]["type"],
                        "ctime": reply.get("ctime", 0)
                    }
                    fetched_count += 1


                print(f"已获取 {fetched_count}/{total_count} 条评论")

                # 检查是否已结束
                if data["data"]["cursor"]["is_end"]:
                    print("所有评论获取完成")
                    break

                # 翻页
                page += 1

                # 延迟，避免请求过快
                time.sleep(3)

            except Exception as e:
                print(f"请求出错: {e}")
                break

    def get_danmus(self, uid: int, page_size: int = 500, raw_json: bool = False) -> Generator[Dict, None, None]:
        """
        获取用户的所有弹幕

        Args:
            uid: 用户 UID
            page_size: 每页大小（最大 500）

        Yields:
            弹幕数据字典
        """
        page = 1
        total_count = None
        fetched_count = 0

        while True:
            url = f"https://api.aicu.cc/api/v3/search/getvideodm"
            params = {
                "uid": uid,
                "pn": page,
                "ps": page_size,
                "mode": 0,
                "keyword": ""
            }

            print(f"正在获取第 {page} 页弹幕...")

            try:
                resp = self.session.get(
                    url,
                    params=params,
                    impersonate="edge99",
                    timeout=30
                )

                if resp.status_code != 200:
                    print(f"请求失败: {resp.status_code}")
                    break

                data = resp.json()

                if "data" not in data:
                    print(f"响应格式错误: {data}")
                    break

                if raw_json:
                    yield data  # 如果需要原始数据，直接 yield 整个 data
                    # 为了防止无限循环，我们需要在获取后跳出或翻页
                    if data["data"]["cursor"]["is_end"]:
                        print("所有评论获取完成")
                        break
                    page += 1
                    time.sleep(3)
                    continue  # 继续下一次循环

                # 获取总数
                if total_count is None:
                    total_count = data["data"]["cursor"]["all_count"]
                    print(f"总弹幕数: {total_count}")

                # 获取弹幕列表
                danmus = data["data"]["videodmlist"]
                if not danmus:
                    print("没有更多弹幕了")
                    break

                for danmu in danmus:
                    yield {
                        "id": danmu["id"],
                        "content": danmu["content"],
                        "oid": danmu["oid"],  # 视频 AV 号
                        "sendtime": danmu.get("sendtime", 0)
                    }
                    fetched_count += 1

                print(f"已获取 {fetched_count}/{total_count} 条弹幕")

                # 检查是否已结束
                if data["data"]["cursor"]["is_end"]:
                    print("所有弹幕获取完成")
                    break

                # 翻页
                page += 1

                # 延迟
                time.sleep(3)

            except Exception as e:
                print(f"请求出错: {e}")
                break

    def get_uid_from_cookie(self, cookie: str) -> Optional[int]:
        """从 B站 Cookie 获取 UID"""
        headers = {
            "User-Agent": self.ua,
            "Cookie": cookie
        }

        try:
            resp = requests.get(
                "https://api.bilibili.com/x/member/web/account",
                headers=headers,
                impersonate="edge99"
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("code") == 0:
                    return data["data"]["mid"]
        except Exception as e:
            print(f"获取 UID 失败: {e}")

        return None


# 使用示例
if __name__ == "__main__":
    # 你的 B站 Cookie
    COOKIE = """     """
    # 创建客户端
    client = AicuClient()

    # 获取 UID
    MAX_COMMENTS_TO_FETCH = 10  # 设置为 None 则获取全部评论
    MAX_DANMUS_TO_FETCH = 10  # 设置为 None 则获取全部弹幕
    API_MAX_PAGE_SIZE = 20  # API允许的单页最大数量
    # ================================================================

    # --- 2. 设置输出目录 ---
    output_dir = Path('..') / 'output'
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"所有数据将保存在: {output_dir.resolve()}")

    # --- 3. 获取 UID ---
    uid = client.get_uid_from_cookie(COOKIE)
    if not uid:
        print("无法获取 UID，程序退出")
        exit(1)
    print(f"成功获取 UID: {uid}")

    # --- 4. 创建本次任务的唯一标识 (基于时间) ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"任务时间戳: {timestamp}")
    print("=" * 60)

    # --- 5. 获取并保存【指定数量】的评论 ---
    print(f"\n[开始] 获取并保存评论 (目标数量: {MAX_COMMENTS_TO_FETCH or '全部'})...")

    ###动态计算请求的 page_size ###
    comments_page_size = API_MAX_PAGE_SIZE
    if MAX_COMMENTS_TO_FETCH is not None:
        # 如果目标数量小于API单页最大值，则直接用目标数量作为 page_size
        # 这样一次请求就能精确获取，不多也不少
        comments_page_size = min(MAX_COMMENTS_TO_FETCH, API_MAX_PAGE_SIZE)

    comments_fetched_count = 0
    page_num = 1

    ### 在调用时传入计算好的 page_size ###
    for raw_comment_page in client.get_comments(uid, page_size=comments_page_size, raw_json=True):
        # 保存文件的逻辑保持不变
        file_name = f"comments_{uid}_{timestamp}_page_{page_num}.json"
        file_path = output_dir / file_name
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(raw_comment_page, f, indent=4, ensure_ascii=False)
            print(f"  -> 已保存第 {page_num} 页评论到 {file_path}")
        except Exception as e:
            print(f"  -> 保存第 {page_num} 页评论失败: {e}")
            break

        # 检查和中断逻辑仍然需要，以处理目标 > 500 的情况
        comments_in_page = len(raw_comment_page.get("data", {}).get("replies", []))
        comments_fetched_count += comments_in_page
        print(f"  -> 本页 {comments_in_page} 条, 累计获取 {comments_fetched_count} 条评论")

        if MAX_COMMENTS_TO_FETCH is not None and comments_fetched_count >= MAX_COMMENTS_TO_FETCH:
            print(f"\n已达到或超过目标评论数量 ({comments_fetched_count}/{MAX_COMMENTS_TO_FETCH})，停止获取。")
            break

        page_num += 1

    print("[完成] 评论获取任务结束。")

    print(f"\n\n[开始] 获取并保存弹幕 (目标数量: {MAX_DANMUS_TO_FETCH or '全部'})...")

    ### 动态计算请求的 page_size ###
    danmus_page_size = API_MAX_PAGE_SIZE
    if MAX_DANMUS_TO_FETCH is not None:
        danmus_page_size = min(MAX_DANMUS_TO_FETCH, API_MAX_PAGE_SIZE)

    danmus_fetched_count = 0
    page_num = 1

    ###在调用时传入计算好的 page_size ###
    for raw_danmu_page in client.get_danmus(uid, page_size=danmus_page_size, raw_json=True):
        # 保存文件的逻辑保持不变
        file_name = f"danmus_{uid}_{timestamp}_page_{page_num}.json"
        file_path = output_dir / file_name
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(raw_danmu_page, f, indent=4, ensure_ascii=False)
            print(f"  -> 已保存第 {page_num} 页弹幕到 {file_path}")
        except Exception as e:
            print(f"  -> 保存第 {page_num} 页弹幕失败: {e}")
            break

        # 检查和中断逻辑仍然需要
        danmus_in_page = len(raw_danmu_page.get("data", {}).get("videodmlist", []))
        danmus_fetched_count += danmus_in_page
        print(f"  -> 本页 {danmus_in_page} 条, 累计获取 {danmus_fetched_count} 条弹幕")

        if MAX_DANMUS_TO_FETCH is not None and danmus_fetched_count >= MAX_DANMUS_TO_FETCH:
            print(f"\n已达到或超过目标弹幕数量 ({danmus_fetched_count}/{MAX_DANMUS_TO_FETCH})，停止获取。")
            break

        page_num += 1

    print("[完成] 弹幕获取任务结束。")