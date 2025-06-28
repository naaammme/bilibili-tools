import json
import os
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import requests

logger = logging.getLogger(__name__)

@dataclass
class AccountInfo:
    uid: int
    username: str
    face_url: str
    cookie: str
    csrf: str
    last_login: str
    is_active: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)

class AccountManager:

    def __init__(self):
        self.accounts: Dict[int, AccountInfo] = {}
        self.current_account: Optional[AccountInfo] = None
        self.config_file = self._get_config_file_path()
        self.load_accounts()

    def _get_config_file_path(self) -> str:
        try:
            home_dir = os.path.expanduser("~")
            config_dir = os.path.join(home_dir, ".bilibili_tools")
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            return os.path.join(config_dir, "accounts.json")
        except Exception:
            return "accounts.json"

    def get_cache_directory(self) -> str:
        try:
            home_dir = os.path.expanduser("~")
            return os.path.join(home_dir, ".bilibili_tools")
        except Exception:
            return "."

    def clear_all_cache(self) -> bool:
        try:
            cache_dir = self.get_cache_directory()
            cache_files = ["accounts.json"]  # 可以添加其他缓存文件

            cleared_files = []
            for cache_file in cache_files:
                file_path = os.path.join(cache_dir, cache_file)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    cleared_files.append(cache_file)

            # 清除内存中的数据
            self.accounts.clear()
            self.current_account = None

            logger.info(f"已清除缓存文件: {cleared_files}")
            return True
        except Exception as e:
            logger.error(f"清除缓存失败: {e}")
            return False

    def load_accounts(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for uid_str, account_data in data.get('accounts', {}).items():
                    try:
                        uid = int(uid_str)
                        account = AccountInfo.from_dict(account_data)
                        self.accounts[uid] = account
                        if account.is_active:
                            self.current_account = account
                    except Exception as e:
                        logger.error(f"加载账号失败: {e}")
        except Exception as e:
            logger.error(f"加载配置失败: {e}")

    def save_accounts(self):
        try:
            data = {
                'accounts': {
                    str(uid): account.to_dict()
                    for uid, account in self.accounts.items()
                }
            }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)


        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def get_complete_user_info_sync(self, api_service) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """同步方式获取完整用户信息"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36 Edg/127.0.2651.86",
                "Cookie": api_service.cookie,
                "Referer": "https://www.bilibili.com"
            }

            # 使用获取用户详细信息的API
            response = requests.get(
                "https://api.bilibili.com/x/space/myinfo",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            if data.get("code") == 0:
                user_data = data["data"]
                uid = user_data.get("mid")
                username = user_data.get("name", "用户")
                face_url = user_data.get("face", "")

                logger.info(f"同步获取用户信息成功: UID={uid}, 用户名={username}")

                # 缓存到 api_service 中
                if hasattr(api_service, 'user_cache'):
                    api_service.user_cache.set_user_info(uid, username, face_url)

                return uid, username, face_url
            else:
                logger.error(f"获取用户信息失败: {data}")
                return None, None, None

        except Exception as e:
            logger.error(f"同步获取用户信息失败: {e}")
            return None, None, None

    def add_account(self, api_service, username: str = "", face_url: str = "") -> bool:
        """自动获取完整用户信息"""
        try:
            # 获取完整用户信息
            uid, real_username, real_face_url = self.get_complete_user_info_sync(api_service)

            if not uid:
                logger.error("无法获取用户信息")
                return False

            # 使用真实获取的用户名，而不是传入的参数
            final_username = real_username or "获取中..."
            final_face_url = real_face_url or face_url or ""

            # 设置其他账号为非活跃
            for account in self.accounts.values():
                account.is_active = False

            from datetime import datetime
            account_info = AccountInfo(
                uid=uid,
                username=final_username,
                face_url=final_face_url,
                cookie=api_service.cookie,
                csrf=api_service.csrf,
                last_login=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                is_active=True
            )

            self.accounts[uid] = account_info
            self.current_account = account_info
            self.save_accounts()

            logger.info(f"添加账号成功: {final_username} (UID: {uid})")
            return True
        except Exception as e:
            logger.error(f"添加账号失败: {e}")
            return False

    def switch_to_account(self, uid: int) -> bool:
        """切换到指定账号"""
        try:
            if uid not in self.accounts:
                logger.error(f"账号不存在: {uid}")
                return False

            # 检查目标账号的信息是否完整
            target_account = self.accounts[uid]
            if not target_account.cookie or not target_account.csrf:
                logger.error(f"账号 {target_account.username} 的登录信息不完整")
                return False

            # 设置所有账号为非活跃
            for account in self.accounts.values():
                account.is_active = False

            # 设置目标账号为活跃
            target_account.is_active = True
            self.current_account = target_account

            # 更新最后登录时间
            from datetime import datetime
            target_account.last_login = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 保存更改
            self.save_accounts()

            logger.info(f"成功切换到账号: {target_account.username} (UID: {uid})")
            return True

        except Exception as e:
            logger.error(f"切换账号失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def remove_account(self, uid: int) -> bool:
        """删除指定账号"""
        try:
            if uid not in self.accounts:
                return False

            account = self.accounts[uid]
            username = account.username

            # 如果删除的是当前账号
            if self.current_account and self.current_account.uid == uid:
                self.current_account = None

            del self.accounts[uid]
            self.save_accounts()

            logger.info(f"删除账号成功: {username} (UID: {uid})")
            return True

        except Exception as e:
            logger.error(f"删除账号失败: {e}")
            return False

    def get_current_account(self) -> Optional[AccountInfo]:
        """获取当前账号"""
        return self.current_account

    def has_accounts(self) -> bool:
        """是否有保存的账号"""
        return len(self.accounts) > 0

    def get_current_api_service(self):
        """获取当前账号的API服务"""
        if not self.current_account:
            logger.warning("没有当前账号")
            return None

        try:
            from .api_service import ApiService

            # 检查必要的字段
            if not self.current_account.cookie or not self.current_account.csrf:
                logger.error(f"账号 {self.current_account.username} 的 cookie 或 csrf 信息不完整")
                return None

            # 使用构造函数创建 API 服务
            api_service = ApiService(
                csrf=self.current_account.csrf,
                cookie=self.current_account.cookie
            )

            # 设置缓存的用户信息
            api_service.user_cache.set_user_info(
                self.current_account.uid,
                self.current_account.username,
                self.current_account.face_url
            )

            logger.info(f"成功恢复账号会话: {self.current_account.username} (UID: {self.current_account.uid})")
            return api_service

        except Exception as e:
            logger.error(f"创建API服务失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def clear_all_accounts(self):
        """清除所有账号"""
        try:
            self.accounts.clear()
            self.current_account = None
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
            logger.info("已清除所有账号")
        except Exception as e:
            logger.error(f"清除账号失败: {e}")

    def get_all_accounts(self) -> List[AccountInfo]:
        """获取所有账号列表"""
        return list(self.accounts.values())

    def refresh_current_account_info(self) -> bool:
        """刷新当前账号信息"""
        if not self.current_account:
            return False

        try:
            api_service = self.get_current_api_service()
            if not api_service:
                return False

            uid, username, face_url = self.get_complete_user_info_sync(api_service)
            if uid and username:
                self.current_account.username = username
                self.current_account.face_url = face_url or self.current_account.face_url
                self.save_accounts()
                logger.info(f"刷新账号信息成功: {username}")
                return True

        except Exception as e:
            logger.error(f"刷新账号信息失败: {e}")

        return False