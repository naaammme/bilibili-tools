import logging
import time
from typing import Dict, List, Optional, Tuple
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QGridLayout, QProgressBar, QScrollArea, QListWidget,
    QListWidgetItem, QTableWidgetItem, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont

from ..api.api_service import ApiService

logger = logging.getLogger(__name__)

class StatsLoader(QThread):
    """统计数据加载线程"""
    data_loaded = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, api_service: ApiService):
        super().__init__()
        self.api_service = api_service

    def run(self):
        try:
            from ..database import DatabaseManager
            db_manager = DatabaseManager()

            uid, _, _ = self.api_service.get_cached_user_info()
            if not uid:
                self.error.emit("无法获取用户信息")
                return

            stats = self._load_stats(db_manager, uid)
            self.data_loaded.emit(stats)

        except Exception as e:
            logger.error(f"加载统计数据失败: {e}")
            self.error.emit(f"加载失败: {e}")

    def _load_stats(self, db_manager, uid):
        """加载统计数据"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            # 评论统计
            cursor.execute('SELECT COUNT(*) FROM comments WHERE uid = ? AND is_deleted = FALSE', (uid,))
            stats['total_comments'] = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM comments WHERE uid = ? AND is_deleted = TRUE', (uid,))
            stats['deleted_comments'] = cursor.fetchone()[0]

            # 弹幕统计
            cursor.execute('SELECT COUNT(*) FROM danmus WHERE uid = ? AND is_deleted = FALSE', (uid,))
            stats['total_danmus'] = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM danmus WHERE uid = ? AND is_deleted = TRUE', (uid,))
            stats['deleted_danmus'] = cursor.fetchone()[0]

            # 通知统计
            cursor.execute('SELECT COUNT(*) FROM notifies WHERE uid = ? AND is_deleted = FALSE', (uid,))
            stats['total_notifies'] = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM notifies WHERE uid = ? AND is_deleted = TRUE', (uid,))
            stats['deleted_notifies'] = cursor.fetchone()[0]

            # 按类型统计通知
            cursor.execute('''
                SELECT tp, COUNT(*) FROM notifies 
                WHERE uid = ? AND is_deleted = FALSE 
                GROUP BY tp
            ''', (uid,))
            notify_by_type = dict(cursor.fetchall())
            stats['notify_by_type'] = {
                'liked': notify_by_type.get(0, 0),
                'replied': notify_by_type.get(1, 0),
                'ated': notify_by_type.get(2, 0),
                'system': notify_by_type.get(4, 0)
            }

            # 按来源统计
            cursor.execute('''
                SELECT source, COUNT(*) FROM comments 
                WHERE uid = ? AND is_deleted = FALSE 
                GROUP BY source
            ''', (uid,))
            comments_by_source = dict(cursor.fetchall())
            stats['comments_by_source'] = comments_by_source

            cursor.execute('''
                SELECT source, COUNT(*) FROM danmus 
                WHERE uid = ? AND is_deleted = FALSE 
                GROUP BY source
            ''', (uid,))
            danmus_by_source = dict(cursor.fetchall())
            stats['danmus_by_source'] = danmus_by_source

            # 时间范围统计
            cursor.execute('''
                SELECT MIN(created_time), MAX(created_time) FROM comments 
                WHERE uid = ? AND is_deleted = FALSE AND created_time > 0
            ''', (uid,))
            comment_time_range = cursor.fetchone()
            stats['comment_time_range'] = comment_time_range

            cursor.execute('''
                SELECT MIN(created_time), MAX(created_time) FROM notifies 
                WHERE uid = ? AND is_deleted = FALSE AND created_time > 0
            ''', (uid,))
            notify_time_range = cursor.fetchone()
            stats['notify_time_range'] = notify_time_range

            # 获取评论点赞排行榜（前20名）
            cursor.execute('''
                SELECT id, content, like_count, oid, type, created_time, source, video_uri
                FROM comments 
                WHERE uid = ? AND is_deleted = FALSE 
                AND source = 'bilibili' 
                AND like_count IS NOT NULL 
                AND like_count > 0
                ORDER BY like_count DESC, created_time DESC
                LIMIT 100
            ''', (uid,))

            like_ranking = []
            for row in cursor.fetchall():
                like_ranking.append({
                    'id': row[0],
                    'content': row[1][:100] + '...' if len(row[1]) > 100 else row[1],  # 限制长度
                    'like_count': row[2],
                    'oid': row[3],
                    'type': row[4],
                    'created_time': row[5],
                    'source': row[6],
                    'video_uri': row[7]
                })

            stats['like_ranking'] = like_ranking
            return stats


class CommentStatsScreen(QWidget):
    """数据统计界面"""

    back_to_tools = pyqtSignal()
    window_closed = pyqtSignal()
    def __init__(self, api_service: ApiService, aicu_state: bool):
        super().__init__()
        self.api_service = api_service
        self.aicu_state = aicu_state
        self.stats_data = {}

        self.init_ui()
        self.load_data()

    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # 顶部工具栏
        self.create_toolbar(layout)

        # 使用QTabWidget创建标签页
        from PyQt6.QtWidgets import QTabWidget
        self.tab_widget = QTabWidget()

        # 评论统计标签页
        comment_stats_widget = QWidget()
        self.create_comment_stats_tab(comment_stats_widget)
        self.tab_widget.addTab(comment_stats_widget, "评论统计")

        # 私信统计标签页
        message_stats_widget = QWidget()
        self.create_message_stats_tab(message_stats_widget)
        self.tab_widget.addTab(message_stats_widget, "私信统计")

        layout.addWidget(self.tab_widget)



    def create_toolbar(self, layout):
        """创建顶部工具栏"""
        toolbar_layout = QHBoxLayout()

        # 返回按钮
        back_btn = QPushButton("← 返回工具选择")
        back_btn.clicked.connect(self.back_to_tools.emit)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #7f8c8d;
                color: white;
                padding: 8px 15px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #95a5a6;
            }
        """)
        toolbar_layout.addWidget(back_btn)

        # 标题
        title_label = QLabel("数据统计")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #ecf0f1;")
        toolbar_layout.addWidget(title_label)

        # 刷新按钮,暂时有bug,懒得修了
        refresh_btn = QPushButton("🔄 不要点击")
        refresh_btn.clicked.connect(self.load_data)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 8px 15px;
                border-radius: 6px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        toolbar_layout.addWidget(refresh_btn)

        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)

    def load_data(self):
        """加载统计数据"""
        if hasattr(self, 'loader_thread') and self.loader_thread.isRunning():
            return

        self.loader_thread = StatsLoader(self.api_service)
        self.loader_thread.data_loaded.connect(self.on_data_loaded)
        self.loader_thread.error.connect(self.on_load_error)
        self.loader_thread.start()

    @pyqtSlot(object)
    def on_data_loaded(self, stats_data):
        """数据加载完成"""
        self.stats_data = stats_data
        self.display_stats()

    @pyqtSlot(str)
    def on_load_error(self, error_msg):
        """数据加载失败"""
        self.loading_label.setText(f"加载失败: {error_msg}")

    def display_stats(self):
        """显示统计数据"""
        # 清除加载提示
        if hasattr(self, 'loading_label'):
            self.loading_label.deleteLater()

        # 基础统计卡片
        self.create_basic_stats_card()

        # 通知类型分布卡片
        self.create_notify_type_card()

        # 数据来源统计卡片
        self.create_source_stats_card()

        # 时间范围统计卡片
        self.create_time_range_card()

        # 点赞排行榜卡片
        self.create_like_ranking_card()

        # 添加底部空间
        self.stats_layout.addStretch()

    def create_basic_stats_card(self):
        """创建基础统计卡片"""
        card = self.create_card("📊 基础数据统计")
        grid = QGridLayout()

        # 数据项
        items = [
            ("评论总数", self.stats_data.get('total_comments', 0), "#3498db"),
            ("已删除评论", self.stats_data.get('deleted_comments', 0), "#e74c3c"),
            ("弹幕总数", self.stats_data.get('total_danmus', 0), "#9b59b6"),
            ("已删除弹幕", self.stats_data.get('deleted_danmus', 0), "#e74c3c"),
            ("通知总数", self.stats_data.get('total_notifies', 0), "#f39c12"),
            ("已删除通知", self.stats_data.get('deleted_notifies', 0), "#e74c3c"),
        ]

        for i, (label, value, color) in enumerate(items):
            row, col = i // 3, i % 3
            stat_widget = self.create_stat_item(label, str(value), color)
            grid.addWidget(stat_widget, row, col)

        card.layout().addLayout(grid)
        self.stats_layout.addWidget(card)

    def create_notify_type_card(self):
        """创建通知类型分布卡片"""
        card = self.create_card("🔔 通知类型分布")
        grid = QGridLayout()

        notify_types = self.stats_data.get('notify_by_type', {})
        type_names = {
            'liked': '点赞通知',
            'replied': '回复通知',
            'ated': '@通知',
            'system': '系统通知'
        }
        colors = {
            'liked': '#e74c3c',
            'replied': '#3498db',
            'ated': '#f39c12',
            'system': '#9b59b6'
        }

        for i, (key, name) in enumerate(type_names.items()):
            count = notify_types.get(key, 0)
            stat_widget = self.create_stat_item(name, str(count), colors[key])
            grid.addWidget(stat_widget, i // 2, i % 2)

        card.layout().addLayout(grid)
        self.stats_layout.addWidget(card)

    def create_source_stats_card(self):
        """创建数据来源统计卡片"""
        card = self.create_card("📡 数据来源统计")
        grid = QGridLayout()

        comments_by_source = self.stats_data.get('comments_by_source', {})
        danmus_by_source = self.stats_data.get('danmus_by_source', {})

        # 评论来源
        bilibili_comments = comments_by_source.get('bilibili', 0)
        aicu_comments = comments_by_source.get('aicu', 0)

        # 弹幕来源
        bilibili_danmus = danmus_by_source.get('bilibili', 0)
        aicu_danmus = danmus_by_source.get('aicu', 0)

        items = [
            ("B站评论", bilibili_comments, "#00a1d6"),
            ("AICU评论", aicu_comments, "#ff6b9d"),
            ("B站弹幕", bilibili_danmus, "#00a1d6"),
            ("AICU弹幕", aicu_danmus, "#ff6b9d"),
        ]

        for i, (label, value, color) in enumerate(items):
            stat_widget = self.create_stat_item(label, str(value), color)
            grid.addWidget(stat_widget, i // 2, i % 2)

        card.layout().addLayout(grid)
        self.stats_layout.addWidget(card)

    def create_time_range_card(self):
        """创建时间范围统计卡片"""
        card = self.create_card("⏰ 时间范围统计")
        layout = QVBoxLayout()

        # 评论时间范围
        comment_range = self.stats_data.get('comment_time_range', (None, None))
        if comment_range[0] and comment_range[1]:
            start_time = time.strftime('%Y-%m-%d', time.localtime(comment_range[0]))
            end_time = time.strftime('%Y-%m-%d', time.localtime(comment_range[1]))
            comment_range_text = f"评论时间范围: {start_time} ~ {end_time}"
        else:
            comment_range_text = "评论时间范围: 无数据"

        comment_label = QLabel(comment_range_text)
        comment_label.setStyleSheet("color: #ecf0f1; font-size: 14px; padding: 5px;")
        layout.addWidget(comment_label)

        # 通知时间范围
        notify_range = self.stats_data.get('notify_time_range', (None, None))
        if notify_range[0] and notify_range[1]:
            start_time = time.strftime('%Y-%m-%d', time.localtime(notify_range[0]))
            end_time = time.strftime('%Y-%m-%d', time.localtime(notify_range[1]))
            notify_range_text = f"通知时间范围: {start_time} ~ {end_time}"
        else:
            notify_range_text = "通知时间范围: 无数据"

        notify_label = QLabel(notify_range_text)
        notify_label.setStyleSheet("color: #ecf0f1; font-size: 14px; padding: 5px;")
        layout.addWidget(notify_label)

        card.layout().addLayout(layout)
        self.stats_layout.addWidget(card)

    def create_like_ranking_card(self):
        """创建评论点赞排行榜卡片"""
        card = self.create_card("👍 评论点赞排行榜")
        layout = QVBoxLayout()

        # 创建排行榜表格
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        self.ranking_table = QTableWidget()
        self.ranking_table.setColumnCount(4)
        self.ranking_table.setHorizontalHeaderLabels(["排名", "点赞数", "内容概要", "发布时间"])

        self.ranking_table.setMinimumHeight(400)
        self.ranking_table.itemDoubleClicked.connect(self.open_comment_detail_from_ranking)

        self.ranking_table.setStyleSheet("""
            QTableWidget {
                background-color: #2c3e50;
                border: 1px solid #566573;
                border-radius: 4px;
                color: #ecf0f1;
                gridline-color: #34495e;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 8px;
                border-bottom: 1px solid #34495e;
                min-height: 20px;
            }
            QTableWidget::item:hover {
                background-color: #34495e;
            }
            QTableWidget::item:selected {
                background-color: #3498db;
            }
            QHeaderView::section {
                background-color: #566573;
                color: #ecf0f1;
                padding: 10px;
                border: 1px solid #7f8c8d;
                font-weight: bold;
                font-size: 14px;
            }
            QHeaderView::section:hover {
                background-color: #7f8c8d;
            }
        """)

        # 设置列宽
        header = self.ranking_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # 排名
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)  # 点赞数
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # 内容概要
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # 发布时间

        self.ranking_table.setColumnWidth(0, 60)  # 排名
        self.ranking_table.setColumnWidth(1, 80)  # 点赞数
        self.ranking_table.setColumnWidth(3, 150)  # 发布时间

        # 设置表格属性
        self.ranking_table.horizontalHeader().setVisible(True)
        self.ranking_table.verticalHeader().setVisible(False)
        self.ranking_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ranking_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        # 加载排行榜数据
        self.load_like_ranking()

        layout.addWidget(QLabel("双击查看评论详情"))
        layout.addWidget(self.ranking_table)

        card.layout().addLayout(layout)
        self.stats_layout.addWidget(card)

    def load_like_ranking(self):
        """加载点赞排行榜数据"""
        try:
            like_ranking = self.stats_data.get('like_ranking', [])

            valid_ranking = []
            for item in like_ranking:
                if (item.get('source') == 'bilibili' and
                        isinstance(item.get('like_count'), int) and
                        item.get('like_count') > 0):
                    valid_ranking.append(item)

            if not valid_ranking:
                self.ranking_table.setRowCount(1)
                no_data_item = QTableWidgetItem("📭 暂无点赞数据")
                no_data_item.setData(Qt.ItemDataRole.UserRole, None)
                self.ranking_table.setItem(0, 0, no_data_item)
                self.ranking_table.setSpan(0, 0, 1, 4)  # 合并所有列
                return

            # 设置表格行数
            self.ranking_table.setRowCount(len(like_ranking))

            # 填充数据
            for i, comment_data in enumerate(like_ranking):
                # 排名
                rank_item = QTableWidgetItem(str(i + 1))
                rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # 设置前三名的特殊颜色
                if i == 0:
                    rank_item.setForeground(Qt.GlobalColor.yellow)  # 金色
                elif i == 1:
                    rank_item.setForeground(Qt.GlobalColor.lightGray)  # 银色
                elif i == 2:
                    rank_item.setForeground(Qt.GlobalColor.red)  # 铜色

                self.ranking_table.setItem(i, 0, rank_item)

                # 点赞数
                like_item = QTableWidgetItem(f"👍 {comment_data['like_count']}")
                like_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if i < 3:  # 前三名特殊颜色
                    like_item.setForeground([Qt.GlobalColor.yellow, Qt.GlobalColor.lightGray, Qt.GlobalColor.red][i])
                self.ranking_table.setItem(i, 1, like_item)

                # 内容概要
                content_item = QTableWidgetItem(comment_data['content'])
                content_item.setData(Qt.ItemDataRole.UserRole, comment_data)  # 存储完整数据
                self.ranking_table.setItem(i, 2, content_item)

                # 发布时间
                try:
                    import time
                    time_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(comment_data['created_time']))
                except:
                    time_str = "未知时间"

                time_item = QTableWidgetItem(time_str)
                time_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.ranking_table.setItem(i, 3, time_item)

                # 数据源标识
                if comment_data.get('source') == 'aicu':
                    for col in range(4):
                        item = self.ranking_table.item(i, col)
                        if item:
                            item.setToolTip("数据来源：AICU")

        except Exception as e:
            logger.error(f"加载点赞排行榜失败: {e}")
            self.ranking_table.setRowCount(1)
            error_item = QTableWidgetItem(f"❌ 加载失败: {e}")
            self.ranking_table.setItem(0, 0, error_item)
            self.ranking_table.setSpan(0, 0, 1, 4)

    def open_comment_detail_from_ranking(self, item):
        """从排行榜打开评论详情"""
        try:
            # 获取该行的内容概要列（第2列）的数据
            row = item.row()
            content_item = self.ranking_table.item(row, 2)
            if not content_item:
                return

            comment_data = content_item.data(Qt.ItemDataRole.UserRole)
            if not comment_data:
                return

            comment_id = comment_data['id']
            oid = comment_data['oid']
            type_ = comment_data['type']

            logger.info(f"从排行榜打开评论详情: comment_id={comment_id}")

            # 检查登录状态
            if not self.api_service:
                QMessageBox.warning(self, "未登录", "请先登录账号才能查看评论详情。")
                return

            # 创建评论对象（简化版）
            from ..types import Comment
            comment = Comment(
                oid=oid,
                type=type_,
                content=comment_data['content'],
                created_time=comment_data['created_time'],
                source=comment_data.get('source', 'bilibili')
            )
            comment.like_count = comment_data['like_count']
            comment.video_uri = comment_data.get('video_uri', None)

            # 打开详情窗口
            from .comment_detail_screen import CommentDetailScreen
            self.detail_window = CommentDetailScreen(
                self.api_service,
                comment_id,
                oid,
                type_,
                comment_data=comment
            )

            self.detail_window.setWindowTitle(f"评论详情 - 排行第{row + 1}名")
            self.detail_window.resize(800, 600)
            self.detail_window.show()

        except Exception as e:
            logger.error(f"从排行榜打开评论详情失败: {e}")
            QMessageBox.warning(self, "打开失败", f"无法打开评论详情: {e}")

    def create_card(self, title: str) -> QFrame:
        """创建统计卡片"""
        card = QFrame()
        card.setFrameStyle(QFrame.Shape.Box)
        card.setStyleSheet("""
            QFrame {
                background-color: #34495e;
                border: 1px solid #566573;
                border-radius: 12px;
                padding: 15px;
                margin: 5px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #ecf0f1; font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        return card

    def create_stat_item(self, label: str, value: str, color: str) -> QFrame:
        """创建统计项目"""
        item = QFrame()
        item.setStyleSheet(f"""
            QFrame {{
                background-color: #2c3e50;
                border: 1px solid {color};
                border-radius: 8px;
                padding: 15px;
                margin: 5px;
            }}
        """)

        layout = QVBoxLayout(item)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 数值
        value_label = QLabel(value)
        value_label.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label)

        # 标签
        label_widget = QLabel(label)
        label_widget.setStyleSheet("color: #bdc3c7; font-size: 12px;")
        label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label_widget)

        return item

    def create_comment_stats_tab(self, widget):
        """创建评论统计标签页"""
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        # 统计内容容器
        stats_widget = QWidget()
        self.stats_layout = QVBoxLayout(stats_widget)
        self.stats_layout.setSpacing(20)

        # 添加加载提示
        self.loading_label = QLabel("正在加载统计数据...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("color: #ecf0f1; font-size: 16px; padding: 50px;")
        self.stats_layout.addWidget(self.loading_label)

        scroll.setWidget(stats_widget)

        # 将滚动区域添加到标签页
        tab_layout = QVBoxLayout(widget)
        tab_layout.setContentsMargins(10, 10, 10, 10)
        tab_layout.addWidget(scroll)

    def create_message_stats_tab(self, widget):
        """创建私信统计标签页"""
        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        # 统计内容容器
        stats_widget = QWidget()
        message_stats_layout = QVBoxLayout(stats_widget)
        message_stats_layout.setSpacing(20)

        # 私信统计内容
        stats_label = QLabel("私信统计功能")
        stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_label.setStyleSheet("font-size: 16px; color: #ecf0f1; padding: 20px;")
        message_stats_layout.addWidget(stats_label)

        # 私信统计卡片
        self.create_message_stats_cards(message_stats_layout)

        scroll.setWidget(stats_widget)

        # 将滚动区域添加到标签页
        tab_layout = QVBoxLayout(widget)
        tab_layout.addWidget(scroll)

    def create_message_stats_cards(self, layout):
        """创建私信统计卡片"""
        # 基础统计卡片
        basic_card = self.create_card("📱 私信基础统计")
        basic_grid = QGridLayout()

        # 获取真实的私信统计数据
        message_stats = self.get_message_stats()

        stats_items = [
            ("总私信数", str(message_stats.get('total_messages', 0)), "#3498db"),
            ("总会话数", str(message_stats.get('total_conversations', 0)), "#9b59b6"),
            ("未读消息", str(message_stats.get('unread_messages', 0)), "#e74c3c"),
            ("今日消息", str(message_stats.get('today_messages', 0)), "#f39c12"),
        ]

        for i, (label, value, color) in enumerate(stats_items):
            row, col = i // 2, i % 2
            stat_widget = self.create_stat_item(label, value, color)
            basic_grid.addWidget(stat_widget, row, col)

        basic_card.layout().addLayout(basic_grid)
        layout.addWidget(basic_card)

        # 活跃度统计卡片
        activity_card = self.create_card("📊 消息活跃度")
        activity_layout = QVBoxLayout()

        if message_stats.get('total_messages', 0) > 0:
            # 显示实际的统计信息
            date_range = message_stats.get('date_range', '无数据')
            most_active = message_stats.get('most_active_user', '无数据')
            avg_daily = message_stats.get('avg_daily_messages', 0)

            activity_info_text = f"""私信活跃度统计：
    - 时间范围：{date_range}
    - 最活跃联系人：{most_active}
    - 日均消息数：{avg_daily:.1f}
    - 会话分布：{message_stats.get('total_conversations', 0)} 个活跃会话"""
        else:
            activity_info_text = """私信活跃度统计将显示：
    - 每日消息数量趋势
    - 最活跃的联系人
    - 消息类型分布
    - 回复速度统计"""

        activity_info = QLabel(activity_info_text)
        activity_info.setStyleSheet("color: #bdc3c7; font-size: 14px; padding: 20px;")
        activity_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        activity_layout.addWidget(activity_info)

        activity_card.layout().addLayout(activity_layout)
        layout.addWidget(activity_card)

        # 提示信息
        tip_text = "💡 提示：私信统计数据来自私信管理工具的缓存"
        if message_stats.get('cache_time'):
            tip_text += f"\n最后更新：{message_stats['cache_time']}"

        tip_label = QLabel(tip_text)
        tip_label.setStyleSheet(
            "color: #f39c12; font-size: 12px; padding: 10px; background-color: rgba(243, 156, 18, 0.1); border-radius: 5px;")
        tip_label.setWordWrap(True)
        layout.addWidget(tip_label)

        # 互动排行榜
        ranking_card = self.create_card("👥 互动排行榜")
        ranking_layout = QVBoxLayout()

        # 创建排行榜表格
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
        self.ranking_table = QTableWidget()
        self.ranking_table.setColumnCount(5)
        self.ranking_table.setHorizontalHeaderLabels(["排名", "UID", "收到消息", "发送消息", "总互动次数"])

        self.ranking_table.setMinimumHeight(2000)

        from PyQt6.QtWidgets import QSizePolicy
        self.ranking_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.ranking_table.itemDoubleClicked.connect(self.open_user_space_from_table)
        self.ranking_table.setStyleSheet("""
            QTableWidget {
                background-color: #2c3e50;
                border: 1px solid #566573;
                border-radius: 4px;
                color: #ecf0f1;
                gridline-color: #34495e;
                font-size: 13px;
            }
            QTableWidget::item {
                padding: 12px;
                border-bottom: 1px solid #34495e;
                min-height: 20px;
            }
            QTableWidget::item:hover {
                background-color: #34495e;
            }
            QTableWidget::item:selected {
                background-color: #3498db;
            }
            QHeaderView::section {
                background-color: #566573;
                color: #ecf0f1;
                padding: 12px;
                border: 1px solid #7f8c8d;
                font-weight: bold;
                font-size: 14px;
                text-align: center;
            }
            QHeaderView::section:hover {
                background-color: #7f8c8d;
            }
        """)

        # 设置列宽 - 让表格占满页面
        from PyQt6.QtWidgets import QHeaderView
        header = self.ranking_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # 排名固定宽度
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # UID自适应
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)  # 收到消息固定
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)  # 发送消息固定
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)  # 总互动固定

        self.ranking_table.setColumnWidth(0, 80)  # 排名
        self.ranking_table.setColumnWidth(2, 120)  # 收到消息
        self.ranking_table.setColumnWidth(3, 120)  # 发送消息
        self.ranking_table.setColumnWidth(4, 120)  # 总互动次数
        # 确保表头显示并设置属性
        self.ranking_table.horizontalHeader().setVisible(True)
        self.ranking_table.horizontalHeader().setStretchLastSection(False)
        self.ranking_table.horizontalHeader().setHighlightSections(True)
        self.ranking_table.verticalHeader().setVisible(False)
        # 禁止编辑
        self.ranking_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.ranking_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        # 加载排行榜数据
        self.load_interaction_ranking()

        ranking_layout.addWidget(QLabel("双击用户查看B站主页,排名"))
        ranking_layout.addWidget(self.ranking_table)

        ranking_card.layout().addLayout(ranking_layout)
        layout.addWidget(ranking_card)

        layout.addStretch()

    def get_message_stats(self):
        """获取私信统计数据"""
        try:
            import pickle
            import os
            from datetime import datetime
            from collections import Counter

            # 尝试从缓存文件读取私信数据
            home_dir = os.path.expanduser("~")
            cache_file = os.path.join(home_dir, ".bilibili_tools", "message_cache.pkl")

            if not os.path.exists(cache_file):
                return {}

            with open(cache_file, 'rb') as f:
                data = pickle.load(f)
                messages = data.get('messages', [])

            if not messages:
                return {}

            # 计算统计数据
            total_messages = len(messages)
            conversations = set(msg['talker_id'] for msg in messages)
            total_conversations = len(conversations)

            # 计算未读消息
            unread_messages = sum(1 for msg in messages if msg.get('is_unread', False))

            # 计算今日消息
            today = datetime.now().date()
            today_messages = 0
            for msg in messages:
                try:
                    ts = msg['timestamp']
                    if ts > 1e10:  # 毫秒级时间戳
                        ts = ts / 1000
                    msg_date = datetime.fromtimestamp(ts).date()
                    if msg_date == today:
                        today_messages += 1
                except:
                    continue

            # 计算时间范围
            try:
                timestamps = [msg['timestamp'] for msg in messages]
                timestamps = [ts / 1000 if ts > 1e10 else ts for ts in timestamps]
                earliest = min(timestamps)
                latest = max(timestamps)
                date_range = f"{datetime.fromtimestamp(earliest).strftime('%Y-%m-%d')} 至 {datetime.fromtimestamp(latest).strftime('%Y-%m-%d')}"
            except:
                date_range = "无数据"

            # 找出最活跃的用户
            talker_counter = Counter(msg['talker_id'] for msg in messages)
            if talker_counter:
                most_active_uid, most_active_count = talker_counter.most_common(1)[0]
                most_active_user = f"UID:{most_active_uid} ({most_active_count}条)"
            else:
                most_active_user = "无数据"

            # 计算日均消息数
            try:
                days_span = (latest - earliest) / (24 * 3600)
                avg_daily = total_messages / max(days_span, 1)
            except:
                avg_daily = 0

            # 缓存时间
            cache_time = datetime.fromtimestamp(os.path.getmtime(cache_file)).strftime('%Y-%m-%d %H:%M:%S')

            return {
                'total_messages': total_messages,
                'total_conversations': total_conversations,
                'unread_messages': unread_messages,
                'today_messages': today_messages,
                'date_range': date_range,
                'most_active_user': most_active_user,
                'avg_daily_messages': avg_daily,
                'cache_time': cache_time
            }

        except Exception as e:
            logger.error(f"获取私信统计数据失败: {e}")
            return {}

    def load_interaction_ranking(self):
        """加载互动排行榜"""
        try:
            import pickle
            import os
            from collections import defaultdict

            # 尝试从缓存文件读取私信数据
            home_dir = os.path.expanduser("~")
            cache_file = os.path.join(home_dir, ".bilibili_tools", "message_cache.pkl")

            if not os.path.exists(cache_file):
                self.ranking_table.setRowCount(1)
                no_data_item = QTableWidgetItem("📭 暂无私信数据")
                no_data_item.setData(Qt.ItemDataRole.UserRole, None)
                self.ranking_table.setItem(0, 0, no_data_item)
                self.ranking_table.setSpan(0, 0, 1, 5)  # 合并所有5列
                return

            with open(cache_file, 'rb') as f:
                data = pickle.load(f)
                messages = data.get('messages', [])

            if not messages:
                self.ranking_table.setRowCount(1)
                no_data_item = QTableWidgetItem("📭 暂无私信数据")
                no_data_item.setData(Qt.ItemDataRole.UserRole, None)
                self.ranking_table.setItem(0, 0, no_data_item)
                self.ranking_table.setSpan(0, 0, 1, 5)
                return

            # 获取当前用户UID
            current_uid = None
            if self.api_service:
                uid, _, _ = self.api_service.get_cached_user_info()
                current_uid = uid

            # 统计每个用户的互动次数
            user_stats = defaultdict(lambda: {'sent': 0, 'received': 0})

            for msg in messages:
                talker_id = msg['talker_id']
                sender_uid = msg['sender_uid']

                if sender_uid == current_uid:
                    # 当前用户发送的消息
                    user_stats[talker_id]['sent'] += 1
                else:
                    # 接收到的消息
                    user_stats[talker_id]['received'] += 1

            # 按总互动次数排序
            sorted_users = sorted(
                user_stats.items(),
                key=lambda x: x[1]['sent'] + x[1]['received'],
                reverse=True
            )

            # 设置表格行数（显示前30名）
            display_count = min(30, len(sorted_users))
            self.ranking_table.setRowCount(display_count)

            # 填充数据
            for i, (uid, stats) in enumerate(sorted_users[:display_count]):
                total = stats['sent'] + stats['received']

                # 排名
                rank_item = QTableWidgetItem(str(i + 1))
                rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.ranking_table.setItem(i, 0, rank_item)

                # UID
                uid_item = QTableWidgetItem(f"UID: {uid}")
                uid_item.setData(Qt.ItemDataRole.UserRole, uid)
                self.ranking_table.setItem(i, 1, uid_item)

                # 收到消息
                received_item = QTableWidgetItem(str(stats['received']))
                received_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.ranking_table.setItem(i, 2, received_item)

                # 发送消息
                sent_item = QTableWidgetItem(str(stats['sent']))
                sent_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.ranking_table.setItem(i, 3, sent_item)

                # 总互动次数
                total_item = QTableWidgetItem(str(total))
                total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.ranking_table.setItem(i, 4, total_item)

                # 根据排名设置不同颜色
                if i == 0:
                    color = Qt.GlobalColor.yellow  # 金色
                elif i == 1:
                    color = Qt.GlobalColor.lightGray  # 银色
                elif i == 2:
                    color = Qt.GlobalColor.red  # 铜色
                else:
                    color = Qt.GlobalColor.white

                # 为前三名设置颜色
                if i < 3:
                    for col in range(5):
                        item = self.ranking_table.item(i, col)
                        if item:
                            item.setForeground(color)

        except Exception as e:
            logger.error(f"加载互动排行榜失败: {e}")
            self.ranking_table.setRowCount(1)
            error_item = QTableWidgetItem(f"❌ 加载失败: {e}")
            error_item.setData(Qt.ItemDataRole.UserRole, None)
            self.ranking_table.setItem(0, 0, error_item)
            self.ranking_table.setSpan(0, 0, 1, 5)

    def open_user_space_from_table(self, item):
        """打开用户B站主页"""
        uid = item.data(Qt.ItemDataRole.UserRole)
        if uid:
            try:
                from PyQt6.QtGui import QDesktopServices
                from PyQt6.QtCore import QUrl

                url = f"https://space.bilibili.com/{uid}"
                QDesktopServices.openUrl(QUrl(url))
                logger.info(f"打开用户主页: {url}")
            except Exception as e:
                logger.error(f"打开用户主页失败: {e}")
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "打开失败", f"无法打开用户主页: {e}")

    def closeEvent(self, event):
        """窗口关闭时清理"""
        self.window_closed.emit()
        super().closeEvent(event)