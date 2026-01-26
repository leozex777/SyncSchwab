
# modals.py
# app.gui.components.modals


import streamlit as st
from app.gui.utils.env_manager import delete_client_from_env


def render_delete_confirmation():
    """Модальное окно подтверждения удаления клиента"""

    if not st.session_state.get('show_delete_modal', False):
        return

    # Проверка если клиент все еще существует
    client_manager = st.session_state.client_manager
    client_to_delete = st.session_state.get('client_to_delete')

    if not client_to_delete:
        st.session_state.show_delete_modal = False
        return

    selected = client_manager.get_client(client_to_delete)

    if not selected:
        st.session_state.show_delete_modal = False
        return

    @st.dialog(f"⚠️ Delete Client?")
    def confirm_delete():
        # Сбросить флаг сразу — при закрытии крестиком диалог не появится снова
        st.session_state.show_delete_modal = False
        
        # Красное предупреждение
        st.markdown("""
        <h2 style='color: red; font-weight: bold; text-align: center;'>
        ⚠️ THIS ACTION CANNOT BE UNDONE!
        </h2>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # Имя клиента с новой строки
        st.markdown(f"### {selected.name}")

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Cancel", type="primary", width="stretch", key="modal_cancel_btn"):
                st.session_state.show_delete_modal = False
                st.session_state.client_to_delete = None
                st.rerun()

        with col2:
            if st.button("✅ Confirm Delete", type="secondary", width="stretch", key="modal_confirm_btn"):
                delete_client_from_env(st.session_state.client_to_delete)
                client_manager.remove_client(st.session_state.client_to_delete)

                if st.session_state.selected_client_id == st.session_state.client_to_delete:
                    st.session_state.selected_client_id = None

                st.session_state.show_delete_modal = False
                st.session_state.client_to_delete = None
                st.success(f"✅ Client '{selected.name}' deleted!")
                st.rerun()

    confirm_delete()