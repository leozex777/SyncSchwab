
# client_details.py
# app.gui.components.client_details

import streamlit as st
from app.gui.utils.env_manager import load_client_from_env
from app.gui.utils.styles import apply_tab_button_styles
import pandas as pd


def render():
    """Отрисовка Client Details"""

    if not st.session_state.selected_client_id:
        return

    if st.session_state.get('show_client_management', False):
        return

    client_manager = st.session_state.client_manager
    selected = client_manager.get_client(st.session_state.selected_client_id)
    env_data = load_client_from_env(st.session_state.selected_client_id)

    st.markdown(f"### 📋 Client: {selected.name}")

    # Применить стили
    apply_tab_button_styles()

    # Получить текущую вкладку
    current_tab = st.session_state.get('client_details_tab', 'Account Information')

    # Кнопки-вкладки (4 вкладки)
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        btn_type1 = "primary" if current_tab == 'Account Information' else "secondary"
        if st.button("📊 Account Information", type=btn_type1, width='stretch', key="detail_tab_account"):
            st.session_state.client_details_tab = 'Account Information'
            st.rerun()

    with col2:
        btn_type2 = "primary" if current_tab == 'Client Settings' else "secondary"
        if st.button("⚙️ Client Settings", type=btn_type2, width='stretch', key="detail_tab_settings"):
            st.session_state.client_details_tab = 'Client Settings'
            st.rerun()

    with col3:
        btn_type3 = "primary" if current_tab == 'History' else "secondary"
        if st.button("📈 History", type=btn_type3, width='stretch', key="detail_tab_history"):
            st.session_state.client_details_tab = 'History'
            st.rerun()

    with col4:
        btn_type4 = "primary" if current_tab == 'Optional Tab' else "secondary"
        if st.button("ℹ️ Optional Tab", type=btn_type4, width='stretch', key="detail_tab_optional"):
            st.session_state.client_details_tab = 'Optional Tab'
            st.rerun()

    st.markdown("---")

    # Отобразить контент
    if current_tab == 'Account Information':
        _render_account_information(selected, env_data)
    elif current_tab == 'Client Settings':
        _render_client_settings(selected, env_data, client_manager)
    elif current_tab == 'History':
        _render_client_history(selected)
    else:
        _render_optional_tab(selected)


