import os
import subprocess
import sys
import time
from PySide6.QtCore import Signal, QThread
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QLineEdit, QFileDialog, QTextEdit, QGroupBox, QFormLayout, QSpinBox, QScrollArea, QListWidget, QMessageBox


# 获取资源文件路径
def get_path(relative_path):
    if getattr(sys, 'frozen', False): base_path = sys._MEIPASS # 打包后的环境：Nuitka 会将资源解压到临时目录 sys._MEIPASS
    else: base_path = os.path.dirname(os.path.abspath(__file__))  # 开发环境：使用当前文件的相对路径
    return os.path.join(base_path, relative_path)


# 打包线程类，用于在后台执行打包命令，避免UI卡顿
class PackagerThread(QThread):
    # 定义信号，用于向主线程发送输出信息
    output_signal = Signal(str)

    def __init__(self, command):
        super().__init__()
        self.command = command  # 要执行的打包命令

    def run(self):
        try:
            # 启动子进程执行打包命令
            process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,  # 捕获标准输出
                stderr=subprocess.STDOUT,  # 将错误输出合并到标准输出
                text=True,  # 以文本模式处理输出
                shell=True  # 使用shell执行命令
            )

            # 实时读取子进程输出并发送信号
            while process.poll() is None:  # 进程未结束时
                output = process.stdout.readline()  # 读取一行输出
                if output: self.output_signal.emit(output)  # 发送输出信息

            # 读取剩余输出
            remaining_output = process.stdout.read()
            if remaining_output: self.output_signal.emit(remaining_output)

            # 发送打包完成信息
            self.output_signal.emit(f"\n✅ 打包完成，返回代码: {process.returncode}")
        except Exception as e: self.output_signal.emit(f"❌ 错误: {str(e)}")


