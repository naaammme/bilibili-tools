#!/usr/bin/env python3
"""
获取B站API原始JSON数据，用于分析数据结构

"""

import asyncio
import json
import os
from datetime import datetime
import sys
import time

COOKIE = """    k"""  # 请填入你的cookie
MAX_ITEMS = 8
# 每种类型获取的最大数量
OUTPUT_DIR = "../output"

async def fetch_system_notify_complete(api_service):
    """完整获取系统通知，包含分页逻辑"""
    all_system_notify = []
    cursor = None
    api_type = 0  # 0: query_user_notify, 1: query_unified_notify

    print("\n正在获取系统通知数据...")

    # 第一次请求
    try:
        # 尝试第一个API
        url = f"https://message.bilibili.com/x/sys-msg/query_user_notify?csrf={api_service.csrf}&page_size=20&build=0&mobi_app=web"
        data = await api_service.get_json(url)

        if data.get("code") == 0:
            notify_list = data.get("data", {}).get("system_notify_list", [])

            if not notify_list:
                # 如果第一个API返回空，尝试第二个API
                print("第一个API返回空，尝试备用API...")
                api_type = 1
                url = f"https://message.bilibili.com/x/sys-msg/query_unified_notify?csrf={api_service.csrf}&page_size=10&build=0&mobi_app=web"
                data = await api_service.get_json(url)
                notify_list = data.get("data", {}).get("system_notify_list", [])

            if notify_list:
                all_system_notify.extend(notify_list)
                # 获取最后一条的cursor用于分页
                if notify_list:
                    cursor = notify_list[-1].get("cursor")
                print(f"✓ 第一页获取到 {len(notify_list)} 条系统通知")
            else:
                print("没有系统通知数据")
                return all_system_notify
        else:
            print(f"API返回错误: {data}")
            return all_system_notify

    except Exception as e:
        print(f"✗ 获取系统通知失败: {e}")
        return all_system_notify

    # 分页获取剩余数据
    page = 2
    while cursor is not None:
        try:
            # 延迟避免请求过快
            await asyncio.sleep(1)

            # 使用分页API
            url = f"https://message.bilibili.com/x/sys-msg/query_notify_list?csrf={api_service.csrf}&data_type=1&cursor={cursor}&build=0&mobi_app=web"
            data = await api_service.get_json(url)

            if data.get("code") == 0:
                # 注意：分页API的data直接是数组
                notify_list = data.get("data", [])

                if not notify_list:
                    print(f"✓ 系统通知获取完毕，共 {len(all_system_notify)} 条")
                    break

                all_system_notify.extend(notify_list)
                # 获取新的cursor
                cursor = notify_list[-1].get("cursor") if notify_list else None
                print(f"✓ 第 {page} 页获取到 {len(notify_list)} 条系统通知，总计 {len(all_system_notify)} 条")
                page += 1
            else:
                print(f"分页API返回错误: {data}")
                break

        except Exception as e:
            print(f"✗ 获取第 {page} 页失败: {e}")
            break

    return all_system_notify

