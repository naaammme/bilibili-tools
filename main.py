import sys
import asyncio
import logging
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMessageBox
from PyQt6.QtGui import QIcon
from src.style import get_stylesheet, get_resource_path

# 不调用控制台输出,打包后不让他调用控制台,不然会在一些电脑报错
class DummyStream:
    def write(self, text): pass
    def flush(self): pass

if sys.stdout is None: sys.stdout = DummyStream()
if sys.stderr is None: sys.stderr = DummyStream()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BilibiliToolsCollection:
    """B站工具集合应用
    主页面自由选择想要的工具

    """

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("B站小工具")


        # 设置图标和样式
        try:
            icon_path = get_resource_path("assets/1.png")
            self.app.setWindowIcon(QIcon(icon_path))
            self.tray_icon = QSystemTrayIcon()#系统托盘图标
            self.tray_icon.setIcon(QIcon(icon_path))
            self.tray_icon.show()
        except: pass

        self.app.setStyleSheet(get_stylesheet())

        # 导入;使用带账号管理的工具选择页面,
        from src.screens.tool_selection_screen import ToolSelectionScreen

        # 不提供初始的api_service，让账号管理器自动加载
        self.main_window = ToolSelectionScreen(None, True)
        self.main_window.resize(900, 600)
        self.main_window.setWindowTitle("Bilibili小工具")

        # 连接每个工具screen
        self.main_window.open_comment_tool.connect(self.open_comment_tool)
        self.main_window.open_unfollow_tool.connect(self.open_unfollow_tool)
        self.main_window.open_comment_stats_tool.connect(self.open_comment_stats_tool)
        self.main_window.open_message_tool.connect(self.open_message_tool)

        # 子窗口引用
        self.comment_clean_window = None
        self.unfollow_window = None
        self.comment_stats_window = None
        self.comment_detail_window = None
        self.message_manager_window = None

        logger.info("应用初始化完成 - 使用账号管理模式")

    def open_comment_tool(self):
        """打开评论清理工具"""
        try:
            # 检查登录状态
            if not self.main_window.api_service:
                QMessageBox.warning(
                    self.main_window,
                    "未登录",
                    "请先登录账号才能使用评论清理工具。\n\n"
                    "点击界面上的登录按钮或使用菜单栏登录。"
                )
                return

            # 检查窗口是否存在
            if self.comment_clean_window and not self.comment_clean_window.isHidden():
                self.comment_clean_window.show()
                self.comment_clean_window.raise_()
                self.comment_clean_window.activateWindow()
                return

            # 导入,创建评论清理窗口
            from src.screens.Comment_Clean_Screen import CommentCleanScreen
            self.comment_clean_window = CommentCleanScreen(
                self.main_window.api_service,
                self.main_window.aicu_state
            )
            #链接清理内存信号
            self.comment_clean_window.window_closed.connect(self.on_comment_clean_window_closed)
            # 连接返回信号
            self.comment_clean_window.back_to_tools.connect(self.close_comment_tool)

            # 连接评论详情信号
            self.comment_clean_window.open_comment_detail.connect(self.open_comment_detail_tool)

            # 设置窗口
            self.comment_clean_window.setWindowTitle("Bilibili 评论清理工具")
            self.comment_clean_window.resize(1200, 800)
            self.comment_clean_window.show()

            logger.info("评论清理工具已打开")

        except Exception as e:
            logger.error(f"打开评论清理工具失败: {e}")
            QMessageBox.critical(self.main_window, "错误", f"无法打开评论清理工具: {e}")

    def open_unfollow_tool(self):
        """打开批量取关工具"""
        try:
            # 也检查登录状态
            if not self.main_window.api_service:
                QMessageBox.warning(
                    self.main_window,
                    "未登录",
                    "请先登录账号才能使用批量取关工具。\n\n"
                    "点击界面上的登录按钮或使用菜单栏登录。"
                )
                return

            # 检查窗口是否已存在
            if self.unfollow_window and not self.unfollow_window.isHidden():
                self.unfollow_window.show()
                self.unfollow_window.raise_()
                self.unfollow_window.activateWindow()
                return

            # 导入,创建批量取关窗口
            from src.screens.unfollow_screen import UnfollowScreen
            self.unfollow_window = UnfollowScreen(self.main_window.api_service)

            # 连接信号
            self.unfollow_window.back_to_tools.connect(self.close_unfollow_tool)
            # 连接窗口关闭信号
            self.unfollow_window.window_closed.connect(self.on_unfollow_window_closed)
            #窗口
            self.unfollow_window.setWindowTitle("Bilibili 批量取关工具")
            self.unfollow_window.resize(900, 700)
            self.unfollow_window.show()

            logger.info("批量取关工具已打开")

        except Exception as e:
            logger.error(f"打开批量取关工具失败: {e}")
            QMessageBox.critical(self.main_window, "错误", f"无法打开批量取关工具: {e}")

    def on_unfollow_window_closed(self):
        """处理批量取关窗口关闭事件"""
        logger.info("收到批量取关窗口关闭信号")

        if self.unfollow_window:
            # 断开信号连接
            try:
                self.unfollow_window.back_to_tools.disconnect()
                self.unfollow_window.window_closed.disconnect()
            except:
                pass

            # 确保窗口被删除
            self.unfollow_window.deleteLater()
            self.unfollow_window = None

            # 强制垃圾回收
            import gc
            gc.collect()

            logger.info("批量取关工具窗口已关闭并清理完成")

    def on_comment_clean_window_closed(self):
        """处理评论清理窗口关闭事件"""
        if self.comment_clean_window:
            self.comment_clean_window = None
            logger.info("评论清理工具窗口已关闭并清理")

    def open_comment_stats_tool(self):
        """打开评论数据统计工具"""
        try:
            # 检查登录状态
            if not self.main_window.api_service:
                QMessageBox.warning(
                    self.main_window,
                    "未登录",
                    "请先登录账号才能使用评论统计工具。\n\n"
                    "点击界面上的登录按钮或使用菜单栏登录。"
                )
                return

            # 检查窗口是否已存在
            if self.comment_stats_window and not self.comment_stats_window.isHidden():
                self.comment_stats_window.show()
                self.comment_stats_window.raise_()
                self.comment_stats_window.activateWindow()
                return

            # 创建评论统计窗口
            from src.screens.comment_stats_screen import CommentStatsScreen
            self.comment_stats_window = CommentStatsScreen(
                self.main_window.api_service,
                self.main_window.aicu_state
            )

            # 连接信号
            self.comment_stats_window.back_to_tools.connect(self.close_comment_stats_tool)
            # 连接窗口关闭信号
            self.comment_stats_window.window_closed.connect(self.on_comment_stats_window_closed)

            # 窗口
            self.comment_stats_window.setWindowTitle("Bilibili 数据统计")
            self.comment_stats_window.resize(1200, 800)
            self.comment_stats_window.show()

            logger.info("数据统计工具已打开")

        except Exception as e:
            logger.error(f"打开数据统计工具失败: {e}")
            QMessageBox.critical(self.main_window, "错误", f"无法打开数据统计工具: {e}")

    def on_comment_stats_window_closed(self):
        """处理数据统计窗口关闭事件"""
        if self.comment_stats_window:
            self.comment_stats_window = None
            logger.info("数据统计工具窗口已关闭并清理")

    def open_comment_detail_tool(self, comment_id: int, oid: int, type_: int):
        """打开评论详情工具"""
        try:
            # 检查登录状态
            if not self.main_window.api_service:
                QMessageBox.warning(
                    self.main_window,
                    "未登录",
                    "请先登录账号才能查看评论详情。"
                )
                return

            # 从评论清理窗口获取评论对象
            comment_data = None
            if self.comment_clean_window and hasattr(self.comment_clean_window, 'all_comments'):
                comment_data = self.comment_clean_window.all_comments.get(comment_id)

            # 关闭之前的详情窗口
            if self.comment_detail_window:
                self.comment_detail_window.close()

            # 创建评论详情窗口 - 传入comment_data
            from src.screens.comment_detail_screen import CommentDetailScreen
            self.comment_detail_window = CommentDetailScreen(
                self.main_window.api_service,
                comment_id,
                oid,
                type_,
                comment_data
            )

            # 连接返回信号
            self.comment_detail_window.back_to_stats.connect(self.close_comment_detail_tool)

            # 设置窗口
            self.comment_detail_window.setWindowTitle(f"评论详情 - ID: {comment_id}")
            self.comment_detail_window.resize(800, 600)
            self.comment_detail_window.show()

            logger.info(f"评论详情工具已打开 - 评论ID: {comment_id}")

        except Exception as e:
            logger.error(f"打开评论详情工具失败: {e}")
            QMessageBox.critical(self.main_window, "错误", f"无法打开评论详情: {e}")

    def close_comment_stats_tool(self):
        """关闭评论统计工具"""
        if self.comment_stats_window:
            self.comment_stats_window.close()
            self.comment_stats_window = None
            logger.info("评论统计工具已关闭")

    def close_unfollow_tool(self):
        """关闭取关工具方法"""
        if self.unfollow_window:
            logger.info("正在关闭批量取关工具...")

            # 先断开信号连接
            try:
                self.unfollow_window.back_to_tools.disconnect()
                self.unfollow_window.window_closed.disconnect()
            except:
                pass  # 忽略断开连接时的错误

            # 关闭窗口
            self.unfollow_window.close()

            # 等待窗口完全关闭
            QApplication.processEvents()

            # 确保窗口被删除
            self.unfollow_window.deleteLater()
            self.unfollow_window = None

            logger.info("批量取关工具已关闭并清理")

    def close_comment_detail_tool(self):
        """关闭评论详情工具"""
        if self.comment_detail_window:
            self.comment_detail_window.close()
            self.comment_detail_window = None
            logger.info("评论详情工具已关闭")

    def open_message_tool(self):
        """打开私信管理工具"""
        try:
            # 检查登录状态
            if not self.main_window.api_service:
                QMessageBox.warning(
                    self.main_window,
                    "未登录",
                    "请先登录账号才能使用私信管理工具。"
                )
                return

            # 检查窗口是否已存在
            if self.message_manager_window and not self.message_manager_window.isHidden():
                self.message_manager_window.show()
                self.message_manager_window.raise_()
                self.message_manager_window.activateWindow()
                return

            # 创建私信管理窗口
            from src.screens.message_manager_screen import MessageManagerScreen
            self.message_manager_window = MessageManagerScreen(self.main_window.api_service)

            # 连接信号
            self.message_manager_window.back_to_tools.connect(self.close_message_tool)
            self.message_manager_window.window_closed.connect(self.on_message_manager_window_closed)

            # 设置窗口
            self.message_manager_window.setWindowTitle("Bilibili 私信管理工具")
            self.message_manager_window.resize(1300, 900)
            self.message_manager_window.show()

            logger.info("私信管理工具已打开")

        except Exception as e:
            logger.error(f"打开私信管理工具失败: {e}")
            QMessageBox.critical(self.main_window, "错误", f"无法打开私信管理工具: {e}")

    def close_message_tool(self):
        """关闭私信管理工具"""
        if self.message_manager_window:
            self.message_manager_window.close()
            self.message_manager_window = None
            logger.info("私信管理工具已关闭")

    def on_message_manager_window_closed(self):
        """处理私信管理窗口关闭事件"""
        if self.message_manager_window:
            self.message_manager_window = None
            logger.info("私信管理工具窗口已关闭并清理")

    def close_comment_tool(self):
        """关闭评论清理工具"""
        if self.comment_clean_window:
            self.comment_clean_window.close()
            self.comment_clean_window = None
            logger.info("评论清理工具已关闭")

    def run(self):
        try:
            self.main_window.show()

            # 显示启动信息
            if self.main_window.account_manager and self.main_window.account_manager.has_accounts():
                if self.main_window.api_service:
                    logger.info("已自动登录保存的账号")
                else:
                    logger.info("发现保存的账号但登录失败，请重新登录")
            else:
                logger.info("首次使用，请登录账号")

            # 导入,异步事件循环
            import qasync
            loop = qasync.QEventLoop(self.app)
            asyncio.set_event_loop(loop)

            with loop:
                loop.run_forever()

        except Exception as e:
            logger.error(f"应用运行失败: {e}")
            QMessageBox.critical(None, "错误", f"应用运行失败: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """清理资源方法"""
        try:
            # 先关闭所有子窗口
            if self.comment_clean_window:
                self.comment_clean_window.close()
                # 等待窗口完全关闭
                if hasattr(self.comment_clean_window, 'fetch_thread'):
                    if self.comment_clean_window.fetch_thread and self.comment_clean_window.fetch_thread.isRunning():
                        self.comment_clean_window.fetch_thread.stop()
                        self.comment_clean_window.fetch_thread.wait(1000)

            if self.unfollow_window:
                self.unfollow_window.close()

            if self.comment_stats_window:
                self.comment_stats_window.close()

            if self.comment_detail_window:
                self.comment_detail_window.close()

            if self.message_manager_window:
                self.message_manager_window.close()
            # 最后关闭主窗口
            if self.main_window:
                # 如果主窗口有用户名线程，等待它结束
                if hasattr(self.main_window, 'username_thread'):
                    if self.main_window.username_thread and self.main_window.username_thread.isRunning():
                        self.main_window.username_thread.stop()
                        self.main_window.username_thread.wait(1000)
                self.main_window.close()

            # 给Qt一点时间来清理
            QApplication.processEvents()

            logger.info("应用清理完成")
        except Exception as e:
            logger.error(f"清理失败: {e}")

def main():
    try:
        app = BilibiliToolsCollection()
        app.run()
    except Exception as e:
        logger.error(f"启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()