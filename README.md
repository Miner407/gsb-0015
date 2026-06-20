# 本地 Markdown 知识库搜索器

一个零依赖的本地 Markdown 知识库搜索引擎，使用 Python 标准库实现，支持关键词搜索、标签搜索、增量索引和跨平台中文输出。

## 功能介绍

- **增量索引**：自动识别文件变更，跳过未修改文件，支持 `--rebuild` 强制重建
- **关键词搜索**：在标题和正文中搜索，支持中英文关键词，命中片段自动高亮
- **标签搜索**：提取 Markdown 中的 `#标签`（支持中英文），按标签或列出所有标签
- **相对路径显示**：显示文件相对路径而非绝对路径，便于阅读
- **跨平台中文输出**：修复 Windows 控制台中文乱码，确保文件名、标题、标签、片段正常显示
- **可配置数据库路径**：默认存放于 `.cache/markdown_index.db`，支持 `--db` 参数自定义
- **一键清理**：`clean` 命令清理数据库和缓存目录，保持仓库干净

## 环境要求

- Python >= 3.6（仅使用标准库，无需 `pip install`）

## 安装命令

本项目零外部依赖，直接克隆或下载即可使用：

```bash
git clone <仓库地址>
cd gsb-0015
```

验证 Python 环境：

```bash
python --version
python -c "import sqlite3; print('OK')"
```

## 快速开始

### 1. 索引示例知识库

```bash
python md_search.py index sample_kb
```

输出示例：

```
发现 3 个 Markdown 文件
  索引中: machine_learning.md (5 个段落)
  索引中: python_basics.md (4 个段落)
  索引中: web_development.md (5 个段落)

索引完成! 新增/更新 3 个文件, 跳过 0 个文件
数据库位置: .cache/markdown_index.db
```

**重建索引**（删除旧库后重新索引）：

```bash
python md_search.py index sample_kb --rebuild
```

### 2. 关键词搜索

```bash
python md_search.py search 机器学习
```

**指定相对路径基准目录**：

```bash
python md_search.py search Python --base-dir sample_kb
```

### 3. 标签搜索

```bash
python md_search.py tag python
```

### 4. 列出所有标签

```bash
python md_search.py tags
```

### 5. 清理运行产物

```bash
python md_search.py clean
```

### 6. 自定义数据库路径

```bash
python md_search.py index sample_kb --db /tmp/my_index.db
python md_search.py search 算法 --db /tmp/my_index.db
```

## 索引命令

```
python md_search.py index <目录路径> [--db <数据库路径>] [--rebuild]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `directory` | 要索引的目录（递归搜索 `*.md`） | 必填 |
| `--db` | SQLite 数据库输出路径 | `.cache/markdown_index.db` |
| `--rebuild` | 删除旧数据库后重建（可选） | 关闭 |

## 关键词搜索

```
python md_search.py search <关键词> [--db <数据库路径>] [--base-dir <基准目录>]
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `keyword` | 搜索关键词（支持中英文） | 必填 |
| `--db` | 已索引的 SQLite 数据库 | `.cache/markdown_index.db` |
| `--base-dir` | 相对路径显示的基准目录 | 当前工作目录 |

搜索结果展示内容：
- **文件**：Markdown 文件名
- **路径**：相对路径（可通过 `--base-dir` 调整基准）
- **标题**：段落所属的 Markdown 标题
- **行号**：段落起止行号
- **标签**：该段落提取到的所有标签
- **命中片段**：关键词上下文 ±50 字符，**关键词自动高亮**（ANSI 黄色）

## 标签搜索

```
python md_search.py tag <标签名> [--db <数据库路径>] [--base-dir <基准目录>]
```

- 标签名不带 `#` 前缀，如输入 `python` 会匹配 `#python`
- 标签提取规则：`#([a-zA-Z0-9_\u4e00-\u9fa5]+)`，支持中英文和下划线

## 列出所有标签

```
python md_search.py tags [--db <数据库路径>]
```

输出标签及出现次数，附带可视化进度条。

## 数据库位置

默认数据库路径为 **仓库根目录下的 `.cache/markdown_index.db`**，通过以下方式可自定义：

1. **命令行参数**（推荐，临时指定）：
   ```bash
   python md_search.py index sample_kb --db ./data/my.db
   ```

2. **修改源码默认值**：编辑 `md_search.py` 中的 `get_default_db_path()` 函数。

**注意**：`.gitignore` 已配置忽略 `.cache/` 目录和所有 `*.db` 文件，默认情况下数据库不会被提交。

## 示例知识库

项目自带 `sample_kb/` 目录，包含 3 份示例文档用于验证功能：

