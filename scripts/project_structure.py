
# project_structure.py
# tools.project_structure
#
# Выводит структуру проекта в виде дерева
# Запуск:
# python scripts/project_structure.py --path . --stats
# Сохранить в scripts/structure.txt
# python scripts/project_structure.py --path . --stats --output scripts/structure.txt
#
# Параметры:
#   --path PATH      Путь к папке (по умолчанию текущая)
#   --depth N        Глубина (по умолчанию 4)
#   --output FILE    Сохранить в файл
#   --no-hidden      Скрыть скрытые файлы (начинающиеся с .)
#   --only-dirs      Только папки
#   --only-py        Только .py файлы

import os
import argparse
from pathlib import Path
from typing import List, Set


# Папки и файлы для игнорирования
IGNORE_DIRS = {
    '__pycache__',
    '.git',
    '.idea',
    '.vscode',
    'venv',
    '.venv',
    'env',
    'node_modules',
    '.pytest_cache',
    '.mypy_cache',
    'dist',
    'build',
    '*.egg-info',
}

IGNORE_FILES = {
    '.DS_Store',
    'Thumbs.db',
    '.gitignore',
    '*.pyc',
    '*.pyo',
}


class Colors:
    """ANSI цвета для терминала"""
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def should_ignore(name: str, ignore_patterns: Set[str]) -> bool:
    """Проверить нужно ли игнорировать файл/папку"""
    for pattern in ignore_patterns:
        if pattern.startswith('*'):
            if name.endswith(pattern[1:]):
                return True
        elif name == pattern:
            return True
    return False


def get_file_icon(filename: str) -> str:
    """Получить иконку для файла по расширению"""
    ext = Path(filename).suffix.lower()
    
    icons = {
        '.py': '🐍',
        '.json': '📋',
        '.yaml': '📋',
        '.yml': '📋',
        '.toml': '📋',
        '.md': '📝',
        '.txt': '📄',
        '.html': '🌐',
        '.css': '🎨',
        '.js': '⚡',
        '.ts': '⚡',
        '.sql': '🗄️',
        '.db': '🗄️',
        '.sqlite': '🗄️',
        '.log': '📜',
        '.env': '🔐',
        '.sh': '⚙️',
        '.bat': '⚙️',
        '.exe': '⚙️',
        '.png': '🖼️',
        '.jpg': '🖼️',
        '.jpeg': '🖼️',
        '.gif': '🖼️',
        '.svg': '🖼️',
        '.pdf': '📕',
        '.zip': '📦',
        '.tar': '📦',
        '.gz': '📦',
    }
    
    return icons.get(ext, '📄')


def get_folder_icon(dirname: str) -> str:
    """Получить иконку для папки"""
    special_folders = {
        'tests': '🧪',
        'test': '🧪',
        'docs': '📚',
        'doc': '📚',
        'config': '⚙️',
        'configs': '⚙️',
        'data': '💾',
        'logs': '📜',
        'static': '🎨',
        'templates': '📐',
        'models': '🧠',
        'views': '👁️',
        'controllers': '🎮',
        'api': '🔌',
        'core': '⚛️',
        'utils': '🔧',
        'helpers': '🔧',
        'gui': '🖥️',
        'components': '🧩',
        'assets': '📁',
        'migrations': '🔄',
        'scripts': '📜',
        'tools': '🛠️',
        'tokens': '🔑',
    }
    
    return special_folders.get(dirname.lower(), '📁')


def print_tree(
    path: Path,
    prefix: str = "",
    max_depth: int = 4,
    current_depth: int = 0,
    show_hidden: bool = False,
    only_dirs: bool = False,
    only_py: bool = False,
    use_colors: bool = True
) -> List[str]:
    """
    Рекурсивно построить дерево директории
    
    Returns:
        Список строк дерева
    """
    if current_depth > max_depth:
        return []
    
    lines = []
    
    try:
        entries = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        return [f"{prefix}[Permission Denied]"]
    
    # Фильтрация
    filtered_entries = []
    for entry in entries:
        name = entry.name
        
        # Скрытые файлы
        if not show_hidden and name.startswith('.'):
            continue
        
        # Игнорируемые папки
        if entry.is_dir() and should_ignore(name, IGNORE_DIRS):
            continue
        
        # Игнорируемые файлы
        if entry.is_file() and should_ignore(name, IGNORE_FILES):
            continue
        
        # Только папки
        if only_dirs and entry.is_file():
            continue
        
        # Только .py файлы
        if only_py and entry.is_file() and not name.endswith('.py'):
            continue
        
        filtered_entries.append(entry)
    
    # Построить дерево
    for i, entry in enumerate(filtered_entries):
        is_last = (i == len(filtered_entries) - 1)
        connector = "└── " if is_last else "├── "
        
        if entry.is_dir():
            icon = get_folder_icon(entry.name)
            if use_colors:
                name_str = f"{Colors.BLUE}{Colors.BOLD}{entry.name}/{Colors.RESET}"
            else:
                name_str = f"{entry.name}/"
            
            lines.append(f"{prefix}{connector}{icon} {name_str}")
            
            # Рекурсия
            extension = "    " if is_last else "│   "
            lines.extend(print_tree(
                entry,
                prefix + extension,
                max_depth,
                current_depth + 1,
                show_hidden,
                only_dirs,
                only_py,
                use_colors
            ))
        else:
            icon = get_file_icon(entry.name)
            if use_colors:
                name_str = f"{Colors.GREEN}{entry.name}{Colors.RESET}"
            else:
                name_str = entry.name
            
            lines.append(f"{prefix}{connector}{icon} {name_str}")
    
    return lines