# Nuitka打包工具主窗口类
class NuitkaPackager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.packager_thread = None  # 打包线程实例
        self.setWindowTitle("✨ PyPacky 打包工具")  # 窗口标题
        self.setGeometry(100, 100, 950, 750)  # 窗口位置和大小
        self.setWindowIcon(QIcon(get_path("./src/static/logo.ico")))

        # 启用拖拽功能
        self.setAcceptDrops(True)

        # 初始化路径变量
        self.main_file_path = ""  # 主Python文件路径
        self.icon_file_path = ""  # 图标文件路径
        self.folder_paths = []  # 需要打包的文件夹列表

        # 插件映射表（中文名称 -> 参数和提示信息）
        self.plugin_map = {
            "减少体积": {"param": "anti-bloat", "tip": "移除不必要的标准库和依赖，减少可执行文件体积"},
            "Tkinter 支持": {"param": "tk-inter", "tip": "启用 Tkinter 插件支持"},
            "PySide6 支持": {"param": "pyside6", "tip": "启用 PySide6 插件支持"},
            "PyQt6 支持": {"param": "pyqt6", "tip": "启用 PyQt6 插件支持"},
            "Numpy 支持": {"param": "numpy", "tip": "为 Numpy 提供优化的打包支持"},
            "Pandas 支持": {"param": "pandas", "tip": "为 Pandas 提供优化的打包支持"},
            "Matplotlib 支持": {"param": "matplotlib", "tip": "为 Matplotlib 提供优化的打包支持"},
            "Django 支持": {"param": "django", "tip": "为 Django Web 框架提供插件支持"},
            "Multiprocessing 支持": {"param": "multiprocessing", "tip": "支持多进程相关模块"},
        }

        # 打包模式映射表
        self.mode_map = {
            "独立运行": {"param": "--standalone", "tip": "独立运行模式，打包所有依赖到输出目录"},
            "exe文件": {"param": "--onefile", "tip": "生成单文件 exe，启动时会自动解压"},
            "移除中间文件": {"param": "--remove-output", "tip": "打包完成后自动清理中间生成目录"},
            "禁用控制台": {"param": "--windows-disable-console", "tip": "禁用控制台窗口（GUI 程序推荐开启）"},
        }

        # Python 标志映射表
        self.python_flag_map = {
            "禁用断言": {"param": "--python-flag=no_asserts", "tip": "移除 assert 语句，优化运行速度"},
            "静态哈希": {"param": "--python-flag=static_hashes", "tip": "使用静态哈希，确保哈希值一致"},
        }

        # 排除设置映射表
        self.exclude_map = {
            "排除 setuptools": {"param": "--noinclude-setuptools-mode=error", "tip": "排除 setuptools，避免无用依赖"},
            "排除 pydoc": {"param": "--noinclude-pydoc-mode=warning", "tip": "排除 pydoc，减少体积"},
            "排除 IPython": {"param": "--noinclude-IPython-mode=error", "tip": "排除 IPython，避免额外依赖"},
        }

        # 设置全局字体（支持中文显示）
        app_font = QFont("Microsoft YaHei", 10)
        self.setFont(app_font)

        # 创建中心窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)  # 主布局
        main_layout.setContentsMargins(12, 12, 12, 12)  # 边距设置

        # 创建滚动区域（用于容纳较多设置项）
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)  # 滚动区域大小自适应
        scroll_content = QWidget()  # 滚动区域内容部件
        scroll_layout = QVBoxLayout(scroll_content)  # 滚动区域布局
        scroll_layout.setSpacing(15)  # 控件间距
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        # 1. 基本设置区域
        input_group = self.create_group("⚙️ 基本设置")  # 创建分组框
        input_layout = QFormLayout()  # 表单布局

        # 添加文件输入框和浏览按钮
        self.main_file_edit, main_btn = self.add_file_input("主Python文件:", self.select_main_file)
        self.icon_file_edit, icon_btn = self.add_file_input("图标文件 (.ico):", self.select_icon_file)
        self.output_name_edit = QLineEdit("app.exe")  # 输出文件名输入框
        self.temp_dir_edit = QLineEdit()  # 临时目录输入框

        # 自动生成临时目录按钮
        gen_temp_btn = QPushButton("自动生成")
        gen_temp_btn.clicked.connect(self.generate_temp_dir)

        # 添加到表单布局
        input_layout.addRow("主文件:", self.wrap_hbox([self.main_file_edit, main_btn]))
        input_layout.addRow("图标:", self.wrap_hbox([self.icon_file_edit, icon_btn]))
        input_layout.addRow("输出文件名:", self.output_name_edit)
        input_layout.addRow("临时目录:", self.wrap_hbox([self.temp_dir_edit, gen_temp_btn]))

        input_group.setLayout(input_layout)
        scroll_layout.addWidget(input_group)

        # 2. 插件设置区域
        self.plugin_checks = self.create_check_group("🔌 启用插件", [
            ("减少体积", True),
            ("Tkinter 支持", False),
            ("PySide6 支持", False),
            ("PyQt6 支持", False),
            ("Numpy 支持", False),
            ("Pandas 支持", False),
            ("Matplotlib 支持", False),
            ("Django 支持", False),
            ("Multiprocessing 支持", False),
        ], self.plugin_map)
        scroll_layout.addWidget(self.plugin_checks)

        # 3. 打包模式设置区域
        self.mode_checks = self.create_check_group("📦 打包模式", [
            ("独立运行", True),
            ("exe文件", True),
            ("移除中间文件", False),
            ("禁用控制台", False),
        ], self.mode_map)
        scroll_layout.addWidget(self.mode_checks)

        # 4. 文件夹打包设置区域
        folder_group = self.create_group("📂 打包文件夹")
        folder_layout = QVBoxLayout()
        self.folder_list = QListWidget()  # 文件夹列表显示
        add_folder_btn = QPushButton("➕ 添加文件夹")
        remove_folder_btn = QPushButton("🗑️ 移除选中")
        add_folder_btn.clicked.connect(self.add_folder)  # 绑定添加文件夹事件
        remove_folder_btn.clicked.connect(self.remove_folder)  # 绑定移除文件夹事件

        folder_layout.addWidget(self.folder_list)
        folder_layout.addWidget(add_folder_btn)
        folder_layout.addWidget(remove_folder_btn)
        folder_group.setLayout(folder_layout)
        scroll_layout.addWidget(folder_group)

        # 5. 编译选项设置区域
        compile_group = self.create_group("🛠️ 编译选项")
        compile_layout = QFormLayout()
        self.use_mingw = QCheckBox("使用Mingw编译器")  # Mingw编译器选项
        self.use_mingw.setChecked(False)
        self.use_lto = QCheckBox("启用LTO (链接时优化)")  # LTO优化选项
        self.use_lto.setChecked(True)
        self.jobs_spin = QSpinBox()  # 并行任务数
        self.jobs_spin.setRange(1, os.cpu_count() or 4)  # 范围设置
        self.jobs_spin.setValue(min(12, os.cpu_count() or 4))  # 默认值

        compile_layout.addRow(self.use_mingw)
        compile_layout.addRow(self.use_lto)
        compile_layout.addRow("并行任务数:", self.jobs_spin)
        compile_group.setLayout(compile_layout)
        scroll_layout.addWidget(compile_group)

        # 6. Python 标志设置区域
        self.python_checks = self.create_check_group("🐍 Python 标志", [
            ("禁用断言", False),
            ("静态哈希", False),
        ], self.python_flag_map)
        scroll_layout.addWidget(self.python_checks)

        # 7. 排除设置区域
        self.exclude_checks = self.create_check_group("🚫 排除设置", [
            ("排除 setuptools", False),
            ("排除 pydoc", False),
            ("排除 IPython", False),
        ], self.exclude_map)
        scroll_layout.addWidget(self.exclude_checks)

        # 添加伸缩项，将上方控件顶起
        scroll_layout.addStretch()

        # 操作按钮区域
        btn_layout = QHBoxLayout()
        self.generate_btn = QPushButton("⚡ 生成命令")  # 生成打包命令按钮
        self.run_btn = QPushButton("🚀 执行打包")  # 执行打包按钮
        btn_layout.addStretch()
        btn_layout.addWidget(self.generate_btn)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        # 绑定按钮事件
        self.generate_btn.clicked.connect(self.generate_command)
        self.run_btn.clicked.connect(self.run_packaging)

        # 日志显示区域
        log_group = self.create_group("📝 打包日志")
        log_layout = QVBoxLayout()
        self.log_edit = QTextEdit()  # 日志文本框
        self.log_edit.setReadOnly(True)  # 只读
        self.log_edit.setFont(QFont("Consolas", 10))  # 使用等宽字体
        self.log_edit.setStyleSheet("background-color: #1e1e1e; color: #dcdcdc; padding: 6px;")  # 深色主题
        log_layout.addWidget(self.log_edit)
        log_group.setLayout(log_layout)
        log_group.setMinimumHeight(220)  # 最小高度
        main_layout.addWidget(log_group)

    # ---------------- 工具函数 ---------------- #
    @staticmethod
    def create_group(title):
        """创建带标题的分组框"""
        group = QGroupBox(title)
        group.setStyleSheet("QGroupBox { font-weight: bold; }")  # 加粗标题
        return group

    @staticmethod
    def wrap_hbox(widgets):
        """将多个控件包装到水平布局中"""
        box = QHBoxLayout()
        for w in widgets: box.addWidget(w)
        box.setContentsMargins(0, 0, 0, 0)  # 去除边距
        container = QWidget()
        container.setLayout(box)
        return container

    @staticmethod
    def add_file_input(label, callback):
        """创建文件输入框和浏览按钮组合"""
        line_edit = QLineEdit()
        line_edit.setToolTip(label)  # 提示信息
        btn = QPushButton("浏览...")
        btn.clicked.connect(callback)  # 绑定浏览事件
        return line_edit, btn

    def create_check_group(self, title, items, mapping):
        """创建带复选框的分组框"""
        group = self.create_group(title)
        layout = QVBoxLayout()
        for entry in items:
            text, checked = entry  # 文本和默认选中状态
            cb = QCheckBox(text)
            cb.setChecked(checked)
            # 设置提示信息
            if text in mapping and "tip" in mapping[text]: cb.setToolTip(mapping[text]["tip"])
            layout.addWidget(cb)
        group.setLayout(layout)
        return group

    # ---------------- 文件夹打包相关方法 ---------------- #
    def add_folder(self):
        """添加文件夹到打包列表"""
        path = QFileDialog.getExistingDirectory(self, "选择要打包的文件夹")
        if path:
            if path not in self.folder_paths:  # 避免重复添加
                self.folder_paths.append(path)
                self.folder_list.addItem(path)
            else: QMessageBox.information(self, "提示", "该文件夹已添加")

    def remove_folder(self):
        """从打包列表移除选中的文件夹"""
        selected = self.folder_list.currentRow()  # 获取选中行索引
        if selected >= 0:
            item = self.folder_list.takeItem(selected)  # 移除列表项
            self.folder_paths.remove(item.text())  # 从路径列表移除

    # ---------------- 临时目录自动生成 ---------------- #
    def generate_temp_dir(self):
        """自动生成临时目录路径"""
        if not self.main_file_edit.text().strip():
            QMessageBox.warning(self, "提示", "请先选择主文件")
            return

        # 提取主文件名（不含扩展名）
        base_name = os.path.splitext(os.path.basename(self.main_file_edit.text().strip()))[0]
        timestamp = time.strftime("%Y%m%d_%H%M%S")  # 时间戳
        new_dir = f"{{TEMP}}/{timestamp}_{base_name}"  # 组合路径
        self.temp_dir_edit.setText(new_dir)

    # ---------------- 拖拽支持相关方法 ---------------- #
    def dragEnterEvent(self, event):
        """拖拽进入事件处理"""
        if event.mimeData().hasUrls():  # 有URL（文件路径）时接受拖拽
            event.acceptProposedAction()

    def dropEvent(self, event):
        """拖拽释放事件处理"""
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()  # 转换为本地文件路径
            # 根据文件类型处理
            if file_path.endswith(".py"):  # Python文件
                self.main_file_path = file_path
                self.main_file_edit.setText(file_path)
                self.log_edit.append(f"📂 已拖入主文件: {file_path}")
            elif file_path.endswith(".ico"):  # 图标文件
                self.icon_file_path = file_path
                self.icon_file_edit.setText(file_path)
                self.log_edit.append(f"🎨 已拖入图标文件: {file_path}")

    # ---------------- Nuitka 检查与安装 ---------------- #
    def check_and_install_nuitka(self):
        """检查Nuitka是否安装，未安装则自动安装"""
        try:
            # 检查是否已安装Nuitka
            subprocess.check_output("nuitka --version", shell=True)
            return True
        except Exception as e:
            self.log_edit.append("⚠️ 未检测到 Nuitka，正在自动安装...")
            try:
                # 安装Nuitka及其依赖
                subprocess.check_call(["python", "-m", "pip", "install", "nuitka", "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"], shell=False)
                self.log_edit.append("✅ Nuitka 安装完成")
                return True
            except Exception as e:
                self.log_edit.append(f"❌ 安装 Nuitka 失败: {e}")
                return False

    # ---------------- 事件处理方法 ---------------- #
    def select_main_file(self):
        """选择主Python文件"""
        path, _ = QFileDialog.getOpenFileName(self, "选择主Python文件", "", "Python Files (*.py)")
        if path:
            self.main_file_path = path
            self.main_file_edit.setText(path)

    def select_icon_file(self):
        """选择图标文件"""
        path, _ = QFileDialog.getOpenFileName(self, "选择图标文件", "", "Icon Files (*.ico)")
        if path:
            self.icon_file_path = path
            self.icon_file_edit.setText(path)

    def generate_command(self):
        """生成Nuitka打包命令"""
        if not self.main_file_edit.text().strip():  # 检查主文件是否已选择
            self.log_edit.append("⚠️ 请先选择主Python文件")
            return None

        command = ["nuitka"]  # 命令起始部分

        # 添加插件参数
        for cb in self.plugin_checks.findChildren(QCheckBox):
            if cb.isChecked() and cb.text() in self.plugin_map:
                command.append(f"--enable-plugin={self.plugin_map[cb.text()]['param']}")

        # 添加打包模式参数
        for cb in self.mode_checks.findChildren(QCheckBox):
            if cb.isChecked() and cb.text() in self.mode_map:
                command.append(self.mode_map[cb.text()]["param"])

        # 添加图标参数
        if self.icon_file_path: command.append(f"--windows-icon-from-ico={self.icon_file_path}")

        # 添加文件夹打包参数
        for folder in self.folder_paths: command.append(f'--include-data-dir="{folder}={os.path.basename(folder)}"')

        # 添加编译选项参数
        if self.use_mingw.isChecked(): command.append("--mingw64")  # 使用Mingw编译器
        if self.use_lto.isChecked(): command.append("--lto=yes")  # 启用LTO优化
        command.append(f"--jobs={self.jobs_spin.value()}")  # 并行任务数

        # 添加Python标志参数
        for cb in self.python_checks.findChildren(QCheckBox):
            if cb.isChecked() and cb.text() in self.python_flag_map:
                command.append(self.python_flag_map[cb.text()]["param"])

        # 添加排除设置参数
        for cb in self.exclude_checks.findChildren(QCheckBox):
            if cb.isChecked() and cb.text() in self.exclude_map:
                command.append(self.exclude_map[cb.text()]["param"])

        # 添加输出目录参数
        temp_dir = self.temp_dir_edit.text().strip()
        if temp_dir: command.append(f'--onefile-tempdir-spec="{temp_dir}"')

        # 添加输出文件名参数
        output_name = self.output_name_edit.text().strip()
        if output_name: command.append(f"--output-filename={output_name}")

        # 添加主文件路径
        command.append(f'"{self.main_file_edit.text().strip()}"')

        # 组合命令字符串
        command_str = " ".join(command)
        self.log_edit.clear()
        self.log_edit.append("✨ 生成的打包命令:\n")
        self.log_edit.append(command_str)
        return command_str

    def run_packaging(self):
        """执行打包操作"""
        # 检查并安装Nuitka
        if not self.check_and_install_nuitka():
            QMessageBox.critical(self, "错误", "Nuitka 未安装且安装失败")
            return

        # 生成打包命令
        command_str = self.generate_command()
        if not command_str:
            return

        # 开始打包
        self.log_edit.append("\n🚀 开始打包...\n")
        self.run_btn.setEnabled(False)  # 禁用打包按钮
        self.generate_btn.setEnabled(False)  # 禁用生成命令按钮

        # 创建并启动打包线程
        self.packager_thread = PackagerThread(command_str)
        self.packager_thread.output_signal.connect(self.update_log)  # 绑定输出信号
        self.packager_thread.finished.connect(self.packaging_finished)  # 绑定完成信号
        self.packager_thread.start()

    def update_log(self, text):
        """更新日志显示"""
        self.log_edit.append(text.strip())
        self.log_edit.moveCursor(self.log_edit.textCursor().End)  # 滚动到末尾

    def packaging_finished(self):
        """打包完成后的处理"""
        self.log_edit.append("\n🎉 打包流程结束")
        self.run_btn.setEnabled(True)  # 恢复按钮状态
        self.generate_btn.setEnabled(True)


# 程序入口
if __name__ == "__main__":
    app = QApplication(sys.argv)  # 创建应用实例
    window = NuitkaPackager()  # 创建主窗口
    window.show()  # 显示窗口
    sys.exit(app.exec())  # 进入事件循环