| 文件 | 内容 | 标签 |
|------|------|------|
| `python_basics.md` | Python 基础入门（变量、函数、列表） | `#python` `#编程` `#基础` `#函数` `#教程` `#列表` `#数据结构` |
| `machine_learning.md` | 机器学习入门指南 | `#机器学习` `#AI` `#入门` `#监督学习` `#算法` `#深度学习` `#神经网络` `#框架` `#TensorFlow` `#PyTorch` |
| `web_development.md` | Web 开发技术栈 | `#前端` `#HTML` `#CSS` `#JavaScript` `#后端` `#Python` `#Node.js` `#API` `#数据库` `#MySQL` `#MongoDB` `#Redis` `#REST` `#架构` |

## 验证命令

项目提供一键验证脚本 `verify.py`，覆盖所有核心功能：

```bash
python verify.py
```

验证覆盖项：

| # | 测试项 | 说明 |
|---|--------|------|
| 1 | 清理旧产物 | 确保每次验证从干净状态开始 |
| 2 | 示例知识库索引 | 索引 sample_kb 全部 3 个文件 |
| 3 | 中文关键词搜索 | 搜索"机器学习"，验证中文搜索正常 |
| 4 | 中文关键词搜索(二) | 搜索"函数"，验证中文片段高亮 |
| 5 | 标签搜索（中文） | 搜索"#机器学习"标签 |
| 6 | 标签搜索（英文） | 搜索"#python"标签 |
| 7 | 无结果搜索 | 搜索不存在的关键词，验证空提示 |
| 8 | 列出所有标签 | 验证标签聚合功能 |
| 9 | 增量索引（未变更） | 再次索引，验证所有文件被跳过 |
| 10 | 增量索引（有变更） | 修改文件后索引，验证仅重新索引变更文件 |
| 11 | 数据库重建 | 使用 `--rebuild` 重建索引 |
| 12 | 帮助命令 | 验证 `--help` 和子命令帮助 |
| 13 | 自定义数据库路径 | 指定 `--db` 参数，验证自定义路径 |
| 14 | 根目录无数据库 | 确认仓库根目录未生成 `*.db` |
| 15 | 最终清理 | 清理所有运行产物 |

验证脚本返回码：`0` 表示全部通过，非 `0` 表示有测试失败。

## 常见问题

### Q1: Windows 控制台中文显示乱码怎么办？

A：新版本已自动处理。`md_search.py` 启动时会：
1. 调用 `sys.stdout.reconfigure(encoding="utf-8")`
2. 通过 `ctypes` 设置 Windows 控制台代码页为 65001 (UTF-8)

如仍有问题，请确保使用 Windows Terminal 或 PowerShell 7+，而非旧版 `cmd.exe`。

### Q2: 搜索无结果，但文件中确实包含关键词？

A：可能原因：
1. **未建立索引**：先运行 `python md_search.py index <目录>`
2. **关键词大小写**：搜索不区分大小写，但索引基于 LIKE 匹配
3. **数据库不一致**：尝试 `python md_search.py index <目录> --rebuild`
4. **指定了错误的 --db**：确保搜索和索引使用同一个数据库

### Q3: 标签没有被正确提取？

A：标签格式必须是 `#标签名`，其中标签名可包含：英文字母、数字、下划线、中文（`\u4e00-\u9fa5`）。

示例：
```markdown
#python          ✓
#机器学习         ✓
#数据结构_算法    ✓
#123             ✓
#python-basics   ✗ (含连字符)
```

### Q4: 想把数据库放在其他位置？

A：两种方式：
1. 每次运行加 `--db /path/to/my.db` 参数
2. 修改 `md_search.py` 顶部的 `get_default_db_path()` 函数

### Q5: 如何完全重置（删除所有运行产物）？

A：运行：
```bash
python md_search.py clean
```

或手动删除：
- `.cache/` 目录
- 所有 `*.db`、`*.db-journal`、`*.db-wal`、`*.db-shm` 文件
- 所有 `__pycache__/` 目录

### Q6: Markdown 标题识别规则？

A：匹配 `^(#{1,6})\s+(.+)$`，即 1-6 个 `#` + 空格 + 标题内容。文档开头到第一个标题之间的内容会作为"文档开头"段落，标题字段显示为 `(文档开头)`。

### Q7: 增量索引如何判断文件是否变更？

A：比较文件的 `mtime`（最后修改时间戳）。若数据库中记录的 `last_modified >=` 文件当前 `mtime`，则跳过该文件。若需强制重新索引，使用 `--rebuild` 参数。

## 命令总览

```
python md_search.py --help              查看总帮助
python md_search.py index --help        查看索引命令帮助
python md_search.py index <dir>         索引目录
python md_search.py index <dir> --rebuild  重建索引
python md_search.py search <keyword>    关键词搜索
python md_search.py tag <tagname>       标签搜索
python md_search.py tags                列出所有标签
python md_search.py clean               清理运行产物
python verify.py                        一键运行全部验证
```
