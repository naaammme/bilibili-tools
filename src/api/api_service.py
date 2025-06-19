import aiohttp
import json
import logging
import asyncio
import random
from typing import Optional, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# 完全遵从 aicu_test.py 的方案，使用同步的 requests
from curl_cffi import requests as cffi_requests
from ..types import CreateApiServiceError, GetUIDError, RequestFailedError

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.2651.86"

class ApiService:
    def __init__(self, csrf: str = "", cookie: str = ""):
        self.csrf = csrf
        self.cookie = cookie
        self.uid: Optional[int] = None  # 添加UID缓存
        self.headers = {
            "User-Agent": UA,
            "Cookie": cookie,
            "Referer": "https://www.bilibili.com"
        }
        #Bilibili api的aiohttp会话
        self._session: Optional[aiohttp.ClientSession] = None
        # curl_cffi 同步 session for AICU APIs
        self._cffi_session: Optional[cffi_requests.Session] = None
        # 用于在后台运行同步代码的线程池
        self._executor = ThreadPoolExecutor(max_workers=5)

    @classmethod
    def new(cls, cookie: str):
        """从cookie字符串创建新的ApiService"""
        try:
            csrf_start = cookie.find("bili_jct=")
            if csrf_start == -1:
                raise CreateApiServiceError("bili_jct not found in cookie")

            csrf_end = cookie.find(";", csrf_start)
            if csrf_end == -1:
                csrf = cookie[csrf_start + 9:]
            else:
                csrf = cookie[csrf_start + 9:csrf_end]

            return cls(csrf=csrf, cookie=cookie)
        except Exception as e:
            raise CreateApiServiceError(f"Failed to create API service: {e}")

    @classmethod
    def new_with_fields(cls, csrf: str, cookie: str = ""):
        """用给定的字段创建新的ApiService"""
        return cls(csrf=csrf, cookie=cookie)

    @property
    def session(self) -> aiohttp.ClientSession:
        """获取或创建aiohttp会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=self.headers)
        return self._session

    @property
    def cffi_session(self) -> cffi_requests.Session:
        """获取或创建curl_Cffi同步会话"""
        if self._cffi_session is None:
            self._cffi_session = cffi_requests.Session()
            self._cffi_session.headers.update({"User-Agent": UA})
        return self._cffi_session

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """关闭会话和关闭执行器"""
        if self._session and not self._session.closed:
            await self._session.close()
        # cffi_session.close() 是同步的, 不需要在 async context 中调用
        self._executor.shutdown(wait=True)

    async def get_json(self, url: str) -> Dict[str, Any]:
        """使用aiohttp发送GET请求并返回JSON响应"""
        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                logger.debug(f"Got response: {json.dumps(data, ensure_ascii=False)[:200]}...")

                if isinstance(data, dict) and data.get("code") != 0:
                    logger.warning(f"API returned error: {data}")

                return data
        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            raise RequestFailedError(f"Request failed: {e}")

    def _sync_get_cffi_json(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        这个函数是同步的，它会阻塞，因此必须在后台线程中运行。
        它完全模仿 aicu_test.py 的行为。
        """
        try:
            resp = self.cffi_session.get(
                url,
                params=params,
                impersonate="edge99",  # 这是绕过 Cloudflare 的关键
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            # 抛出自定义错误，以便被异步部分捕获
            raise RequestFailedError(f"CFFI sync request failed for {url}: {e}")

    async def get_cffi_json(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        在后台线程中运行同步的 CFFI GET 请求，以避免阻塞UI。
        """
        loop = asyncio.get_running_loop()
        try:
            # 使用 functools.partial 将参数传递给同步函数
            func_to_run = partial(self._sync_get_cffi_json, url, params=params)
            # run_in_executor 返回一个 future, 我们可以 await 它
            data = await loop.run_in_executor(self._executor, func_to_run)
            logger.debug(f"Got CFFI response: {json.dumps(data, ensure_ascii=False)[:200]}...")
            return data
        except Exception as e:
            logger.error(f"CFFI request failed for {url}: {e}")
            # 将原始异常链起来，便于调试
            raise RequestFailedError(f"CFFI async wrapper failed: {e}") from e

    async def fetch_data(self, url: str) -> Dict[str, Any]:
        return await self.get_json(url)

    async def post_form(self, url: str, form_data: List[Tuple[str, str]]) -> Dict[str, Any]:
        """发送带有表单数据的POST请求，每次都使用新的会话以提高稳定性。"""
        try:
            data = aiohttp.FormData()
            for key, value in form_data:
                data.add_field(key, str(value))

            # 不再使用 self.session，而是为每个请求创建一个新的临时会话
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(url, data=data) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            raise RequestFailedError(f"Request failed: {e}")

    async def post_json(self, url: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """发送带有JSON主体的POST请求，每次都使用新的会话以提高稳定性。"""
        try:
            # 不再使用 self.session，而是为每个请求创建一个新的临时会话
            async with aiohttp.ClientSession(headers=self.headers) as session:
                async with session.post(url, json=json_data) as response:
                    response.raise_for_status()
                    return await response.json()
        except Exception as e:
            raise RequestFailedError(f"Request failed with JSON body: {e}")

    async def get_uid(self) -> int:
        """从API获取UID并缓存它。"""
        if self.uid is not None:
            return self.uid
        try:
            json_res = await self.get_json("https://api.bilibili.com/x/member/web/account")
            if json_res.get("code") != 0:
                raise GetUIDError(f"API returned error: {json_res}")
            uid = json_res["data"]["mid"]
            self.uid = uid  # 缓存UID
            return uid
        except Exception as e:
            raise GetUIDError(f"Failed to get UID: {e}")
