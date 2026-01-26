# log_viewer.py
# app.gui.components.log_viewer

import streamlit as st
import hashlib
from app.core.paths import LOGS_DIR
from app.gui.utils.styles import apply_tab_button_styles

# ═══════════════════════════════════════════════════════════════
# ЗНАЧЕНИЯ ПО УМОЛЧАНИЮ
# ═══════════════════════════════════════════════════════════════

DEFAULT_LEVEL = "All"
DEFAULT_LOG_FILE = "app_schwab.log"
DEFAULT_LINES = "100"
DEFAULT_SEARCH = ""


def render():
    """Отрисовка страницы логов"""

    apply_tab_button_styles()

    # ═══════════════════════════════════════════════════════════════
    # ИНИЦИАЛИЗАЦИЯ SESSION STATE
    # ═══════════════════════════════════════════════════════════════

    if "log_level_filter" not in st.session_state:
        st.session_state.log_level_filter = DEFAULT_LEVEL
    if "log_file_select" not in st.session_state:
        st.session_state.log_file_select = DEFAULT_LOG_FILE
    if "log_lines_count" not in st.session_state:
        st.session_state.log_lines_count = DEFAULT_LINES
    if "log_search" not in st.session_state:
        st.session_state.log_search = DEFAULT_SEARCH
    if "log_search_applied" not in st.session_state:
        st.session_state.log_search_applied = DEFAULT_SEARCH

    # ═══════════════════════════════════════════════════════════════
    # ЗАГОЛОВОК И КНОПКИ (в одну линию)
    # ═══════════════════════════════════════════════════════════════

    col_title, col_spacer, col_reset, col_download, col_clear = st.columns([2, 1, 1, 1, 1])

    with col_title:
        st.markdown("### 📋 Log File")

    with col_reset:
        if st.button("🔄 Reset", width='stretch', help="Reset all filters to default"):
            # Сброс всех фильтров к значениям по умолчанию
            st.session_state.log_level_filter = DEFAULT_LEVEL
            st.session_state.log_file_select = DEFAULT_LOG_FILE
            st.session_state.log_lines_count = DEFAULT_LINES
            st.session_state.log_search = DEFAULT_SEARCH
            st.session_state.log_search_applied = DEFAULT_SEARCH
            st.rerun()

    with col_download:
        # Placeholder - будет обновлен после фильтрации
        download_placeholder = st.empty()

    with col_clear:
        clear_placeholder = st.empty()

    # ═══════════════════════════════════════════════════════════════
    # ФИЛЬТРЫ UI
    # ═══════════════════════════════════════════════════════════════

    col1, col2, col3, col4, col5 = st.columns([1, 1.5, 1, 0.23, 1.77])

    with col1:
        level_options = ["All", "INFO", "WARNING", "ERROR"]
        level_filter = st.selectbox(
            "Level",
            level_options,
            key="log_level_filter"
        )

    with col2:
        # Список доступных лог-файлов
        log_files_list = ["app_schwab.log", "sync.log", "orders.log", "errors.log"]
        selected_log = st.selectbox(
            "Log File",
            log_files_list,
            key="log_file_select"
        )
        log_file = LOGS_DIR / selected_log

    with col3:
        lines_options = ["50", "100", "200", "500", "1000"]
        lines_values = [50, 100, 200, 500, 1000]

        selected_option = st.selectbox(
            "Show Lines",
            lines_options,
            key="log_lines_count"
        )

        selected_index = lines_options.index(selected_option)
        lines_limit = lines_values[selected_index]

    with col4:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)  # Spacer для выравнивания
        search_clicked = st.button("🔍", key="search_btn", help="Apply search filter")

    with col5:
        search_text = st.text_input(
            "Search",
            value=st.session_state.log_search,
            placeholder="Filter by text... ",
            key="log_search_input",
            label_visibility="visible"
        )

    # Применить поиск при клике на кнопку или изменении текста (Enter)
    if search_clicked or search_text != st.session_state.log_search_applied:
        st.session_state.log_search = search_text
        st.session_state.log_search_applied = search_text
        if search_clicked:
            st.rerun()

    # Использовать применённый поиск
    applied_search = st.session_state.log_search_applied

    # ═══════════════════════════════════════════════════════════════
    # ЧТЕНИЕ ЛОГА (только последние N строк для производительности)
    # ═══════════════════════════════════════════════════════════════

    total_lines = 0
    all_lines = []

    if log_file.exists():
        try:
            # Читаем только последние строки для больших файлов
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                # Сначала посчитаем общее количество строк
                all_content = f.readlines()
                total_lines = len(all_content)
                # Берём последние 1000 строк максимум для обработки
                all_lines = all_content[-1000:] if total_lines > 1000 else all_content
        except (OSError, IOError, PermissionError):
            pass

    # ═══════════════════════════════════════════════════════════════
    # ВЫВОД ЛОГОВ
    # ═══════════════════════════════════════════════════════════════

    st.markdown("")

    if not log_file.exists():
        st.info(f"No log file yet: {selected_log}")
        return

    if not all_lines:
        st.info("Log file is empty.")
        return

    # Применить фильтры
    filtered_lines = []

    for line in all_lines:
        # Фильтр по уровню
        if level_filter != "All":
            if f"| {level_filter}" not in line:
                continue

        # Фильтр по тексту (используем applied_search)
        if applied_search:
            if applied_search.lower() not in line.lower():
                continue

        filtered_lines.append(line)

    # Ограничить количество строк
    display_lines = filtered_lines[-lines_limit:]

    # ═══════════════════════════════════════════════════════════════
    # КНОПКА DOWNLOAD (с отфильтрованными данными)
    # ═══════════════════════════════════════════════════════════════

    with download_placeholder:
        if display_lines:
            download_content = "".join(display_lines)

            # Имя файла зависит от фильтра
            base_name = selected_log.replace('.log', '')
            if level_filter != "All":
                filename = f"{base_name}_{level_filter.lower()}.log"
            elif applied_search:
                filename = f"{base_name}_filtered.log"
            else:
                filename = selected_log

            # Уникальный ключ для download_button (исправление ошибки MediaFileHandler)
            content_hash = hashlib.md5(download_content.encode()).hexdigest()[:8]
            download_key = f"download_{selected_log}_{content_hash}"

            st.download_button(
                "📥 Download Filtered",
                data=download_content,
                file_name=filename,
                mime="text/plain",
                width='stretch',
                key=download_key,
                help=f"Download {len(display_lines)} filtered lines"
            )
        else:
            st.button("📥 Download Filtered", disabled=True, width='stretch')

    # ═══════════════════════════════════════════════════════════════
    # КНОПКА CLEAR LOG (с подтверждением)
    # ═══════════════════════════════════════════════════════════════

    with clear_placeholder:
        if st.button("🗑️ Clear Log", width='stretch'):
            st.session_state['confirm_clear_log'] = True
            st.rerun()

    # Диалог подтверждения
    if st.session_state.get('confirm_clear_log', False):
        st.warning(f"⚠️ Are you sure you want to clear **{selected_log}**? This cannot be undone.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("✅ Yes, Clear", type="primary", width='stretch'):
                if log_file.exists():
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.write("")
                st.session_state['confirm_clear_log'] = False
                st.rerun()
        with col_no:
            if st.button("❌ Cancel", width='stretch'):
                st.session_state['confirm_clear_log'] = False
                st.rerun()
        return

    # ═══════════════════════════════════════════════════════════════
    # ОТОБРАЖЕНИЕ ЛОГОВ (адаптивная тема)
    # ═══════════════════════════════════════════════════════════════

    if display_lines:
        log_html = []

        for line in reversed(display_lines):  # Новые сверху
            line = line.strip()

            # Цвета адаптированы для тёмной и светлой темы через CSS переменные
            if "| ERROR" in line:
                color = "#ff6b6b"
                border_color = "#ff4444"
                icon = "❌"
            elif "| WARNING" in line:
                color = "#ffa94d"
                border_color = "#ff8800"
                icon = "⚠️"
            else:  # INFO
                color = "var(--text-color, #e0e0e0)"
                border_color = "#4a90d9"
                icon = "ℹ️"

            log_html.append(
                f'<div style="font-family: \'Consolas\', \'Monaco\', monospace; '
                f'font-size: 12px; padding: 6px 10px; margin: 2px 0; '
                f'background: var(--secondary-background-color, #1e1e1e); '
                f'color: {color}; border-radius: 4px; '
                f'border-left: 4px solid {border_color}; white-space: pre-wrap; '
                f'word-wrap: break-word;">{icon} {line}</div>'
            )

        st.markdown(
            f'''
            <div style="max-height: 500px; overflow-y: auto; 
                        border: 1px solid var(--secondary-background-color, #333); 
                        border-radius: 5px; padding: 8px; 
                        background: var(--background-color, #0e1117);">
                {"".join(log_html)}
            </div>
            ''',
            unsafe_allow_html=True
        )

        st.caption(f"Showing {len(display_lines)} of {len(filtered_lines)} filtered lines ({total_lines} total)")
    else:
        st.info("No log entries match the filter")