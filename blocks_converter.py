#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notion Blocks ↔ Markdown 双向转换器

支持的 Notion block 类型：
- paragraph, heading_1/2/3, bulleted_list_item, numbered_list_item
- to_do, quote, code, divider, image, callout, toggle

支持的 Markdown 元素：
- # ## ###, -, 1., - [ ] / - [x], >, ```, ---, ![alt](url), [text](url), **, *, ~~, `
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from markdown_it import MarkdownIt
from markdown_it.token import Token


# ==================== Notion Blocks → Markdown ====================

def rich_text_to_markdown(rich_texts: List[Dict[str, Any]]) -> str:
    """将 Notion rich_text 数组转为 Markdown 字符串"""
    parts = []
    for rt in rich_texts:
        text = rt.get("plain_text", "")
        if not text:
            continue
        
        annotations = rt.get("annotations", {})
        
        # 应用格式标记
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
        
        # 链接
        href = rt.get("href", "")
        if href and not href.startswith("mention:"):
            text = f"[{text}]({href})"
        
        parts.append(text)
    
    return "".join(parts)


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
        return f"{indent}- {text}\n"
    
    elif block_type == "numbered_list_item":
        text = rich_text_to_markdown(content.get("rich_text", []))
        return f"{indent}1. {text}\n"
    
    elif block_type == "to_do":
        text = rich_text_to_markdown(content.get("rich_text", []))
        checked = content.get("checked", False)
        mark = "x" if checked else " "
        return f"{indent}- [{mark}] {text}\n"
    
    elif block_type == "quote":
        text = rich_text_to_markdown(content.get("rich_text", []))
        lines = text.split("\n")
        quoted = "\n".join(f"{indent}> {line}" for line in lines)
        return f"{quoted}\n\n"
    
    elif block_type == "code":
        code_text = content.get("rich_text", [])
        code = "".join(t.get("plain_text", "") for t in code_text)
        language = content.get("language", "")
        return f"{indent}```{language}\n{code}\n```\n\n"
    
    elif block_type == "divider":
        return f"{indent}---\n\n"
    
    elif block_type == "image":
        caption = rich_text_to_markdown(content.get("caption", []))
        
        # 获取图片 URL
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
        lines = text.split("\n")
        quoted = "\n".join(f"{indent}> {line}" for line in lines)
        return f"{indent}> {emoji}\n{quoted}\n\n"
    
    elif block_type == "toggle":
        text = rich_text_to_markdown(content.get("rich_text", []))
        children = block.get("children", [])
        child_md = blocks_to_markdown(children, indent + "  ")
        return f"{indent}<details>\n{indent}<summary>{text}</summary>\n\n{child_md}{indent}</details>\n\n"
    
    elif block_type == "bookmark":
        url = content.get("url", "")
        return f"{indent}[Bookmark]({url})\n\n"
    
    elif block_type == "link_to_page":
        page_type = content.get("type", "")
        page_id = content.get(page_type, "")
        return f"{indent}[Linked Page](https://www.notion.so/{page_id.replace('-', '')})\n\n"
    
    elif block_type == "table":
        return table_block_to_markdown(block, indent)
    
    elif block_type == "equation":
        expression = content.get("expression", "")
        return f"{indent}$${expression}$$\n\n"
    
    else:
        # 不支持的 block 类型，尝试提取文本
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
            # 清理表格中的换行
            text = text.replace("\n", " ")
            cell_texts.append(text)
        
        row_md = "| " + " | ".join(cell_texts) + " |"
        rows_md.append(row_md)
        
        # 表头后添加分隔线
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
        
        # 处理列表分组（连续相同类型的列表项合并）
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
    """将 Markdown 字符串转为 Notion blocks 数组"""
    md = MarkdownIt()
    tokens = md.parse(markdown_text)
    return tokens_to_blocks(tokens)


def tokens_to_blocks(tokens: List[Token]) -> List[Dict[str, Any]]:
    """将 markdown-it tokens 转为 Notion blocks"""
    blocks = []
    i = 0
    
    while i < len(tokens):
        token = tokens[i]
        
        if token.type == "paragraph_open":
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            if inline and inline.type == "inline":
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": inline_to_rich_text(inline)
                    }
                })
            i += 3  # paragraph_open, inline, paragraph_close
            continue
        
        elif token.type == "heading_open":
            level = int(token.tag[1])  # h1 -> 1
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            if inline and inline.type == "inline":
                block_type = f"heading_{min(level, 3)}"
                blocks.append({
                    "object": "block",
                    "type": block_type,
                    block_type: {
                        "rich_text": inline_to_rich_text(inline)
                    }
                })
            i += 3
            continue
        
        elif token.type == "bullet_list_open":
            list_blocks, i = parse_list(tokens, i, list_type="bullet")
            blocks.extend(list_blocks)
            continue
        
        elif token.type == "ordered_list_open":
            list_blocks, i = parse_list(tokens, i, list_type="ordered")
            blocks.extend(list_blocks)
            continue
        
        elif token.type == "blockquote_open":
            content, i = parse_blockquote(tokens, i)
            blocks.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            })
            continue
        
        elif token.type == "fence":
            blocks.append({
                "object": "block",
                "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": token.content}}],
                    "language": token.info or "plain text"
                }
            })
        
        elif token.type == "hr":
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
        
        elif token.type == "html_block":
            # 处理 details/summary (toggle)
            if "<details>" in token.content.lower():
                toggle_text = parse_toggle_html(token.content)
                if toggle_text:
                    blocks.append({
                        "object": "block",
                        "type": "toggle",
                        "toggle": {
                            "rich_text": [{"type": "text", "text": {"content": toggle_text}}]
                        }
                    })
        
        i += 1
    
    # 如果没有解析出任何 block，添加一个默认段落
    if not blocks:
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": markdown_text.strip()}}]
            }
        })
    
    return blocks


