# Obsidian ↔ Notion 双向同步工具

实现 Notion 数据库与 Obsidian Markdown 文件之间的**准双向同步**，以时间戳判断谁新听谁。

---

## 功能特性

- ✅ **属性级双向同步**：Notion 数据库属性 ↔ Obsidian YAML frontmatter
- ✅ **时间戳冲突解决**：自动比较 `last_edited_time` 与文件 `mtime`，新的覆盖旧的
- ✅ **首次全量初始化**：一键将 Notion 数据库拉取到 Obsidian
- ✅ **软删除支持**：Notion 删除的行可配置为移入 `.trash` 文件夹（防误删）
- ✅ **多数据库支持**：可同时同步多个 Notion 数据库到不同子目录
- ✅ **完整类型映射**：title, rich_text, select, multi_select, status, date, number, checkbox, url, email, relation 等
- ✅ **API 限流保护**：内置请求间隔，避免触发 Notion 限流

---

## 项目结构

```
obsidian_notion_sync/
├── config.yaml          # 同步配置（Token、多数据库、行为参数）
├── sync.py              # 主同步引擎
├── notion_client.py     # Notion API 封装
├── obsidian_client.py   # 本地文件操作封装
├── mapper.py            # 类型映射与时间戳工具
├── requirements.txt     # Python 依赖
├── sync_state.json      # 同步状态（自动生成）
└── README.md            # 本文档
```

---

## 安装步骤

### 1. 安装依赖

```bash
cd obsidian_notion_sync
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置 Notion

#### 2.1 创建 Integration（获取 Token）

1. 访问 [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. 点击 **「New integration」**
3. 填写名称（如 `Obsidian-Sync`），关联你的工作区
4. 复制 **Internal Integration Token**（格式 `secret_xxxxxxxx`）

#### 2.2 授权数据库

1. 在 Notion 中打开你要同步的数据库
2. 点击右上角 **「⋯」** → **「Add connections」**
3. 选择刚才创建的 Integration

#### 2.3 获取 Database ID

数据库页面 URL 类似：

```
https://www.notion.so/workspace/32ef2b9e-437d-80bc-8a47-e2fd7b67ea0b?v=...
```

`32ef2b9e-437d-80bc-8a47-e2fd7b67ea0b` 就是 Database ID。

### 3. 编辑配置

打开 `config.yaml`，填入你的信息：

#### 单数据库

```yaml
notion:
  token: "secret_你的Token"
  databases:
    - id: "你的DatabaseID"
      sub_dir: ""

obsidian:
  sync_dir: "/Users/liurainbow/Obsidian/我的仓库/Notion-Sync"

sync:
  init_from_notion: true
  delete_strategy: "soft"
```

#### 多数据库（推荐）

```yaml
notion:
  token: "secret_你的Token"
  databases:
    - id: "32ef2b9e-437d-80bc-8a47-e2fd7b67ea0b"
      sub_dir: "时令养生"
      excluded_properties: []

    - id: "另一个DatabaseID"
      sub_dir: "工作日志"
      excluded_properties: []

obsidian:
  sync_dir: "/Users/liurainbow/Obsidian/我的仓库/Notion-Sync"
  filename_template: "{title}"

sync:
  init_from_notion: true
  delete_strategy: "soft"
  append_notion_link: true
  track_sync_time: true
```

### 4. 运行同步

```bash
source venv/bin/activate
python sync.py
```

---

## 同步效果

### Notion 数据库行

| Name | Status | Tags | 创建日期 |
|------|--------|------|---------|
| 时令养生 | 已完成 | 健康,理论 | 2026-04-20 |

### 同步后 Obsidian Markdown 文件

```markdown
---
Name: 时令养生
Status: 已完成
Tags:
  - 健康
  - 理论
