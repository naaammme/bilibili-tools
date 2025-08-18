# Bilibili 工具集
[![GitHub release](https://img.shields.io/github/release/naaammme/bilibili-tools.svg?style=flat-square&logo=github&color=black)](https://github.com/naaammme/bilibili-tools/releases)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-FF69B4.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://python.org)

一个Bilibili小工具集合,提供评论清理、批量取关、数据统计、私信管理等功能。

## ✨ 主要功能
 **评论清理工具**

- 批量删除评论、弹幕和通知
- 智能搜索和过滤功能
- 双击查看评论详情对话

 **批量取关工具**
- 一键批量取消关注
- 搜索和过滤功能

**评论弹幕记录**
- 通过脚本记录自己发送的评论，弹幕
- 程序自动查找历史观看视频里自己的评论
- 支持查找特定视频的评论

**自动取消点赞工具**
- 自动取消点赞历史里的点赞
- 批量取消对一个up所有视频的点赞

 **数据统计中心**
- 评论、弹幕、私信、通知统计
- 私信互动排行榜

 **私信管理工具**
- 批量删除私信会话 
- 内容和UID搜索 
- 批量标记已读
- 双击查看完整对话详情

 **账号管理**
- 多账号支持，一键切换
-  二维码扫码 / Cookie 登录 
- 自动保存登录状态
-  本地安全存储

## 📋使用说明
**方式一**:
- 从 [Releases 页面](https://github.com/naaammme/bilibili-tools/releases) 下载可执行文件
- 运行程序，选择扫码或Cookie登录

**方式二**:
- 克隆仓库:

  git clone https://github.com/naaammme/bilibili-tools.git

  cd bilibili-comment-cleaning

- 创建虚拟环境:
bashpython -m venv venv
- 安装依赖:
pip install -r requirements.txt
- 运行程序:
python main.py


## ⚠️ 潜在风险提示
- 短时间大量请求api可能触发风控，导致部分操作失败，请使用网络代理工具
- 尽管概率较低，但不能完全排除因滥用导致账号被封禁或触发其他限制的可能性
- 为了控制风险,如果你有上千条内容需要清理，请不要一次性完成并保持默认延迟

## 🦕 开发中的
- 历史用户名查询功能
- 其他功能随缘更新
## 🙏  致谢

本项目部分功能的实现思路参考了[Initsnow/bilibili-comment-cleaning](https://github.com/Initsnow/bilibili-comment-cleaning) 和[sw1128/Bilinili_UnFolow](https://github.com/sw1128/Bilibili_UnFollow.git)
项目的代码。

非常感谢作者 **Initsnow**和**sw1128** 的开源分享，为本项目奠定了坚实的基础。

同时感谢[bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)和[aicu](aicu.cc)分享的api接口
