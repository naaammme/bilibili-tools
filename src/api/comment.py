import re
import logging
from typing import Optional, Tuple, Dict
from ..types import Comment, Notify, Error, UnrecognizedURIError, DeleteCommentError

logger = logging.getLogger(__name__)

VIDEO_REGEX = re.compile(r"bilibili://video/(\d+)")

def parse_oid(detail: Dict) -> Tuple[int, int]:
    """从嵌套的细节中解析OID和类型"""
    uri = detail.get("uri", "")
    business_id = detail.get("business_id", 0)
    native_uri = detail.get("native_uri", "")

    if "t.bilibili.com" in uri:
        # 动态内评论
        oid = int(uri.replace("https://t.bilibili.com/", ""))
        tp = business_id if business_id != 0 else 17
        return (oid, tp)
    elif "https://h.bilibili.com/ywh/" in uri:
        # 带图动态内评论
        oid = int(uri.replace("https://h.bilibili.com/ywh/", ""))
        return (oid, 11)
    elif "https://www.bilibili.com/read/cv" in uri:
        # 专栏内评论
        oid = int(uri.replace("https://www.bilibili.com/read/cv", ""))
        return (oid, 12)
    elif "https://www.bilibili.com/opus/" in uri:
        # 新版动态内评论 (opus格式)
        oid = int(uri.replace("https://www.bilibili.com/opus/", ""))
        tp = business_id if business_id != 0 else 17  # 动态类型
        return (oid, tp)
    elif "https://www.bilibili.com/video/" in uri:
        # 视频内评论
        match = VIDEO_REGEX.search(native_uri)
        if match:
            oid = int(match.group(1))
            return (oid, 1)
    elif "https://www.bilibili.com/bangumi/play/" in uri:
        # 番剧（电影）内评论
        match = VIDEO_REGEX.search(native_uri)
        if match:
            oid = int(match.group(1))
            return (oid, 1)

    raise UnrecognizedURIError(f"Unrecognized URI: {uri}")

async def remove_comment(comment: Comment, rpid: int, api_service) -> int:

    # 此处不再需要导入 remove_notify，因为我们移除了反向删除逻辑

    try:
        if comment.type == 11:
            form_data = [
                ("oid", str(comment.oid)),
                ("type", str(comment.type)),
                ("rpid", str(rpid))
            ]
            json_res = await api_service.post_form(
                f"https://api.bilibili.com/x/v2/reply/del?csrf={api_service.csrf}",
                form_data
            )
        else:
            form_data = [
                ("oid", str(comment.oid)),
                ("type", str(comment.type)),
                ("rpid", str(rpid)),
                ("csrf", api_service.csrf)
            ]
            json_res = await api_service.post_form(
                "https://api.bilibili.com/x/v2/reply/del",
                form_data
            )

        if json_res.get("code") == 0:
            logger.info(f"获取AICU评论 {rpid}")
            return rpid
        else:
            # 抛出更详细的错误信息
            error_message = json_res.get('message', 'Unknown error')
            raise DeleteCommentError(f"删除评论失败 (rpid: {rpid}): {error_message} (code: {json_res.get('code')})")
    except Exception as e:
        # 抛出异常，以便上层捕获
        raise DeleteCommentError(f"删除评论时发生网络或未知错误 (rpid: {rpid}): {e}") from e