def parse_list(tokens: List[Token], start: int, list_type: str) -> Tuple[List[Dict], int]:
    """解析列表（bullet 或 ordered）"""
    blocks = []
    i = start + 1  # skip list_open
    
    while i < len(tokens):
        token = tokens[i]
        if token.type == "bullet_list_close" or token.type == "ordered_list_close":
            i += 1
            break
        
        if token.type == "list_item_open":
            inline = None
            checkbox_state = None
            
            # 查找 inline 和 checkbox
            j = i + 1
            while j < len(tokens) and tokens[j].type != "list_item_close":
                if tokens[j].type == "inline":
                    inline = tokens[j]
                    # 检查是否包含 checkbox
                    content = inline.content.strip()
                    if content.startswith("[ ]"):
                        checkbox_state = False
                        inline.content = content[3:].strip()
                    elif content.startswith("[x]") or content.startswith("[X]"):
                        checkbox_state = True
                        inline.content = content[3:].strip()
                j += 1
            
            if inline is not None:
                if checkbox_state is not None:
                    blocks.append({
                        "object": "block",
                        "type": "to_do",
                        "to_do": {
                            "rich_text": inline_to_rich_text(inline),
                            "checked": checkbox_state
                        }
                    })
                elif list_type == "bullet":
                    blocks.append({
                        "object": "block",
                        "type": "bulleted_list_item",
                        "bulleted_list_item": {
                            "rich_text": inline_to_rich_text(inline)
                        }
                    })
                else:
                    blocks.append({
                        "object": "block",
                        "type": "numbered_list_item",
                        "numbered_list_item": {
                            "rich_text": inline_to_rich_text(inline)
                        }
                    })
            
            i = j + 1  # skip list_item_close
        else:
            i += 1
    
    return blocks, i


def parse_blockquote(tokens: List[Token], start: int) -> Tuple[str, int]:
    """解析引用块，提取文本内容"""
    lines = []
    i = start + 1  # skip blockquote_open
    
    while i < len(tokens):
        if tokens[i].type == "blockquote_close":
            i += 1
            break
        if tokens[i].type == "inline":
            lines.append(tokens[i].content)
        elif tokens[i].type == "paragraph_open":
            pass
        elif tokens[i].type == "paragraph_close":
            lines.append("\n")
        i += 1
    
    return "".join(lines).strip(), i


def parse_toggle_html(html: str) -> str:
    """从 HTML details/summary 中提取 summary 文本"""
    match = re.search(r"<summary>(.*?)</summary>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else "Toggle"


def inline_to_rich_text(inline: Token) -> List[Dict[str, Any]]:
    """将 inline token 转为 Notion rich_text 数组"""
    rich_texts = []
    
    if not hasattr(inline, 'children') or not inline.children:
        # 简单文本
        return [{"type": "text", "text": {"content": inline.content}}]
    
    for child in inline.children:
        if child.type == "text":
            rich_texts.append({"type": "text", "text": {"content": child.content}})
        
        elif child.type == "strong_open":
            # 查找对应的文本和关闭标记
            pass  # 由子 token 处理
        
        elif child.type == "code_inline":
            rich_texts.append({
                "type": "text",
                "text": {"content": child.content},
                "annotations": {"code": True}
            })
        
        elif child.type == "link_open":
            href = child.attrs.get("href", "") if hasattr(child, 'attrs') else ""
            # 查找链接文本
            link_text = ""
            for j in range(inline.children.index(child) + 1, len(inline.children)):
                if inline.children[j].type == "link_close":
                    break
                if inline.children[j].type == "text":
                    link_text += inline.children[j].content
            
            rich_texts.append({
                "type": "text",
                "text": {"content": link_text, "link": {"url": href}}
            })
        
        elif child.type in ("softbreak", "hardbreak"):
            rich_texts.append({"type": "text", "text": {"content": "\n"}})
    
    # 简化处理：如果没有解析出内容，直接返回原内容
    if not rich_texts:
        return [{"type": "text", "text": {"content": inline.content}}]
    
    return rich_texts


def format_inline_with_annotations(content: str) -> List[Dict[str, Any]]:
    """
    解析 Markdown 内联格式（**bold**, *italic*, `code`, [link](url)）
    转为 Notion rich_text 数组
    """
    result = []
    
    # 按顺序解析：先处理 code，再 bold/italic，最后 links
    # 这是一个简化版解析器
    pattern = r'(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[([^\]]+)\]\(([^)]+)\)|[^`*\[]+)'
    
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
        elif match.group(2) and match.group(3):
            # 链接 [text](url)
            result.append({
                "type": "text",
                "text": {"content": match.group(2), "link": {"url": match.group(3)}}
            })
        else:
            result.append({"type": "text", "text": {"content": text}})
    
    return result if result else [{"type": "text", "text": {"content": content}}]


def simple_markdown_to_blocks(markdown_text: str) -> List[Dict[str, Any]]:
    """
    简化版 Markdown → Notion blocks
    按行解析，适合大多数简单场景
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
        
        # 代码块
        if stripped.startswith('```'):
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip ```
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
        if stripped == '---' or stripped == '***':
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
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
        todo_match = re.match(r'^-\s*\[([ xX])\]\s+(.*)$', stripped)
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
        
        # 引用
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
