
# log_viewer.py
# app.gui.components.log_viewer

import streamlit as st
from app.core.paths import LOGS_DIR
from app.gui.utils.styles import apply_tab_button_styles


def render():
    """Отрисовка страницы логов"""

    apply_tab_button_styles()

    log_file = LOGS_DIR / "schwab_client.log"

    # Получить все строки лога
    total_lines = 0
    all_lines = []

    if log_file.exists():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            total_lines = len(all_lines)
        except (OSError, IOError, PermissionError):
            pass

    # ═══════════════════════════════════════════════════════════════
    # ЗАГОЛОВОК И КНОПКИ (в одну линию)
    # ═══════════════════════════════════════════════════════════════

    col_title, col_spacer, col_refresh, col_download, col_clear = st.columns([2, 1, 1, 1, 1])

    with col_title:
        st.markdown("### 📋 Log File")

    with col_refresh:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    with col_download:
        # Placeholder - будет обновлен после фильтрации
        download_placeholder = st.empty()

    with col_clear:
        if st.button("🗑️ Clear Log", use_container_width=True):
            if log_file.exists():
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write("")
                st.rerun()

    # ═══════════════════════════════════════════════════════════════
    # ФИЛЬТРЫ UI
    # ═══════════════════════════════════════════════════════════════

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        level_filter = st.selectbox(
            "Level",
            ["All", "DEBUG", "INFO", "WARNING", "ERROR"],
            index=0,
            key="log_level_filter"
        )

    with col2:
        lines_options = [
            f"50 ({total_lines})",
            f"100 ({total_lines})",
            f"200 ({total_lines})",
            f"500 ({total_lines})",
            f"All ({total_lines})"
        ]
        lines_values = [50, 100, 200, 500, "All"]

        selected_option = st.selectbox(
            "Show lines",
            lines_options,
            index=1,
            key="log_lines_count"
        )

        selected_index = lines_options.index(selected_option)
        lines_limit = lines_values[selected_index]

    with col3:
        search_text = st.text_input(
            "Search",
            placeholder="Filter by text...",
            key="log_search"
        )

    # ═══════════════════════════════════════════════════════════════
    # ВЫВОД ЛОГОВ
    # ═══════════════════════════════════════════════════════════════

    st.markdown("")

    if not log_file.exists():
        st.info("No log file yet. Logs will appear after application activity.")
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

        # Фильтр по тексту
        if search_text:
            if search_text.lower() not in line.lower():
                continue

        filtered_lines.append(line)

    # Ограничить количество строк
    if lines_limit != "All":
        display_lines = filtered_lines[-lines_limit:]
    else:
        display_lines = filtered_lines

    # ═══════════════════════════════════════════════════════════════
    # КНОПКА DOWNLOAD (с отфильтрованными данными)
    # ═══════════════════════════════════════════════════════════════

    with download_placeholder:
        if display_lines:
            download_content = "".join(display_lines)

            # Имя файла зависит от фильтра
            if level_filter != "All":
                filename = f"schwab_{level_filter.lower()}.log"
            elif search_text:
                filename = "schwab_filtered.log"
            else:
                filename = "schwab_client.log"

            st.download_button(
                "📥 Download Log",
                data=download_content,
                file_name=filename,
                mime="text/plain",
                use_container_width=True,
                help=f"Download {len(display_lines)} filtered lines"
            )
        else:
            st.button("📥 Download Log", disabled=True, use_container_width=True)

    # ═══════════════════════════════════════════════════════════════
    # ОТОБРАЖЕНИЕ ЛОГОВ
    # ═══════════════════════════════════════════════════════════════

    if display_lines:
        log_html = []

        for line in reversed(display_lines):  # Новые сверху
            line = line.strip()

            if "| ERROR" in line:
                color = "#ff4444"
                bg = "#fff0f0"
                icon = "❌"
            elif "| WARNING" in line:
                color = "#ff8800"
                bg = "#fff8e0"
                icon = "⚠️"
            elif "| DEBUG" in line:
                color = "#888888"
                bg = "#f8f8f8"
                icon = "🔍"
            else:  # INFO
                color = "#333333"
                bg = "#ffffff"
                icon = "ℹ️"

            log_html.append(
                f'<div style="font-family: \'Consolas\', \'Monaco\', monospace; '
                f'font-size: 12px; padding: 6px 10px; margin: 2px 0; '
                f'background: {bg}; color: {color}; border-radius: 4px; '
                f'border-left: 4px solid {color}; white-space: pre-wrap; '
                f'word-wrap: break-word;">{icon} {line}</div>'
            )

        st.markdown(
            f'''
            <div style="max-height: 500px; overflow-y: auto; border: 1px solid #ddd; 
                        border-radius: 5px; padding: 8px; background: #fafafa;">
                {"".join(log_html)}
            </div>
            ''',
            unsafe_allow_html=True
        )

        st.caption(f"Showing {len(display_lines)} of {len(filtered_lines)} filtered lines ({total_lines} total)")
    else:
        st.info("No log entries match the filter")