#!/usr/bin/env python3
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def setup_console_encoding():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleCP(65001)
            kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass


PASS_MARK = "[OK]"
FAIL_MARK = "[FAIL]"


PROJECT_ROOT = Path(__file__).parent.resolve()
SCRIPT = PROJECT_ROOT / "md_search.py"
SAMPLE_KB = PROJECT_ROOT / "sample_kb"
DEFAULT_DB = PROJECT_ROOT / ".cache" / "markdown_index.db"
TEST_DB = PROJECT_ROOT / ".cache" / "test_verify.db"

PASS = 0
FAIL = 0
TOTAL = 0


def run_cmd(args, capture=True, cwd=None):
    cmd = [sys.executable, str(SCRIPT)] + args
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd) if cwd else str(PROJECT_ROOT),
            env=env,
            timeout=30
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "命令执行超时 (30s)"
    except Exception as e:
        return -1, "", f"命令执行异常: {e}"


def section(title):
    global TOTAL
    TOTAL += 1
    print(f"\n{'='*78}")
    print(f"  测试 {TOTAL}: {title}")
    print(f"{'='*78}")


def check(condition, desc, stdout="", stderr=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  {PASS_MARK} PASS: {desc}")
    else:
        FAIL += 1
        print(f"  {FAIL_MARK} FAIL: {desc}")
        if stdout:
            print(f"    stdout: {stdout[:500]}")
        if stderr:
            print(f"    stderr: {stderr[:500]}")


def has_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fa5]', text))


def clean_all():
    for db_path in [DEFAULT_DB, TEST_DB]:
        if db_path.exists():
            try:
                db_path.unlink()
            except Exception:
                pass
        for suffix in ["-journal", "-wal", "-shm"]:
            f = Path(str(db_path) + suffix)
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
    cache_dir = PROJECT_ROOT / ".cache"
    if cache_dir.exists():
        for item in cache_dir.iterdir():
            if item.is_file():
                try:
                    item.unlink()
                except Exception:
                    pass
    for pycache in PROJECT_ROOT.rglob("__pycache__"):
        try:
            shutil.rmtree(pycache, ignore_errors=True)
        except Exception:
            pass
    root_dbs = list(PROJECT_ROOT.glob("*.db"))
    root_dbs += list(PROJECT_ROOT.glob("*.db-*"))
    for f in root_dbs:
        if f.is_file():
            try:
                f.unlink()
            except Exception:
                pass


