import aiohttp
import json
import logging
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import threading

from curl_cffi import requests as cffi_requests #需要curl_cffi绕过aicu的cloudeflare
from ..types import CreateApiServiceError, GetUIDError, RequestFailedError

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"

class UserInfoCache:
    """用户信息缓存类"""
    def __init__(self):
        self.uid: Optional[int] = None
        self.username: Optional[str] = None
        self.face_url: Optional[str] = None
        self._lock = threading.Lock()

    def set_user_info(self, uid: int, username: str, face_url: str):
        """设置用户信息"""
        with self._lock:
            self.uid = uid
            self.username = username
            self.face_url = face_url

    def get_user_info(self) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """获取用户信息"""
        with self._lock:
            return self.uid, self.username, self.face_url

    def is_cached(self) -> bool:
        """检查是否已缓存"""
        with self._lock:
            return all([self.uid, self.username, self.face_url])

    def clear(self):
        """清除缓存"""
        with self._lock:
            self.uid = None
            self.username = None
            self.face_url = None

class ApiService:
    def __init__(self, csrf: str = "", cookie: str = ""):
        self.csrf = csrf
        self.cookie = cookie
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
        self._executor: Optional[ThreadPoolExecutor] = None
        self._executor_lock = threading.Lock()  # 用于线程安全的executor管理

        # 用户信息缓存
        self.user_cache = UserInfoCache()

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
            self._cffi_session = cffi_requests.Session(impersonate="chrome110 ")
            self._cffi_session.headers.update({"User-Agent": UA})
        return self._cffi_session

    def _get_or_create_executor(self) -> ThreadPoolExecutor:
        """线程安全地获取或创建executor"""
        with self._executor_lock:
            if self._executor is None or self._executor._shutdown:
                logger.debug("Creating new ThreadPoolExecutor")
                self._executor = ThreadPoolExecutor(max_workers=5)
            return self._executor

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """关闭会话，但延迟关闭执行器"""
        if self._session and not self._session.closed:
            await self._session.close()
        # 注意：我们不在这里立即关闭executor，而是让它在需要时自动重新创建
        # 这避免了在AICU请求还在进行时就关闭executor的问题

    def __del__(self):
        """析构函数，确保资源最终被清理"""
        try:
            if self._executor and not self._executor._shutdown:
                self._executor.shutdown(wait=False)
        except Exception:
            pass  # 忽略析构时的错误

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

    def _sync_get_cffi_json(self, url: str, params: Optional[Dict] = None,
                            headers: Optional[Dict] = None) -> Dict[str, Any]:
        """
        这个函数是同步的，它会阻塞，因此必须在后台线程中运行。
        """
        try:

            # 如果是AICU的请求，使用专门的headers
            if headers is None and "aicu.cc" in url:
                headers = self.get_aicu_headers()

            resp = self.cffi_session.get(
                url,
                params=params,
                headers=headers,
                impersonate="chrome110",
                verify=True,
                timeout=30
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            # 抛出自定义错误，以便被异步部分捕获
            raise RequestFailedError(f"CFFI sync request failed for {url}: {e}")

    def get_aicu_headers(self) -> Dict[str, str]:
        """获取AICU专用请求头"""
        return {
            'User-Agent': UA,  # 使用固定的UA，避免同IP多UA被识别
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Dnt': '1',
            'Origin': 'https://www.aicu.cc',
            'priority': 'u=1, i',
            'Sec-Ch-Ua': '"Google Chrome";v="110", "Chromium";v="110", "Not/A)Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        }

    async def get_cffi_json(self, url: str, params: Optional[Dict] = None,
                            headers: Optional[Dict] = None) -> Dict[str, Any]:
        """
        在后台线程中运行同步的 CFFI GET 请求，以避免阻塞UI。
        使用线程安全的executor管理。
        """
        loop = asyncio.get_running_loop()
        try:
            executor = self._get_or_create_executor()
            func_to_run = partial(self._sync_get_cffi_json, url, params=params, headers=headers)
            # 使用 functools.partial 将参数传递给同步函数

            # run_in_executor 返回一个 future, 我们可以 await 它
            data = await loop.run_in_executor(executor, func_to_run)
            logger.debug(f"Got CFFI response: {json.dumps(data, ensure_ascii=False)[:200]}...")
            return data
        except Exception as e:
            logger.error(f"CFFI request failed for {url}: {e}")
            # 如果是executor相关的错误，尝试重新创建executor
            if "cannot schedule new futures after shutdown" in str(e):
                logger.warning("Executor was shutdown, attempting to recreate...")
                with self._executor_lock:
                    if self._executor:
                        try:
                            self._executor.shutdown(wait=False)
                        except:
                            pass
                        self._executor = None
                # 重新抛出原始错误，让上层处理
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
        """从API获取UID并缓存它"""
        uid, _, _ = self.user_cache.get_user_info()
        if uid is not None:
            return uid

        try:
            json_res = await self.get_json("https://api.bilibili.com/x/member/web/account")
            if json_res.get("code") != 0:
                raise GetUIDError(f"API returned error: {json_res}")
            uid = json_res["data"]["mid"]

            # 如果还没有完整的用户信息，获取并缓存
            if not self.user_cache.is_cached():
                await self._fetch_and_cache_user_info()

            return uid
        except Exception as e:
            raise GetUIDError(f"Failed to get UID: {e}")

    async def get_user_info(self, force_refresh: bool = False) -> Tuple[int, str, str]:
        """获取用户信息（UID, 用户名, 头像URL）"""
        if not force_refresh and self.user_cache.is_cached():
            return self.user_cache.get_user_info()

        return await self._fetch_and_cache_user_info()

    async def _fetch_and_cache_user_info(self) -> Tuple[int, str, str]:
        """从API获取并缓存用户信息"""
        try:
            data = await self.get_json("https://api.bilibili.com/x/space/myinfo")
            if data.get("code") != 0:
                raise GetUIDError(f"API returned error: {data}")

            user_data = data.get("data", {})
            uid = user_data.get("mid")
            username = user_data.get("name", "用户")
            face_url = user_data.get("face", "")

            # 缓存用户信息
            self.user_cache.set_user_info(uid, username, face_url)
            logger.info(f"用户信息已缓存: UID={uid}, 用户名={username}")

            return uid, username, face_url
        except Exception as e:
            logger.error(f"获取用户信息失败: {e}")
            raise GetUIDError(f"Failed to get user info: {e}")

    def get_cached_user_info(self) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """同步获取缓存的用户信息"""
        return self.user_cache.get_user_info()

    def clear_user_cache(self):
        """清除用户信息缓存"""
        self.user_cache.clear()

