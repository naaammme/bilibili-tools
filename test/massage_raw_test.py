import requests
import json
import time
import os
from datetime import datetime
import random


class BilibiliMessageCrawler:
    def __init__(self, output_dir=r"C:\Users\mm\Desktop\mypython\bilibili_comment_cleaning\output"):
        self.api_base = "https://api.vc.bilibili.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://message.bilibili.com/'
        }
        self.cookies = {   }
        self.output_dir = output_dir

        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        # 智能延迟参数
        self.base_delay = 1.0
        self.failure_count = 5
        self.success_count = 5

    def log(self, message):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    def smart_delay(self):
        """智能延迟，根据成功失败率动态调整"""
        if self.failure_count > 0:
            delay = self.base_delay * (1.5 ** self.failure_count)
        else:
            delay = self.base_delay * (0.9 ** min(self.success_count, 3))

        delay = max(0.5, min(delay, 30))
        actual_delay = random.uniform(delay * 0.8, delay * 1.2)
        time.sleep(actual_delay)

    def parse_cookie(self, cookie_string):
        """解析Cookie字符串"""
        parsed = {}
        if not cookie_string:
            return parsed

        try:
            for item in cookie_string.split(';'):
                item = item.strip()
                if not item:
                    continue
                parts = item.split('=', 1)
                if len(parts) == 2:
                    parsed[parts[0].strip()] = parts[1].strip()
                else:
                    self.log(f"无法解析的Cookie片段: '{item}'")
        except Exception as e:
            self.log(f"解析Cookie时出错: {e}")

        return parsed

    def set_cookie(self, cookie_string):
        """设置Cookie"""
        parsed_cookies = self.parse_cookie(cookie_string)
        sessdata = parsed_cookies.get('SESSDATA')
        bili_jct = parsed_cookies.get('bili_jct')

        if not sessdata or not bili_jct:
            raise ValueError("Cookie中未能解析出SESSDATA或bili_jct，请检查Cookie格式")

        self.cookies = {'SESSDATA': sessdata, 'bili_jct': bili_jct}
        if parsed_cookies.get('buvid3'):
            self.cookies['buvid3'] = parsed_cookies['buvid3']

        self.log(f"Cookie设置成功: SESSDATA=...{sessdata[-10:]}, bili_jct={bili_jct}")
        return True

    def save_json(self, data, filename):
        """保存JSON数据到文件"""
        filepath = os.path.join(self.output_dir, filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.log(f"数据已保存到: {filepath}")
        except Exception as e:
            self.log(f"保存文件失败: {e}")

    def fetch_sessions(self, max_pages=5):
        """获取会话列表"""
        self.log(f"开始获取会话列表，最大页数: {max_pages}")

        all_sessions = []
        page_count = 0
        current_page_end_ts = 0
        has_more = True

        while has_more and page_count < max_pages:
            try:
                params = {
                    'session_type': 1,
                    'group_fold': 1,
                    'unfollow_fold': 0,
                    'sort_rule': 2,
                    'build': 0,
                    'mobi_app': 'web',
                    'size': 20
                }

                if current_page_end_ts > 0:
                    params['end_ts'] = current_page_end_ts

                resp = requests.get(
                    f"{self.api_base}/session_svr/v1/session_svr/get_sessions",
                    params=params,
                    headers=self.headers,
                    cookies=self.cookies,
                    timeout=15
                )
                resp.raise_for_status()
                data = resp.json()

                # 保存原始响应
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"sessions_page_{page_count + 1}_{timestamp}.json"
                self.save_json(data, filename)

                if data['code'] != 0:
                    self.log(f"获取会话列表失败: {data.get('message', 'Unknown error')} (Code: {data['code']})")
                    break

                sessions = data['data'].get('session_list', [])
                has_more = data['data'].get('has_more', False)

                if not sessions:
                    self.log("未获取到更多会话")
                    break

                all_sessions.extend(sessions)
                page_count += 1
                current_page_end_ts = sessions[-1]['session_ts']

                self.log(f"第{page_count}页: 获取到{len(sessions)}个会话，总计{len(all_sessions)}个")
                self.success_count += 1
                self.failure_count = max(0, self.failure_count - 1)
                self.smart_delay()

            except Exception as e:
                self.log(f"获取会话列表时发生错误: {e}")
                self.failure_count += 1
                has_more = False
                break

        self.log(f"会话列表获取完成，共{len(all_sessions)}个会话")
        return all_sessions

    def fetch_session_messages(self, talker_id, session_info=None):
        """获取指定会话的消息"""
        self.log(f"开始获取会话 {talker_id} 的消息")

        try:
            params = {
                'talker_id': talker_id,
                'session_type': 1,
                'size': 30,
                'build': 0,
                'mobi_app': 'web'
            }

            resp = requests.get(
                f"{self.api_base}/svr_sync/v1/svr_sync/fetch_session_msgs",
                params=params,
                headers=self.headers,
                cookies=self.cookies,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()

            # 保存原始响应
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"messages_talker_{talker_id}_{timestamp}.json"
            self.save_json(data, filename)

            if data['code'] == 0:
                messages = data['data'].get('messages', [])
                self.log(f"会话 {talker_id}: 获取到 {len(messages)} 条消息")
                self.success_count += 1
                self.failure_count = max(0, self.failure_count - 1)
                return messages
            else:
                self.log(f"获取会话 {talker_id} 消息失败: {data.get('message', '')} (Code: {data['code']})")
                self.failure_count += 1
                return []

        except Exception as e:
            self.log(f"获取会话 {talker_id} 消息时发生错误: {e}")
            self.failure_count += 1
            return []

    def crawl_all_messages(self, max_session_pages=5, max_sessions=None):
        """抓取所有私信消息"""
        self.log("=" * 50)
        self.log("开始抓取B站私信消息")
        self.log("=" * 50)

        # 获取会话列表
        sessions = self.fetch_sessions(max_session_pages)
        if not sessions:
            self.log("未获取到任何会话，抓取结束")
            return

        # 限制处理的会话数量
        if max_sessions and len(sessions) > max_sessions:
            sessions = sessions[:max_sessions]
            self.log(f"限制处理会话数量为: {max_sessions}")

        # 获取每个会话的消息
        total_messages = 0
        for i, session in enumerate(sessions, 1):
            talker_id = session['talker_id']
            self.log(f"处理第 {i}/{len(sessions)} 个会话: UID {talker_id}")

            messages = self.fetch_session_messages(talker_id, session)
            total_messages += len(messages)

            self.smart_delay()

        self.log("=" * 50)
        self.log("抓取完成！")
        self.log(f"总计处理: {len(sessions)} 个会话")
        self.log(f"总计消息: {total_messages} 条")
        self.log(f"数据保存在: {self.output_dir}")
        self.log("=" * 50)


def main():
    """主函数"""
    print("B站私信抓取测试程序")
    print("=" * 50)

    # 创建爬虫实例
    crawler = BilibiliMessageCrawler()

    # 输入Cookie
    print("请输入完整的Cookie字符串:")
    print("格式示例: SESSDATA=xxx; bili_jct=xxx; buvid3=xxx")
    cookie_input = input("Cookie: ").strip()

    if not cookie_input:
        print("Cookie不能为空！")
        return

    try:
        # 设置Cookie
        crawler.set_cookie(cookie_input)

        # 设置抓取参数
        max_session_pages = int(input("请输入要抓取的会话列表页数 (默认5): ") or "5")
        max_sessions_input = input("请输入最大处理会话数量 (默认不限制，直接回车): ").strip()
        max_sessions = int(max_sessions_input) if max_sessions_input else None

        print("\n抓取参数:")
        print(f"- 会话列表页数: {max_session_pages}")
        print(f"- 最大会话数量: {max_sessions or '不限制'}")
        print(f"- 输出目录: {crawler.output_dir}")

        confirm = input("\n确认开始抓取? (y/N): ").strip().lower()
        if confirm != 'y':
            print("取消抓取")
            return

        # 开始抓取
        crawler.crawl_all_messages(max_session_pages, max_sessions)

    except ValueError as e:
        print(f"参数错误: {e}")
    except Exception as e:
        print(f"抓取过程中发生错误: {e}")

    input("\n按回车键退出...")


if __name__ == "__main__":
    main()