创建日期: 2026-04-20
notion-id: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
notion-url: https://www.notion.so/xxx
notion-created: 2026-04-20T10:00:00.000Z
synced-at: 2026-04-20 22:30:00
source: [在 Notion 中打开](https://www.notion.so/xxx)
---
```

---

## 定时自动同步

### macOS launchd（推荐）

创建 `~/Library/LaunchAgents/com.obsidian.notion.sync.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.obsidian.notion.sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>cd /path/to/obsidian_notion_sync &amp;&amp; source venv/bin/activate &amp;&amp; python sync.py</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>StandardOutPath</key>
    <string>/tmp/notion_sync.out</string>
    <key>StandardErrorPath</key>
    <string>/tmp/notion_sync.err</string>
</dict>
</plist>
```

加载任务：

```bash
launchctl load ~/Library/LaunchAgents/com.obsidian.notion.sync.plist
```

### Linux/macOS cron

```bash
crontab -e
```

添加：

```cron
0 * * * * cd /path/to/obsidian_notion_sync && source venv/bin/activate && python sync.py >> /tmp/notion_sync.log 2>&1
```

---

## 配置说明

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `notion.token` | Notion Integration Token | 必填 |
| `notion.databases` | 数据库列表，每项含 `id`, `sub_dir`, `excluded_properties` | 必填 |
| `notion.databases[].id` | 数据库 ID | 必填 |
| `notion.databases[].sub_dir` | Obsidian 子文件夹名（可选） | `""` |
| `notion.databases[].excluded_properties` | 该数据库单独排除的属性 | `[]` |
| `notion.excluded_properties` | 全局排除属性（所有数据库生效） | `[]` |
| `obsidian.sync_dir` | Obsidian 同步文件夹绝对路径 | 必填 |
| `obsidian.filename_template` | 文件名模板，`{title}` 和 `{id}` 可用 | `{title}` |
| `sync.init_from_notion` | 首次运行时是否从 Notion 全量拉取 | `true` |
| `sync.delete_strategy` | 删除策略：`none`/`soft`/`hard` | `soft` |
| `sync.append_notion_link` | 是否在 frontmatter 追加 Notion 链接 | `true` |
| `sync.track_sync_time` | 是否记录同步时间 | `true` |
| `sync.api_delay` | API 请求间隔（秒） | `0.35` |

---

## 同步逻辑详解

```
对于每个 Notion 数据库行 ↔ Obsidian Markdown 文件配对：

1. 获取 Notion last_edited_time
2. 获取 Obsidian 文件 mtime
3. 比较时间戳（阈值 5 秒）：

   Notion 更新  →  覆盖 Obsidian frontmatter，对齐文件 mtime
   Obsidian 更新 →  推送 frontmatter 到 Notion，对齐文件 mtime
   时间一致    →  跳过
```

---

## 局限与注意事项

| 局限 | 说明 |
|------|------|
| **不同步正文内容** | 只同步 frontmatter ↔ properties，正文保留在各自平台。正文双向转换（Markdown ↔ Notion blocks）过于复杂，不适合 MVP。 |
| **冲突可能丢数据** | 以时间戳为准，旧版本静默覆盖。建议配合 Obsidian Git 插件做版本备份。 |
| **删除不可逆** | `hard` 模式会直接删除文件；`soft` 模式移入 `.trash`，30 天后需手动清理。 |
| **首次同步方向** | 默认从 Notion 拉取全量数据到 Obsidian。 |
| **关系属性** | relation 只同步 ID，不做名称解析。 |

---

## Obsidian 中配合 Dataview

安装 **Dataview** 插件后，可以创建动态索引：

```dataview
TABLE Status, Tags, synced-at
FROM "Notion-Sync"
SORT synced-at DESC
```

条件筛选：

```dataview
TABLE 创建日期, notion-url
FROM "Notion-Sync"
WHERE Status = "已完成"
```

---

## 故障排查

**Q: 运行后提示 "获取数据库失败"**
A: 检查 `token` 和 `database_id` 是否正确；确认数据库已授权给 Integration。

**Q: Obsidian 文件没有更新**
A: 检查文件 mtime 是否大于 Notion 的 `last_edited_time`；如果时间一致会跳过同步。

**Q: 属性类型报错**
A: 检查数据库中是否有不支持的特殊属性类型（如 formula 中的复杂对象）；可在 `excluded_properties` 中排除。

---

## License

MIT
