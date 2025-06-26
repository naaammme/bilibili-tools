import asyncio
import logging
from typing import Optional, Tuple, Dict
from ..api.api_service import ApiService

logger = logging.getLogger(__name__)

class QRData:
    #二维码登录数据

    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.cookie_dict: Dict[str, str] = {}

    @classmethod
    async def request_qrcode(cls) -> 'QRData':#请求二维码登录
        api = ApiService()
        async with api:
            data = await api.get_json(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
            )
            return cls(
                url=data["data"]["url"],
                key=data["data"]["qrcode_key"]
            )

    async def get_state(self, api_service: ApiService) -> Tuple[int, Optional[str], Optional[str]]:
        #获取二维码扫描状态
        url = f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={self.key}"

        # 需要从响应中捕获cookie
        async with api_service.session.get(url) as response:
            res = await response.json()

            res_code = res["data"]["code"]
            if res_code == 0:
                # 登录成功
                res_url = res["data"]["url"]

                # 提取csrf令牌
                csrf_start = res_url.find("bili_jct=")
                if csrf_start != -1:
                    csrf_end = res_url.find("&", csrf_start)
                    if csrf_end == -1:
                        csrf = res_url[csrf_start + 9:]
                    else:
                        csrf = res_url[csrf_start + 9:csrf_end]

                    # 从会话中获取cookie
                    cookies = []
                    for cookie in api_service.session.cookie_jar:
                        cookies.append(f"{cookie.key}={cookie.value}")

                    cookie_string = "; ".join(cookies)
                    return (res_code, csrf, cookie_string)

            return (res_code, None, None)