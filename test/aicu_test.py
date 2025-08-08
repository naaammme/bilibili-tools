import tkinter as tk
from tkinter import ttk, scrolledtext
import json
import time
import threading
from datetime import datetime

# DrissionPage导入
try:
    from DrissionPage import ChromiumPage, ChromiumOptions
except ImportError:
    print("请安装DrissionPage: pip install DrissionPage")
    exit()

class HeadlessDrissionClient:
    """使用DrissionPage的无头模式客户端"""

    def __init__(self):
        self.page = None
        self.is_headless = True  # 默认无头模式

    def create_page(self, headless=True):
        """创建页面实例"""
        # 配置选项
        co = ChromiumOptions()

        if headless:
            # 无头模式配置
            co.headless(True)  # 启用无头模式
            co.set_argument('--no-sandbox')
            co.set_argument('--disable-dev-shm-usage')
            co.set_argument('--disable-gpu')
            co.set_argument('--disable-web-security')
            co.set_argument('--disable-features=VizDisplayCompositor')
            co.set_argument('--disable-software-rasterizer')

        # 隐身相关设置
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

        # 设置窗口大小（即使无头模式也需要）
        co.set_argument('--window-size=1920,1080')

        # 忽略证书错误
        co.set_argument('--ignore-certificate-errors')
        co.set_argument('--ignore-ssl-errors')

        # 其他优化
        co.set_argument('--disable-extensions')
        co.set_argument('--disable-images')  # 不加载图片，加快速度
        co.set_argument('--disable-plugins')

        # 创建页面
        self.page = ChromiumPage(co)

        # 注入JavaScript以绕过检测
        self.page.run_js("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = {
                runtime: {}
            };
        """)

        return self.page

    def fetch_api(self, url, timeout=30):
        """获取API数据"""
        try:
            if not self.page:
                print("初始化浏览器（无头模式）...")
                self.create_page(headless=self.is_headless)

            print(f"访问URL: {url}")
            self.page.get(url)

            # 等待页面加载
            start_time = time.time()
            max_wait = timeout

            # 智能等待策略
            while time.time() - start_time < max_wait:
                # 检查是否有JSON响应
                try:
                    # 方法1：检查pre标签
                    pre_element = self.page.ele('tag:pre')
                    if pre_element:
                        text = pre_element.text
                        if text and (text.startswith('{') or text.startswith('[')):
                            print("从<pre>标签获取到JSON响应")
                            return {
                                'success': True,
                                'data': text,
                                'method': 'pre_tag'
                            }
                except:
                    pass

                # 方法2：检查body文本
                try:
                    body_text = self.page.ele('tag:body').text
                    if body_text and (body_text.startswith('{') or body_text.startswith('[')):
                        # 尝试解析为JSON验证
                        json.loads(body_text)
                        print("从body获取到JSON响应")
                        return {
                            'success': True,
                            'data': body_text,
                            'method': 'body_text'
                        }
                except:
                    pass

                # 检查是否还在处理WAF挑战
                current_url = self.page.url
                page_title = self.page.title

                if 'challenge' in current_url.lower() or 'waf' in page_title.lower():
                    print(f"检测到WAF挑战，等待处理... ({int(time.time() - start_time)}秒)")

                time.sleep(0.5)

            # 超时后返回页面内容
            return {
                'success': False,
                'data': self.page.html,
                'error': '未能获取到JSON响应'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def close(self):
        """关闭浏览器"""
        if self.page:
            self.page.quit()
            self.page = None

class DrissionPageGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DrissionPage API客户端（后台静默版）")
        self.root.geometry("900x700")

        self.client = HeadlessDrissionClient()
        self.create_widgets()

        # 窗口关闭时清理
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # URL配置
        config_frame = ttk.LabelFrame(main_frame, text="API配置", padding="10")
        config_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(config_frame, text="API URL:").grid(row=0, column=0, sticky=tk.W)
        self.url_var = tk.StringVar(value="https://apibackup2.aicu.cc:88/api/v3/search/getreply")
        ttk.Entry(config_frame, textvariable=self.url_var, width=70).grid(row=0, column=1, padx=5, sticky=(tk.W, tk.E))

        # 参数
        param_frame = ttk.LabelFrame(main_frame, text="请求参数", padding="10")
        param_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        params = [
            ("UID:", "uid_var", "452981646"),
            ("页码:", "pn_var", "1"),
            ("页大小:", "ps_var", "20"),
            ("模式:", "mode_var", "0")
        ]

        for i, (label, var_name, default) in enumerate(params):
            ttk.Label(param_frame, text=label).grid(row=i//2, column=(i%2)*2, sticky=tk.W, padx=5)
            setattr(self, var_name, tk.StringVar(value=default))
            ttk.Entry(param_frame, textvariable=getattr(self, var_name), width=20).grid(row=i//2, column=(i%2)*2+1, padx=5)

        # 模式选择
        mode_frame = ttk.LabelFrame(main_frame, text="运行模式", padding="10")
        mode_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        self.headless_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(mode_frame, text="无头模式（后台运行，不显示浏览器窗口）",
                        variable=self.headless_var).grid(row=0, column=0, sticky=tk.W)

        ttk.Label(mode_frame, text="提示：取消勾选可看到浏览器操作过程，用于调试",
                  foreground="gray").grid(row=1, column=0, sticky=tk.W, padx=20)

        # 按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)

        self.fetch_btn = ttk.Button(btn_frame, text="获取数据", command=self.fetch_data)
        self.fetch_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="清空结果", command=self.clear_results).pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="重启浏览器", command=self.restart_browser).pack(side=tk.LEFT, padx=5)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN).grid(
            row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)

        # 结果显示
        result_frame = ttk.LabelFrame(main_frame, text="结果", padding="10")
        result_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)

        self.result_text = scrolledtext.ScrolledText(result_frame, wrap=tk.WORD, width=80, height=20)
        self.result_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 配置权重
        self.root.columnconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(5, weight=1)

    def log(self, message):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.result_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.result_text.see(tk.END)
        self.root.update_idletasks()

    def fetch_data(self):
        """获取数据"""
        self.fetch_btn.config(state="disabled")
        self.status_var.set("正在请求...")

        # 更新客户端的无头模式设置
        self.client.is_headless = self.headless_var.get()

        thread = threading.Thread(target=self._fetch_thread)
        thread.daemon = True
        thread.start()

    def _fetch_thread(self):
        """请求线程"""
        try:
            # 构建URL
            params = {
                'uid': self.uid_var.get(),
                'pn': self.pn_var.get(),
                'ps': self.ps_var.get(),
                'mode': self.mode_var.get()
            }
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            url = f"{self.url_var.get()}?{query_string}"

            self.log(f"目标URL: {url}")
            self.log(f"运行模式: {'无头模式（后台静默）' if self.headless_var.get() else '有头模式（显示浏览器）'}")
            self.log("-" * 60)

            # 获取数据
            result = self.client.fetch_api(url)

            if result['success']:
                self.log("✓ 成功获取到数据")
                self.log(f"获取方式: {result.get('method', 'unknown')}")
                self.log("=" * 60)

                # 解析并格式化JSON
                try:
                    data = json.loads(result['data'])
                    formatted = json.dumps(data, indent=2, ensure_ascii=False)
                    self.log("JSON响应:")
                    self.log(formatted)

                    # 显示关键信息
                    if 'code' in data:
                        self.log(f"\n响应码: {data['code']}")
                    if 'data' in data and isinstance(data['data'], list):
                        self.log(f"数据条数: {len(data['data'])}")

                except json.JSONDecodeError:
                    self.log("原始响应:")
                    self.log(result['data'])

            else:
                self.log(f"✗ 获取失败: {result.get('error', '未知错误')}")
                if 'data' in result:
                    self.log("\n页面内容预览:")
                    self.log(result['data'][:500] + "...")

        except Exception as e:
            self.log(f"错误: {str(e)}")

        finally:
            self.root.after(0, lambda: self.fetch_btn.config(state="normal"))
            self.root.after(0, lambda: self.status_var.set("就绪"))

    def restart_browser(self):
        """重启浏览器"""
        self.log("重启浏览器...")
        self.client.close()
        self.log("浏览器已关闭，下次请求时将重新启动")

    def clear_results(self):
        """清空结果"""
        self.result_text.delete(1.0, tk.END)

    def on_closing(self):
        """关闭窗口时清理"""
        self.client.close()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = DrissionPageGUI(root)

    app.log("=== DrissionPage API客户端（后台静默版）===")
    app.log("特点:")
    app.log("• 默认无头模式，不会弹出浏览器窗口")
    app.log("• 自动处理JavaScript挑战")
    app.log("• 保持会话，多次请求更快")
    app.log("• 可切换到有头模式进行调试")
    app.log("=" * 50)

    root.mainloop()

if __name__ == "__main__":
    main()