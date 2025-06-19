import re
import logging
from typing import Optional, Dict
from ..types import Danmu, Notify, DeleteDanmuError

logger = logging.getLogger(__name__)

def extract_cid(native_uri: str) -> Optional[int]:#从本机URI中提取CID
    match = re.search(r"cid=(\d+)", native_uri)
    if match:
        return int(match.group(1))
    return None

async def remove_danmu(danmu: Danmu, dmid: int, api_service) -> int:
    """
    移除
    note：这个功能是为了保持结构的一致性，
    但是Bilibili API似乎不支持通过这个删除弹幕了.
   移除反向删除逻辑，保持函数职责单一
    """
    try:
        # 该API似乎已失效，但保留代码结构
        form_data = [
            ("dmid", str(dmid)),
            ("cid", str(danmu.cid)),
            ("type", "1"),
            ("csrf", api_service.csrf)
        ]
        json_res = await api_service.post_form(
            "https://api.bilibili.com/x/msgfeed/del", # This endpoint likely doesn't work for danmu
            form_data
        )

        if json_res.get("code") == 0:
            logger.info(f"成功删除弹幕 {dmid}.")
            return dmid
        else:
            raise DeleteDanmuError(f"删除弹幕失败 (API可能已失效): {json_res.get('message', 'Unknown error')}")
    except Exception as e:
        raise DeleteDanmuError(f"删除弹幕时发生网络或未知错误: {e}") from e
