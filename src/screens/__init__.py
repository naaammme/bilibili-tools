#导入需要避免循环导入的内容
__all__ = ['MainWindow', 'CommentCleanScreen', 'CookieScreen', 'QRCodeScreen',
           'UnfollowScreen', 'ToolSelectionScreen', 'ImprovedToolSelectionScreen',
           'AccountManager', 'CommentStatsScreen', 'CommentDetailScreen']

from src.screens.cookie_screen import CookieScreen
from src.screens.Comment_Clean_Screen import MainWindow, CommentCleanScreen
from src.screens.qrcode_screen import QRCodeScreen
from src.screens.unfollow_screen import UnfollowScreen
from src.screens.tool_selection_screen import ToolSelectionScreen
from src.screens.comment_stats_screen import CommentStatsScreen
from src.screens.comment_detail_screen  import CommentDetailScreen
# 尝试导入新模块，如果失败则跳过
try:
    from src.screens.improved_tool_selection_screen import ImprovedToolSelectionScreen
except ImportError:
    ImprovedToolSelectionScreen = None

try:
    from src.screens.account_manager import AccountManager
except ImportError:
    AccountManager = None