def main():
    global PASS, FAIL, TOTAL

    setup_console_encoding()

    print("\n" + "#" * 78)
    print("#  本地 Markdown 知识库搜索器 - 功能验证脚本")
    print("#  项目根目录:", PROJECT_ROOT)
    print("#  Python 版本:", sys.version)
    print("#" * 78)

    if not SCRIPT.exists():
        print(f"错误: 未找到主脚本 {SCRIPT}")
        sys.exit(1)
    if not SAMPLE_KB.is_dir():
        print(f"错误: 未找到示例知识库 {SAMPLE_KB}")
        sys.exit(1)

    section("清理旧产物，确保从干净状态开始")
    clean_all()
    check(not DEFAULT_DB.exists(), "默认数据库已清除")
    check(not TEST_DB.exists(), "测试数据库已清除")
    root_db_files = list(PROJECT_ROOT.glob("*.db")) + list(PROJECT_ROOT.glob("*.db-*"))
    check(len(root_db_files) == 0, f"仓库根目录无 *.db 文件 (当前 {len(root_db_files)} 个)")

    section("示例知识库全量索引")
    rc, out, err = run_cmd(["index", "sample_kb", "--db", str(DEFAULT_DB)])
    check(rc == 0, f"index 命令返回码为 0 (实际 {rc})", out, err)
    check("发现 3 个 Markdown 文件" in out, "输出显示发现 3 个 Markdown 文件", out)
    check("索引完成" in out, "输出显示索引完成", out)
    check(DEFAULT_DB.exists(), f"数据库文件已生成: {DEFAULT_DB}")
    md_count = out.count("索引中:")
    check(md_count == 3, f"3 个文件被索引 (实际 {md_count})", out)
    check(has_chinese(out), "索引输出包含中文，编码正常", out)

    section("中文关键词搜索 - '机器学习'")
    rc, out, err = run_cmd(["search", "机器学习", "--db", str(DEFAULT_DB), "--base-dir", "sample_kb"])
    check(rc == 0, f"search 命令返回码为 0 (实际 {rc})", out, err)
    check("找到" in out and "条匹配结果" in out, "输出显示找到结果", out)
    count_match = re.search(r'找到\s+(\d+)\s+条匹配结果', out)
    result_count = int(count_match.group(1)) if count_match else 0
    check(result_count >= 2, f"至少找到 2 条匹配 (实际 {result_count})", out)
    check("机器学习" in out, "输出中包含关键词原文", out)
    check("路径" in out and ":" in out, "结果包含文件相对路径字段", out)
    check("标题" in out and ":" in out, "结果包含标题字段", out)
    check("行号" in out and ":" in out, "结果包含行号字段", out)
    check("标签" in out and ":" in out, "结果包含标签字段", out)
    check("命中片段" in out and ":" in out, "结果包含命中片段字段", out)
    check("sample_kb" in out or "路径" in out, "路径显示正常（含 sample_kb 或相对路径）", out)
    check(has_chinese(out), "搜索结果中文显示正常", out)

    section("中文关键词搜索(二) - '函数'")
    rc, out, err = run_cmd(["search", "函数", "--db", str(DEFAULT_DB), "--base-dir", "sample_kb"])
    check(rc == 0, f"search 命令返回码为 0 (实际 {rc})", out, err)
    check("找到" in out, "输出显示找到结果", out)
    count_match = re.search(r'找到\s+(\d+)\s+条匹配结果', out)
    result_count = int(count_match.group(1)) if count_match else 0
    check(result_count >= 1, f"至少找到 1 条匹配 (实际 {result_count})", out)
    check("命中片段" in out and ":" in out, "包含命中片段", out)
    check("python_basics.md" in out, "命中 python_basics.md 文件", out)

    section("标签搜索（中文） - '机器学习'")
    rc, out, err = run_cmd(["tag", "机器学习", "--db", str(DEFAULT_DB), "--base-dir", "sample_kb"])
    check(rc == 0, f"tag 命令返回码为 0 (实际 {rc})", out, err)
    check("找到" in out and "条匹配结果" in out, "输出显示找到结果", out)
    count_match = re.search(r'找到\s+(\d+)\s+条匹配结果', out)
    result_count = int(count_match.group(1)) if count_match else 0
    check(result_count >= 2, f"标签 #机器学习 至少 2 段 (实际 {result_count})", out)
    check("#机器学习" in out or ("标签" in out and ":" in out), "结果中显示标签字段", out)

    section("标签搜索（英文） - 'python'")
    rc, out, err = run_cmd(["tag", "python", "--db", str(DEFAULT_DB), "--base-dir", "sample_kb"])
    check(rc == 0, f"tag 命令返回码为 0 (实际 {rc})", out, err)
    count_match = re.search(r'找到\s+(\d+)\s+条匹配结果', out)
    result_count = int(count_match.group(1)) if count_match else 0
    check(result_count >= 2, f"标签 #python 至少 2 段 (实际 {result_count})", out)
    check("python_basics.md" in out or "web_development.md" in out, "命中含 python 标签的文档", out)

    section("无结果搜索 - 搜索不存在的关键词")
    rc, out, err = run_cmd(["search", "不存在的关键词xyz123456", "--db", str(DEFAULT_DB)])
    check(rc == 0, f"无结果搜索返回码仍为 0 (实际 {rc})", out, err)
    check("未找到" in out, "输出清晰提示未找到匹配", out)
    check("建议" in out, "输出包含改进建议", out)

    section("列出所有标签")
    rc, out, err = run_cmd(["tags", "--db", str(DEFAULT_DB)])
    check(rc == 0, f"tags 命令返回码为 0 (实际 {rc})", out, err)
    check("共找到" in out and "个标签" in out, "显示标签总数", out)
    check("#机器学习" in out, "标签列表包含 #机器学习", out)
    check("#python" in out, "标签列表包含 #python", out)
    count_match = re.search(r'共找到\s+(\d+)\s+个标签', out)
    tag_count = int(count_match.group(1)) if count_match else 0
    check(tag_count >= 15, f"标签数量 >= 15 (实际 {tag_count})", out)

    section("增量索引（未变更） - 再次运行应全部跳过")
    rc, out, err = run_cmd(["index", "sample_kb", "--db", str(DEFAULT_DB)])
    check(rc == 0, f"再次 index 返回码为 0 (实际 {rc})", out, err)
    skip_count = out.count("跳过 (未变更)")
    check(skip_count == 3, f"3 个文件全部被跳过 (实际 {skip_count})", out)
    indexed_count = out.count("索引中:")
    check(indexed_count == 0, f"0 个文件被重新索引 (实际 {indexed_count})", out)

    section("增量索引（有变更） - 修改文件后仅重索引变更文件")
    test_file = SAMPLE_KB / "python_basics.md"
    original_mtime = test_file.stat().st_mtime
    test_content = test_file.read_text(encoding="utf-8")
    appended = False
    try:
        with open(test_file, "a", encoding="utf-8") as f:
            f.write("\n\n## 临时测试段落\n\n这是一段用于测试增量索引的临时文本。\n\n#测试 #临时\n")
        os.utime(test_file, None)
        rc, out, err = run_cmd(["index", "sample_kb", "--db", str(DEFAULT_DB)])
        check(rc == 0, f"变更后 index 返回码为 0 (实际 {rc})", out, err)
        indexed_count = out.count("索引中:")
        check(indexed_count == 1, f"仅 1 个文件被重新索引 (实际 {indexed_count})", out)
        skip_count = out.count("跳过 (未变更)")
        check(skip_count == 2, f"2 个未变更文件被跳过 (实际 {skip_count})", out)
        rc2, out2, err2 = run_cmd(["search", "临时测试段落", "--db", str(DEFAULT_DB)])
        check("找到" in out2 and "条匹配结果" in out2, "搜索新增内容能找到结果", out2)
        appended = True
    finally:
        if appended:
            test_file.write_text(test_content, encoding="utf-8")
            try:
                os.utime(test_file, (original_mtime, original_mtime))
            except Exception:
                pass

    section("数据库重建 --rebuild")
    rc, out, err = run_cmd(["index", "sample_kb", "--db", str(DEFAULT_DB), "--rebuild"])
    check(rc == 0, f"rebuild 返回码为 0 (实际 {rc})", out, err)
    check("删除旧数据库" in out or "已删除旧数据库" in out, "输出提示删除旧数据库", out)
    indexed_count = out.count("索引中:")
    check(indexed_count == 3, f"rebuild 模式下 3 个文件全部被索引 (实际 {indexed_count})", out)

    section("帮助命令 --help")
    rc, out, err = run_cmd(["--help"])
    check(rc == 0, f"主 --help 返回码为 0 (实际 {rc})", out, err)
    check("本地 Markdown 知识库搜索器" in out, "帮助信息包含项目描述", out)
    check("index" in out, "帮助信息列出 index 子命令", out)
    check("search" in out, "帮助信息列出 search 子命令", out)
    check("tag" in out, "帮助信息列出 tag 子命令", out)
    check("tags" in out, "帮助信息列出 tags 子命令", out)
    check("clean" in out, "帮助信息列出 clean 子命令", out)

    rc2, out2, err2 = run_cmd(["index", "--help"])
    check(rc2 == 0, f"index --help 返回码为 0 (实际 {rc2})", out2, err2)
    check("--rebuild" in out2, "index 帮助包含 --rebuild 参数说明", out2)
    check("--db" in out2, "index 帮助包含 --db 参数说明", out2)

    section("自定义数据库路径 --db")
    custom_db = PROJECT_ROOT / ".cache" / "custom_test.db"
    if custom_db.exists():
        try:
            custom_db.unlink()
        except Exception:
            pass
    rc, out, err = run_cmd(["index", "sample_kb", "--db", str(custom_db)])
    check(rc == 0, f"自定义 db 索引返回码为 0 (实际 {rc})", out, err)
    check(custom_db.exists(), f"自定义数据库文件已创建: {custom_db}")
    rc2, out2, err2 = run_cmd(["search", "算法", "--db", str(custom_db)])
    check(rc2 == 0, f"自定义 db 搜索返回码为 0 (实际 {rc2})", out2, err2)
    check("找到" in out2 and "条匹配结果" in out2, "自定义数据库中能搜索到内容", out2)
    try:
        if custom_db.exists():
            custom_db.unlink()
        for s in ["-journal", "-wal", "-shm"]:
            f = Path(str(custom_db) + s)
            if f.exists():
                f.unlink()
    except Exception:
        pass

    section("确认仓库根目录无运行生成的数据库文件")
    root_db_files = list(PROJECT_ROOT.glob("*.db")) + list(PROJECT_ROOT.glob("*.db-*"))
    check(len(root_db_files) == 0, f"仓库根目录无 *.db 文件 (当前 {len(root_db_files)} 个: {[str(f.name) for f in root_db_files]})")
    sample_db_files = list(SAMPLE_KB.glob("*.db"))
    check(len(sample_db_files) == 0, f"sample_kb 目录无 *.db 文件")

    section("最终清理 - 还原干净状态")
    rc, out, err = run_cmd(["clean", "--db", str(DEFAULT_DB)])
    check(rc == 0, f"clean 命令返回码为 0 (实际 {rc})", out, err)
    check("已清理" in out or "没有需要清理" in out, "clean 命令执行成功", out)
    clean_all()
    check(not DEFAULT_DB.exists(), "clean 后默认数据库被删除")
    root_db_files = list(PROJECT_ROOT.glob("*.db")) + list(PROJECT_ROOT.glob("*.db-*"))
    check(len(root_db_files) == 0, "最终清理后根目录无 *.db 文件")

    print("\n" + "=" * 78)
    print(f"  验证完成: 通过 {PASS}/{TOTAL}, 失败 {FAIL}/{TOTAL}")
    print("=" * 78)

    if FAIL > 0:
        print("\n  [X] 存在失败的测试项，请检查上方日志。")
        sys.exit(1)
    else:
        print("\n  [*] 全部测试通过！")
        sys.exit(0)


if __name__ == "__main__":
    main()