def count_stats(path: Path, show_hidden: bool = False) -> dict:
    """Посчитать статистику проекта"""
    stats = {
        'dirs': 0,
        'files': 0,
        'py_files': 0,
        'json_files': 0,
        'lines_py': 0,
    }
    
    for root, dirs, files in os.walk(path):
        # Фильтрация папок
        dirs[:] = [d for d in dirs if not should_ignore(d, IGNORE_DIRS)]
        if not show_hidden:
            dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        stats['dirs'] += len(dirs)
        
        for f in files:
            if not show_hidden and f.startswith('.'):
                continue
            if should_ignore(f, IGNORE_FILES):
                continue
            
            stats['files'] += 1
            
            if f.endswith('.py'):
                stats['py_files'] += 1
                # Посчитать строки
                try:
                    file_path = Path(root) / f
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as fp:
                        stats['lines_py'] += sum(1 for _ in fp)
                except:
                    pass
            
            elif f.endswith('.json'):
                stats['json_files'] += 1
    
    return stats


def main():
    parser = argparse.ArgumentParser(description='Показать структуру проекта')
    parser.add_argument('--path', '-p', default='.', help='Путь к папке')
    parser.add_argument('--depth', '-d', type=int, default=4, help='Глубина (по умолчанию 4)')
    parser.add_argument('--output', '-o', help='Сохранить в файл')
    parser.add_argument('--no-hidden', action='store_true', help='Скрыть скрытые файлы')
    parser.add_argument('--only-dirs', action='store_true', help='Только папки')
    parser.add_argument('--only-py', action='store_true', help='Только .py файлы')
    parser.add_argument('--no-color', action='store_true', help='Без цветов')
    parser.add_argument('--stats', action='store_true', help='Показать статистику')
    
    args = parser.parse_args()
    
    path = Path(args.path).resolve()
    
    if not path.exists():
        print(f"❌ Путь не существует: {path}")
        return
    
    # Заголовок
    header = f"\n📂 {path.name}/"
    print(header)
    print("=" * 50)
    
    # Дерево
    use_colors = not args.no_color and not args.output
    lines = print_tree(
        path,
        max_depth=args.depth,
        show_hidden=not args.no_hidden,
        only_dirs=args.only_dirs,
        only_py=args.only_py,
        use_colors=use_colors
    )
    
    output = "\n".join(lines)
    print(output)
    
    # Статистика
    if args.stats:
        print("\n" + "=" * 50)
        stats = count_stats(path, show_hidden=not args.no_hidden)
        print(f"📊 Статистика:")
        print(f"   Папок:       {stats['dirs']}")
        print(f"   Файлов:      {stats['files']}")
        print(f"   .py файлов:  {stats['py_files']}")
        print(f"   .json файлов: {stats['json_files']}")
        print(f"   Строк Python: {stats['lines_py']:,}")
    
    print("=" * 50)
    
    # Сохранить в файл
    if args.output:
        # Без цветов для файла
        lines_no_color = print_tree(
            path,
            max_depth=args.depth,
            show_hidden=not args.no_hidden,
            only_dirs=args.only_dirs,
            only_py=args.only_py,
            use_colors=False
        )
        
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(f"📂 {path.name}/\n")
            f.write("=" * 50 + "\n")
            f.write("\n".join(lines_no_color))
            
            if args.stats:
                stats = count_stats(path, show_hidden=not args.no_hidden)
                f.write("\n\n" + "=" * 50 + "\n")
                f.write(f"📊 Статистика:\n")
                f.write(f"   Папок:       {stats['dirs']}\n")
                f.write(f"   Файлов:      {stats['files']}\n")
                f.write(f"   .py файлов:  {stats['py_files']}\n")
                f.write(f"   .json файлов: {stats['json_files']}\n")
                f.write(f"   Строк Python: {stats['lines_py']:,}\n")
        
        print(f"\n✅ Сохранено в: {args.output}")


if __name__ == "__main__":
    main()
