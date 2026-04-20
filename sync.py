#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Obsidian ↔ Notion 双向同步主引擎

同步逻辑：
1. 获取 Notion 数据库所有行
2. 扫描 Obsidian 同步目录所有 Markdown 文件
3. 通过 notion-id 建立配对关系
4. 比较 last_edited_time（Notion）与文件 mtime（Obsidian）
5. 以时间戳为准，新的覆盖旧的
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from mapper import (
    NotionToYamlMapper,
    YamlToNotionMapper,
    iso_to_timestamp,
    timestamp_to_iso,
    sanitize_filename,
)
from notion_client import NotionClient, NotionDatabaseRow
from obsidian_client import ObsidianClient, ObsidianNote
from blocks_converter import blocks_to_markdown, simple_markdown_to_blocks


class SyncEngine:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)
        self.notion = NotionClient(
            token=self.config["notion"]["token"],
            api_delay=self.config["sync"].get("api_delay", 0.35),
        )
        self.base_sync_dir = self.config["obsidian"]["sync_dir"]
        self.filename_template = self.config["obsidian"].get("filename_template", "{title}")
        self.state_file = Path("sync_state.json")
        self.state = self._load_state()

        # 数据库属性 schema（db_id -> {name -> type}）
        self.db_schemas: Dict[str, Dict[str, str]] = {}

    def _load_config(self, path: str) -> Dict[str, Any]:
        """加载 YAML 配置"""
        config_path = Path(path)
        if not config_path.exists():
            print(f"❌ 配置文件不存在: {path}")
            sys.exit(1)
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_state(self) -> Dict[str, Any]:
        """加载同步状态"""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                pass
        return {
            "last_sync": 0,
            "notion_to_file": {},  # notion-id -> filename
        }

    def _save_state(self):
        """保存同步状态"""
        self.state["last_sync"] = time.time()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _fetch_db_schema(self, database_id: str) -> Dict[str, str]:
        """获取数据库属性定义"""
        db_info = self.notion.get_database(database_id)
        if not db_info:
            print(f"❌ 无法获取数据库信息: {database_id}")
            return {}

        properties = db_info.get("properties", {})
        schema = {
            name: prop.get("type", "")
            for name, prop in properties.items()
        }
        self.db_schemas[database_id] = schema
        print(f"📐 数据库属性: {list(schema.keys())}")
        return schema

    def _build_frontmatter(
        self,
        row: NotionDatabaseRow,
        excluded: List[str],
    ) -> Dict[str, Any]:
        """从 Notion 行构建 Obsidian frontmatter"""
        properties = row.get_all_parsed_properties(excluded=excluded)

        # 添加元数据
        properties["notion-id"] = row.id
        properties["notion-url"] = row.url
        properties["notion-created"] = row.created_time

        if self.config["sync"].get("track_sync_time", True):
            properties["synced-at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if self.config["sync"].get("append_notion_link", True):
            properties["source"] = f"[在 Notion 中打开]({row.url})"

        return properties

    def _notion_to_obsidian(self, row: NotionDatabaseRow, existing_note: Optional[ObsidianNote] = None):
        """Notion → Obsidian：拉取更新"""
        title = row.get_title()
        filename = self.obsidian.build_filename(title, row.id)

        # 如果有现有文件，保留其文件名
        if existing_note:
            filename = existing_note.filepath.name

        # 确保唯一
        if not existing_note:
            filename = self.obsidian.ensure_unique_filename(filename)

        # 构建 frontmatter
        excluded = self.config["notion"].get("excluded_properties", [])
        metadata = self._build_frontmatter(row, excluded)

        # 保留原有正文（如果存在）
        existing_body = ""
        if existing_note:
            existing_body = existing_note.body

        # 写入文件
        filepath = self.obsidian.write_file(
            filename=filename,
            metadata=metadata,
            body=existing_body,
            preserve_existing_body=True,
        )

        # 对齐文件修改时间（避免下次同步误判）
        notion_ts = row.get_last_edited_timestamp()
        if notion_ts > 0:
            self.obsidian.set_file_mtime(filepath, notion_ts)

        # 记录映射关系
        self.state["notion_to_file"][row.id] = filename

        print(f"  ⬇️  Notion → Obsidian: {filename}")

    def _obsidian_to_notion(self, note: ObsidianNote, db_schema: Dict[str, str], sync_body: bool = True):
        """Obsidian → Notion：推送更新"""
        if not note.notion_id:
            print(f"  ⚠️  跳过（无 notion-id）: {note.filepath.name}")
            return

        # 构建 properties
        properties = note.to_notion_properties(db_schema)

        # 确保不修改 notion-id 等系统字段
        for key in ["notion-id", "notion-url", "notion-created", "synced-at", "source"]:
            properties.pop(key, None)
            properties.pop(key.replace("-", " "), None)

        # 更新 Notion 属性
        success = self.notion.update_page_properties(note.notion_id, properties)

        if not success:
            print(f"  ❌ 推送属性失败: {note.filepath.name}")
            return

        # 同步正文
        body_synced = False
        if sync_body and note.body and note.body.strip():
            blocks = simple_markdown_to_blocks(note.body.strip())
            if blocks:
                body_success = self.notion.update_page_content(note.notion_id, blocks)
                if body_success:
                    body_synced = True
                else:
                    print(f"  ⚠️  正文同步失败: {note.filepath.name}")

        # 获取更新后的页面时间戳，对齐本地文件
        updated_page = self.notion.get_page(note.notion_id)
        if updated_page:
            new_ts = iso_to_timestamp(updated_page.get("last_edited_time", ""))
            if new_ts > 0:
                self.obsidian.set_file_mtime(note.filepath, new_ts)

        body_info = " (含正文)" if body_synced else ""
        print(f"  ⬆️  Obsidian → Notion: {note.filepath.name}{body_info}")

    def _compare_and_sync(self, row: NotionDatabaseRow, note: Optional[ObsidianNote]) -> str:
        """
        比较时间戳并执行同步
        返回: "notion", "obsidian", "skip", "new"
        """
        notion_ts = row.get_last_edited_timestamp()

        if not note:
            # Obsidian 端不存在，从 Notion 创建
            self._notion_to_obsidian(row)
            return "new"

        obsidian_ts = note.get_last_edited_timestamp()

        # 时间差阈值（5秒），避免浮点精度问题
        threshold = 5

        if notion_ts > obsidian_ts + threshold:
            # Notion 更新
            self._notion_to_obsidian(row, note)
            return "notion"
        elif obsidian_ts > notion_ts + threshold:
            # Obsidian 更新
            self._obsidian_to_notion(note)
            return "obsidian"
        else:
            # 时间一致，跳过
            return "skip"

    def _handle_deletions(self, active_notion_ids: Set[str]):
        """处理 Notion 中已删除的行"""
        delete_strategy = self.config["sync"].get("delete_strategy", "soft")
        if delete_strategy == "none":
            return

        # 找出 Obsidian 中有 notion-id 但 Notion 中已不存在的文件
        for md_file in self.obsidian.list_markdown_files():
            result = self.obsidian.read_file(md_file)
            if not result:
                continue
            metadata, _ = result
            notion_id = metadata.get("notion-id", "")

            if notion_id and notion_id not in active_notion_ids:
                if delete_strategy == "soft":
                    self.obsidian.move_to_trash(md_file)
                elif delete_strategy == "hard":
                    self.obsidian.delete_file(md_file)

                # 从状态中移除
                self.state["notion_to_file"].pop(notion_id, None)

    def sync_single_database(self, db_config: Dict[str, Any]) -> Dict[str, int]:
        """同步单个数据库"""
        database_id = db_config["id"]
        sub_dir = db_config.get("sub_dir", "")
        db_excluded = db_config.get("excluded_properties", [])
        global_excluded = self.config["notion"].get("excluded_properties", [])
        excluded = list(set(global_excluded + db_excluded))

        print(f"\n{'─' * 50}")
        print(f"📂 同步数据库: {database_id}")
        if sub_dir:
            print(f"📁 Obsidian 子目录: {sub_dir}")
        print("─" * 50)

        # 初始化 Obsidian 客户端（指向子目录）
        sync_path = Path(self.base_sync_dir)
        if sub_dir:
            sync_path = sync_path / sub_dir
        self.obsidian = ObsidianClient(
            sync_dir=str(sync_path),
            filename_template=self.filename_template,
        )

        # 获取数据库结构
        db_schema = self._fetch_db_schema(database_id)
        if not db_schema:
            return {"notion": 0, "obsidian": 0, "skip": 0, "new": 0, "error": 1}

        # 获取所有 Notion 行
        notion_rows = self.notion.query_database(database_id)
        if not notion_rows:
            print("⚠️  数据库为空或无法访问")
            return {"notion": 0, "obsidian": 0, "skip": 0, "new": 0}

        rows = [NotionDatabaseRow(r) for r in notion_rows]
        active_notion_ids = {r.id for r in rows}

        # 扫描 Obsidian 文件
        obsidian_notes: Dict[str, ObsidianNote] = {}
        orphan_files: List[Path] = []

        for md_file in self.obsidian.list_markdown_files():
            result = self.obsidian.read_file(md_file)
            if not result:
                continue
            metadata, body = result
            notion_id = metadata.get("notion-id", "")

            if notion_id:
                obsidian_notes[notion_id] = ObsidianNote(md_file, metadata, body)
            else:
                orphan_files.append(md_file)

        print(f"📁 Obsidian 文件: {len(obsidian_notes)} 已配对, {len(orphan_files)} 未配对")

        # 同步每个行
        stats = {"notion": 0, "obsidian": 0, "skip": 0, "new": 0}

        for row in rows:
            note = obsidian_notes.get(row.id)
            direction = self._compare_and_sync_single(row, note, excluded, db_schema)
            stats[direction] += 1

        # 处理删除
        self._handle_deletions(active_notion_ids)

        if orphan_files:
            print(f"\n⚠️  发现 {len(orphan_files)} 个无 notion-id 的文件（跳过同步）")

        return stats

    def _compare_and_sync_single(
        self,
        row: NotionDatabaseRow,
        note: Optional[ObsidianNote],
        excluded: List[str],
        db_schema: Dict[str, str],
    ) -> str:
        """比较并同步单个行（使用传入的 schema）"""
        notion_ts = row.get_last_edited_timestamp()
        sync_body = self.config["sync"].get("sync_body", True)

        if not note:
            self._notion_to_obsidian(row, excluded, note, sync_body=sync_body)
            return "new"

        obsidian_ts = note.get_last_edited_timestamp()
        threshold = 5

        if notion_ts > obsidian_ts + threshold:
            self._notion_to_obsidian(row, excluded, note, sync_body=sync_body)
            return "notion"
        elif obsidian_ts > notion_ts + threshold:
            self._obsidian_to_notion(note, db_schema, sync_body=sync_body)
            return "obsidian"
        else:
            return "skip"

    def _notion_to_obsidian(
        self,
        row: NotionDatabaseRow,
        excluded: List[str],
        existing_note: Optional[ObsidianNote] = None,
        sync_body: bool = True,
    ):
        """Notion → Obsidian：拉取更新（使用传入的 excluded 列表）"""
        title = row.get_title()
        filename = self.obsidian.build_filename(title, row.id)

        if existing_note:
            filename = existing_note.filepath.name

        if not existing_note:
            filename = self.obsidian.ensure_unique_filename(filename)

        metadata = self._build_frontmatter(row, excluded)

        # 获取正文内容
        new_body = ""
        if sync_body:
            blocks = self.notion.get_page_blocks(row.id)
            if blocks:
                new_body = blocks_to_markdown(blocks)
                # 去除首尾空行
                new_body = new_body.strip()

        # 如果已有文件且不同步正文，保留原有正文
        if existing_note and not sync_body:
            new_body = existing_note.body

        filepath = self.obsidian.write_file(
            filename=filename,
            metadata=metadata,
            body=new_body,
            preserve_existing_body=False,  # 我们已自行处理正文合并
        )

        notion_ts = row.get_last_edited_timestamp()
        if notion_ts > 0:
            self.obsidian.set_file_mtime(filepath, notion_ts)

        self.state["notion_to_file"][row.id] = str(filepath.relative_to(Path(self.base_sync_dir)))
        body_info = " (含正文)" if sync_body and new_body else ""
        print(f"  ⬇️  Notion → Obsidian: {filename}{body_info}")

    def run(self):
        """执行完整同步流程（支持多数据库）"""
        print("=" * 50)
        print(f"🔄 Obsidian ↔ Notion 双向同步")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)

        databases = self.config["notion"].get("databases", [])
        if not databases:
            print("❌ 配置错误：notion.databases 为空")
            return

        total_stats = {"notion": 0, "obsidian": 0, "skip": 0, "new": 0}

        for db_config in databases:
            stats = self.sync_single_database(db_config)
            for k in total_stats:
                total_stats[k] += stats.get(k, 0)

        self._save_state()

        print("\n" + "=" * 50)
        print("📊 全局同步统计")
        print(f"   Notion → Obsidian: {total_stats['notion'] + total_stats['new']} 条")
        print(f"   Obsidian → Notion: {total_stats['obsidian']} 条")
        print(f"   跳过（已同步）:   {total_stats['skip']} 条")
        print("=" * 50)


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    engine = SyncEngine(config_path)
    engine.run()


if __name__ == "__main__":
    main()
