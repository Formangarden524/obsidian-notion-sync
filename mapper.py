#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion Property ↔ YAML/Frontmatter 类型映射器
处理双向类型转换
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional


class NotionToYamlMapper:
    """将 Notion API 返回的 property 转为 Python 原生类型"""

    @staticmethod
    def parse(prop: Dict[str, Any]) -> Any:
        prop_type = prop.get("type")
        handler = getattr(NotionToYamlMapper, f"_parse_{prop_type}", NotionToYamlMapper._parse_unknown)
        return handler(prop)

    @staticmethod
    def _parse_title(prop: Dict) -> str:
        texts = [t["plain_text"] for t in prop.get("title", [])]
        return "".join(texts)

    @staticmethod
    def _parse_rich_text(prop: Dict) -> str:
        texts = [t["plain_text"] for t in prop.get("rich_text", [])]
        return "".join(texts)

    @staticmethod
    def _parse_select(prop: Dict) -> str:
        s = prop.get("select")
        return s["name"] if s else ""

    @staticmethod
    def _parse_multi_select(prop: Dict) -> List[str]:
        return [s["name"] for s in prop.get("multi_select", [])]

    @staticmethod
    def _parse_status(prop: Dict) -> str:
        s = prop.get("status")
        return s["name"] if s else ""

    @staticmethod
    def _parse_date(prop: Dict) -> str:
        d = prop.get("date")
        if d:
            return d.get("start", "")
        return ""

    @staticmethod
    def _parse_number(prop: Dict) -> Optional[float]:
        return prop.get("number")

    @staticmethod
    def _parse_checkbox(prop: Dict) -> bool:
        return bool(prop.get("checkbox", False))

    @staticmethod
    def _parse_url(prop: Dict) -> str:
        return prop.get("url", "") or ""

    @staticmethod
    def _parse_email(prop: Dict) -> str:
        return prop.get("email", "") or ""

    @staticmethod
    def _parse_phone_number(prop: Dict) -> str:
        return prop.get("phone_number", "") or ""

    @staticmethod
    def _parse_relation(prop: Dict) -> List[str]:
        return [r["id"] for r in prop.get("relation", [])]

    @staticmethod
    def _parse_formula(prop: Dict) -> Any:
        f = prop.get("formula")
        if not f:
            return ""
        return f.get("string") or f.get("number") or f.get("boolean") or ""

    @staticmethod
    def _parse_rollup(prop: Dict) -> Any:
        r = prop.get("rollup")
        if not r:
            return ""
        # 简化处理：返回 rollup 的原始类型值
        roll_type = r.get("type")
        if roll_type == "number":
            return r.get("number")
        elif roll_type == "date":
            d = r.get("date")
            return d.get("start", "") if d else ""
        elif roll_type == "array":
            return [NotionToYamlMapper.parse(item) for item in r.get("array", [])]
        return ""

    @staticmethod
    def _parse_created_time(prop: Dict) -> str:
        return prop.get("created_time", "")

    @staticmethod
    def _parse_last_edited_time(prop: Dict) -> str:
        return prop.get("last_edited_time", "")

    @staticmethod
    def _parse_created_by(prop: Dict) -> str:
        u = prop.get("created_by")
        return u.get("name", "") if u else ""

    @staticmethod
    def _parse_last_edited_by(prop: Dict) -> str:
        u = prop.get("last_edited_by")
        return u.get("name", "") if u else ""

    @staticmethod
    def _parse_files(prop: Dict) -> List[str]:
        return [f.get("name", "") for f in prop.get("files", [])]

    @staticmethod
    def _parse_unknown(prop: Dict) -> str:
        return ""


class YamlToNotionMapper:
    """将 Python 原生类型转为 Notion API 可接受的 property 格式"""

    @staticmethod
    def build(prop_type: str, value: Any) -> Optional[Dict[str, Any]]:
        if value is None or value == "":
            return None
        handler = getattr(YamlToNotionMapper, f"_build_{prop_type}", None)
        if handler:
            return handler(value)
        return None

    @staticmethod
    def _build_title(value: Any) -> Dict:
        return {"title": [{"text": {"content": str(value)}}]}

    @staticmethod
    def _build_rich_text(value: Any) -> Dict:
        return {"rich_text": [{"text": {"content": str(value)}}]}

    @staticmethod
    def _build_select(value: Any) -> Dict:
        return {"select": {"name": str(value)}}

    @staticmethod
    def _build_multi_select(value: Any) -> Dict:
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        if not isinstance(value, list):
            value = [value] if value else []
        return {"multi_select": [{"name": str(v)} for v in value]}

    @staticmethod
    def _build_status(value: Any) -> Dict:
        return {"status": {"name": str(value)}}

    @staticmethod
    def _build_date(value: Any) -> Dict:
        return {"date": {"start": str(value)}}

    @staticmethod
    def _build_number(value: Any) -> Dict:
        try:
            num = float(value) if isinstance(value, str) else value
            return {"number": num}
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _build_checkbox(value: Any) -> Dict:
        if isinstance(value, bool):
            return {"checkbox": value}
        if isinstance(value, str):
            return {"checkbox": value.lower() in ("true", "yes", "1", "on")}
        return {"checkbox": bool(value)}

    @staticmethod
    def _build_url(value: Any) -> Dict:
        return {"url": str(value) if value else None}

    @staticmethod
    def _build_email(value: Any) -> Dict:
        return {"email": str(value) if value else None}

    @staticmethod
    def _build_phone_number(value: Any) -> Dict:
        return {"phone_number": str(value) if value else None}

    @staticmethod
    def _build_relation(value: Any) -> Dict:
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        if not isinstance(value, list):
            value = [value] if value else []
        return {"relation": [{"id": str(v)} for v in value]}


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """清理文件名中的非法字符"""
    name = name.strip()
    # 替换常见非法字符
    name = re.sub(r'[\\/*<>"|?#^\[\]]', '_', name)
    # 控制长度
    if len(name) > max_length:
        name = name[:max_length]
    return name or "untitled"


def iso_to_timestamp(iso_str: str) -> float:
    """ISO 8601 字符串转 Unix timestamp"""
    if not iso_str:
        return 0.0
    # 处理带 Z 和带 +08:00 的情况
    iso_str = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.timestamp()
    except ValueError:
        return 0.0


def timestamp_to_iso(ts: float) -> str:
    """Unix timestamp 转 ISO 8601 字符串"""
    dt = datetime.fromtimestamp(ts)
    return dt.isoformat()
