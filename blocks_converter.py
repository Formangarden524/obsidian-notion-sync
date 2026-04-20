#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion Blocks ↔ Markdown 双向转换器（增强版）

支持更多 block 类型与内联格式：
- paragraph, heading_1/2/3, bulleted/numbered_list_item, to_do, quote
- code, divider, image, callout, toggle, table, equation
- column_list, embed, video, file, pdf, link_preview
- 内联格式: bold, italic, code, strikethrough, underline, link, color, math
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from markdown_it import MarkdownIt
from markdown_it.token import Token


# ==================== 工具函数 ====================

def escape_md(text: str) -> str:
    """转义 Markdown 特殊字符"""
    return text.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")


# ==================== Notion rich_text → Markdown ====================

def rich_text_to_markdown(rich_texts: List[Dict[str, Any]], escape: bool = False) -> str:
    """将 Notion rich_text 数组转为 Markdown 字符串"""
    parts = []
    for rt in rich_texts:
        text = rt.get("plain_text", "")
        if not text:
            continue
        
        # 如果需要转义，先处理
        if escape:
            text = text.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`")
        
        annotations = rt.get("annotations", {})
        
        # 应用格式标记（从内到外）
        if annotations.get("code"):
            text = f"`{text}`"
        if annotations.get("bold"):
            text = f"**{text}**"
        if annotations.get("italic"):
            text = f"*{text}*"
        if annotations.get("strikethrough"):
            text = f"~~{text}~~"
        if annotations.get("underline"):
            text = f"<u>{text}</u>"
        if annotations.get("color") and annotations["color"] != "default":
            color = annotations["color"]
            text = f'<span style="color:{color}">{text}</span>'
        
        # 链接
        href = rt.get("href", "")
        if href and not href.startswith("mention:"):
            text = f"[{text}]({href})"
        
        # equation 内联公式
        if rt.get("type") == "equation":
            expr = rt.get("equation", {}).get("expression", "")
            text = f"${expr}$"
        
        parts.append(text)
    
    return "".join(parts)


# ==================== Notion Block → Markdown ====================

def block_to_markdown(block: Dict[str, Any], indent: str = "") -> str:
    """将单个 Notion block 转为 Markdown 字符串"""
    block_type = block.get("type", "")
    content = block.get(block_type, {})
    
    if block_type == "paragraph":
        text = rich_text_to_markdown(content.get("rich_text", []))
        return f"{indent}{text}\n" if text else "\n"
    
    elif block_type == "heading_1":
        text = rich_text_to_markdown(content.get("rich_text", []))
        return f"{indent}# {text}\n\n"
    
    elif block_type == "heading_2":
        text = rich_text_to_markdown(content.get("rich_text", []))
        return f"{indent}## {text}\n\n"
    
    elif block_type == "heading_3":
        text = rich_text_to_markdown(content.get("rich_text", []))
        return f"{indent}### {text}\n\n"
    
    elif block_type == "bulleted_list_item":
        text = rich_text_to_markdown(content.get("rich_text", []))
        children = block.get("children", [])
        md = f"{indent}- {text}\n"
        if children:
            md += blocks_to_markdown(children, indent + "  ")
        return md
    
    elif block_type == "numbered_list_item":
        text = rich_text_to_markdown(content.get("rich_text", []))
        children = block.get("children", [])
        md = f"{indent}1. {text}\n"
        if children:
            md += blocks_to_markdown(children, indent + "  ")
        return md
    
    elif block_type == "to_do":
        text = rich_text_to_markdown(content.get("rich_text", []))
        checked = content.get("checked", False)
        mark = "x" if checked else " "
        children = block.get("children", [])
        md = f"{indent}- [{mark}] {text}\n"
        if children:
            md += blocks_to_markdown(children, indent + "  ")
        return md
    
    elif block_type == "quote":
        text = rich_text_to_markdown(content.get("rich_text", []))
        lines = text.split("\n")
        quoted = "\n".join(f"{indent}> {line}" for line in lines)
        children = block.get("children", [])
        md = f"{quoted}\n"
        if children:
            md += blocks_to_markdown(children, indent + "> ")
        return md + "\n"
    
    elif block_type == "code":
        code_text = content.get("rich_text", [])
        code = "".join(t.get("plain_text", "") for t in code_text)
        language = content.get("language", "")
        return f"{indent}```{language}\n{code}\n```\n\n"
    
    elif block_type == "divider":
        return f"{indent}---\n\n"
    
    elif block_type == "image":
        caption = rich_text_to_markdown(content.get("caption", []))
        img_url = ""
        if "external" in content:
            img_url = content["external"].get("url", "")
        elif "file" in content:
            img_url = content["file"].get("url", "")
        
        if img_url:
            return f"{indent}![{caption}]({img_url})\n\n"
        return ""
    
    elif block_type == "callout":
        text = rich_text_to_markdown(content.get("rich_text", []))
        icon = content.get("icon", {})
        emoji = icon.get("emoji", "💡")
        color = content.get("color", "default")
        lines = text.split("\n")
        quoted = "\n".join(f"{indent}> {line}" for line in lines)
        return f"{indent}> {emoji} **Callout**\n{quoted}\n\n"
    
    elif block_type == "toggle":
        text = rich_text_to_markdown(content.get("rich_text", []))
        children = block.get("children", [])
        child_md = blocks_to_markdown(children, indent + "  ")
        return f"{indent}<details>\n{indent}<summary>{text}</summary>\n\n{child_md}{indent}</details>\n\n"
    
    elif block_type == "bookmark":
        url = content.get("url", "")
        caption = content.get("caption", [])
        cap_text = rich_text_to_markdown(caption) if caption else "Bookmark"
        return f"{indent}[{cap_text}]({url})\n\n"
    
    elif block_type == "link_to_page":
        page_type = content.get("type", "")
        page_id = content.get(page_type, "")
        return f"{indent}[Linked Page](https://www.notion.so/{page_id.replace('-', '')})\n\n"
    
    elif block_type == "table":
        return table_block_to_markdown(block, indent)
    
    elif block_type == "equation":
        expression = content.get("expression", "")
        return f"{indent}$${expression}$$\n\n"
    
    elif block_type == "column_list":
        children = block.get("children", [])
        md_parts = [f"{indent}<!-- column_list -->\n"]
        for col in children:
            if col.get("type") == "column":
                col_children = col.get("children", [])
                col_md = blocks_to_markdown(col_children, indent + "  ")
                md_parts.append(f"{indent}<!-- column -->\n{col_md}")
        md_parts.append(f"{indent}<!-- /column_list -->\n\n")
        return "".join(md_parts)
    
    elif block_type == "embed":
        url = content.get("url", "")
        return f"{indent}[Embed: {url}]({url})\n\n"
    
    elif block_type == "video":
        url = ""
        if "external" in content:
            url = content["external"].get("url", "")
        elif "file" in content:
            url = content["file"].get("url", "")
        return f"{indent}[Video: {url}]({url})\n\n"
    
    elif block_type == "file":
        url = ""
        name = "File"
        if "external" in content:
            url = content["external"].get("url", "")
        elif "file" in content:
            url = content["file"].get("url", "")
            name = content["file"].get("name", "File")
        return f"{indent}[File: {name}]({url})\n\n"
    
    elif block_type == "pdf":
        url = ""
        if "external" in content:
            url = content["external"].get("url", "")
        elif "file" in content:
            url = content["file"].get("url", "")
        return f"{indent}[PDF]({url})\n\n"
    
    elif block_type == "link_preview":
        url = content.get("url", "")
        return f"{indent}[Link Preview]({url})\n\n"
    
    elif block_type == "table_of_contents":
        return f"{indent}<!-- Table of Contents -->\n\n"
    
    elif block_type == "breadcrumb":
        return f"{indent}<!-- Breadcrumb -->\n\n"
    
    elif block_type == " synced_block":
        return f"{indent}<!-- Synced Block -->\n\n"
    
    else:
        return ""


def table_block_to_markdown(block: Dict[str, Any], indent: str = "") -> str:
    """将 Notion table 转为 Markdown 表格"""
    children = block.get("children", [])
    if not children:
        return ""
    
    rows_md = []
    for i, row_block in enumerate(children):
        if row_block.get("type") != "table_row":
            continue
        
        cells = row_block.get("table_row", {}).get("cells", [])
        cell_texts = []
        for cell in cells:
            text = rich_text_to_markdown(cell)
            text = text.replace("\n", " ")
            cell_texts.append(text)
        
        row_md = "| " + " | ".join(cell_texts) + " |"
        rows_md.append(row_md)
        
        if i == 0:
            separator = "|" + "|".join([" --- " for _ in cell_texts]) + "|"
            rows_md.append(separator)
    
    return indent + ("\n" + indent).join(rows_md) + "\n\n"


def blocks_to_markdown(blocks: List[Dict[str, Any]], indent: str = "") -> str:
    """将 Notion blocks 数组转为完整 Markdown 字符串"""
    parts = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        block_type = block.get("type", "")
        
        # 列表分组
        if block_type in ("bulleted_list_item", "numbered_list_item", "to_do"):
            list_blocks = [block]
            j = i + 1
            while j < len(blocks) and blocks[j].get("type") == block_type:
                list_blocks.append(blocks[j])
                j += 1
            for lb in list_blocks:
                parts.append(block_to_markdown(lb, indent))
            parts.append("\n")
            i = j
            continue
        
        parts.append(block_to_markdown(block, indent))
        i += 1
    
    return "".join(parts)


# ==================== Markdown → Notion Blocks ====================

def markdown_to_blocks(markdown_text: str) -> List[Dict[str, Any]]:
    """将 Markdown 字符串转为 Notion blocks 数组（使用简化解析器）"""
    return simple_markdown_to_blocks(markdown_text)


def format_inline_with_annotations(content: str) -> List[Dict[str, Any]]:
    """
    解析 Markdown 内联格式，转为 Notion rich_text 数组
    支持: **bold**, *italic*, ~~strikethrough~~, __underline__, `code`, [link](url), $math$
    """
    result = []
    if not content:
        return result
    
    # 按优先级匹配：code > bold/italic > strikethrough > underline > link > math
    pattern = (
        r'(`[^`]+`|'                           # code
        r'\*\*[^*]+\*\*|'                      # bold
        r'\*[^*]+\*|'                          # italic
        r'~~[^~]+~~|'                          # strikethrough
        r'__[^_]+__|'                          # underline
        r'\$[^$]+\$|'                          # inline math
        r'\[([^\]]+)\]\(([^)]+)\)|'            # link
        r'[^`*~_\[$]+)'                        # plain text
    )
    
    for match in re.finditer(pattern, content):
        text = match.group(0)
        
        if text.startswith('`') and text.endswith('`'):
            result.append({
                "type": "text",
                "text": {"content": text[1:-1]},
                "annotations": {"code": True}
            })
        elif text.startswith('**') and text.endswith('**'):
            result.append({
                "type": "text",
                "text": {"content": text[2:-2]},
                "annotations": {"bold": True}
            })
        elif text.startswith('*') and text.endswith('*'):
            result.append({
                "type": "text",
                "text": {"content": text[1:-1]},
                "annotations": {"italic": True}
            })
        elif text.startswith('~~') and text.endswith('~~'):
            result.append({
                "type": "text",
                "text": {"content": text[2:-2]},
                "annotations": {"strikethrough": True}
            })
        elif text.startswith('__') and text.endswith('__'):
            result.append({
                "type": "text",
                "text": {"content": text[2:-2]},
                "annotations": {"underline": True}
            })
        elif text.startswith('$') and text.endswith('$'):
            expr = text[1:-1]
            result.append({
                "type": "equation",
                "equation": {"expression": expr}
            })
        elif match.group(1) and match.group(2):
            # link [text](url)
            result.append({
                "type": "text",
                "text": {"content": match.group(1), "link": {"url": match.group(2)}}
            })
        else:
            result.append({"type": "text", "text": {"content": text}})
    
    return result if result else [{"type": "text", "text": {"content": content}}]


