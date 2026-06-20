#!/usr/bin/env python3
import argparse
import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path


def get_default_db_path() -> str:
    cache_dir = Path(".cache")
    cache_dir.mkdir(exist_ok=True)
    return str(cache_dir / "markdown_index.db")


DB_PATH = get_default_db_path()


def setup_console_encoding():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
            sys.stdin.reconfigure(encoding="utf-8")
        except Exception:
            pass
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleCP(65001)
            kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass


def highlight_keyword(text: str, keyword: str) -> str:
    if not keyword:
        return text
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    return pattern.sub(lambda m: f"\x1b[93m{m.group(0)}\x1b[0m", text)


def get_relative_path(file_path: str, base_dir: str = None) -> str:
    try:
        if base_dir:
            return str(Path(file_path).relative_to(Path(base_dir).resolve()))
        return str(Path(file_path).relative_to(Path.cwd()))
    except ValueError:
        return file_path


def get_section_tags(section_id: int, cursor: sqlite3.Cursor) -> list:
    cursor.execute("SELECT tag FROM tags WHERE section_id = ?", (section_id,))
    return [row[0] for row in cursor.fetchall()]


def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    db_parent = Path(db_path).parent
    if db_parent and not db_parent.exists():
        db_parent.mkdir(parents=True, exist_ok=True)
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sections_heading ON sections(heading)")
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


def index_directory(directory: str, db_path: str = DB_PATH, rebuild: bool = False) -> None:
    if rebuild and os.path.exists(db_path):
        os.remove(db_path)
        print(f"已删除旧数据库: {db_path}")

    conn = init_db(db_path)
    cursor = conn.cursor()

    abs_dir = Path(directory).resolve()
    md_files = list(abs_dir.rglob("*.md"))
    print(f"发现 {len(md_files)} 个 Markdown 文件")

    indexed_count = 0
    skipped_count = 0

    for md_file in md_files:
        file_path = str(md_file.resolve())
        file_name = md_file.name
        last_modified = md_file.stat().st_mtime

        cursor.execute("SELECT id, last_modified FROM documents WHERE file_path = ?", (file_path,))
        existing = cursor.fetchone()

        if existing and existing[1] >= last_modified and not rebuild:
            rel = get_relative_path(file_path, str(abs_dir))
            print(f"  跳过 (未变更): {rel}")
            skipped_count += 1
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
        rel = get_relative_path(file_path, str(abs_dir))
        print(f"  索引中: {rel} ({len(sections)} 个段落)")
        indexed_count += 1

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
    print(f"\n索引完成! 新增/更新 {indexed_count} 个文件, 跳过 {skipped_count} 个文件")
    print(f"数据库位置: {db_path}")


def search_keyword(keyword: str, db_path: str = DB_PATH) -> list:
    conn = init_db(db_path)
    cursor = conn.cursor()

    query = """
        SELECT s.id, d.file_name, d.file_path, s.heading, s.content, s.line_start, s.line_end
        FROM sections s
        JOIN documents d ON s.document_id = d.id
        WHERE s.content LIKE ? OR s.heading LIKE ?
        ORDER BY d.file_name, s.line_start
    """
    search_pattern = f"%{keyword}%"
    cursor.execute(query, (search_pattern, search_pattern))
    raw_results = cursor.fetchall()

    results = []
    for row in raw_results:
        section_id, file_name, file_path, heading, content, line_start, line_end = row
        tags = get_section_tags(section_id, cursor)
        results.append((file_name, file_path, heading, content, line_start, line_end, tags))

    conn.close()
    return results


def get_snippet(content: str, keyword: str = None, context_chars: int = 50) -> str:
    if not keyword:
        clean = re.sub(r'\s+', ' ', content).strip()
        return clean[:120] + "..." if len(clean) > 120 else clean

    content_lower = content.lower()
    keyword_lower = keyword.lower()
    pos = content_lower.find(keyword_lower)

    if pos == -1:
        clean = re.sub(r'\s+', ' ', content).strip()
        return clean[:120] + "..." if len(clean) > 120 else clean

    start = max(0, pos - context_chars)
    end = min(len(content), pos + len(keyword) + context_chars)

    snippet = content[start:end]
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    return snippet


def display_results(results: list, keyword: str = None, base_dir: str = None) -> None:
    if not results:
        if keyword:
            print(f"\n  未找到与 \"{keyword}\" 匹配的结果。")
            print("  建议:")
            print("    - 尝试不同的关键词")
            print("    - 检查索引目录是否正确")
            print("    - 运行 index 命令重建索引\n")
        else:
            print("\n  未找到匹配的结果。\n")
        return

    label = f"关键词 \"{keyword}\"" if keyword else "查询"
    print(f"\n  找到 {len(results)} 条匹配结果 ({label}):\n")
    print("  " + "=" * 78)

    for i, row in enumerate(results, 1):
        if len(row) == 7:
            file_name, file_path, heading, content, line_start, line_end, tags = row
        else:
            file_name, file_path, heading, content, line_start, line_end = row
            tags = []

        snippet = get_snippet(content, keyword)
        if keyword:
            snippet = highlight_keyword(snippet, keyword)

        rel_path = get_relative_path(file_path, base_dir)
        tag_str = " ".join([f"#{t}" for t in tags]) if tags else "(无标签)"

        print(f"\n  [{i}] 文件   : {file_name}")
        print(f"      路径   : {rel_path}")
        print(f"      标题   : {heading if heading else '(文档开头)'}")
        print(f"      行号   : {line_start}-{line_end}")
        print(f"      标签   : {tag_str}")
        print(f"      命中片段: {snippet}")
        print()
        print("  " + "-" * 78)

    print()


