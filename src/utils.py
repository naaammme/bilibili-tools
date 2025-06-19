import asyncio
import logging
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
    """
    实现模糊搜索，
    :param search_query: 用户输入的搜索关键词。
    :param text: 要被搜索的完整文本（如评论内容、UP主名称）。
    :return: 如果匹配成功则返回 True，否则返回 False。
    """
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