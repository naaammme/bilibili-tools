import logging
import time
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QTextEdit, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QDesktopServices
from PyQt6.QtCore import QUrl
from ..api.api_service import ApiService
from ..types import Comment

logger = logging.getLogger(__name__)

class CommentDetailScreen(QWidget):
    """评论详情界面 - 显示单个评论的详细信息"""

    back_to_stats = pyqtSignal()

    def __init__(self, api_service: ApiService, comment_id: int, oid: int, type_: int, comment_data: Optional[Comment] = None):
        super().__init__()
        self.api_service = api_service
        self.comment_id = comment_id
        self.oid = oid
        self.type_ = type_
        self.comment_data = comment_data  # 传入的评论对象

        self.init_ui()
        self.display_comment_detail()

    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 顶部工具栏
        toolbar_layout = QHBoxLayout()

        # 返回按钮
        back_btn = QPushButton("← 返回")
        back_btn.clicked.connect(self.close)
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
        self.title_label = QLabel(f"评论详情 - ID: {self.comment_id}")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #ecf0f1;")
        toolbar_layout.addWidget(self.title_label)

        toolbar_layout.addStretch()
        layout.addLayout(toolbar_layout)

        # 主内容区域
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setSpacing(15)

        layout.addWidget(self.content_widget)
        layout.addStretch()

    def display_comment_detail(self):
        """显示评论详细信息"""
        if not self.comment_data:
            self.show_error("无评论数据")
            return

        # 检查数据源
        source = getattr(self.comment_data, 'source', 'bilibili')

        if source == 'aicu':
            self.display_aicu_comment()
        else:
            self.display_bilibili_comment()

    def display_bilibili_comment(self):
        """显示B站评论详情"""
        basic_group = QGroupBox("基本信息")
        basic_layout = QVBoxLayout()

        id_layout = self.create_info_row("评论ID:", str(self.comment_id))
        basic_layout.addLayout(id_layout)
        # 对象信息
        obj_layout = QHBoxLayout()
        obj_layout.addWidget(self.create_label("OID:", bold=True))
        obj_layout.addWidget(self.create_label(str(self.oid)))
        obj_layout.addWidget(self.create_label("Type:", bold=True))
        obj_layout.addWidget(self.create_label(str(self.type_)))
        obj_layout.addStretch()
        basic_layout.addLayout(obj_layout)
        # 显示点赞数（如果有）
        if hasattr(self.comment_data, 'like_count') and self.comment_data.like_count:
            like_layout = self.create_info_row("点赞数:", f"👍 {self.comment_data.like_count}")
            basic_layout.addLayout(like_layout)

        # 根据通知类型显示不同信息
        if hasattr(self.comment_data, 'tp') and self.comment_data.tp is not None:
            notify_type_text = {
                0: "点赞通知",
                1: "回复通知",
                2: "@通知"
            }.get(self.comment_data.tp, f"未知类型({self.comment_data.tp})")

            notify_layout = self.create_info_row("通知类型:", notify_type_text)
            basic_layout.addLayout(notify_layout)

            # 显示通知特定信息
            if self.comment_data.tp == 0:  # 点赞
                info_text = "有用户点赞了你的评论"
            elif self.comment_data.tp == 1:  # 回复
                info_text = "有用户回复了你的评论"
            else:
                info_text = "有用户@了你"

            info_layout = self.create_info_row("通知说明:", info_text)
            basic_layout.addLayout(info_layout)

        # 创建时间
        if hasattr(self.comment_data, 'created_time') and self.comment_data.created_time:
            time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.comment_data.created_time))
            time_layout = self.create_info_row("发布时间:", time_str)
            basic_layout.addLayout(time_layout)

        basic_group.setLayout(basic_layout)
        self.content_layout.addWidget(basic_group)

        # 评论内容组
        content_group = QGroupBox("评论内容")
        content_layout = QVBoxLayout()

        content_text = QTextEdit()
        content_text.setPlainText(self.comment_data.content)
        content_text.setReadOnly(True)
        content_text.setMinimumHeight(150)

        # 设置objectName，之前是在内部设置样式现在统一移到style
        content_text.setObjectName("bilibiliCommentContent")


        content_layout.addWidget(content_text)

        content_group.setLayout(content_layout)
        self.content_layout.addWidget(content_group)

        # 关联信息组
        if hasattr(self.comment_data, 'notify_id') and self.comment_data.notify_id:
            related_group = QGroupBox("关联信息")
            related_layout = QVBoxLayout()

            notify_id_layout = self.create_info_row("通知ID:", str(self.comment_data.notify_id))
            related_layout.addLayout(notify_id_layout)

            related_group.setLayout(related_layout)
            self.content_layout.addWidget(related_group)

        # 操作按钮
        self.add_action_buttons()

    def display_aicu_comment(self):
        """显示AICU评论详情"""
        # 来源提示
        source_frame = QFrame()
        source_frame.setStyleSheet("""
            QFrame {
                background-color: #ff6b9d;
                border-radius: 4px;
                padding: 10px;
                margin-bottom: 10px;
            }
        """)
        source_layout = QHBoxLayout(source_frame)
        source_label = QLabel("📡 数据来源：AICU")
        source_label.setStyleSheet("color: white; font-weight: bold;")
        source_layout.addWidget(source_label)
        self.content_layout.addWidget(source_frame)

        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QVBoxLayout()

        # 评论ID
        id_layout = self.create_info_row("评论ID (rpid):", str(self.comment_id))
        basic_layout.addLayout(id_layout)

        # 视频信息
        if self.oid and self.type_:
            video_layout = self.create_info_row("视频OID:", str(self.oid))
            basic_layout.addLayout(video_layout)

            type_layout = self.create_info_row("评论类型:", str(self.type_))
            basic_layout.addLayout(type_layout)

        # Parent信息（如果有）
        if hasattr(self.comment_data, 'parent') and self.comment_data.parent:
            parent_info = self.comment_data.parent
            rootid = parent_info.get('rootid', 'N/A')
            parentid = parent_info.get('parentid', 'N/A')

            parent_layout = self.create_info_row("根评论ID:", str(rootid))
            basic_layout.addLayout(parent_layout)

            if rootid != parentid:
                parent_id_layout = self.create_info_row("父评论ID:", str(parentid))
                basic_layout.addLayout(parent_id_layout)

        # Rank信息
        if hasattr(self.comment_data, 'rank'):
            rank_text = "根评论" if self.comment_data.rank == 1 else f"子评论 (rank={self.comment_data.rank})"
            rank_layout = self.create_info_row("评论层级:", rank_text)
            basic_layout.addLayout(rank_layout)

        # 时间信息
        if hasattr(self.comment_data, 'created_time') and self.comment_data.created_time:
            time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.comment_data.created_time))
            time_layout = self.create_info_row("发布时间:", time_str)
            basic_layout.addLayout(time_layout)

        basic_group.setLayout(basic_layout)
        self.content_layout.addWidget(basic_group)

        # 评论内容
        content_group = QGroupBox("评论内容")
        content_layout = QVBoxLayout()

        content_text = QTextEdit()
        content_text.setPlainText(self.comment_data.content)
        content_text.setReadOnly(True)
        content_text.setMinimumHeight(150)
        content_text.setObjectName("aicuCommentContent")


        content_layout.addWidget(content_text)

        content_group.setLayout(content_layout)
        self.content_layout.addWidget(content_group)

        # 操作按钮
        self.add_action_buttons()

    def add_action_buttons(self):
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 10, 0, 0)

        # 打开B站视频按钮（B站和AICU都显示）
        view_video_btn = QPushButton("打开B站视频看评论")
        view_video_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl(
                f"https://www.bilibili.com/video/av{self.oid}/?vd_source=84720652665df200f207840449fc86f5#reply{self.comment_id}")
        ))
        if hasattr(self.comment_data, 'source') and self.comment_data.source == 'aicu':
            view_video_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ff6b9d;
                    color: white;
                    padding: 8px 20px;
                    border-radius: 6px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #ff5a8c;
                }
            """)
        else:
             view_video_btn.setStyleSheet("""
                 QPushButton {
                     background-color: #00a1d6;
                     color: white;
                     padding: 8px 20px;
                     border-radius: 6px;
                     font-weight: bold;
                 }
                 QPushButton:hover {
                     background-color: #0080a6;
                 }
             """)
        action_layout.addWidget(view_video_btn)

        # 查看评论按钮（AICU和B站都有）
        view_comment_btn = QPushButton(" 在B站查看评论")
        view_comment_btn.clicked.connect(self.open_aicu_comment)

        # 根据数据源设置不同的样式
        if hasattr(self.comment_data, 'source') and self.comment_data.source == 'aicu':
            view_comment_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ff6b9d;
                    color: white;
                    padding: 8px 20px;
                    border-radius: 6px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #ff5a8c;
                }
            """)
        else:
            view_comment_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    padding: 8px 20px;
                    border-radius: 6px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
            """)

        action_layout.addWidget(view_comment_btn)
        action_layout.addStretch()
        self.content_layout.addLayout(action_layout)

    def open_aicu_comment(self):
        """打开AICU评论页面 - 需要正确处理parent关系"""
        if self.comment_data and hasattr(self.comment_data, 'oid'):
            oid = self.comment_data.oid

            # 对于AICU评论
            if hasattr(self.comment_data, 'source') and self.comment_data.source == 'aicu':
                # AICU评论可能有parent信息
                if hasattr(self.comment_data, 'parent') and self.comment_data.parent:
                    parent_info = self.comment_data.parent
                    root_id = parent_info.get('rootid', self.comment_id)

                    # 如果是子评论，使用rootid
                    if self.comment_data.rank > 1:
                        comment_id_to_use = root_id
                    else:
                        comment_id_to_use = self.comment_id
                else:
                    comment_id_to_use = self.comment_id
            else:
                # Bilibili评论直接使用comment_id
                comment_id_to_use = self.comment_id

            # 构造URL
            page_type_map = {
                1: 1,  # 视频
                11: 11,  # 图文动态
                12: 12,  # 专栏
                17: 17,  # 文字动态
            }
            page_type = page_type_map.get(self.type_, 1)

            url = f"https://www.bilibili.com/h5/comment/sub?oid={oid}&pageType={page_type}&root={comment_id_to_use}"
            logger.info(f"打开评论链接: {url}")
            QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.warning(self, "错误", "无法获取评论信息")

    def open_bilibili_video(self):
        """打开B站视频页面"""
        if self.oid:
            # 尝试构造视频URL
            url = f"https://www.bilibili.com/video/av{self.oid}"
            QDesktopServices.openUrl(QUrl(url))

    def open_aicu_website(self):
        """打开AICU网站 - 使用正确的评论链接"""
        if self.comment_data and hasattr(self.comment_data, 'oid'):
            # 构造正确的链接
            # https://www.bilibili.com/h5/comment/sub?oid=724844631&pageType=1&root=105853036144
            oid = self.comment_data.oid
            root_id = self.comment_id  # comment_id 就是 rpid/root_id

            # 根据类型确定 pageType
            page_type = 1  # 默认为视频
            if self.type_ == 11:
                page_type = 11  # 图文动态
            elif self.type_ == 17:
                page_type = 17  # 文字动态

            url = f"https://www.bilibili.com/h5/comment/sub?oid={oid}&pageType={page_type}&root={root_id}"
            logger.info(f"打开AICU评论链接: {url}")
            QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.warning(self, "错误", "无法获取评论信息")

    def create_info_row(self, label: str, value: str) -> QHBoxLayout:
        """创建信息行"""
        layout = QHBoxLayout()
        layout.addWidget(self.create_label(label, bold=True))
        layout.addWidget(self.create_label(value))
        layout.addStretch()
        return layout


    def create_label(self, text: str, bold: bool = False) -> QLabel:
        """创建标签"""
        label = QLabel(text)
        if bold:
            font = label.font()
            font.setBold(True)
            label.setFont(font)
        label.setStyleSheet("color: #ecf0f1;")
        return label


    def show_error(self, message: str):
        """显示错误信息"""
        error_label = QLabel(message)
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setStyleSheet("color: #e74c3c; font-size: 16px; padding: 50px;")
        self.content_layout.addWidget(error_label)