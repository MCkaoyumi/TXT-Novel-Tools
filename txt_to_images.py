import os
import re
import math
import shutil
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
# 全局默认配置
# 页面边距设置
marginy = 25 # 页面纵向边距 单位:px
marginx = 5 # 页面横向边距 单位:px

# 图片分辨率设置
default_width = 215
default_height = 290
# 文件夹层数设置
default_max_folders_per_level = 10 #最大文件夹层数
default_chapters_per_folder = 100
# 字体设置
default_font_size = 12
class ProgressBar:
    """进度条类"""
    def __init__(self, total, prefix='', suffix='', length=50, fill='█', print_end="\r"):
        self.total = total
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
            remaining_items = self.total - self.current
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
                 chapters_per_folder=10, max_folders_per_level=10, font_name="等线 Light"):
        """
        初始化文档转换器
        """
        self.input_path = input_path
        self.output_dir = output_dir
        self.font_size = font_size
        self.page_width, self.page_height = page_size
        self.chapters_per_folder = chapters_per_folder
        self.max_folders_per_level = max_folders_per_level
        self.font_name = font_name
        
        self.font = self._load_font()
        self.file_ext = os.path.splitext(input_path)[1].lower()
        self.is_txt = self.file_ext == '.txt'
        
    def _load_font(self):
        """加载字体"""
        font_search_paths = []
        
        if sys.platform == 'win32':
            font_search_paths.extend([
                "C:/Windows/Fonts/DengXian-Light.ttf",
                "C:/Windows/Fonts/DengXian.ttf",
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simsun.ttc",
            ])
        elif sys.platform == 'darwin':
            font_search_paths.extend([
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
                "/Library/Fonts/Arial Unicode.ttf",
            ])
        elif sys.platform.startswith('linux'):
            font_search_paths.extend([
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ])
        
        font_names_to_try = [
            self.font_name,
            "等线 Light",
            "DengXian-Light",
            "微软雅黑 Light",
            "Arial",
            "Helvetica",
        ]
        
        for font_name in font_names_to_try:
            try:
                return ImageFont.truetype(font_name, self.font_size)
            except:
                pass
        
        for font_path in font_search_paths:
            try:
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, self.font_size)
            except:
                continue
        
        print(f"警告: 未找到字体 '{self.font_name}'，使用默认字体")
        try:
            return ImageFont.truetype("arial.ttf", self.font_size)
        except:
            return ImageFont.load_default()
    
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
                except:
                    continue
            else:
                print("无法解码TXT文件")
                return chapters
        
        # 询问章节分割模式
        print("\n请选择章节分割模式:")
        print("1. 第xxx章 模式 (默认)")
        print("2. Chapter xxx 模式")
        print("3. 自定义正则表达式")
        
        choice = input("请选择 (1-3, 默认1): ").strip()
        
        if choice == '2':
            patterns = [
                r'^(Chapter|CHAPTER|Ch\.?|ch\.?)\s*(\d+|[IVXLCDMivxlcdm]+|[A-Za-z]+)\b[\s\-]*([^\n]*)',
                r'^\s*(\d+)\s*[\-\.]?\s*([^\n]*)',
            ]
        elif choice == '3':
            custom_pattern = input("请输入正则表达式: ").strip()
            if custom_pattern:
                patterns = [custom_pattern]
            else:
                patterns = self._get_default_chapter_patterns()
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
        
        # 提取章节内容，保持原始顺序
        progress_bar = ProgressBar(len(all_matches), prefix='提取章节:', suffix='完成', length=30)
        
        for i, match in enumerate(all_matches):
            start_pos = match.start()
            
            if i < len(all_matches) - 1:
                end_pos = all_matches[i+1].start()
            else:
                end_pos = len(full_text)
            
            chapter_text = full_text[start_pos:end_pos].strip()
            
            # 提取章节标题
            chapter_title = self._chapter_title_from_match(match)
            if not chapter_title:
                chapter_title = f"第{i+1}章"
            
            # 从章节内容中移除标题行
            chapter_text = self._remove_title_from_content(chapter_text, chapter_title)
            
            chapters.append({
                'index': i + 1,
                'name': chapter_title,
                'text': chapter_text,
                'file_path': self.input_path
            })
            
            progress_bar.update(1)
        
        return chapters
    
    def _remove_title_from_content(self, content, chapter_title):
        """从章节内容中移除标题"""
        if not content or not chapter_title:
            return content
        
        # 提取纯标题文本（移除"第X章"部分）
        title_only = re.sub(r'^第[零一二三四五六七八九十百千万\d]+章\s*', '', chapter_title)
        
        # 构建要移除的模式列表
        patterns_to_remove = []
        
        # 添加完整章节标题
        patterns_to_remove.append(re.escape(chapter_title))
        
        # 添加纯标题文本
        if title_only and title_only.strip():
            patterns_to_remove.append(re.escape(title_only))
            patterns_to_remove.append(re.escape(title_only.strip()))
        
        # 尝试移除标题
        for pattern in patterns_to_remove:
            if pattern:
                # 移除开头的标题
                content = re.sub(f'^\\s*{pattern}\\s*[\r\n]*', '', content)
                # 移除段落开头的标题
                content = re.sub(f'[\r\n]+\\s*{pattern}\\s*[\r\n]*', '\n', content)
        
        return content.strip()
    
    def _get_default_chapter_patterns(self):
        """获取默认的章节正则表达式"""
        return [
            r'^\s*第[零一二三四五六七八九十百千万\d]+\s*章[：:】]?\s*[^\n]*',
            r'^\s*第[零一二三四五六七八九十百千万\d]+\s*回[：:】]?\s*[^\n]*',
            r'^\s*[零一二三四五六七八九十百千万\d]+\s*[\.、]\s*[^\n]*',
            r'^\s*[\d]+\s*[\.、]\s*[^\n]*',
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
        # 测量字体尺寸
        test_img = Image.new('RGB', (100, 100), (255, 255, 255))
        test_draw = ImageDraw.Draw(test_img)
        
        bbox = test_draw.textbbox((0, 0), "中", font=self.font)
        char_height = bbox[3] - bbox[1]
        line_height = int(char_height * 1.5)

        usable_width = self.page_width - 2 * marginx
        usable_height = self.page_height - 2 * marginy
        
        # 第一页需要为标题留出空间
        title_bbox = test_draw.textbbox((0, 0), chapter_name, font=self.font)
        title_height = title_bbox[3] - title_bbox[1] + line_height * 2
        lines_per_page_first = (usable_height - title_height) // line_height
        lines_per_page_normal = usable_height // line_height
        
        # 分割文本为行
        lines = self._split_text_into_lines(text, test_draw, usable_width)
        
        if not lines:
            lines = ["（本章节内容为空）"]
        
        # 计算总页数
        if len(lines) <= lines_per_page_first:
            total_pages = 1
        else:
            remaining_lines = len(lines) - lines_per_page_first
            total_pages = 1 + math.ceil(remaining_lines / lines_per_page_normal)
        
        # 生成每页
        for page_idx in range(total_pages):
            img = Image.new('L', (self.page_width, self.page_height), color=0)
            draw = ImageDraw.Draw(img)
            
            # 第一页特殊处理
            if page_idx == 0:
                title_y = marginy
                draw.text((marginx, title_y), chapter_name, font=self.font, fill=255)
                
                chapter_num_text = f"第{chapter_index}章"
                chapter_num_bbox = test_draw.textbbox((0, 0), chapter_num_text, font=self.font)
                chapter_num_width = chapter_num_bbox[2] - chapter_num_bbox[0]
                draw.text((self.page_width - marginx - chapter_num_width, title_y), 
                         chapter_num_text, font=self.font, fill=128)
                
                separator_y = title_y + title_height - line_height
                draw.line([(marginx, separator_y), (self.page_width - marginx, separator_y)], fill=128, width=1)
                
                content_start_y = separator_y + line_height
                start_line = 0
                end_line = min(lines_per_page_first, len(lines))
                
                for i in range(start_line, end_line):
                    y_pos = content_start_y + (i - start_line) * line_height
                    draw.text((marginx, y_pos), lines[i], font=self.font, fill=255)
            else:
                content_start_y = marginy
                start_line = lines_per_page_first + (page_idx - 1) * lines_per_page_normal
                end_line = min(start_line + lines_per_page_normal, len(lines))
                
                for i in range(start_line, end_line):
                    y_pos = content_start_y + (i - start_line) * line_height
                    draw.text((marginx, y_pos), lines[i], font=self.font, fill=255)
            
            # 添加页码
            page_num = page_idx + 1
            # page_text = f"{page_num}/{total_pages}"
            # page_bbox = test_draw.textbbox((0, 0), page_text, font=self.font)
            # page_width = page_bbox[2] - page_bbox[0]
            # draw.text((self.page_width - marginy - page_width, self.page_height - marginy - line_height), 
            #          page_text, font=self.font, fill=128)
            
            # 保存图片
            filename = f"{chapter_index:03d}-{page_num:03d}.jpg"
            filepath = os.path.join(output_folder, filename)
            img.save(filepath, 'JPEG', quality=95)
        
        return total_pages
    
    def _split_text_into_lines(self, text, draw, max_width):
        """将文本分割成适合宽度的行"""
        lines = []
        paragraphs = text.split('\n')
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                lines.append('')
                continue
            
            current_line = ''
            words = list(para)
            
            for word in words:
                test_line = current_line + word
                bbox = draw.textbbox((0, 0), test_line, font=self.font)
                line_width = bbox[2] - bbox[0]
                
                if line_width <= max_width or not current_line:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
            
            if current_line:
                lines.append(current_line)
        
        return lines
    
    def _organize_folders_recursive(self, base_dir, folders, level=1):
        """递归组织文件夹结构，使用第X章-第X章命名"""
        if len(folders) <= self.max_folders_per_level:
            return folders
        
        print(f"\n{'='*60}")
        print(f"第{level}层文件夹合并 (当前{len(folders)}个文件夹 > {self.max_folders_per_level})")
        print(f"{'='*60}")
        
        # 按顺序分组文件夹
        grouped_folders = []
        for i in range(0, len(folders), self.max_folders_per_level):
            group = folders[i:i+self.max_folders_per_level]
            grouped_folders.append(group)
        
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
                # 如果无法提取章节号，使用通用命名
                first_folder_num = ''.join(filter(str.isdigit, os.path.basename(group[0])))
                last_folder_num = ''.join(filter(str.isdigit, os.path.basename(group[-1])))
                
                if first_folder_num and last_folder_num:
                    group_name = f"L{level}_{int(first_folder_num):03d}-{int(last_folder_num):03d}"
                else:
                    group_name = f"第{level}层_第{group_idx+1:02d}组"
            
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
            chapter_folders = []
            total_chapters = len(chapters)
            total_pages = 0
            
            # 创建进度条
            process_progress = ProgressBar(total_chapters, prefix='生成图片:', suffix='完成', length=30)
            
            print(f"\n{'='*60}")
            print("章节处理详情:")
            print(f"{'='*60}")
            
            # 按章节顺序处理
            for i, chapter_data in enumerate(chapters):
                chapter_index = i + 1
                chapter_name = chapter_data['name']
                
                # 计算当前章节属于哪个分组
                group_idx = (chapter_index - 1) // self.chapters_per_folder
                group_start = group_idx * self.chapters_per_folder + 1
                group_end = min((group_idx + 1) * self.chapters_per_folder, total_chapters)
                
                # 创建分组文件夹：第X章-第Y章
                group_folder_name = f"第{group_start:03d}章-第{group_end:03d}章"
                group_folder_path = os.path.join(self.output_dir, group_folder_name)
                os.makedirs(group_folder_path, exist_ok=True)
                
                # 如果是该组的第一个章节，记录组文件夹
                if chapter_index == group_start:
                    chapter_folders.append(group_folder_path)
                
                # 创建章节子文件夹：第X章_章节名
                title_only = re.sub(r'^\s*第[零一二三四五六七八九十百千万\d]+\s*章[：:】]?\s', '', chapter_name)
                safe_chapter_name = re.sub(r'[<>:"/\\|?*\.]', '_', title_only)
                safe_chapter_name = safe_chapter_name[:50]
                chapter_subfolder = os.path.join(group_folder_path, f"{chapter_index:03d}.{safe_chapter_name}")
                os.makedirs(chapter_subfolder, exist_ok=True)
                
                try:
                    # 生成图片页面
                    pages = self._create_text_pages_single(
                        chapter_data['text'], 
                        chapter_name, 
                        chapter_index, 
                        chapter_subfolder
                    )
                    
                    print(f"  ✓ 章节 {chapter_index:03d}: {chapter_name} - 生成 {pages:3d} 页")
                    total_pages += pages
                    
                except Exception as e:
                    print(f"  ❌ 章节 {chapter_index:03d}: {chapter_name} - 处理失败: {e}")
                
                # 更新进度
                process_progress.update(1)
            
            print(f"\n{'='*60}")
            print(f"章节处理完成!")
            print(f"总章节数: {total_chapters}")
            print(f"总页数: {total_pages}")
            print(f"初始文件夹数: {len(chapter_folders)}")
            
            # 递归组织文件夹结构
            if len(chapter_folders) > 0:
                final_folders = self._organize_folders_recursive(self.output_dir, chapter_folders)
                print(f"\n最终文件夹数: {len(final_folders)}")
            
            print(f"\n{'='*60}")
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
        
        # 按章节号排序
        items.sort(key=lambda x: self._extract_chapter_number_for_sort(x[0]))
        
        for i, (name, path) in enumerate(items):
            is_last_item = (i == len(items) - 1)
            
            if os.path.isdir(path):
                jpg_count = self._count_jpg_files(path)
                prefix = "└── " if is_last_item else "├── "
                print(f"{indent}{prefix}[{name}]", end="")
                
                if jpg_count > 0:
                    print(f" ({jpg_count}张图片)")
                else:
                    print()
                
                new_indent = indent + ("    " if is_last_item else "│   ")
                self._print_directory_structure(path, new_indent, is_last_item)
    
    def _extract_chapter_number_for_sort(self, name):
        """从文件夹名提取章节号用于排序"""
        # 尝试匹配"第X章"格式
        match = re.search(r'第(\d+)章', name)
        if match:
            return int(match.group(1))
        
        # 尝试提取数字
        numbers = re.findall(r'\d+', name)
        if numbers:
            return int(numbers[0])
        
        return name.lower()
    
    def _count_jpg_files(self, directory):
        """递归计算目录中的JPG文件数量"""
        count = 0
        for root, dirs, files in os.walk(directory):
            count += sum(1 for f in files if f.lower().endswith('.jpg'))
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
    print("1. 等线 Light (默认)")
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
        font_name = "等线 Light"
    
    font_size_input = input(f"字体大小(pt，默认{default_font_size}): ").strip()
    if font_size_input:
        try:
            font_size = int(font_size_input)
        except:
            font_size = default_font_size
            print(f"输入无效，使用默认值{default_font_size}")
    else:
        font_size = default_font_size
    
    chapters_per_input = input(f"每个底层文件夹包含的章节数 (默认{default_chapters_per_folder}): ").strip()
    if chapters_per_input:
        try:
            chapters_per_folder = int(chapters_per_input)
        except:
            chapters_per_folder = default_chapters_per_folder
            print(f"输入无效，使用默认值{default_chapters_per_folder}")
    else:
        chapters_per_folder = default_chapters_per_folder
    
    max_folders_input = input(f"每层最大文件夹数 (默认{default_max_folders_per_level}): ").strip()
    if max_folders_input:
        try:
            max_folders_per_level = int(max_folders_input)
        except:
            max_folders_per_level = default_max_folders_per_level
            print(f"输入无效，使用默认值{default_max_folders_per_level}")
    else:
        max_folders_per_level = default_max_folders_per_level
    
    custom_size = input("使用自定义页面尺寸？(y/n，默认n): ").lower()
    if custom_size == 'y':
        try:
            width = int(input(f"宽度 (默认{default_width}): ") or f"{default_width}")
            height = int(input(f"高度 (默认{default_height}): ") or f"{default_height}")
            page_size = (width, height)
        except:
            page_size = (default_width, default_height)
            print(f"输入无效，使用默认尺寸{default_width}x{default_height}")
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

def convert_document_simple(input_path, output_dir=None, font_name="等线 Light", 
                          chapters_per_folder=10, max_folders_per_level=10):
    """简化版本的转换函数"""
    if output_dir is None:
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        output_dir = f"{base_name}_images"
    
    converter = DocumentConverter(
        input_path, 
        output_dir,
        font_name=font_name,
        chapters_per_folder=chapters_per_folder,
        max_folders_per_level=max_folders_per_level
    )
    converter.convert()

if __name__ == "__main__":
    main()