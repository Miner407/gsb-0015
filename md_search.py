#!/usr/bin/env python3
import argparse
import os
import re
import sqlite3
import sys
from pathlib import Path


DB_PATH = "markdown_index.db"


def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            file_name TEXT NOT NULL,
            last_modified REAL NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            heading TEXT,
            content TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            FOREIGN KEY (section_id) REFERENCES sections(id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sections_content ON sections(content)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag)")
    conn.commit()
    return conn


def extract_tags(text: str) -> list:
    tag_pattern = r'#([a-zA-Z0-9_\u4e00-\u9fa5]+)'
    return re.findall(tag_pattern, text)


def parse_markdown(file_path: str) -> list:
    sections = []
    current_heading = None
    current_content = []
    current_line_start = 1

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    for line_num, line in enumerate(lines, 1):
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading_match:
            if current_content:
                sections.append({
                    'heading': current_heading,
                    'content': ''.join(current_content).strip(),
                    'line_start': current_line_start,
                    'line_end': line_num - 1
                })
            current_heading = heading_match.group(2).strip()
            current_content = []
            current_line_start = line_num
        else:
            current_content.append(line)

    if current_content:
        sections.append({
            'heading': current_heading,
            'content': ''.join(current_content).strip(),
            'line_start': current_line_start,
            'line_end': len(lines)
        })

    return sections


def index_directory(directory: str, db_path: str = DB_PATH) -> None:
    conn = init_db(db_path)
    cursor = conn.cursor()

    md_files = list(Path(directory).rglob("*.md"))
    print(f"Found {len(md_files)} markdown files")

    for md_file in md_files:
        file_path = str(md_file.resolve())
        file_name = md_file.name
        last_modified = md_file.stat().st_mtime

        cursor.execute("SELECT id, last_modified FROM documents WHERE file_path = ?", (file_path,))
        existing = cursor.fetchone()

        if existing and existing[1] >= last_modified:
            print(f"Skipping unchanged: {file_name}")
            continue

        if existing:
            doc_id = existing[0]
            cursor.execute("DELETE FROM tags WHERE section_id IN (SELECT id FROM sections WHERE document_id = ?)", (doc_id,))
            cursor.execute("DELETE FROM sections WHERE document_id = ?", (doc_id,))
            cursor.execute("UPDATE documents SET last_modified = ? WHERE id = ?", (last_modified, doc_id))
        else:
            cursor.execute(
                "INSERT INTO documents (file_path, file_name, last_modified) VALUES (?, ?, ?)",
                (file_path, file_name, last_modified)
            )
            doc_id = cursor.lastrowid

        sections = parse_markdown(file_path)
        print(f"Indexing: {file_name} ({len(sections)} sections)")

        for section in sections:
            cursor.execute(
                "INSERT INTO sections (document_id, heading, content, line_start, line_end) VALUES (?, ?, ?, ?, ?)",
                (doc_id, section['heading'], section['content'], section['line_start'], section['line_end'])
            )
            section_id = cursor.lastrowid

            tags = extract_tags(section['content'])
            if section['heading']:
                tags.extend(extract_tags(section['heading']))
            tags = list(set(tags))

            for tag in tags:
                cursor.execute("INSERT INTO tags (section_id, tag) VALUES (?, ?)", (section_id, tag))

    conn.commit()
    conn.close()
    print("Indexing complete!")


def search_keyword(keyword: str, db_path: str = DB_PATH) -> list:
    conn = init_db(db_path)
    cursor = conn.cursor()

    query = """
        SELECT d.file_name, d.file_path, s.heading, s.content, s.line_start, s.line_end
        FROM sections s
        JOIN documents d ON s.document_id = d.id
        WHERE s.content LIKE ? OR s.heading LIKE ?
        ORDER BY d.file_name, s.line_start
    """
    search_pattern = f"%{keyword}%"
    cursor.execute(query, (search_pattern, search_pattern))
    results = cursor.fetchall()
    conn.close()
    return results


def get_snippet(content: str, keyword: str, context_chars: int = 50) -> str:
    content_lower = content.lower()
    keyword_lower = keyword.lower()
    pos = content_lower.find(keyword_lower)

    if pos == -1:
        return content[:100] + "..." if len(content) > 100 else content

    start = max(0, pos - context_chars)
    end = min(len(content), pos + len(keyword) + context_chars)

    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    return snippet


def display_results(results: list, keyword: str) -> None:
    if not results:
        print(f"No results found for keyword: '{keyword}'")
        return

    print(f"\nFound {len(results)} result(s) for keyword: '{keyword}'\n")
    print("=" * 80)

    for i, (file_name, file_path, heading, content, line_start, line_end) in enumerate(results, 1):
        snippet = get_snippet(content, keyword)
        snippet = snippet.replace(keyword, f"\033[93m{keyword}\033[0m")

        print(f"\n[{i}] 文件: {file_name}")
        print(f"    路径: {file_path}")
        print(f"    标题: {heading if heading else '(无标题)'}")
        print(f"    行号: {line_start}-{line_end}")
        print(f"    片段: {snippet}")
        print()
        print("-" * 80)


def search_by_tag(tag: str, db_path: str = DB_PATH) -> list:
    conn = init_db(db_path)
    cursor = conn.cursor()

    query = """
        SELECT d.file_name, d.file_path, s.heading, s.content, s.line_start, s.line_end
        FROM tags t
        JOIN sections s ON t.section_id = s.id
        JOIN documents d ON s.document_id = d.id
        WHERE t.tag = ?
        ORDER BY d.file_name, s.line_start
    """
    cursor.execute(query, (tag,))
    results = cursor.fetchall()
    conn.close()
    return results


def list_all_tags(db_path: str = DB_PATH) -> list:
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tag, COUNT(*) as count FROM tags GROUP BY tag ORDER BY count DESC")
    tags = cursor.fetchall()
    conn.close()
    return tags


def main():
    parser = argparse.ArgumentParser(description="本地 Markdown 知识库搜索器")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="索引指定目录下的 Markdown 文件")
    index_parser.add_argument("directory", help="要索引的目录路径")
    index_parser.add_argument("--db", default=DB_PATH, help="SQLite 数据库路径")

    search_parser = subparsers.add_parser("search", help="按关键词搜索")
    search_parser.add_argument("keyword", help="搜索关键词")
    search_parser.add_argument("--db", default=DB_PATH, help="SQLite 数据库路径")

    tag_parser = subparsers.add_parser("tag", help="按标签搜索")
    tag_parser.add_argument("tag", help="标签名称（不带 # 号）")
    tag_parser.add_argument("--db", default=DB_PATH, help="SQLite 数据库路径")

    tags_parser = subparsers.add_parser("tags", help="列出所有标签")
    tags_parser.add_argument("--db", default=DB_PATH, help="SQLite 数据库路径")

    args = parser.parse_args()

    if args.command == "index":
        if not os.path.isdir(args.directory):
            print(f"错误: 目录 '{args.directory}' 不存在")
            sys.exit(1)
        index_directory(args.directory, args.db)

    elif args.command == "search":
        results = search_keyword(args.keyword, args.db)
        display_results(results, args.keyword)

    elif args.command == "tag":
        results = search_by_tag(args.tag, args.db)
        display_results(results, args.tag)

    elif args.command == "tags":
        tags = list_all_tags(args.db)
        if not tags:
            print("No tags found")
        else:
            print("\n所有标签:\n")
            for tag, count in tags:
                print(f"  #{tag} ({count} 次)")
            print()


if __name__ == "__main__":
    main()
