#!/usr/bin/env python3
"""
aicu.cc API 客户端
使用 curl_cffi 绕过 Cloudflare 检测
"""
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

    def get_comments(self, uid: int, page_size: int = 500) -> Generator[Dict, None, None]:
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
            url = f"https://api.aicu.cc/api/v3/search/getvideodm"
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
                    timeout=30
                )

                if resp.status_code != 200:
                    print(f"请求失败: {resp.status_code}")
                    break

                data = resp.json()

                if "data" not in data:
                    print(f"响应格式错误: {data}")
                    break

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

    def get_danmus(self, uid: int, page_size: int = 500) -> Generator[Dict, None, None]:
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
    COOKIE = """buvid3=BBCB3A37-1766-8F7C-96D7-C4C5EBBA043373537infoc; b_nut=1725722473; _uuid=6C4AC314-224C-914A-9578-BD9F104B9DEAF47010infoc; enable_web_push=DISABLE; buvid4=A4B61B47-FB41-D5E1-C6A3-2C47707BB45275183-024090715-XeyYqz3FAW7rX8A5EvJ%2FHg%3D%3D; rpdid=|(u)Ykm|lJ)~0J'u~kl~kkYYm; DedeUserID=3546388174473844; DedeUserID__ckMd5=ad284fff700baef2; buvid_fp_plain=undefined; header_theme_version=CLOSE; LIVE_BUVID=AUTO2117257627017441; hit-dyn-v2=1; PVID=1; blackside_state=0; CURRENT_BLACKGAP=0; is-2022-channel=1; enable_feed_channel=ENABLE; fingerprint=48f63749e9a84a159c0f9e41ff55dc99; buvid_fp=48f63749e9a84a159c0f9e41ff55dc99; CURRENT_QUALITY=80; home_feed_column=5; browser_resolution=1699-941; bili_ticket=eyJhbGciOiJIUzI1NiIsImtpZCI6InMwMyIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NTAzMTQzMjYsImlhdCI6MTc1MDA1NTA2NiwicGx0IjotMX0.gc7foTqLe3vxDC1KMQTEIxp4oBFRV6ELALCZlgtIZFk; bili_ticket_expires=1750314266; SESSDATA=692161fd%2C1765607127%2C0457a%2A61CjBvpz2CMjVlsZCbdXJpwgFU2BqhabKTNFRXDAjLzSa6ZYfiUOkFdpHfigrFNKgAgpgSVmJROVhsYjJHTk1aNjE0WTU0RDdIdlctT2QtZERoOGtIRV9wZ20yMWhaeUZmRW5mRHgtbGtCYmMzb0dDVkJyUGx3RkxXbkdtT3psa0hnLThDRjFTWnR3IIEC; bili_jct=1d494819ade2cb27005034383665fe33; CURRENT_FNVAL=4048; b_lsid=27EDE1FE_19781994E04; bp_t_offset_3546388174473844=1079701516324962304"""
    # 创建客户端
    client = AicuClient()

    # 获取 UID
    uid = client.get_uid_from_cookie(COOKIE)
    if not uid:
        print("无法获取 UID")
        exit(1)

    print(f"UID: {uid}")
    print("="*60)

    # 获取评论
    print("\n获取评论:")
    comments = []
    for comment in client.get_comments(uid):
        comments.append(comment)
        # 只获取前 10 条作为示例
        if len(comments) >= 10:
            break

    print(f"\n获取到 {len(comments)} 条评论")
    for i, comment in enumerate(comments[:5], 1):
        print(f"{i}. {comment['message'][:50]}...")

    # 获取弹幕
    print("\n\n获取弹幕:")
    danmus = []
    for danmu in client.get_danmus(uid):
        danmus.append(danmu)
        # 只获取前 10 条作为示例
        if len(danmus) >= 10:
            break

    print(f"\n获取到 {len(danmus)} 条弹幕")
    for i, danmu in enumerate(danmus[:5], 1):
        print(f"{i}. {danmu['content']}")