def _render_account_information(selected, env_data):
    """Вкладка с информацией о счете клиента (из кэша)"""

    from app.core.cache_manager import get_cached_client, update_client_cache

    # Проверить credentials
    if not env_data.get('key_id'):
        st.warning("⚠️ Client credentials not configured properly.")
        return

    # Получить данные из КЭША
    cached = get_cached_client(selected.id)

    # Если кэш пустой - загрузить
    if not cached:
        with st.spinner("Loading..."):
            cached = update_client_cache(selected.id)

    if not cached:
        st.error("❌ Could not load account data. Click Refresh.")
        return

    try:
        # Данные из кэша
        balances = cached.get('balances', {})
        positions = cached.get('positions', [])

        # Компактные метрики
        col1, col2, col3, col4, col5, col6 = st.columns(6)

        with col1:
            st.markdown(f"**Account**<br>{env_data.get('account_number', 'N/A')}", unsafe_allow_html=True)

        with col2:
            total_value = balances.get('liquidation_value', 0)
            st.markdown(f"**Total Value**<br>${total_value:,.0f}", unsafe_allow_html=True)

        with col3:
            cash_balance = balances.get('cash_balance', 0)
            st.markdown(f"**Cash**<br>${cash_balance:,.0f}", unsafe_allow_html=True)

        with col4:
            positions_value = sum(p.get('market_value', 0) for p in positions) if positions else 0
            st.markdown(f"**Positions Value**<br>${positions_value:,.2f}", unsafe_allow_html=True)

        with col5:
            buying_power = balances.get('buying_power', 0)
            st.markdown(f"**Buying Power**<br>${buying_power:,.0f}", unsafe_allow_html=True)

        with col6:
            st.markdown(f"**Open Positions**<br>{len(positions)}", unsafe_allow_html=True)

        st.markdown("---")

        # Компактная таблица позиций
        if positions:
            st.markdown("**Positions**")

            # Посчитать итоги
            total_pl = sum(p.get('unrealized_pl', 0) for p in positions)
            total_cost = sum(p.get('average_price', 0) * p.get('quantity', 0) for p in positions)
            total_pl_pct = (total_pl / total_cost * 100) if total_cost > 0 else 0

            positions_df = pd.DataFrame([
                {
                    'Symbol': p.get('symbol', 'N/A'),
                    'Qty': int(p.get('quantity', 0)),
                    'Mkt Value': f"${p.get('market_value', 0):,.2f}",
                    'P&L': f"${p.get('unrealized_pl', 0):+,.2f}",
                }
                for p in positions
            ])

            st.dataframe(
                positions_df,
                width='stretch',
                hide_index=True,
                height=min(len(positions) * 35 + 38, 400)
            )

            # Компактный summary
            st.markdown(f"""
            <div style='background-color: #f0f2f6; padding: 10px; border-radius: 5px; text-align: center;'>
                <span style='font-size: 14px;'>📊 <b>Summary:</b></span> &nbsp;&nbsp;
                <span style='font-size: 16px; font-weight: bold; color: {"green" if total_pl >= 0 else "red"};'>
                    P&L: ${total_pl:+,.2f} ({total_pl_pct:+.1f}%)
                </span> &nbsp; | &nbsp;
                <span style='font-size: 14px;'>
                    Cost: <b>${total_cost:,.2f}</b>
                </span> &nbsp; | &nbsp;
                <span style='font-size: 14px;'>
                    Market: <b>${positions_value:,.2f}</b>
                </span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No open positions")

    except Exception as e:
        st.error(f"❌ Error loading account data: {e}")


def _render_client_settings(selected, env_data, client_manager):
    """Объединенная вкладка: Client Info + Individual Settings"""

    # Счетчик для сброса формы
    counter = st.session_state.get(f'client_settings_form_counter_{selected.id}', 0)

    current_settings = selected.settings

    # ═══════════════════════════════════════════════════════════════
    # ДВЕ КОЛОНКИ
    # ═══════════════════════════════════════════════════════════════

    col_left, col_right = st.columns(2)

    # ═══════════════════════════════════════════════════════════════
    # ЛЕВАЯ КОЛОНКА: Client Information
    # ═══════════════════════════════════════════════════════════════

    with col_left:
        st.markdown("**Client Information:**")

        st.write(f"Name: {selected.name}")
        st.write(f"Account: {env_data.get('account_number', 'N/A')}")
        st.write(f"Status: {'✅ Active' if selected.enabled else '⏸️ Inactive'}")

        st.write("")  # Spacer

        # Кнопка Enable/Disable
        if st.button(
                "⏸️ Disable Client" if selected.enabled else "✅ Enable Client",
                type="primary" if not selected.enabled else "secondary",
                key="client_toggle_btn"
        ):
            client_manager.toggle_client(selected.id)
            st.rerun()

    # ═══════════════════════════════════════════════════════════════
    # ПРАВАЯ КОЛОНКА: Current Settings + Margin Settings
    # ═══════════════════════════════════════════════════════════════

    with col_right:
        st.markdown("**Current Settings:**")

        # Получить данные клиента из кэша
        from app.core.cache_manager import get_cached_client
        cached = get_cached_client(selected.id)
        slave_equity = 0
        if cached:
            slave_equity = cached.get('balances', {}).get('liquidation_value', 0)

        # CSS для скрытия "Press Enter to apply" и выравнивания полей
        st.markdown("""
            <style>
            div[data-testid="stTextInput"] div[data-testid="InputInstructions"] {
                display: none;
            }
            div[data-testid="stTextInput"] {
                margin-top: -2px;
            }
            </style>
        """, unsafe_allow_html=True)

        # Scale Method + Value (две колонки)
        scale_col1, scale_col2 = st.columns([1, 1])
        
        with scale_col1:
            current_method = current_settings.get('scale_method', 'DYNAMIC_RATIO')
            
            # Если нет кэша — FIXED_AMOUNT недоступен (показываем оба, но с пометкой)
            if slave_equity > 0:
                scale_options = ['DYNAMIC_RATIO', 'FIXED_AMOUNT']
                scale_index = 1 if current_method == 'FIXED_AMOUNT' else 0
            else:
                # Показываем FIXED_AMOUNT как disabled
                scale_options = ['DYNAMIC_RATIO', 'FIXED_AMOUNT (no data)']
                scale_index = 0  # Всегда DYNAMIC_RATIO если нет кэша
            
            scale_method_raw = st.selectbox(
                "Scale Method:",
                scale_options,
                index=scale_index,
                key=f"client_scale_{selected.id}_{counter}"
            )
            
            # Определить реальный метод
            if scale_method_raw == 'FIXED_AMOUNT (no data)':
                scale_method = 'DYNAMIC_RATIO'  # Fallback
                st.caption("⚠️ Start Auto Sync to enable FIXED_AMOUNT")
            else:
                scale_method = scale_method_raw
        
        with scale_col2:
            if scale_method == 'DYNAMIC_RATIO':
                # Usage percent для DYNAMIC_RATIO (по умолчанию 100%)
                usage_percent = st.number_input(
                    "Usage %:",
                    min_value=1,
                    max_value=100,
                    value=int(current_settings.get('usage_percent', 100)),
                    step=5,
                    key=f"client_usage_percent_{selected.id}_{counter}",
                    help="Percentage of slave equity to use for synchronization"
                )
                fixed_amount = None
            else:
                # Fixed amount для FIXED_AMOUNT (в долларах)
                current_fixed = current_settings.get('fixed_amount')
                
                if current_fixed:
                    # Уже настроенный FIXED_AMOUNT - number_input
                    fixed_amount = st.number_input(
                        "Amount $:",
                        value=int(current_fixed),
                        step=1000,
                        key=f"client_fixed_amount_{selected.id}_{counter}",
                        help=f"Account equity: ${slave_equity:,.0f}"
                    )
                else:
                    # Новый FIXED_AMOUNT - text_input с placeholder
                    amount_str = st.text_input(
                        "Amount $:",
                        value="",
                        placeholder="Enter amount",
                        key=f"client_fixed_amount_{selected.id}_{counter}",
                        help=f"Account equity: ${slave_equity:,.0f}",
                        autocomplete="off"
                    )
                    # Конвертировать в число
                    try:
                        fixed_amount = int(amount_str) if amount_str.strip() else None
                    except ValueError:
                        fixed_amount = None
                
                usage_percent = 100

        # Quantity Rounding
        rounding_method = st.selectbox(
            "Quantity Rounding:",
            ['ROUND_DOWN', 'ROUND_NEAREST', 'ROUND_UP'],
            index=['ROUND_DOWN', 'ROUND_NEAREST', 'ROUND_UP'].index(
                current_settings.get('rounding_method', 'ROUND_NEAREST')
            ),
            key=f"client_rounding_{selected.id}_{counter}"
        )

        # Threshold Slider
        threshold = st.slider(
            f"Threshold: {current_settings.get('threshold', 0.03) * 100:.1f}%",
            min_value=0.0,
            max_value=10.0,
            value=current_settings.get('threshold', 0.03) * 100,
            step=0.5,
            format="%.2f",
            key=f"client_threshold_{selected.id}_{counter}"
        ) / 100

        # ═══════════════════════════════════════════════════════════════
        # MARGIN SETTINGS (справа внизу)
        # ═══════════════════════════════════════════════════════════════

        st.markdown("**Margin Settings:**")

        # Проверить разрешение маржи от Schwab (cached уже получен выше)
        schwab_allows_margin = False
        if cached:
            balances = cached.get('balances', {})
            buying_power = balances.get('buying_power', 0)
            cash_balance = balances.get('cash_balance', 0)
            schwab_allows_margin = buying_power > cash_balance * 1.1  # 10% buffer
        
        if not schwab_allows_margin:
            st.warning("⚠️ Margin not available for this account (Schwab restriction)")
            use_margin = False
            margin_percent = 0
        else:
            # Use Margin checkbox
            use_margin = st.checkbox(
                "Use Margin",
                value=current_settings.get('use_margin', False),
                key=f"client_use_margin_{selected.id}_{counter}",
                help="Enable margin buffer for this client. Margin allows small overspend for slippage protection."
            )

            # Margin Percent slider (только если use_margin включен)
            if use_margin:
                margin_percent = st.slider(
                    "Margin Buffer:",
                    min_value=0,
                    max_value=100,
                    value=current_settings.get('margin_percent', 5),
                    step=5,
                    format="%d%%",
                    key=f"client_margin_percent_{selected.id}_{counter}",
                    help="Percent of Total Value to use as margin buffer. 5-10% recommended for slippage protection."
                )

                # Показать расчёт
                if cached:
                    total_value = balances.get('liquidation_value', 0)
                    positions_value = sum(p.get('market_value', 0) for p in cached.get('positions', []))
                    max_positions = total_value * (1 + margin_percent / 100)
                    available = max(0, max_positions - positions_value)
                    
                    st.caption(f"📊 Max positions: ${max_positions:,.0f} | Available: ${available:,.0f}")
                
                if margin_percent > 20:
                    st.warning(f"⚠️ {margin_percent}% margin increases risk!")
            else:
                margin_percent = 0
                st.caption("💡 Margin disabled - using cash balance only")

        st.write("---")  # Spacer

        # ═══════════════════════════════════════════════════════════════
        # КНОПКИ SAVE / RESET
        # ═══════════════════════════════════════════════════════════════

        col_save, col_reset = st.columns(2)

        with col_save:
            if st.button("💾 Save Settings", type="primary", width='stretch'):
                # Автокоррекция fixed_amount (тихо, без уведомлений)
                corrected_fixed_amount = fixed_amount
                amount_was_corrected = False
                save_slave_equity_nomin = current_settings.get('slave_equity_nomin')
                
                if scale_method == 'FIXED_AMOUNT' and slave_equity > 0:
                    min_amount = int(slave_equity * 0.1)
                    max_amount = int(slave_equity)
                    
                    # Коррекция amount
                    if fixed_amount is None or fixed_amount < min_amount:
                        corrected_fixed_amount = min_amount
                        amount_was_corrected = True
                    elif fixed_amount > max_amount:
                        corrected_fixed_amount = max_amount
                        amount_was_corrected = True
                    
                    # Всегда обновлять slave_equity_nomin при Save FIXED_AMOUNT
                    save_slave_equity_nomin = slave_equity
                
                updated_settings = {
                    'scale_method': scale_method,
                    'usage_percent': usage_percent,
                    'fixed_amount': corrected_fixed_amount,
                    'slave_equity_nomin': save_slave_equity_nomin,
                    'threshold': threshold,
                    'rounding_method': rounding_method,
                    'history_file': current_settings.get('history_file'),
                    'use_margin': use_margin,
                    'margin_percent': margin_percent
                }

                client_manager.update_client(
                    selected.id,
                    {'settings': updated_settings}
                )

                # Обновить counter чтобы поле обновилось с новым значением
                if amount_was_corrected:
                    st.session_state[f'client_settings_form_counter_{selected.id}'] = counter + 1
                
                st.rerun()

        with col_reset:
            if st.button("🔄 Reset to Defaults", width='stretch'):
                reset_settings = {
                    'scale_method': 'DYNAMIC_RATIO',
                    'usage_percent': 100,
                    'fixed_amount': None,
                    'slave_equity_nomin': None,
                    'threshold': 0.03,
                    'rounding_method': 'ROUND_NEAREST',
                    'history_file': current_settings.get('history_file'),
                    'use_margin': False,
                    'margin_percent': 0
                }

                client_manager.update_client(
                    selected.id,
                    {'settings': reset_settings}
                )

                st.session_state[f'client_settings_form_counter_{selected.id}'] = counter + 1
                st.toast("✅ Reset to defaults!")
                st.rerun()


def _render_client_history(selected):
    """История синхронизаций клиента с фильтрацией"""
    
    import hashlib
    from pathlib import Path
    from app.core.json_utils import load_json
    from app.core.config_cache import ConfigCache

    # ═══════════════════════════════════════════════════════════════
    # ЗНАЧЕНИЯ ПО УМОЛЧАНИЮ
    # ═══════════════════════════════════════════════════════════════
    
    default_status = "All"
    default_lines = "50"
    default_search = ""
    
    # Уникальный префикс для session_state этого клиента
    prefix = f"hist_{selected.id}_"

    # ═══════════════════════════════════════════════════════════════
    # ИНИЦИАЛИЗАЦИЯ SESSION STATE
    # ═══════════════════════════════════════════════════════════════
    
    if f"{prefix}status_filter" not in st.session_state:
        st.session_state[f"{prefix}status_filter"] = default_status
    if f"{prefix}lines_count" not in st.session_state:
        st.session_state[f"{prefix}lines_count"] = default_lines
    if f"{prefix}search" not in st.session_state:
        st.session_state[f"{prefix}search"] = default_search
    if f"{prefix}search_applied" not in st.session_state:
        st.session_state[f"{prefix}search_applied"] = default_search

    # ═══════════════════════════════════════════════════════════════
    # ОПРЕДЕЛИТЬ РЕЖИМ И ФАЙЛ ИСТОРИИ
    # ═══════════════════════════════════════════════════════════════
    
    general_settings = ConfigCache.get_general_settings()
    operating_mode = general_settings.get('operating_mode', 'monitor')
    
    # Получить monitor_sync_mode из general_settings
    monitor_sync_mode = general_settings.get("monitor_sync_mode", "live")
    
    # Выбрать файл истории в зависимости от режима
    base_history_file = selected.settings.get(
        'history_file', 
        f'data/clients/{selected.id}_history.json'
    )
    
    if operating_mode == 'live':
        history_file = base_history_file
        section_title = "Order History"
        mode_icon = "🔴"
    elif operating_mode == 'monitor':
        if monitor_sync_mode == 'live':
            # Monitor Live Delta → Order History (реальные ордера)
            history_file = base_history_file
            section_title = "Order History"
            mode_icon = "🔴"
        else:
            # Monitor Simulation Delta → Sync History (dry run)
            if base_history_file.endswith('.json'):
                history_file = base_history_file.replace('.json', '_dry.json')
            else:
                history_file = base_history_file + '_dry'
            section_title = "Sync History"
            mode_icon = "🔶"
    else:
        # Simulation: использовать _dry.json
        if base_history_file.endswith('.json'):
            history_file = base_history_file.replace('.json', '_dry.json')
        else:
            history_file = base_history_file + '_dry'
        section_title = "Sync History"
        mode_icon = "🔶"

    # ═══════════════════════════════════════════════════════════════
    # ЗАГОЛОВОК И КНОПКИ
    # ═══════════════════════════════════════════════════════════════

    col_title, col_spacer, col_reset, col_download = st.columns([2, 1, 1, 1])

    with col_title:
        # mode_icon уже определён выше
        st.markdown(f"**{mode_icon} {section_title}**")

    with col_reset:
        if st.button("🔄 Reset", width='stretch', help="Reset all filters", 
                     key=f"{prefix}reset_btn"):
            st.session_state[f"{prefix}status_filter"] = default_status
            st.session_state[f"{prefix}lines_count"] = default_lines
            st.session_state[f"{prefix}search"] = default_search
            st.session_state[f"{prefix}search_applied"] = default_search
            st.rerun()

    with col_download:
        download_placeholder = st.empty()

    # ═══════════════════════════════════════════════════════════════
    # ФИЛЬТРЫ UI
    # ═══════════════════════════════════════════════════════════════

    col1, col2, col3, col4 = st.columns([1, 1, 0.17, 1.83])

    with col1:
        status_options = ["All", "✅ Success", "❌ Failed", "➖ No Orders"]
        st.selectbox(
            "Status",
            status_options,
            key=f"{prefix}status_filter"
        )

    with col2:
        lines_options = ["20", "50", "100", "200"]
        st.selectbox(
            "Show",
            lines_options,
            key=f"{prefix}lines_count"
        )

    with col3:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        search_clicked = st.button("🔍", key=f"{prefix}search_btn", help="Apply search")

    with col4:
        search_text = st.text_input(
            "Search",
            value=st.session_state[f"{prefix}search"],
            placeholder="Filter by symbol...",
            key=f"{prefix}search_input",
            label_visibility="visible"
        )

    # Применить поиск
    if search_clicked or search_text != st.session_state[f"{prefix}search_applied"]:
        st.session_state[f"{prefix}search"] = search_text
        st.session_state[f"{prefix}search_applied"] = search_text
        if search_clicked:
            st.rerun()

    applied_search = st.session_state[f"{prefix}search_applied"]
    status_filter = st.session_state[f"{prefix}status_filter"]
    lines_limit = int(st.session_state[f"{prefix}lines_count"])

    # ═══════════════════════════════════════════════════════════════
    # ЗАГРУЗКА ИСТОРИИ
    # ═══════════════════════════════════════════════════════════════

    history_path = Path(history_file)
    
    if not history_path.exists():
        st.info(f"No {section_title.lower()} yet")
        return

    try:
        history = load_json(str(history_path), default=[])
    except (KeyError, TypeError, ValueError):
        history = []

    if not history:
        st.info(f"No {section_title.lower()} yet")
        return

    total_entries = len(history)

    # ═══════════════════════════════════════════════════════════════
    # ФИЛЬТРАЦИЯ
    # ═══════════════════════════════════════════════════════════════

    filtered_history = []

    for entry in history:
        summary = entry.get('summary', {})
        total_deltas = summary.get('total_deltas', len(entry.get('deltas', [])))
        orders_success = summary.get('orders_success', 0)
        orders_failed = summary.get('orders_failed', 0)

        # Фильтр по статусу
        if status_filter == "✅ Success":
            if orders_success == 0:
                continue
        elif status_filter == "❌ Failed":
            if orders_failed == 0:
                continue
        elif status_filter == "➖ No Orders":
            if total_deltas > 0:
                continue

        # Фильтр по тексту (поиск в symbols)
        if applied_search:
            deltas = entry.get('deltas', {})
            symbols_str = " ".join(deltas.keys()) if isinstance(deltas, dict) else ""
            if applied_search.lower() not in symbols_str.lower():
                continue

        filtered_history.append(entry)

    # Ограничить и отсортировать (новые первые)
    display_history = list(reversed(filtered_history))[:lines_limit]

    # ═══════════════════════════════════════════════════════════════
    # КНОПКА DOWNLOAD
    # ═══════════════════════════════════════════════════════════════

    with download_placeholder:
        if display_history:
            import json
            download_content = json.dumps(display_history, indent=2, default=str)
            
            # Имя файла
            base_name = f"{selected.id}_history"
            if status_filter != "All":
                filename = f"{base_name}_filtered.json"
            elif applied_search:
                filename = f"{base_name}_{applied_search}.json"
            else:
                filename = f"{base_name}.json"

            content_hash = hashlib.md5(download_content.encode()).hexdigest()[:8]
            
            st.download_button(
                "📥 Download",
                data=download_content,
                file_name=filename,
                mime="application/json",
                width='stretch',
                key=f"{prefix}download_{content_hash}",
                help=f"Download {len(display_history)} entries"
            )
        else:
            st.button("📥 Download", disabled=True, width='stretch', 
                      key=f"{prefix}download_disabled")

    # ═══════════════════════════════════════════════════════════════
    # ОТОБРАЖЕНИЕ ИСТОРИИ
    # ═══════════════════════════════════════════════════════════════

    st.markdown("")

    if not display_history:
        st.info("No entries match the filter")
        return

    # Построить HTML для истории
    history_html = []

    for entry in display_history:
        timestamp = entry.get('timestamp', '')[:16].replace('T', ' ')
        entry_mode = entry.get('operating_mode', '')
        
        # Иконка режима записи
        if entry_mode == 'simulation':
            entry_icon = "🔶"
        elif entry_mode == 'live':
            entry_icon = "🔴"
        else:
            entry_icon = "🧪"

        summary = entry.get('summary', {})
        total_deltas = summary.get('total_deltas', len(entry.get('deltas', [])))
        orders_success = summary.get('orders_success', 0)
        orders_failed = summary.get('orders_failed', 0)
        
        # Статус
        if total_deltas == 0:
            status_icon = "➖"
            border_color = "#666666"
        elif orders_success > 0 and orders_failed == 0:
            status_icon = "✅"
            border_color = "#4CAF50"
        elif orders_failed > 0:
            status_icon = "❌"
            border_color = "#ff4444"
        else:
            status_icon = "⚠️"
            border_color = "#ff8800"

        # Символы
        deltas = entry.get('deltas', {})
        if isinstance(deltas, dict) and deltas:
            symbols = ", ".join([f"{k}: {v:+d}" for k, v in deltas.items()])
        else:
            symbols = "No changes"

        # Scale
        scale = entry.get('scale', 0)
        scale_str = f"{scale * 100:.1f}%"

        history_html.append(
            f'<div style="font-family: \'Consolas\', monospace; '
            f'font-size: 12px; padding: 8px 10px; margin: 3px 0; '
            f'background: var(--secondary-background-color, #1e1e1e); '
            f'border-radius: 4px; border-left: 4px solid {border_color};">'
            f'{status_icon} <b>{timestamp}</b> {entry_icon} | '
            f'Scale: {scale_str} | Orders: {orders_success}/{total_deltas} | '
            f'<span style="color: #888;">{symbols}</span>'
            f'</div>'
        )

    st.markdown(
        f'''
        <div style="max-height: 400px; overflow-y: auto; 
                    border: 1px solid var(--secondary-background-color, #333); 
                    border-radius: 5px; padding: 8px; 
                    background: var(--background-color, #0e1117);">
            {"".join(history_html)}
        </div>
        ''',
        unsafe_allow_html=True
    )

    st.caption(
        f"Showing {len(display_history)} of {len(filtered_history)} filtered "
        f"({total_entries} total)"
    )


def _render_optional_tab(_selected):
    """Опциональная вкладка (пустая, для будущего использования)"""

    st.markdown("**Optional Tab**")
    st.info("This tab is reserved for future functionality.")

    # Можно добавить сюда любой контент в будущем
    # Например:
    # - Графики производительности
    # - Сравнение с Main Account
    # - Расширенные настройки
    # - Логи конкретного клиента