async def main():
    print("=== B站API数据获取工具 ===\n")

    # 检查cookie
    if not COOKIE or COOKIE == "这里填入你的完整cookie":
        print("错误：请先在脚本中填入你的完整cookie")
        input("按Enter键退出...")
        return

    # 添加项目路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)

    try:
        from src.api.api_service import ApiService
    except ImportError as e:
        print(f"导入失败: {e}")
        print("请确保脚本在项目根目录运行")
        input("按Enter键退出...")
        return

    # 创建输出目录
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 创建API服务
    try:
        api_service = ApiService.new(COOKIE)
    except Exception as e:
        print(f"创建API服务失败: {e}")
        print("请检查cookie格式是否正确，必须包含 bili_jct 字段")
        input("按Enter键退出...")
        return

    async with api_service:
        # 测试API是否正常工作
        try:
            print("测试API连接...")
            test_data = await api_service.get_json("https://api.bilibili.com/x/member/web/account")
            if test_data.get("code") == 0:
                print(f"✓ API连接正常，当前用户UID: {test_data['data']['mid']}")
            else:
                print(f"API返回错误: {test_data}")
                input("按Enter键退出...")
                return
        except Exception as e:
            print(f"API测试失败: {e}")
            input("按Enter键退出...")
            return

        # 1. 获取点赞数据
        print("\n正在获取点赞数据...")
        liked_data = []

        try:
            # 点赞数据的分页逻辑
            cursor_id = None
            cursor_time = None
            page = 1

            while True:
                if cursor_id is None and cursor_time is None:
                    url = "https://api.bilibili.com/x/msgfeed/like?platform=web&build=0&mobi_app=web"
                else:
                    url = f"https://api.bilibili.com/x/msgfeed/like?platform=web&build=0&mobi_app=web&id={cursor_id}&like_time={cursor_time}"

                data = await api_service.fetch_data(url)
                liked_data.append(data)

                items = data.get('data', {}).get('total', {}).get('items', [])
                cursor = data.get('data', {}).get('total', {}).get('cursor', {})

                print(f"✓ 第 {page} 页获取到 {len(items)} 条点赞数据")

                if not cursor or cursor.get('is_end', True):
                    break

                cursor_id = cursor.get('id')
                cursor_time = cursor.get('time')
                page += 1
                await asyncio.sleep(1)  # 避免请求过快

        except Exception as e:
            print(f"✗ 获取点赞数据失败: {e}")

        if liked_data:
            with open(os.path.join(OUTPUT_DIR, "liked_raw.json"), "w", encoding="utf-8") as f:
                json.dump(liked_data, f, ensure_ascii=False, indent=2)
            print(f"✓ 点赞数据已保存")

        # 2. 获取回复数据
        print("\n正在获取回复数据...")
        reply_data = []

        try:
            # 回复数据的分页逻辑
            cursor_id = None
            cursor_time = None
            page = 1

            while True:
                if cursor_id is None and cursor_time is None:
                    url = "https://api.bilibili.com/x/msgfeed/reply?platform=web&build=0&mobi_app=web"
                else:
                    url = f"https://api.bilibili.com/x/msgfeed/reply?platform=web&build=0&mobi_app=web&id={cursor_id}&reply_time={cursor_time}"

                data = await api_service.fetch_data(url)
                reply_data.append(data)

                items = data.get('data', {}).get('items', [])
                cursor = data.get('data', {}).get('cursor', {})

                print(f"✓ 第 {page} 页获取到 {len(items)} 条回复数据")

                if not cursor or cursor.get('is_end', True):
                    break

                cursor_id = cursor.get('id')
                cursor_time = cursor.get('time')
                page += 1
                await asyncio.sleep(1)

        except Exception as e:
            print(f"✗ 获取回复数据失败: {e}")

        if reply_data:
            with open(os.path.join(OUTPUT_DIR, "reply_raw.json"), "w", encoding="utf-8") as f:
                json.dump(reply_data, f, ensure_ascii=False, indent=2)
            print(f"✓ 回复数据已保存")

        # 3. 获取@数据
        print("\n正在获取@数据...")
        at_data = []

        try:
            # @数据的分页逻辑
            cursor_id = None
            cursor_time = None
            page = 1

            while True:
                if cursor_id is None and cursor_time is None:
                    url = "https://api.bilibili.com/x/msgfeed/at?build=0&mobi_app=web"
                else:
                    url = f"https://api.bilibili.com/x/msgfeed/at?build=0&mobi_app=web&id={cursor_id}&at_time={cursor_time}"

                data = await api_service.fetch_data(url)
                at_data.append(data)

                items = data.get('data', {}).get('items', [])
                cursor = data.get('data', {}).get('cursor', {})

                print(f"✓ 第 {page} 页获取到 {len(items)} 条@数据")

                if not cursor or cursor.get('is_end', True):
                    break

                cursor_id = cursor.get('id')
                cursor_time = cursor.get('time')
                page += 1
                await asyncio.sleep(1)

        except Exception as e:
            print(f"✗ 获取@数据失败: {e}")

        if at_data:
            with open(os.path.join(OUTPUT_DIR, "at_raw.json"), "w", encoding="utf-8") as f:
                json.dump(at_data, f, ensure_ascii=False, indent=2)
            print(f"✓ @数据已保存")

        # 4. 获取系统通知数据（使用完整的分页逻辑）
        system_notify_list = await fetch_system_notify_complete(api_service)

        if system_notify_list:
            system_data = [{"type": "system_notify", "data": {"system_notify_list": system_notify_list}}]
            with open(os.path.join(OUTPUT_DIR, "system_notify_raw.json"), "w", encoding="utf-8") as f:
                json.dump(system_data, f, ensure_ascii=False, indent=2)
            print(f"✓ 系统通知数据已保存，共 {len(system_notify_list)} 条")

    print(f"\n完成！所有数据已保存到 {OUTPUT_DIR} 目录")
    input("按Enter键退出...")

if __name__ == "__main__":
    # Windows下的事件循环策略
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())