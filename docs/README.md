# Nmail 文档索引（docs/README.md）

面向用户的全部文档都在这里维护（官网 <https://nmail.whizzzest.com/docs/> 由构建脚本从本目录白名单同步镜像）。安装与产品概览见仓库 [README](../README.zh-CN.md)。

## 上手

| 文档 | 内容 |
|---|---|
| [INSTALL.md](INSTALL.md) | 安装与更新：全部安装方式（uvx / 单文件 / winget / Homebrew / pip / 源码）、首次使用、应用内更新、数据位置与备份、卸载 |
| [使用指南.md](%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97.md) | 日常操作手册：界面导览、快捷键、文件夹与归档、AI 总管家、写信草稿、每日摘要、设置速览 |
| [FAQ.md](FAQ.md) | 高频问题：安装启动、网络代理、授权码、AI、同步、数据与隐私 |

## 了解

| 文档 | 内容 |
|---|---|
| [隐私与安全.md](%E9%9A%90%E7%A7%81%E4%B8%8E%E5%AE%89%E5%85%A8.md) | 数据存哪、什么会外发、网络边界、内容安全与 AI 安全设计 |

## 进阶

| 文档 | 内容 |
|---|---|
| [OAuth2 使用指南.md](OAuth2%20%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97.md) | Gmail / Outlook 授权登录：内置公开凭证零配置、自建 OAuth 客户端、令牌刷新 |
| [自建邮箱客户端 Gmail+Outlook OAuth2 完整教程.md](%E8%87%AA%E5%BB%BA%E9%82%AE%E7%AE%B1%E5%AE%A2%E6%88%B7%E7%AB%AF%20Gmail+Outlook%20OAuth2%20%E5%AE%8C%E6%95%B4%E6%95%99%E7%A8%8B.md) | 从零注册 Google / 微软云应用并跑通 OAuth2 的完整教程 |
| [Agent接入指南.md](Agent%E6%8E%A5%E5%85%A5%E6%8C%87%E5%8D%97.md) | 把 Nmail 交给 Claude Code 等 agent：skill 一键安装、`nmail-cli`、两阶段确认与安全边界 |
| [对外API使用指南.md](%E5%AF%B9%E5%A4%96API%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97.md) | 本机对外 API：API Key 与 scope 分级、`nmail-cli`、隧道接入、调用示例 |

## 开发者

| 文档 | 内容 |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构说明：模块划分、数据表、同步管线、AI 层与安全模型 |
| [CHANGELOG.md](CHANGELOG.md) | 提交级变更记录（与 git 提交一一对应） |
| [RELEASE.md](RELEASE.md) | 发版手册：release.sh 全流程（PyPI / GitHub Release / Homebrew / winget / 官网） |
| [PRODUCT_PLAN.md](PRODUCT_PLAN.md) | 产品定位、决策原则与路线图 |

> 其余文件（REDESIGN_PLAN / SESSIONS / 各专项方案）为内部工作文档：方案决策记录与多会话看板，不面向最终用户。
