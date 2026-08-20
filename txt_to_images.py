import os
import re
import math
import shutil
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont

# 防止打印非常用字符（如 emoji）时在 GBK 控制台下崩溃
try:
    sys.stdout.reconfigure(errors='replace')
    sys.stderr.reconfigure(errors='replace')
except Exception:
    pass

# 全局默认配置
# 页面边距设置
margin_left = 5
margin_right = 5
margin_top = 26
margin_bottom = 40
# 图片分辨率设置
default_width = 240
default_height = 320
# 文件夹结构设置
default_max_folders_per_level = 10  # 每层最大文件夹数量
default_chapters_per_folder = 100   # 每个底层文件夹包含的章节数
# 字体设置
default_font_size = 12


# 章节标题前缀（"第X章/序章/楔子…"部分），用于识别章节标题及从标题中剥离前缀
# 负向前瞻用于排除正文误判：标题标记后紧跟连接词/标点的行不是章节标题
_CHAPTER_TITLE_GUARD = r'(?!的|了|是|在|这|那|，|。|、|：|:|完|结)'
# 独立关键词（序章/楔子/正文/终章/后记/尾声/番外）要求后面跟分隔符/行尾/编号，
# 避免正文中"番外篇""番外设定""正文内容"等行被误判为章节，导致正文中间跳出番外
_STANDALONE_KEYWORD_FOLLOW = r'(?=[ 　\t\-—–:：、·，,。.．]|$|[零〇一二三四五六七八九十百千\d]+)'
CHAPTER_TITLE_PREFIX = (r'[ 　\t]{0,4}(?:'
                        r'(?:序章|楔子|终章|后记|尾声|番外)' + _STANDALONE_KEYWORD_FOLLOW +
                        r'|正文' + _STANDALONE_KEYWORD_FOLLOW +
                        r'|第\s{0,4}[\d〇零一二两三四五六七八九十百千万壹贰叁肆伍陆柒捌玖拾佰仟]+?\s{0,4}(?:章|节(?!课)|卷|集(?![合和])|部(?![分赛游])|篇(?!张))' + _CHAPTER_TITLE_GUARD +
                        r')')


