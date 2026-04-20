#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
附件管理器：处理 Notion ↔ Obsidian 的图片/文件双向同步

Notion → Obsidian：下载图片到本地 attachments 目录
Obsidian → Notion：上传本地图片到 Notion 服务器
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests


class AttachmentsManager:
    """管理 Notion 与 Obsidian 之间的图片/附件同步"""

    def __init__(self, sync_dir: str, token: str):
        self.sync_dir = Path(sync_dir).expanduser().resolve()
        self.attachments_dir = self.sync_dir / "attachments"
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        self.token = token
        self.map_file = self.attachments_dir / ".url_map.json"
        self.url_map: Dict[str, str] = self._load_map()

    def _load_map(self) -> Dict[str, str]:
        """加载 {原始URL: 本地文件名} 映射"""
        if self.map_file.exists():
            try:
                with open(self.map_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_map(self):
        """保存 URL 映射关系"""
        try:
            with open(self.map_file, "w", encoding="utf-8") as f:
                json.dump(self.url_map, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"  ⚠️  保存附件映射失败: {e}")

    def _guess_extension(self, response: requests.Response, suggested_name: Optional[str] = None) -> str:
        """根据响应头或文件名猜测扩展名"""
        if suggested_name and "." in suggested_name:
            return Path(suggested_name).suffix

        content_type = response.headers.get("Content-Type", "")
        ct_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
            "application/pdf": ".pdf",
        }
        for ct, ext in ct_map.items():
            if ct in content_type:
                return ext
        return ".bin"

    def _guess_content_type(self, suffix: str) -> str:
        """根据扩展名获取 Content-Type"""
        mapping = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".pdf": "application/pdf",
        }
        return mapping.get(suffix.lower(), "application/octet-stream")

    def _generate_filename(self, url: str, suggested_name: Optional[str] = None) -> str:
        """生成安全的本地文件名"""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        if suggested_name:
            safe_name = re.sub(r'[^\w\-.]', '_', Path(suggested_name).stem)
            ext = Path(suggested_name).suffix or ".png"
            return f"{safe_name}_{url_hash}{ext}"
        return f"image_{url_hash}.png"

    # ==================== Notion → Obsidian ====================

    def download_image(self, url: str, suggested_name: Optional[str] = None) -> Optional[str]:
        """
        下载图片到本地 attachments 目录
        返回: 相对于 sync_dir 的路径 (如 "attachments/xxx.png")
        """
        if not url:
            return None

        # 已下载过且文件存在，直接返回
        if url in self.url_map:
            filename = self.url_map[url]
            if (self.attachments_dir / filename).exists():
                return f"attachments/{filename}"

        try:
            headers = {}
            # Notion 托管的文件需要 Authorization
            if "notion.so" in url or "amazonaws.com" in url:
                headers["Authorization"] = f"Bearer {self.token}"

            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()

            ext = self._guess_extension(resp, suggested_name)
            filename = self._generate_filename(url, suggested_name or f"image{ext}")
            filepath = self.attachments_dir / filename

            with open(filepath, "wb") as f:
                f.write(resp.content)

            self.url_map[url] = filename
            self._save_map()

            return f"attachments/{filename}"
        except Exception as e:
            print(f"  ⚠️  下载附件失败: {e}")
            return None

    def download_all_from_blocks(self, blocks: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        遍历 Notion blocks，下载所有图片/文件附件
        返回: {原始URL: 本地路径} 映射
        """
        url_map = {}
        for block in blocks:
            block_type = block.get("type", "")
            content = block.get(block_type, {})

            if block_type == "image":
                img_url = ""
                original_name = None
                if "external" in content:
                    img_url = content["external"].get("url", "")
                elif "file" in content:
                    img_url = content["file"].get("url", "")

                if img_url:
                    local_path = self.download_image(img_url, original_name)
                    if local_path:
                        url_map[img_url] = local_path

            elif block_type in ("file", "pdf"):
                file_url = ""
                original_name = content.get("name", "")
                if "external" in content:
                    file_url = content["external"].get("url", "")
                elif "file" in content:
                    file_url = content["file"].get("url", "")

                if file_url:
                    local_path = self.download_image(file_url, original_name)
                    if local_path:
                        url_map[file_url] = local_path

            # 递归处理子 blocks
            children = block.get("children", [])
            if children:
                child_map = self.download_all_from_blocks(children)
                url_map.update(child_map)

        return url_map

    # ==================== Obsidian → Notion ====================

    def upload_image(self, local_path: str) -> Optional[Dict[str, Any]]:
        """
        上传本地图片到 Notion 服务器
        返回: Notion file 对象（可用于创建 image block）
        """
        path = self._resolve_local_path(local_path)
        if not path or not path.exists():
            print(f"  ⚠️  本地文件不存在: {local_path}")
            return None

        try:
            content_length = path.stat().st_size
            content_type = self._guess_content_type(path.suffix)

            # 1. 创建 upload session
            resp = requests.post(
                "https://api.notion.com/v1/file_uploads",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json={
                    "name": path.name,
                    "content_type": content_type,
                    "content_length": content_length,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            upload_url = data.get("upload_url")
            if not upload_url:
                print(f"  ⚠️  Notion 未返回 upload_url")
                return None

            # 2. PUT 上传文件到 S3 预签名 URL
            with open(path, "rb") as f:
                put_resp = requests.put(
                    upload_url,
                    data=f,
                    headers={"Content-Type": content_type},
                    timeout=120,
                )
                put_resp.raise_for_status()

            # 3. 返回 file 对象
            file_obj = data.get("file")
            if file_obj:
                print(f"  ☁️  已上传: {path.name}")
            return file_obj

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                print(f"  ⚠️  Notion 文件上传 API 未授权（请检查 Integration 权限）")
            else:
                print(f"  ⚠️  上传失败 HTTP {e.response.status_code}: {e}")
            return None
        except Exception as e:
            print(f"  ⚠️  上传附件失败: {e}")
            return None

    def _resolve_local_path(self, rel_path: str) -> Optional[Path]:
        """解析相对路径为绝对路径"""
        # 去除开头的 ./
        rel_path = rel_path.lstrip("./")

        # 尝试直接相对 sync_dir
        p = self.sync_dir / rel_path
        if p.exists():
            return p

        # 尝试相对 attachments 目录
        if rel_path.startswith("attachments/"):
            p = self.attachments_dir / rel_path[len("attachments/"):]
            if p.exists():
                return p

        return None

    def find_local_images(self, markdown: str) -> List[Tuple[str, str]]:
        """
        查找 Markdown 中的本地图片路径
        返回: [(alt_text, local_path), ...]
        """
        results = []
        for match in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', markdown):
            alt = match.group(1)
            path = match.group(2)
            if not path.startswith(("http://", "https://", "data:")):
                results.append((alt, path))
        return results

    def upload_all_in_markdown(self, markdown: str) -> Dict[str, Dict[str, Any]]:
        """
        上传 Markdown 中所有本地图片到 Notion
        返回: {本地路径: Notion file 对象}
        """
        images = self.find_local_images(markdown)
        uploaded = {}
        for alt, path in images:
            file_obj = self.upload_image(path)
            if file_obj:
                uploaded[path] = file_obj
        return uploaded