def search_by_tag(tag: str, db_path: str = DB_PATH) -> list:
    conn = init_db(db_path)
    cursor = conn.cursor()

    query = """
        SELECT s.id, d.file_name, d.file_path, s.heading, s.content, s.line_start, s.line_end
        FROM tags t
        JOIN sections s ON t.section_id = s.id
        JOIN documents d ON s.document_id = d.id
        WHERE t.tag = ?
        ORDER BY d.file_name, s.line_start
    """
    cursor.execute(query, (tag,))
    raw_results = cursor.fetchall()

    results = []
    for row in raw_results:
        section_id, file_name, file_path, heading, content, line_start, line_end = row
        section_tags = get_section_tags(section_id, cursor)
        results.append((file_name, file_path, heading, content, line_start, line_end, section_tags))

    conn.close()
    return results


def list_all_tags(db_path: str = DB_PATH) -> list:
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT tag, COUNT(*) as count FROM tags GROUP BY tag ORDER BY count DESC, tag ASC")
    tags = cursor.fetchall()
    conn.close()
    return tags


def display_tags(tags: list) -> None:
    if not tags:
        print("\n  未找到任何标签。\n")
        print("  提示: 运行 index 命令索引 Markdown 文件后才能查看标签。\n")
        return

    print(f"\n  共找到 {len(tags)} 个标签:\n")
    max_tag_len = max(len(tag) for tag, _ in tags)
    for tag, count in tags:
        bar = "█" * min(count * 3, 40)
        print(f"    #{tag.ljust(max_tag_len)}  ({count:2d} 段)  {bar}")
    print()


def clean_artifacts(db_path: str = DB_PATH) -> None:
    removed = []
    if os.path.exists(db_path):
        os.remove(db_path)
        removed.append(f"  数据库: {db_path}")

    db_journal = db_path + "-journal"
    if os.path.exists(db_journal):
        os.remove(db_journal)
        removed.append(f"  事务日志: {db_journal}")

    db_wal = db_path + "-wal"
    if os.path.exists(db_wal):
        os.remove(db_wal)
        removed.append(f"  WAL 文件: {db_wal}")

    db_shm = db_path + "-shm"
    if os.path.exists(db_shm):
        os.remove(db_shm)
        removed.append(f"  SHM 文件: {db_shm}")

    pycache_dirs = list(Path(".").rglob("__pycache__"))
    for pyc in pycache_dirs:
        shutil.rmtree(pyc, ignore_errors=True)
        removed.append(f"  缓存目录: {pyc}")

    if removed:
        print("\n  已清理以下运行产物:\n")
        for item in removed:
            print(item)
        print()
    else:
        print("\n  没有需要清理的运行产物。\n")


def main():
    setup_console_encoding()

    parser = argparse.ArgumentParser(
        description="本地 Markdown 知识库搜索器 - 支持关键词搜索、标签搜索和增量索引",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s index sample_kb                    索引示例知识库
  %(prog)s index sample_kb --rebuild          重建索引
  %(prog)s search 机器学习                     关键词搜索
  %(prog)s tag python                         按标签搜索
  %(prog)s tags                               列出所有标签
  %(prog)s clean                              清理运行产物
        """
    )
    subparsers = parser.add_subparsers(dest="command")

    index_parser = subparsers.add_parser("index", help="索引指定目录下的 Markdown 文件")
    index_parser.add_argument("directory", help="要索引的目录路径")
    index_parser.add_argument("--db", default=DB_PATH, help=f"SQLite 数据库路径 (默认: {DB_PATH})")
    index_parser.add_argument("--rebuild", action="store_true", help="删除旧数据库后重建索引")

    search_parser = subparsers.add_parser("search", help="按关键词搜索")
    search_parser.add_argument("keyword", help="搜索关键词 (支持中英文)")
    search_parser.add_argument("--db", default=DB_PATH, help=f"SQLite 数据库路径 (默认: {DB_PATH})")
    search_parser.add_argument("--base-dir", default=None, help="显示相对路径时的基准目录")

    tag_parser = subparsers.add_parser("tag", help="按标签搜索")
    tag_parser.add_argument("tag", help="标签名称 (不带 # 号)")
    tag_parser.add_argument("--db", default=DB_PATH, help=f"SQLite 数据库路径 (默认: {DB_PATH})")
    tag_parser.add_argument("--base-dir", default=None, help="显示相对路径时的基准目录")

    tags_parser = subparsers.add_parser("tags", help="列出所有标签")
    tags_parser.add_argument("--db", default=DB_PATH, help=f"SQLite 数据库路径 (默认: {DB_PATH})")

    clean_parser = subparsers.add_parser("clean", help="清理运行产物 (数据库、缓存等)")
    clean_parser.add_argument("--db", default=DB_PATH, help=f"要清理的 SQLite 数据库路径 (默认: {DB_PATH})")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "index":
        if not os.path.isdir(args.directory):
            print(f"错误: 目录 '{args.directory}' 不存在")
            sys.exit(1)
        index_directory(args.directory, args.db, args.rebuild)

    elif args.command == "search":
        results = search_keyword(args.keyword, args.db)
        display_results(results, args.keyword, args.base_dir)

    elif args.command == "tag":
        results = search_by_tag(args.tag, args.db)
        display_results(results, None, args.base_dir)

    elif args.command == "tags":
        tags = list_all_tags(args.db)
        display_tags(tags)

    elif args.command == "clean":
        clean_artifacts(args.db)


if __name__ == "__main__":
    main()
