
# styles.py
# app.gui.utils.styles

import streamlit as st


def apply_tab_button_styles():
    """CSS для кнопок-вкладок"""

    st.markdown("""
    <style>
    /* Активная вкладка - светло-голубая */
    div[data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"]
    :first-of-type button[data-testid="stBaseButton-primary"] {
        background-color: #E3F2FD !important;
        border-color: #64B5F6 !important;
        color: #000000 !important;
    }

    div[data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"]
    :first-of-type button[data-testid="stBaseButton-primary"]:hover {
        background-color: #E3F2FD !important;
        border-color: #2196F3 !important;
    }

    /* Неактивная вкладка - белая */
    div[data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"]
    :first-of-type button[data-testid="stBaseButton-secondary"] {
        background-color: #ffffff !important;
        border-color: #e0e0e0 !important;
        color: #000000 !important;
    }

    div[data-testid="stMainBlockContainer"] div[data-testid="stHorizontalBlock"]
    :first-of-type button[data-testid="stBaseButton-secondary"]:hover {
        background-color: #E3F2FD  !important;
        border-color: #E3F2FD !important;
        color: #000000 !important;
    }

    /* Кнопка Save - светло-голубая */
    button[data-testid="stBaseButton-primary"] {
        background-color: #E3F2FD !important;
        border-color: #e0e0e0 !important;
        color: #000000 !important;
    }

    button[data-testid="stBaseButton-primary"]:hover {
        background-color: #E3F2FD !important;
        border-color: #2196F3 !important;
    }
    </style>
    """, unsafe_allow_html=True)