#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion API 封装客户端
"""

import time
from typing import Any, Dict, List, Optional, Tuple
from notion_client import Client
from notion_client.errors import APIResponseError

from mapper import NotionToYamlMapper, iso_to_timestamp


class NotionClient:
    def __init__(self, token: str, api_delay: float = 0.35):
        self.client = Client(auth=token)
        self.api_delay = api_delay

    def _delay(self):
        """请求间隔，避免限流"""
        if self.api_delay > 0:
            time.sleep(self.api_delay)

    def get_database(self, database_id: str) -> Optional[Dict]:
        """获取数据库元信息（包括属性定义）"""
        try:
            self._delay()
            return self.client.databases.retrieve(database_id=database_id)
        except APIResponseError as e:
            print(f"❌ 获取数据库失败: {e}")
            return None

    def query_database(
        self,
        database_id: str,
        filter_obj: Optional[Dict] = None,
        sorts: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """分页查询数据库所有行"""
        results = []
        has_more = True
        start_cursor = None

        print(f"📡 正在查询数据库: {database_id}")

        while has_more:
            self._delay()
            kwargs = {"database_id": database_id}
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
            if filter_obj:
                kwargs["filter"] = filter_obj
            if sorts:
                kwargs["sorts"] = sorts

            try:
                response = self.client.databases.query(**kwargs)
                batch = response.get("results", [])
                results.extend(batch)
                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")
                if batch:
                    print(f"  已获取 {len(results)} 条...")
            except APIResponseError as e:
                print(f"❌ 查询数据库失败: {e}")
                break

        print(f"📋 共获取 {len(results)} 条记录")
        return results

    def get_page(self, page_id: str) -> Optional[Dict]:
        """获取单个页面详情"""
        try:
            self._delay()
            return self.client.pages.retrieve(page_id=page_id)
        except APIResponseError as e:
            print(f"❌ 获取页面失败: {e}")
            return None

    def update_page_properties(self, page_id: str, properties: Dict[str, Any]) -> bool:
        """更新页面属性（数据库行）"""
        try:
            self._delay()
            self.client.pages.update(page_id=page_id, properties=properties)
            return True
        except APIResponseError as e:
            print(f"❌ 更新页面属性失败: {e}")
            return False

    def create_page(self, database_id: str, properties: Dict[str, Any]) -> Optional[Dict]:
        """在数据库中创建新行"""
        try:
            self._delay()
            return self.client.pages.create(
                parent={"database_id": database_id},
                properties=properties,
            )
        except APIResponseError as e:
            print(f"❌ 创建页面失败: {e}")
            return None

    def get_page_blocks(self, page_id: str) -> List[Dict]:
        """获取页面的 block 内容（正文）"""
        blocks = []
        has_more = True
        start_cursor = None

        while has_more:
            self._delay()
            try:
                response = self.client.blocks.children.list(
                    block_id=page_id,
                    start_cursor=start_cursor,
                )
                blocks.extend(response.get("results", []))
                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")
            except APIResponseError as e:
                print(f"❌ 获取页面内容失败: {e}")
                break

        return blocks


class NotionDatabaseRow:
    """Notion 数据库行的包装对象，便于访问"""

    def __init__(self, page_data: Dict[str, Any]):
        self.id = page_data.get("id", "")
        self.created_time = page_data.get("created_time", "")
        self.last_edited_time = page_data.get("last_edited_time", "")
        self.properties = page_data.get("properties", {})
        self.url = page_data.get("url", "")

    def get_title(self) -> str:
        """获取标题（假设第一个 title 类型字段为标题）"""
        for key, prop in self.properties.items():
            if prop.get("type") == "title":
                return NotionToYamlMapper.parse(prop)
        return "untitled"

    def get_property(self, name: str) -> Any:
        """获取指定属性的解析值"""
        prop = self.properties.get(name)
        if prop:
            return NotionToYamlMapper.parse(prop)
        return None

    def get_all_parsed_properties(self, excluded: List[str] = None) -> Dict[str, Any]:
        """获取所有解析后的属性（排除指定字段）"""
        excluded = excluded or []
        result = {}
        for key, prop in self.properties.items():
            if key in excluded:
                continue
            clean_key = self._clean_key(key)
            result[clean_key] = NotionToYamlMapper.parse(prop)
        return result

    @staticmethod
    def _clean_key(key: str) -> str:
        """清理属性名，使其适合作为 YAML key"""
        import re
        key = re.sub(r'[^\w\s\-]', '', key).strip().replace(' ', '-')
        return key

    def get_last_edited_timestamp(self) -> float:
        return iso_to_timestamp(self.last_edited_time)