def simple_markdown_to_blocks(markdown_text: str) -> List[Dict[str, Any]]:
    """
    简化版 Markdown → Notion blocks
    按行解析，支持绝大多数常见场景
    """
    blocks = []
    lines = markdown_text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        if not stripped:
            i += 1
            continue
        
        # HTML 注释（跳过 column_list 等标记）
        if stripped.startswith('<!--') and stripped.endswith('-->'):
            i += 1
            continue
        
        # 代码块
        if stripped.startswith('```'):
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": '\n'.join(code_lines)}}],
                    "language": lang or "plain text"
                }
            })
            continue
        
        # 分隔线
        if stripped in ('---', '***', '___'):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue
        
        # 块级公式 $$...$$
        if stripped.startswith('$$') and stripped.endswith('$$') and len(stripped) > 4:
            expr = stripped[2:-2].strip()
            blocks.append({
                "object": "block",
                "type": "equation",
                "equation": {"expression": expr}
            })
            i += 1
            continue
        
        # 多行块级公式
        if stripped.startswith('$$'):
            expr_lines = []
            if not stripped.endswith('$$'):
                expr_lines.append(stripped[2:])
                i += 1
                while i < len(lines) and not lines[i].strip().endswith('$$'):
                    expr_lines.append(lines[i])
                    i += 1
                if i < len(lines):
                    expr_lines.append(lines[i].strip()[:-2])
                    i += 1
            else:
                expr_lines.append(stripped[2:-2])
                i += 1
            
            expr = '\n'.join(expr_lines).strip()
            if expr:
                blocks.append({
                    "object": "block",
                    "type": "equation",
                    "equation": {"expression": expr}
                })
            continue
        
        # 标题
        heading_match = re.match(r'^(#{1,3})\s+(.+)$', stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            block_type = f"heading_{level}"
            blocks.append({
                "object": "block",
                "type": block_type,
                block_type: {
                    "rich_text": format_inline_with_annotations(text)
                }
            })
            i += 1
            continue
        
        # 待办事项
        todo_match = re.match(r'^[\-*]\s*\[([ xX])\]\s+(.*)$', stripped)
        if todo_match:
            checked = todo_match.group(1).lower() == 'x'
            text = todo_match.group(2)
            blocks.append({
                "object": "block",
                "type": "to_do",
                "to_do": {
                    "rich_text": format_inline_with_annotations(text),
                    "checked": checked
                }
            })
            i += 1
            continue
        
        # 无序列表
        bullet_match = re.match(r'^[\-*]\s+(.+)$', stripped)
        if bullet_match:
            text = bullet_match.group(1)
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": format_inline_with_annotations(text)
                }
            })
            i += 1
            continue
        
        # 有序列表
        numbered_match = re.match(r'^\d+\.\s+(.+)$', stripped)
        if numbered_match:
            text = numbered_match.group(1)
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": format_inline_with_annotations(text)
                }
            })
            i += 1
            continue
        
        # 引用块（支持多行）
        if stripped.startswith('>'):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                quote_lines.append(lines[i].strip()[1:].strip())
                i += 1
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": format_inline_with_annotations(' '.join(quote_lines))
                }
            })
            continue
        
        # 图片
        img_match = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
        if img_match:
            blocks.append({
                "object": "block",
                "type": "image",
                "image": {
                    "external": {"url": img_match.group(2)},
                    "caption": format_inline_with_annotations(img_match.group(1))
                }
            })
            i += 1
            continue
        
        # 表格（简化识别：以 | 开头和结尾的行）
        if stripped.startswith('|') and stripped.endswith('|'):
            table_rows = []
            while i < len(lines) and lines[i].strip().startswith('|') and lines[i].strip().endswith('|'):
                row_text = lines[i].strip()
                # 跳过分隔行 |---|---|
                if not re.match(r'^\|[-\s|]+\|$', row_text):
                    cells = [c.strip() for c in row_text[1:-1].split('|')]
                    table_rows.append(cells)
                i += 1
            
            if table_rows:
                table_blocks = []
                for row_cells in table_rows:
                    row_block = {
                        "type": "table_row",
                        "table_row": {
                            "cells": [[{"type": "text", "text": {"content": c}}] for c in row_cells]
                        }
                    }
                    table_blocks.append(row_block)
                
                blocks.append({
                    "object": "block",
                    "type": "table",
                    "table": {
                        "table_width": len(table_rows[0]) if table_rows else 1,
                        "has_column_header": True,
                        "has_row_header": False,
                        "children": table_blocks
                    }
                })
            continue
        
        # 默认段落
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": format_inline_with_annotations(stripped)
            }
        })
        i += 1
    
    return blocks
