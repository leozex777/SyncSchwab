
# app.core.json_utils

import json
from pathlib import Path
from typing import Any, Dict, List, Union, Optional
from app.core.logger import logger


class JSONFile:
    """Класс для работы с JSON файлами"""

    def __init__(self, file_path: Union[str, Path]):
        """
        Args:
            file_path: Путь к JSON файлу
        """
        self.file_path = Path(file_path)
        self._data = None

    def load(self, default: Any = None) -> Any:
        """Загрузить данные из файла"""
        self._data = load_json(self.file_path, default=default)
        return self._data

    def save(self, data: Any = None) -> None:
        """Сохранить данные в файл"""
        data_to_save = data if data is not None else self._data
        save_json(self.file_path, data_to_save)

    def update(self, updates: Dict) -> None:
        """
        Обновить данные в файле (для словарей)

        Args:
            updates: Словарь с обновлениями
        """
        if self._data is None:
            self._data = self.load(default={})

        if not isinstance(self._data, dict):
            raise TypeError("Can only update dict data")

        self._data.update(updates)
        self.save()
        logger.debug(f"✅ Updated {self.file_path}")

    def append(self, item: Any) -> None:
        """
        Добавить элемент в список

        Args:
            item: Элемент для добавления
        """
        if self._data is None:
            self._data = self.load(default=[])

        if not isinstance(self._data, list):
            raise TypeError("Can only append to list data")

        self._data.append(item)
        self.save()
        logger.debug(f"✅ Appended item to {self.file_path}")

    @property
    def exists(self) -> bool:
        """Проверить существование файла"""
        return self.file_path.exists()

    @property
    def data(self) -> Any:
        """Получить данные (загрузить если нужно)"""
        if self._data is None:
            self.load()
        return self._data


def load_json(
        file_path: Union[str, Path],
        default: Optional[Any] = None,
        create_if_missing: bool = False,
        encoding: str = 'utf-8'
) -> Union[Dict, List, Any]:
    """
    Универсальная загрузка JSON файла

    Args:
        file_path: Путь к JSON файлу
        default: Значение по умолчанию если файл не найден
        create_if_missing: Создать файл с default если не существует
        encoding: Кодировка файла

    Returns:
        Данные из JSON или default

    Raises:
        ValueError: Если JSON невалидный и default не указан
    """
    file_path = Path(file_path)

    # Если файл не существует
    if not file_path.exists():
        if default is not None:
            logger.warning(f"⚠️ File not found: {file_path}, using default")

            # Создать файл если нужно
            if create_if_missing:
                save_json(file_path, default, encoding=encoding)
                logger.info(f"✅ Created new file: {file_path}")

            return default
        else:
            logger.error(f"❌ File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")

    # Загрузить файл
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            data = json.load(f)

        logger.debug(f"✅ Loaded JSON from {file_path}")

        # Показать размер данных
        if isinstance(data, list):
            logger.debug(f"   Loaded {len(data)} items")
        elif isinstance(data, dict):
            logger.debug(f"   Loaded {len(data)} keys")

        return data

    except json.JSONDecodeError as e:
        logger.error(f"❌ Invalid JSON in {file_path}: {e}")
        logger.error(f"   Line {e.lineno}, Column {e.colno}")

        if default is not None:
            logger.warning(f"⚠️ Using default value")
            return default
        else:
            raise ValueError(f"Invalid JSON: {e}") from e

    except Exception as e:
        logger.error(f"❌ Error loading {file_path}: {e}")

        if default is not None:
            return default
        else:
            raise


def save_json(
        file_path: Union[str, Path],
        data: Any,
        indent: int = 2,
        encoding: str = 'utf-8',
        ensure_ascii: bool = False
) -> None:
    """
    Сохранить данные в JSON файл

    Args:
        file_path: Путь к файлу
        data: Данные для сохранения
        indent: Отступ для форматирования
        encoding: Кодировка файла
        ensure_ascii: Экранировать не-ASCII символы
    """
    file_path = Path(file_path)

    try:
        # Создать директорию если не существует
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Сохранить файл
        with open(file_path, 'w', encoding=encoding) as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)

        logger.debug(f"✅ Saved JSON to {file_path}")

    except Exception as e:
        logger.error(f"❌ Error saving JSON to {file_path}: {e}")
        raise