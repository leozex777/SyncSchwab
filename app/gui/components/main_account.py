# main_account.py
# app.gui.components.main_account

import streamlit as st
from app.gui.components.oauth_wizard import render_oauth_wizard
from app.gui.utils.env_manager import save_main_account_to_env, load_main_account_from_env
from app.core.config import get_main_client
import pandas as pd
from app.gui.utils.styles import apply_tab_button_styles


def render():

    """Отрисовка Main Account Management"""

    st.markdown("### 🏦 Main Account Management")

    # Получить текущую вкладку
    current_tab = st.session_state.get('main_account_tab', 'Account Information')

    # CSS для светло-голубых кнопок-вкладок

    apply_tab_button_styles()

    # Кнопки-вкладки
    col1, col2 = st.columns(2)

    with col1:
        btn_type1 = "primary" if current_tab == 'Account Information' else "secondary"
        if st.button("📊 Account Information", type=btn_type1, width='stretch', key="main_tab_info"):
            st.session_state.main_account_tab = 'Account Information'
            st.rerun()

    with col2:
        btn_type2 = "primary" if current_tab == 'Edit Main Account' else "secondary"
        if st.button("✏️ Edit Main Account", type=btn_type2, width='stretch', key="main_tab_edit"):
            st.session_state.main_account_tab = 'Edit Main Account'
            st.rerun()

    st.markdown("---")

    # Отобразить контент
    if current_tab == 'Account Information':
        _render_account_info()
    else:
        _render_edit_account()


def _render_account_info():
    """Показать информацию о Main Account (из кэша)"""

    from app.core.cache_manager import get_cached_main_account, update_main_account_cache

    # Проверить токен
    client = get_main_client()

    if not client:
        st.warning("⚠️ Main account not authorized. Please authorize in the 'Edit Main Account' tab.")
        return

    # Загрузить данные из .env
    main_data = load_main_account_from_env()

    if not main_data.get('account_number'):
        st.warning("⚠️ Main account not configured. Please configure it in the 'Edit Main Account' tab.")
        return

    # Получить данные из КЭША
    cached = get_cached_main_account()

    # Если кэш пустой - загрузить
    if not cached:
        with st.spinner("Loading..."):
            cached = update_main_account_cache()

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
            st.markdown(f"**Account**<br>{main_data.get('account_number', 'N/A')}", unsafe_allow_html=True)

        with col2:
            total_value = balances.get('liquidation_value', 0)
            st.markdown(f"**Total Value**<br>${total_value:,.0f}", unsafe_allow_html=True)

        with col3:
            cash_balance = balances.get('cash_balance', 0)
            st.markdown(f"**Cash**<br>${cash_balance:,.0f}", unsafe_allow_html=True)

        with col4:
            positions_value = sum(p.get('market_value', 0) for p in positions) if positions else 0
            st.markdown(f"**Positions Value**<br>${positions_value:,.0f}", unsafe_allow_html=True)

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
                    'Mkt Value': f"${p.get('market_value', 0):,.0f}",
                    'P&L': f"${p.get('unrealized_pl', 0):,.0f}",
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
                    P&L: ${total_pl:,.0f} ({total_pl_pct:+.1f}%)
                </span> &nbsp; | &nbsp;
                <span style='font-size: 14px;'>
                    Cost: <b>${total_cost:,.0f}</b>
                </span> &nbsp; | &nbsp;
                <span style='font-size: 14px;'>
                    Market: <b>${positions_value:,.0f}</b>
                </span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No open positions")

    except Exception as e:
        st.error(f"❌ Error loading account data: {e}")


def _render_edit_account():
    """Форма редактирования Main Account"""

    # Проверить наличие токена
    from pathlib import Path
    token_file = Path('tokens/main_tokens.json')

    if not token_file.exists():
        # Токена нет - показать OAuth wizard
        render_oauth_wizard()
        return

    counter = st.session_state.get('main_form_reset_counter', 0)
    main_data = load_main_account_from_env()

    st.markdown("**Main Account Credentials**")

    col1, col2 = st.columns([1, 1])

    with col1:
        account_raw = st.text_input(
            "Account Number *",
            placeholder="12345678",
            key=f"main_edit_account_{counter}"
        )

        if account_raw:
            st.caption(f"Display: {account_raw}")
        elif main_data.get('account_number'):
            st.caption(f"Current: {main_data.get('account_number')}")

        key_id_raw = st.text_input(
            "App Key *",
            placeholder="Enter Key ID",
            type="password",
            key=f"main_edit_key_id_{counter}"
        )

        if main_data.get('key_id') and not key_id_raw:
            st.caption(f"Current: {main_data.get('key_id')[:3]}...{main_data.get('key_id')[-3:]}")

    with col2:
        secret_raw = st.text_input(
            "App Secret *",
            placeholder="Enter secret",
            type="password",
            key=f"main_edit_secret_{counter}"
        )

        if main_data.get('client_secret') and not secret_raw:
            st.caption(f"Current: {main_data.get('client_secret')[:3]}...{main_data.get('client_secret')[-3:]}")

        redirect_raw = st.text_input(
            "Redirect URI *",
            placeholder="https://127.0.0.1:8182",
            key=f"main_edit_redirect_{counter}"
        )

        if redirect_raw:
            st.caption(f"Will use: {redirect_raw}")
        elif main_data.get('redirect_uri'):
            st.caption(f"Current: {main_data.get('redirect_uri')}")

    st.markdown("---")

    # Проверить работает ли Worker
    from app.core.worker_client import is_worker_running
    worker_running = is_worker_running()
    
    if worker_running:
        st.warning("⚠️ Stop Worker before updating tokens")

    col_save, col_cancel, col_spacer = st.columns([1, 1, 2])

    with col_save:
        if st.button("💾 Save & Authorize", type="primary", width='stretch', disabled=worker_running):
            final_account = account_raw if account_raw else main_data.get('account_number', '')
            final_key_id = key_id_raw if key_id_raw else main_data.get('key_id', '')
            final_secret = secret_raw if secret_raw else main_data.get('client_secret', '')
            final_redirect = redirect_raw if redirect_raw else main_data.get('redirect_uri', '')

            if final_account and final_key_id and final_secret and final_redirect:
                account_data = {
                    'account_number': final_account,
                    'key_id': final_key_id,
                    'client_secret': final_secret,
                    'redirect_uri': final_redirect
                }

                # Сохранить credentials
                save_main_account_to_env(account_data)
                
                # Автоматическая авторизация
                with st.spinner("Authorizing with Schwab..."):
                    from app.utils.schwab_auth import authorize_main_account
                    success = authorize_main_account()
                
                if success:
                    st.session_state.main_form_reset_counter = counter + 1
                    st.success("✅ Saved and authorized!")
                    st.rerun()
                else:
                    # Удалить сохранённые данные при неудаче
                    st.error("❌ Authorization failed! Data not saved.")
                    st.info("Please check your credentials and try again.")
            else:
                st.error("⚠️ Fill all fields")

    with col_cancel:
        if st.button("Cancel", width='stretch'):
            # Сбросить форму (увеличить счетчик)
            st.session_state.main_form_reset_counter = counter + 1
            st.rerun()