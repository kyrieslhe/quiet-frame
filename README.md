# Quiet Frame · 留影

**引用原文件路径的本地照片管理软件。** 独立桌面窗口，系统文件选择器；不打开浏览器、不复制原片、不上传云端。

[English](README.en.md) · 中文

![浅色桌面界面](docs/preview.png)
![深色桌面界面](docs/preview-dark.png)

## 启动

macOS Apple 芯片打包版包含运行环境，无需安装 Python。源码运行需要 Python 3.9+，首次安装依赖需要网络。

- **macOS 打包版**：从 Releases 下载 `quiet-frame-macos-arm64.zip`，解压后双击 **`留影.app`**；可将应用移到「应用程序」。源码版使用 `启动留影.command`，仍打开独立窗口。
- **Windows**：安装 Python（包含 Python Launcher）后双击 `start.bat`，需要系统 WebView2。
- **Linux**：运行 `sh start.sh`，需要 GTK 或 Qt 环境。Qt 可在虚拟环境安装 `PyQt5 PyQtWebEngine qtpy`。

macOS 原生窗口已经实测；Windows/Linux 启动脚本未在对应系统实测。本地应用未做 Apple 公证；若系统阻止打开，可在终端执行 `bash 启动留影.command`。

关闭窗口会停止内部服务。macOS 再次启动会聚焦已有窗口。中英文、深浅模式和缩略图大小会保留。

## 使用

1. 点击「添加照片」或按 `⌘O` / `Ctrl+O`。
2. 通过系统选择器选择照片或文件夹，可包含子文件夹。也可手动粘贴绝对路径，每行一个。
3. 在「全部照片」中添加会自动建立摄影集；选中摄影集后添加，会放入当前集。点击左侧 `＋` 可手动新建集。
4. 单击照片查看右侧参数和原文件路径，双击或按 Enter 打开大图。
5. 可编辑参数、设封面、在文件夹中显示原片，以及重新定位或移除记录。

支持 JPG、PNG、WebP、TIFF。HEIC/RAW 请先导出为 JPG。读取相机、镜头、焦距、光圈、快门、ISO、时间及 GPS；缺失信息留空，可人工填写。GPS 显示为坐标，不在线查询地名。时间按相机记录显示，不推断时区。

## 路径引用

仅保存 **原文件绝对路径、摄影集信息、可编辑参数和 JPEG 预览缓存**，不复制新导入的原片，也不把编辑信息写回原片。同一摄影集内相同路径会跳过。预览最长边 2400 像素。

- 移动、重命名原片或断开磁盘后，会显示离线；缓存预览仍可查看。
- 「重新定位文件」选择新位置，保留已编辑的参数。
- 刷新按钮重新检查文件状态；暂不实时监视文件夹、不自动发现新增照片。
- **移除照片或摄影集仅删除目录记录和预览缓存，绝不删除原文件。**

旧版记录会自动迁移为指向 `data/originals/` 中已有副本的路径引用。迁移不删除旧副本，也不猜测原来的源路径。可用「重新定位文件」指向真正原片；旧副本由你自行确认处理，应用不会自动清理。

## 数据和备份

打包版的数据保存在 `~/Library/Application Support/Quiet Frame/`；源码版保存在项目的 `data/`。其中 `archive.sqlite3` 保存摄影集、参数和路径，`previews/` 保存缓存，`window-state/` 保存界面偏好。源码版 `data/` 被 Git 忽略。两个版本使用独立目录；切换时可在退出应用后复制原有数据目录内容，旧版数据库会自动迁移。

「备份照片目录」通过系统保存对话框导出数据库 SQL、路径和预览，**不包含原片**。原片请单独备份。退出应用后复制整个 `data/` 也可备份目录。

ZIP 恢复：退出应用，解压到新目录 `restored/`，执行：

```sh
python3 -c "import sqlite3,pathlib; p=pathlib.Path('restored'); c=sqlite3.connect(p/'archive.sqlite3'); c.executescript((p/'archive.sql').read_text(encoding='utf-8')); c.close()"
```

保留原有 `data/` 备份后，把 `restored/` 改名为 `data/`。原片需保持原位置，或在应用中重新定位。只恢复可信备份。

## 界面和开发

固定三栏：摄影集目录、可调缩略图网格/列表、照片检查器。没有展示网站首页、宣传文案和示例摄影作品。支持中文/English 和深浅模式；首次跟随系统，手动选择后记住。照片不加主题滤镜。

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-desktop.txt
python desktop.py
python -m unittest discover -s tests -v
```

pywebview 提供原生窗口与系统对话框；Flask、SQLite、Pillow 处理本机目录及预览，HTML/CSS/JS 仅作为内嵌 UI。内部服务只监听回环地址，校验 Host 和写入令牌。没有网站部署或多用户功能。

`QUIET_FRAME_DATA` 指定数据目录；`PORT` 修改内部端口（默认 47321）。`python app.py` 仅用于调试界面，不自动打开浏览器；系统文件选择器只在桌面窗口提供。

测试覆盖不复制原片、EXIF/GPS、文件夹扫描、重复引用、离线与重新定位、移除不删原片、旧数据迁移、备份和本地访问保护。另验证 macOS 原生窗口、JS/Python 桥接和三栏 UI。

### 构建 macOS 应用

```sh
pip install -r requirements-build.txt
sh build-macos.sh
```

产物在 `dist/留影.app`，包含 Python 和运行依赖，不包含个人数据。当前提供的二进制是 Apple 芯片版本。

## 开源

MIT License。请勿提交个人目录、照片或含真实文件路径的截图。
