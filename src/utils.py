
import logging
import random
from typing import Optional
from .api.api_service import ApiService

logger = logging.getLogger(__name__)

async def get_cid(api_service: ApiService, av: int) -> Optional[int]:#从AV号中获取CID
    try:
        url = f"https://api.bilibili.com/x/player/pagelist?aid={av}"
        data = await api_service.fetch_data(url)

        if data.get("data") and len(data["data"]) > 0:
            return data["data"][0]["cid"]
        return None
    except Exception as e:
        logger.error(f"Failed to get CID for av{av}: {e}")
        return None

def normalize_string(s: str) -> str:
    full_to_half_map = {i: i - 65248 for i in range(65281, 65375)}
    full_to_half_map[12288] = 32  # 转换全角空格

    return s.translate(full_to_half_map)

def fuzzy_search(search_query: str, text: str) -> bool:

    # 标准化
    search_query_norm = normalize_string(search_query)
    text_norm = normalize_string(text)
    # 统一转为小写以实现不区分大小写的搜索
    search_query_norm = search_query_norm.lower()
    text_norm = text_norm.lower()

    last_index = -1
    for char in search_query_norm:
        # 从上一个字符找到的位置之后开始查找当前字符
        found_index = text_norm.find(char, last_index + 1)

        if found_index == -1:
            # 如果任何一个字符按顺序找不到，则匹配失败
            return False

        # 更新最后找到的位置，为查找下一个字符做准备
        last_index = found_index

    # 所有字符都按顺序找到了
    return True


class ClickTracker:
    def __init__(self, target_clicks: int):
        # 将传入的整数作为随机范围的上限，并存储起来
        # _max_target 是一个内部变量，对类的使用者不可见
        self._max_target = target_clicks
        self.current_clicks = 0

        # self.target_clicks 将用于存储当前周期的随机目标
        self.target_clicks = 0
        self.reset()

    def click(self) -> bool:
        self.current_clicks += 1
        if self.current_clicks >= self.target_clicks:
            self.reset()
            return True
        return False

    def get_remaining_clicks(self) -> int:
        return max(0, self.target_clicks - self.current_clicks)

    def reset(self):
        self.current_clicks = 0
        # 从 1 到设定的上限之间，生成一个新的随机目标
        self.target_clicks = random.randint(1, self._max_target)