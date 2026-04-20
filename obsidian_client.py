#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Obsidian 本地文件操作封装
处理 Markdown 文件的读取、写入、frontmatter 解析
"""

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import frontmatter

from mapper import sanitize_filename, timestamp_to_iso


class ObsidianClient:
    def __init__(self, sync_dir: str, filename_template: str = "{title}"):
        self.sync_dir = Path(sync_dir).expanduser().resolve()
        self.filename_template = filename_template
        self.trash_dir = self.sync_dir / ".trash"

        # 确保目录存在
        self.sync_dir.mkdir(parents=True, exist_ok=True)

    def list_markdown_files(self) -> List[Path]:
        """列出同步目录下所有 Markdown 文件"""
        if not self.sync_dir.exists():
            return []
        return sorted(self.sync_dir.glob("*.md"))

    def read_file(self, filepath: Path) -> Optional[Tuple[Dict[str, Any], str]]:
        """
        读取 Markdown 文件
        返回: (frontmatter_dict, body_content)
        """
        try:
            post = frontmatter.load(str(filepath))
            return dict(post.metadata), post.content
        except Exception as e:
            print(f"❌ 读取文件失败 {filepath}: {e}")
            return None

    def write_file(
        self,
        filename: str,
        metadata: Dict[str, Any],
        body: str = "",
        preserve_existing_body: bool = True,
    ) -> Path:
        """
        写入 Markdown 文件
        preserve_existing_body=True 时，如果文件已存在且正文非空，保留原有正文只更新 frontmatter
        """
        filepath = self.sync_dir / filename
        existing_body = ""

        if preserve_existing_body and filepath.exists():
            result = self.read_file(filepath)
            if result:
                existing_body = result[1]

        # 如果传入了 body 且不为空，使用传入的；否则保留原有正文
        final_body = body if body is not None else existing_body

        # 构建 frontmatter
        post = frontmatter.Post(final_body, **metadata)
        content = frontmatter.dumps(post, allow_unicode=True, sort_keys=False)

        # 确保内容以换行结尾
        if not content.endswith("\n"):
            content += "\n"

        filepath.write_text(content, encoding="utf-8")
        return filepath

    def get_file_mtime(self, filepath: Path) -> float:
        """获取文件修改时间（Unix timestamp）"""
        try:
            return filepath.stat().st_mtime
        except OSError:
            return 0.0

    def set_file_mtime(self, filepath: Path, mtime: float):
        """设置文件修改时间（用于同步后对齐时间戳）"""
        try:
            atime = filepath.stat().st_atime
            os.utime(filepath, (atime, mtime))
        except OSError:
            pass

    def move_to_trash(self, filepath: Path):
        """软删除：移入 .trash 文件夹"""
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        new_name = f"{timestamp}-{filepath.name}"
        shutil.move(str(filepath), str(self.trash_dir / new_name))
        print(f"  🗑️  已移入回收站: {filepath.name}")

    def delete_file(self, filepath: Path):
        """硬删除"""
        try:
            filepath.unlink()
            print(f"  🗑️  已删除: {filepath.name}")
        except OSError as e:
            print(f"  ❌ 删除失败 {filepath.name}: {e}")

    def find_file_by_notion_id(self, notion_id: str) -> Optional[Path]:
        """根据 notion-id 查找对应的 Markdown 文件"""
        for md_file in self.list_markdown_files():
            result = self.read_file(md_file)
            if result:
                metadata, _ = result
                if metadata.get("notion-id") == notion_id:
                    return md_file
        return None

    def build_filename(self, title: str, notion_id: str) -> str:
        """根据模板构建文件名"""
        safe_title = sanitize_filename(title)
        short_id = notion_id.replace("-", "")[:8]

        name = self.filename_template.format(title=safe_title, id=short_id)
        name = sanitize_filename(name)

        if not name.endswith(".md"):
            name += ".md"

        return name

    def ensure_unique_filename(self, filename: str) -> str:
        """确保文件名不重复（如果已存在则追加序号）"""
        filepath = self.sync_dir / filename
        if not filepath.exists():
            return filename

        stem = Path(filename).stem
        suffix = Path(filename).suffix
        counter = 1

        while True:
            new_name = f"{stem}-{counter}{suffix}"
            if not (self.sync_dir / new_name).exists():
                return new_name
            counter += 1


class ObsidianNote:
    """Obsidian 笔记的包装对象"""

    def __init__(self, filepath: Path, metadata: Dict[str, Any], body: str):
        self.filepath = filepath
        self.metadata = metadata
        self.body = body
        self.notion_id = metadata.get("notion-id", "")
        self.title = metadata.get("Name", "") or metadata.get("name", "") or filepath.stem

    def get_last_edited_timestamp(self) -> float:
        """从 metadata 或文件系统获取最后修改时间"""
        # 优先使用文件系统 mtime
        try:
            return self.filepath.stat().st_mtime
        except OSError:
            return 0.0

    def get_property(self, name: str) -> Any:
        """获取 frontmatter 中的属性值"""
        return self.metadata.get(name)

    def set_property(self, name: str, value: Any):
        """设置 frontmatter 属性"""
        self.metadata[name] = value

    def to_notion_properties(self, schema: Dict[str, str]) -> Dict[str, Any]:
        """
        将 frontmatter 转为 Notion properties
        schema: {property_name: property_type}
        """
        from mapper import YamlToNotionMapper

        properties = {}
        for prop_name, prop_type in schema.items():
            # 尝试多种 key 匹配方式
            value = None
            for key in [prop_name, prop_name.replace(" ", "-"), prop_name.replace("-", " ")]:
                if key in self.metadata:
                    value = self.metadata[key]
                    break

            if value is not None and value != "":
                built = YamlToNotionMapper.build(prop_type, value)
                if built:
                    properties[prop_name] = built

        return properties
