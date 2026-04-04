# Voice Diary Bot

Telegram 语音日记机器人：发送语音/文字消息，自动转写保存，定时整理为日记写入 Notion。

## 快速开始

### 1. 前置准备

- 通过 [@BotFather](https://t.me/BotFather) 创建 Telegram Bot，获取 Token
- 火山引擎 ASR AppKey + AccessToken（需开通 `volc.bigasr.auc_turbo`）
- LLM API Key（豆包/DeepSeek 等 OpenAI 兼容接口）
- Notion Integration Token + 数据库 ID（数据库只需 Title 属性）

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env 填入各项配置
```

### 3. 运行

**Docker（推荐）：**

```bash
docker compose up -d
```

清理 30 天前的数据：

```bash
./scripts/cleanup_old_data.sh
```

**本地运行：**

```bash
uv sync
uv run python main.py
```

## Bot 使用方式

| 操作 | 说明 |
|------|------|
| 发送语音 | 自动转写并保存 |
| 发送文字 | 直接保存为记录 |
| `/diary` | 整理今天的记录为日记并写入 Notion |
| `/status` | 查看今天的记录状态 |
| `/list` | 列出今天所有记录 |
| `/start` | 显示帮助信息 |

## 架构

```
Telegram → Bot → ASR(火山引擎极速版) → 本地存储
                                         ↓
               定时/指令 → LLM整理 → Notion(含语音附件)
```
