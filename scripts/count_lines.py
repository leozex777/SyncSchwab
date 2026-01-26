
# count_lines.py
# scripts.count_lines.py

"""
Подсчет количества строк кода в проекте.

Использование:
    python scripts/count_lines.py
    python scripts/count_lines.py --details
    python scripts/count_lines.py --by-folder
"""

import os
from pathlib import Path
from typing import Dict, Tuple

# Папки для исключения
EXCLUDE_DIRS = {
    '__pycache__',
    '.git',
    '.idea',
    'venv',
    'env',
    '.venv',
    'node_modules',
    'logs',
    '.pytest_cache',
    'htmlcov',
    'dist',
    'build',
    '*.egg-info',
}

# Расширения файлов для подсчета
INCLUDE_EXTENSIONS = {
    '.py',
    '.json',
    '.md',
    '.txt',
    '.yaml',
    '.yml',
    '.toml',
    '.env',
    '.html',
    '.css',
    '.js',
}


def should_exclude_dir(dir_name: str) -> bool:
    """Проверить, нужно ли исключить папку"""
    return dir_name in EXCLUDE_DIRS or dir_name.startswith('.')


def count_lines_in_file(file_path: Path) -> Tuple[int, int, int]:
    """
    Подсчитать строки в файле.

    Returns:
        (total_lines, code_lines, blank_lines)
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        total = len(lines)
        blank = sum(1 for line in lines if line.strip() == '')
        code = total - blank

        return total, code, blank

    except (OSError, IOError, PermissionError, UnicodeDecodeError):
        return 0, 0, 0


def count_project_lines(root_dir: Path = None, details: bool = False) -> Dict:
    """
    Подсчитать строки во всем проекте.

    Args:
        root_dir: Корневая папка проекта
        details: Показывать детали по каждому файлу

    Returns:
        Словарь со статистикой
    """
    if root_dir is None:
        root_dir = Path(__file__).parent.parent  # Корень проекта

    stats = {
        'total_files': 0,
        'total_lines': 0,
        'code_lines': 0,
        'blank_lines': 0,
        'by_extension': {},
        'by_folder': {},
        'files': [],
    }

    for root, dirs, files in os.walk(root_dir):
        # Исключить папки
        dirs[:] = [d for d in dirs if not should_exclude_dir(d)]

        root_path = Path(root)
        relative_root = root_path.relative_to(root_dir)

        for file_name in files:
            file_path = root_path / file_name
            ext = file_path.suffix.lower()

            # Только нужные расширения
            if ext not in INCLUDE_EXTENSIONS:
                continue

            total, code, blank = count_lines_in_file(file_path)

            if total == 0:
                continue

            stats['total_files'] += 1
            stats['total_lines'] += total
            stats['code_lines'] += code
            stats['blank_lines'] += blank

            # По расширению
            if ext not in stats['by_extension']:
                stats['by_extension'][ext] = {'files': 0, 'lines': 0, 'code': 0}
            stats['by_extension'][ext]['files'] += 1
            stats['by_extension'][ext]['lines'] += total
            stats['by_extension'][ext]['code'] += code

            # По папке
            folder = str(relative_root) if str(relative_root) != '.' else 'root'
            if folder not in stats['by_folder']:
                stats['by_folder'][folder] = {'files': 0, 'lines': 0, 'code': 0}
            stats['by_folder'][folder]['files'] += 1
            stats['by_folder'][folder]['lines'] += total
            stats['by_folder'][folder]['code'] += code

            # Детали файла
            if details:
                stats['files'].append({
                    'path': str(file_path.relative_to(root_dir)),
                    'total': total,
                    'code': code,
                    'blank': blank,
                })

    return stats


def print_report(stats: Dict, details: bool = False, by_folder: bool = False):
    """Вывести отчет"""

    print("\n" + "=" * 60)
    print("📊 PROJECT LINE COUNT REPORT")
    print("=" * 60)

    print(f"\n📁 Total Files:    {stats['total_files']:,}")
    print(f"📝 Total Lines:    {stats['total_lines']:,}")
    print(f"💻 Code Lines:     {stats['code_lines']:,}")
    print(f"⬜ Blank Lines:    {stats['blank_lines']:,}")

    # По расширению
    print("\n" + "-" * 40)
    print("📎 BY EXTENSION:")
    print("-" * 40)
    print(f"{'Ext':<10} {'Files':>8} {'Lines':>10} {'Code':>10}")
    print("-" * 40)

    for ext, data in sorted(stats['by_extension'].items(), key=lambda x: x[1]['lines'], reverse=True):
        print(f"{ext:<10} {data['files']:>8} {data['lines']:>10,} {data['code']:>10,}")

    # По папке
    if by_folder:
        print("\n" + "-" * 60)
        print("📂 BY FOLDER:")
        print("-" * 60)
        print(f"{'Folder':<35} {'Files':>8} {'Lines':>10}")
        print("-" * 60)

        for folder, data in sorted(stats['by_folder'].items(), key=lambda x: x[1]['lines'], reverse=True):
            folder_display = folder[:33] + '..' if len(folder) > 35 else folder
            print(f"{folder_display:<35} {data['files']:>8} {data['lines']:>10,}")

    # Детали по файлам
    if details and stats['files']:
        print("\n" + "-" * 70)
        print("📄 FILES (sorted by lines):")
        print("-" * 70)
        print(f"{'File':<50} {'Total':>8} {'Code':>8}")
        print("-" * 70)

        for file_info in sorted(stats['files'], key=lambda x: x['total'], reverse=True)[:30]:
            path = file_info['path']
            path_display = '...' + path[-47:] if len(path) > 50 else path
            print(f"{path_display:<50} {file_info['total']:>8,} {file_info['code']:>8,}")

        if len(stats['files']) > 30:
            print(f"... and {len(stats['files']) - 30} more files")

    print("\n" + "=" * 60)


def main():
    """Главная функция"""
    import argparse

    parser = argparse.ArgumentParser(description='Count lines in project')
    parser.add_argument('--details', '-d', action='store_true', help='Show file details')
    parser.add_argument('--by-folder', '-f', action='store_true', help='Show by folder')
    parser.add_argument('--path', '-p', type=str, default=None, help='Project path')

    args = parser.parse_args()

    root_dir = Path(args.path) if args.path else None

    stats = count_project_lines(root_dir, details=args.details)
    print_report(stats, details=args.details, by_folder=args.by_folder)

    return stats


if __name__ == '__main__':
    main()