class ProgressBar:
    """进度条类"""
    def __init__(self, total, prefix='', suffix='', length=50, fill='█', print_end="\r"):
        self.total = max(1, total)
        self.prefix = prefix
        self.suffix = suffix
        self.length = length
        self.fill = fill
        self.print_end = print_end
        self.current = 0
        self.start_time = time.time()

    def update(self, progress=1):
        """更新进度"""
        self.current += progress
        percent = ("{0:.1f}").format(100 * (self.current / float(self.total)))
        filled_length = int(self.length * self.current // self.total)
        bar = self.fill * filled_length + '-' * (self.length - filled_length)

        # 计算耗时
        elapsed_time = time.time() - self.start_time
        if self.current > 0:
            time_per_item = elapsed_time / self.current
            remaining_items = max(0, self.total - self.current)
            remaining_time = time_per_item * remaining_items

            # 格式化时间
            elapsed_str = self._format_time(elapsed_time)
            remaining_str = self._format_time(remaining_time)

            time_info = f" 耗时:{elapsed_str} 剩余:{remaining_str}"
        else:
            time_info = ""

        print(f'\r{self.prefix} |{bar}| {percent}% {self.suffix}{time_info}', end=self.print_end)

        if self.current >= self.total:
            print()

    def _format_time(self, seconds):
        """格式化时间显示"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m{secs:.0f}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h{minutes}m"


class DocumentConverter:
    def __init__(self, input_path, output_dir="output", font_size=8, page_size=(215, 290),
                 chapters_per_folder=10, max_folders_per_level=10, font_name="等线"):
        """
        初始化文档转换器
        """
        self.input_path = input_path
        self.output_dir = output_dir
        self.font_size = font_size
        # 防止页面尺寸小于边距导致计算异常
        self.page_width = max(page_size[0], margin_left + margin_right + 2)
        self.page_height = max(page_size[1], margin_top + margin_bottom + 2)
        self.chapters_per_folder = max(1, chapters_per_folder)
        self.max_folders_per_level = max(1, max_folders_per_level)
        self.font_name = font_name

        self.font = self._load_font()

        # 复用测量用画布，避免每章重新创建
        self._measure_img = Image.new('L', (1, 1))
        self._measure_draw = ImageDraw.Draw(self._measure_img)
        self._cache_font_metrics()

        # 多线程相关
        self._print_lock = threading.Lock()
        self._max_workers = max(1, os.cpu_count() or 1)

        self.file_ext = os.path.splitext(input_path)[1].lower()
        self.is_txt = self.file_ext == '.txt'

    def _get_font_candidates(self, font_name):
        """返回指定字体的候选路径/名称列表（按平台，优先用户选择的字体）"""
        candidates = []

        if sys.platform == 'win32':
            font_map = {
                "等线": ["C:/Windows/Fonts/Deng.ttf",
                         "C:/Windows/Fonts/DengXian.ttf",
                         "C:/Windows/Fonts/Dengb.ttf",
                         "等线", "DengXian"],
                "微软雅黑": ["C:/Windows/Fonts/msyh.ttc",
                             "C:/Windows/Fonts/msyhbd.ttc",
                             "微软雅黑", "Microsoft YaHei"],
                "宋体": ["C:/Windows/Fonts/simsun.ttc",
                         "C:/Windows/Fonts/simsunb.ttf",
                         "宋体", "SimSun"],
                "Arial": ["C:/Windows/Fonts/arial.ttf",
                          "C:/Windows/Fonts/arialbd.ttf",
                          "Arial"],
            }
            candidates = font_map.get(font_name, [font_name])
        elif sys.platform == 'darwin':
            candidates = [font_name, "/System/Library/Fonts/PingFang.ttc",
                          "/System/Library/Fonts/STHeiti Medium.ttc"]
        elif sys.platform.startswith('linux'):
            candidates = [font_name, "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"]

        # 去重且保持顺序
        seen = set()
        result = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                result.append(candidate)
        return result

    def _get_fallback_font_paths(self):
        """平台可用字体的兜底路径列表（仅当所选字体完全加载失败时使用）"""
        if sys.platform == 'win32':
            return ["C:/Windows/Fonts/Deng.ttf",
                    "C:/Windows/Fonts/msyh.ttc",
                    "C:/Windows/Fonts/simsun.ttc",
                    "C:/Windows/Fonts/arial.ttf"]
        if sys.platform == 'darwin':
            return ["/System/Library/Fonts/PingFang.ttc",
                    "/System/Library/Fonts/STHeiti Medium.ttc",
                    "/Library/Fonts/Arial Unicode.ttf"]
        if sys.platform.startswith('linux'):
            return ["/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        return []

    def _load_font(self):
        """加载字体：优先加载用户选择的字体，不再默认回退到等线Light"""
        # 1) 用户选择的字体：路径 + 名称依次尝试
        for candidate in self._get_font_candidates(self.font_name):
            try:
                return ImageFont.truetype(candidate, self.font_size)
            except Exception:
                continue

        # 2) 兜底：平台常用字体
        for font_path in self._get_fallback_font_paths():
            if os.path.exists(font_path):
                try:
                    return ImageFont.truetype(font_path, self.font_size)
                except Exception:
                    continue

        print(f"警告: 未找到字体 '{self.font_name}'，使用默认字体")
        try:
            return ImageFont.truetype("arial.ttf", self.font_size)
        except Exception:
            return ImageFont.load_default()

    def _cache_font_metrics(self):
        """缓存字体度量，避免每章重复测量"""
        bbox = self._measure_draw.textbbox((0, 0), "中", font=self.font)
        char_height = bbox[3] - bbox[1]
        self.char_height = max(1, char_height)
        self.line_height = max(1, int(self.char_height * 1.5))

    def _process_txt(self):
        """处理TXT文件，保持章节顺序"""
        print("处理TXT文件...")

        chapters = []

        try:
            with open(self.input_path, 'r', encoding='utf-8') as f:
                full_text = f.read()
        except UnicodeDecodeError:
            encodings = ['gbk', 'gb2312', 'latin-1', 'cp1252']
            for encoding in encodings:
                try:
                    with open(self.input_path, 'r', encoding=encoding) as f:
                        full_text = f.read()
                    break
                except Exception:
                    continue
            else:
                print("无法解码TXT文件")
                return chapters

        # 补一个换行，避免"空行匹配模式"漏掉文件末尾的最后一个章节
        if full_text and not full_text.endswith('\n'):
            full_text += '\n'

        # 询问章节分割模式
        print("\n请选择章节分割模式:")
        print("1. 第xxx章 模式 (默认)")
        print("2. Chapter xxx 模式")
        print("3. 空行匹配模式")
        print("4. 自定义正则表达式")
        print("5. 空行匹配(前瞻)")
        print("6. 顶格匹配")

        choice = input("请选择 (1-6, 默认1): ").strip()

        if choice == '2':
            patterns = [
                r'^(Chapter|CHAPTER|Ch\.?|ch\.?)\s*(\d+|[IVXLCDMivxlcdm]+|[A-Za-z]+)\b[\s\-]*([^\n]*)',
                r'^\s*(\d+)\s*[\-\.]?\s*([^\n]*)',
            ]
        elif choice == '3':
            patterns = [
                r'\n[ \t\r]*\n([^\n]+)\n'
            ]
        elif choice == '4':
            custom_pattern = input("请输入正则表达式: ").strip()
            if custom_pattern:
                patterns = [custom_pattern]
            else:
                patterns = self._get_default_chapter_patterns()
        elif choice == '5':
            patterns = [
                r'^(?!\s)(.+)(?=\n{2,})'
            ]
        elif choice == '6':
            patterns = [
                r'^[^\s].*'
            ]
        else:
            patterns = self._get_default_chapter_patterns()

        # 查找所有章节分割点
        all_matches = []
        for pattern in patterns:
            matches = list(re.finditer(pattern, full_text, re.MULTILINE))
            if matches:
                all_matches.extend(matches)
                print(f"使用模式: {pattern}")
                print(f"找到 {len(matches)} 个章节")
                break

        if not all_matches:
            print("未找到章节分割点，将整个文件作为一个章节")
            chapters.append({
                'index': 1,
                'name': '全文',
                'text': full_text,
                'file_path': self.input_path
            })
            return chapters

        # 按位置排序匹配结果
        all_matches.sort(key=lambda x: x.start())

        # 保留第一个章节之前的文本（书名/简介等），避免数据丢失
        prefix_text = full_text[:all_matches[0].start()].strip()
        has_prefix = bool(prefix_text)

        # 提取章节内容，保持原始顺序（内容与前文完全重复的章节自动跳过）
        seen_content = set()
        progress_bar = ProgressBar(len(all_matches) + (1 if has_prefix else 0),
                                   prefix='提取章节:', suffix='完成', length=30)

        for i, match in enumerate(all_matches):
            start_pos = match.start()

            if i < len(all_matches) - 1:
                end_pos = all_matches[i + 1].start()
            else:
                end_pos = len(full_text)

            chapter_text = full_text[start_pos:end_pos].strip()

            # 提取章节标题
            chapter_title = self._chapter_title_from_match(match)
            if not chapter_title:
                chapter_title = f"第{i + 1}章"

            # 从章节内容中移除标题行
            chapter_text = self._remove_title_from_content(chapter_text, chapter_title)

            # 跳过与前文重复的章节（源文件可能重复收录前言/章节）
            content_key = re.sub(r'\s', '', chapter_text)
            if content_key in seen_content:
                print(f"跳过重复章节: {chapter_title}（内容与前面章节相同）")
                progress_bar.update(1)
                continue
            seen_content.add(content_key)

            chapters.append({
                'index': i + 1,
                'name': chapter_title,
                'text': chapter_text,
                'file_path': self.input_path
            })

            progress_bar.update(1)

        if has_prefix:
            chapters.insert(0, {
                'name': '前言',
                'text': prefix_text,
                'file_path': self.input_path
            })
            progress_bar.update(1)
            print(f"开头 {len(prefix_text)} 字内容作为'前言'章节保留")

        # 统一重编章节号（跳过重复章节后序号可能不连续）
        for idx, chapter in enumerate(chapters):
            chapter['index'] = idx + 1

        return chapters

    def _remove_title_from_content(self, content, chapter_title):
        """从章节内容中移除开头的标题行（仅移除首个标题行，避免误删正文）"""
        if not content:
            return content

        # 提取纯标题文本（移除"第X章"部分）
        title_only = re.sub(r'^第[零一二三四五六七八九十百千万\d]+章\s*', '', chapter_title)

        candidates = [chapter_title]
        if title_only and title_only.strip():
            candidates.append(title_only.strip())

        for pattern in candidates:
            if not pattern:
                continue
            # 限定到行尾，防止把正文行"再见，老朋友"截成"，老朋友"
            content = re.sub(f'^\\s*{re.escape(pattern)}\\s*(?:$|[\r\n]+)', '', content, count=1)

        return content.strip()

    def _get_default_chapter_patterns(self):
        """获取默认的章节正则表达式"""
        return [
            '^' + CHAPTER_TITLE_PREFIX + '.{0,30}$',
        ]

    def _chapter_title_from_match(self, match):
        """从正则匹配中提取章节标题"""
        matched_text = match.group(0).strip()
        title = re.sub(r'^[\s　]*', '', matched_text)

        if len(title) > 100:
            title = title[:100] + "..."

        return title

    def _create_text_pages_single(self, text, chapter_name, chapter_index, output_folder):
        """为单个章节创建图片页面（单线程版本）"""
        # 计算本章字数（统计纯文本中非空白字符）
        chapter_word_count = len(re.sub(r'\s', '', text.strip()))
        line_height = self.line_height

        usable_width = self.page_width - margin_left - margin_right
        usable_height = self.page_height - margin_top - margin_bottom

        # 第一页需要为标题留出空间（过长的标题拆分为多行显示）
        title_lines = self._split_text_into_lines(chapter_name, usable_width)
        if not title_lines or not any(line for line in title_lines):
            title_lines = [chapter_name]
        title_block_height = (len(title_lines) + 1) * line_height  # 标题行 + 标题与分隔线的间距
        lines_per_page_first = max(0, (usable_height - title_block_height) // line_height)
        lines_per_page_normal = max(1, usable_height // line_height)

        # 分割文本为行
        lines = self._split_text_into_lines(text, usable_width)

        if not lines or not any(line for line in lines):
            lines = ["（本章节内容为空）"]

        # 计算总页数
        if lines_per_page_first >= len(lines):
            total_pages = 1
        else:
            remaining_lines = len(lines) - lines_per_page_first
            total_pages = 1 + math.ceil(remaining_lines / lines_per_page_normal)

        # 只测量一次，避免每页重复测量
        chapter_num_text = f"第{chapter_index}章"
        word_count_text = f"本章字数：{chapter_word_count}"
        chapter_num_bbox = self._measure_draw.textbbox((0, 0), chapter_num_text, font=self.font)
        chapter_num_width = chapter_num_bbox[2] - chapter_num_bbox[0]
        word_count_bbox = self._measure_draw.textbbox((0, 0), word_count_text, font=self.font)
        word_count_width = word_count_bbox[2] - word_count_bbox[0]
        word_count_x = margin_left + (usable_width - word_count_width) // 2

        # 生成每页
        for page_idx in range(total_pages):
            img = Image.new('L', (self.page_width, self.page_height), color=0)
            draw = ImageDraw.Draw(img)

            # 第一页特殊处理
            if page_idx == 0:
                title_y = margin_top
                # 标题可能被拆分为多行，逐行绘制
                for line_idx, title_line in enumerate(title_lines):
                    draw.text((margin_left, title_y + line_idx * line_height),
                              title_line, font=self.font, fill=255)

                # 章节号显示在标题最后一行的右侧
                draw.text(((self.page_width - margin_left - chapter_num_width),
                           title_y + (len(title_lines) - 1) * line_height),
                          chapter_num_text, font=self.font, fill=128)

                separator_y = title_y + len(title_lines) * line_height

                # 绘制左直线（从左边距到字数文本左侧）
                if word_count_x > margin_left:
                    draw.line([(margin_left, separator_y), (word_count_x - 2, separator_y)],
                              fill=128, width=1)

                # 绘制字数文本
                draw.text((word_count_x, separator_y), word_count_text, font=self.font, fill=128)

                # 绘制右直线（从字数文本右侧到右边距）
                right_line_start = word_count_x + word_count_width + 2
                if right_line_start < self.page_width - margin_right:
                    draw.line([(right_line_start, separator_y),
                               (self.page_width - margin_right, separator_y)],
                              fill=128, width=1)

                content_start_y = separator_y + line_height
                end_line = min(lines_per_page_first, len(lines))
                for i in range(end_line):
                    y_pos = content_start_y + i * line_height
                    draw.text((margin_left, y_pos), lines[i], font=self.font, fill=255)
            else:
                content_start_y = margin_top
                start_line = int(lines_per_page_first + (page_idx - 1) * lines_per_page_normal)
                end_line = min(start_line + lines_per_page_normal, len(lines))

                for i in range(start_line, end_line):
                    y_pos = content_start_y + (i - start_line) * line_height
                    draw.text((margin_left, y_pos), lines[i], font=self.font, fill=255)

            # 保存图片
            filename = f"{chapter_index:03d}-{page_idx + 1:03d}.png"
            filepath = os.path.join(output_folder, filename)
            img.save(filepath, 'PNG', optimize=True)

        return total_pages

    def _generate_chapter_pages(self, chapter_data, chapter_index, group_folder_path):
        """在子线程中为单个章节生成图片页面（各线程只写自己的子文件夹，互不冲突）"""
        chapter_name = chapter_data['name']
        error = None
        pages = 0

        try:
            # 创建章节子文件夹：第X章_章节名
            title_only = re.sub('^' + CHAPTER_TITLE_PREFIX, '', chapter_name)
            safe_chapter_name = self._sanitize_folder_name(title_only)
            chapter_subfolder = os.path.join(group_folder_path, f"{chapter_index:03d}.{safe_chapter_name}")
            os.makedirs(chapter_subfolder, exist_ok=True)

            pages = self._create_text_pages_single(
                chapter_data['text'],
                chapter_name,
                chapter_index,
                chapter_subfolder
            )
        except Exception as e:
            error = str(e)

        # 进度条更新需要加锁，避免多线程输出交错
        with self._print_lock:
            self._progress.update(1)

        return chapter_index, chapter_name, pages, error

    def _split_text_into_lines(self, text, max_width):
        """将文本分割成适合宽度的行（按字符宽度缓存，O(n) 而非 O(n^2)）"""
        lines = []
        font = self.font
        width_cache = {}
        get_width = width_cache.get

        for para in text.split('\n'):
            para = para.strip()
            if not para:
                lines.append('')
                continue

            current_line = ''
            current_width = 0.0

            for ch in para:
                char_width = get_width(ch)
                if char_width is None:
                    char_width = font.getlength(ch)
                    width_cache[ch] = char_width

                if current_width + char_width <= max_width or not current_line:
                    current_line += ch
                    current_width += char_width
                else:
                    lines.append(current_line)
                    current_line = ch
                    current_width = char_width

            if current_line:
                lines.append(current_line)

        return lines

    def _organize_folders_recursive(self, base_dir, folders, level=1):
        """递归组织文件夹结构，使用第X章-第X章命名"""
        if self.max_folders_per_level < 1:
            self.max_folders_per_level = 1

        if len(folders) <= self.max_folders_per_level:
            return folders

        # 按顺序分组文件夹
        grouped_folders = []
        for i in range(0, len(folders), self.max_folders_per_level):
            group = folders[i:i + self.max_folders_per_level]
            grouped_folders.append(group)

        # 防止分组数量没有减少（如 max_folders_per_level=1）导致无限递归
        if len(grouped_folders) >= len(folders):
            return folders

        print(f"\n{'=' * 60}")
        print(f"第{level}层文件夹合并 (当前{len(folders)}个文件夹 > {self.max_folders_per_level})")
        print(f"{'=' * 60}")

        # 为每组创建父文件夹
        new_parent_folders = []
        for group_idx, group in enumerate(grouped_folders):
            # 获取组中第一个和最后一个文件夹的章节号
            first_chapter_num = None
            last_chapter_num = None

            for folder in group:
                # 从文件夹名中提取章节号
                folder_name = os.path.basename(folder)
                chapter_match = re.search(r'第(\d+)章', folder_name)
                if chapter_match:
                    chapter_num = int(chapter_match.group(1))
                    if first_chapter_num is None:
                        first_chapter_num = chapter_num
                    last_chapter_num = chapter_num

            # 生成文件夹名：第X章-第Y章
            if first_chapter_num is not None and last_chapter_num is not None:
                group_name = f"第{first_chapter_num:03d}章-第{last_chapter_num:03d}章"
            else:
                # 无法提取章节号时，取名称中的第一个数字段（不要拼接所有数字）
                first_digits = re.search(r'\d+', os.path.basename(group[0]))
                last_digits = re.search(r'\d+', os.path.basename(group[-1]))

                if first_digits and last_digits:
                    group_name = f"L{level}_{int(first_digits.group()):03d}-{int(last_digits.group()):03d}"
                else:
                    group_name = f"第{level}层_第{group_idx + 1:02d}组"

            # 创建父文件夹
            parent_folder_path = os.path.join(base_dir, group_name)
            os.makedirs(parent_folder_path, exist_ok=True)

            print(f"创建父文件夹: {group_name}")
            print(f"  包含子文件夹: {len(group)}个")
            if first_chapter_num is not None and last_chapter_num is not None:
                print(f"  章节范围: 第{first_chapter_num}章 - 第{last_chapter_num}章")

            # 移动子文件夹到父文件夹
            for folder in group:
                folder_name = os.path.basename(folder)
                new_path = os.path.join(parent_folder_path, folder_name)
                if os.path.exists(folder) and os.path.exists(os.path.dirname(new_path)):
                    try:
                        shutil.move(folder, new_path)
                        print(f"    移动: {folder_name} -> {group_name}/")
                    except Exception as e:
                        print(f"    移动失败 {folder_name}: {e}")

            new_parent_folders.append(parent_folder_path)

        # 递归处理
        return self._organize_folders_recursive(base_dir, new_parent_folders, level + 1)

    @staticmethod
    def _sanitize_folder_name(name):
        """清理文件夹名中的非法字符/保留名/首尾点号"""
        safe = re.sub(r'[<>:"/\\|?*\.]', '_', name).strip(' .')
        if not safe:
            safe = "chapter"
        if safe.lower() in ('con', 'prn', 'aux', 'nul') or \
                re.match(r'^(com|lpt)[1-9]$', safe.lower()):
            safe = '_' + safe
        return safe[:50]

    def convert(self):
        """执行转换"""
        print(f"开始转换文件: {self.input_path}")
        print(f"文件类型: {self.file_ext}")
        print(f"配置: 每{self.chapters_per_folder}章一个文件夹，每层最多{self.max_folders_per_level}个文件夹")

        os.makedirs(self.output_dir, exist_ok=True)

        try:
            chapters = []

            if self.is_txt:
                chapters = self._process_txt()
            else:
                print(f"不支持的文件类型: {self.file_ext}")
                return

            if not chapters:
                print("未提取到任何章节内容")
                return

            # 验证章节顺序
            print(f"\n验证章节顺序...")
            for i, chapter in enumerate(chapters):
                expected_index = i + 1
                actual_index = chapter['index']
                if expected_index != actual_index:
                    print(f"  警告: 章节索引不匹配 - 期望:{expected_index}, 实际:{actual_index}")
                    chapter['index'] = expected_index

            print(f"共提取 {len(chapters)} 章")
            print("开始生成图片...")

            # 创建章节文件夹结构
            print(f"\n准备章节文件夹结构...")
            total_chapters = len(chapters)
            total_pages = 0

            # 预计算分组文件夹（保持章节顺序），由主线程统一创建
            group_folder_paths = []
            chapter_folders = []
            for chapter_index in range(1, total_chapters + 1):
                group_idx = (chapter_index - 1) // self.chapters_per_folder
                group_start = group_idx * self.chapters_per_folder + 1
                group_end = min((group_idx + 1) * self.chapters_per_folder, total_chapters)
                group_folder_name = f"第{group_start:03d}章-第{group_end:03d}章"
                group_folder_path = os.path.join(self.output_dir, group_folder_name)
                os.makedirs(group_folder_path, exist_ok=True)
                group_folder_paths.append(group_folder_path)
                if chapter_index == group_start:
                    chapter_folders.append(group_folder_path)

            # 创建进度条（多线程更新，用锁保护）
            self._progress = ProgressBar(total_chapters, prefix='生成图片:', suffix='完成', length=30)

            print(f"\n{'=' * 60}")
            print("章节处理详情:")
            print(f"{'=' * 60}")

            # 多线程并行生成图片（每个章节写入自己的子文件夹，互不冲突）
            worker_count = min(self._max_workers, total_chapters)
            print(f"使用 {worker_count} 个线程并行生成图片...")

            results = [None] * total_chapters
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_to_index = {}
                for i, chapter_data in enumerate(chapters):
                    chapter_index = i + 1
                    future_to_index[executor.submit(
                        self._generate_chapter_pages,
                        chapter_data, chapter_index, group_folder_paths[i]
                    )] = i

                for future in as_completed(future_to_index):
                    idx = future_to_index[future]
                    results[idx] = future.result()

            # 按章节顺序汇总结果
            for chapter_index, chapter_name, pages, error in sorted(results, key=lambda r: r[0]):
                if error:
                    print(f"  [失败] 章节 {chapter_index:03d}: {chapter_name} - 处理失败: {error}")
                else:
                    print(f"  [成功] 章节 {chapter_index:03d}: {chapter_name} - 生成 {pages:3d} 页")
                    total_pages += pages

            print(f"\n{'=' * 60}")
            print(f"章节处理完成!")
            print(f"总章节数: {total_chapters}")
            print(f"总页数: {total_pages}")
            print(f"初始文件夹数: {len(chapter_folders)}")

            # 递归组织文件夹结构
            if len(chapter_folders) > 0:
                final_folders = self._organize_folders_recursive(self.output_dir, chapter_folders)
                print(f"\n最终文件夹数: {len(final_folders)}")

            print(f"\n{'=' * 60}")
            print(f"转换完成!")
            print(f"输出目录: {os.path.abspath(self.output_dir)}")

            # 显示最终目录结构
            print(f"\n最终的目录结构:")
            self._print_directory_structure(self.output_dir)

        except Exception as e:
            print(f"转换过程中出错: {e}")
            import traceback
            traceback.print_exc()

    def _print_directory_structure(self, startpath, indent="", is_last=True):
        """打印目录结构"""
        items = []
        for item in os.listdir(startpath):
            if item.startswith('.'):
                continue
            itempath = os.path.join(startpath, item)
            items.append((item, itempath))

        # 按章节号排序（返回统一格式的元组，避免 int/str 混排崩溃）
        items.sort(key=lambda x: self._extract_chapter_number_for_sort(x[0]))

        for i, (name, path) in enumerate(items):
            is_last_item = (i == len(items) - 1)

            if os.path.isdir(path):
                png_count = self._count_png_files(path)
                prefix = "└── " if is_last_item else "├── "
                print(f"{indent}{prefix}[{name}]", end="")

                if png_count > 0:
                    print(f" ({png_count}张图片)")
                else:
                    print()

                new_indent = indent + ("    " if is_last_item else "│   ")
                self._print_directory_structure(path, new_indent, is_last_item)

    def _extract_chapter_number_for_sort(self, name):
        """从文件夹名提取章节号用于排序（返回同类型元组）"""
        # 尝试匹配"第X章"格式
        match = re.search(r'第(\d+)章', name)
        if match:
            return (0, int(match.group(1)), 0)

        # 尝试提取数字
        numbers = re.findall(r'\d+', name)
        if numbers:
            return (1, int(numbers[0]), 0)

        # 无数字时按名称排序
        return (2, 0, name.lower())

    def _count_png_files(self, directory):
        """递归计算目录中的png文件数量"""
        count = 0
        for root, dirs, files in os.walk(directory):
            count += sum(1 for f in files if f.lower().endswith('.png'))
        return count


def main():
    print("=== TXT文档转图片工具 ===")
    print(f"支持TXT文件转换为{default_width}x{default_height}的灰度图片")
    print("保持章节原始顺序，递归合并文件夹，使用单线程处理\n")

    input_path = input("请输入文件路径 (TXT): ").strip('"').strip("'")

    if not os.path.exists(input_path):
        print(f"错误: 文件不存在 - {input_path}")
        return

    file_ext = os.path.splitext(input_path)[1].lower()
    if file_ext not in ['.txt']:
        print(f"错误: 不支持的文件类型 {file_ext}，仅支持TXT")
        return

    default_output = os.path.join(os.path.dirname(input_path),
                                  f"{os.path.splitext(os.path.basename(input_path))[0]}_images")
    output_dir = input(f"输出目录 (默认: {default_output}): ").strip('"').strip("'")

    if not output_dir:
        output_dir = default_output

    print(f"\n字体设置:")
    print("1. 等线 (默认)")
    print("2. 微软雅黑")
    print("3. 宋体")
    print("4. Arial")
    font_choice = input("选择字体 (1-4, 默认1): ").strip()

    if font_choice == '2':
        font_name = "微软雅黑"
    elif font_choice == '3':
        font_name = "宋体"
    elif font_choice == '4':
        font_name = "Arial"
    else:
        font_name = "等线"

    font_size_input = input(f"字体大小(pt，默认{default_font_size}): ").strip()
    if font_size_input:
        try:
            font_size = int(font_size_input)
        except Exception:
            font_size = default_font_size
            print(f"输入无效，使用默认值{default_font_size}")
    else:
        font_size = default_font_size

    # 防止非法输入导致除零/死循环
    if font_size < 4:
        font_size = 4
        print("字体大小过小，已调整为4pt")

    chapters_per_input = input(f"每个底层文件夹包含的章节数 (默认{default_chapters_per_folder}): ").strip()
    if chapters_per_input:
        try:
            chapters_per_folder = int(chapters_per_input)
        except Exception:
            chapters_per_folder = default_chapters_per_folder
            print(f"输入无效，使用默认值{default_chapters_per_folder}")
    else:
        chapters_per_folder = default_chapters_per_folder

    if chapters_per_folder < 1:
        chapters_per_folder = 1
        print("章节数至少为1，已调整为1")

    max_folders_input = input(f"每层最大文件夹数 (默认{default_max_folders_per_level}): ").strip()
    if max_folders_input:
        try:
            max_folders_per_level = int(max_folders_input)
        except Exception:
            max_folders_per_level = default_max_folders_per_level
            print(f"输入无效，使用默认值{default_max_folders_per_level}")
    else:
        max_folders_per_level = default_max_folders_per_level

    if max_folders_per_level < 1:
        max_folders_per_level = 1
        print("文件夹数至少为1，已调整为1")

    custom_size = input("使用自定义页面尺寸？(y/n，默认n): ").lower()
    if custom_size == 'y':
        try:
            width = int(input(f"宽度 (默认{default_width}): ") or f"{default_width}")
            height = int(input(f"高度 (默认{default_height}): ") or f"{default_height}")
            page_size = (width, height)
        except Exception:
            page_size = (default_width, default_height)
            print(f"输入无效，使用默认尺寸{default_width}x{default_height}")
        if page_size[0] < margin_left + margin_right + 20 or page_size[1] < margin_top + margin_bottom + 20:
            page_size = (default_width, default_height)
            print(f"页面尺寸过小，使用默认尺寸{default_width}x{default_height}")
    else:
        page_size = (default_width, default_height)

    converter = DocumentConverter(
        input_path,
        output_dir,
        font_size,
        page_size,
        chapters_per_folder,
        max_folders_per_level,
        font_name
    )
    converter.convert()

    print("\n按Enter键退出...")
    input()


if __name__ == "__main__":
    main()
