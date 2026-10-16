"""
Login and role-based access for the Streamlit app.

    user = login.require_login()      # shows the sign-in form and stops the app until authenticated
    login.sidebar_account(user)       # "Signed in as ..." + Sign out button
    pages = login.allowed_pages(user) # pages this user's role may open

Accounts live in the SQLite `users` table (see db.py); sign-in is by email address
and password. Passwords are stored only as hashes (werkzeug.security) and verified
with check_password_hash on sign-in.
Create accounts with `python db.py` (demo users) or
`python db.py add-user <name> <role> --email <email>`.

Role -> pages (maps to the three dashboards in the proposal):
    business_manager -> Portfolio overview
    credit_analyst   -> Portfolio overview, Model evaluation
    loan_officer     -> Score applications
"""
from __future__ import annotations

import streamlit as st

import db

ROLE_PAGES = {
    "business_manager": ["Portfolio overview"],
    "credit_analyst": ["Portfolio overview", "Model evaluation"],
    "loan_officer": ["Score applications"],
}


def show_login() -> bool:
    """Render the sign-in form; return True once a user is authenticated."""
    if st.session_state.get("user"):
        return True
    st.title("Loan Creditworthiness")
    st.subheader("Sign in")
    if not db.has_users():
        st.warning("No accounts exist yet. Run `python db.py` in the project folder to "
                   "create the database and demo accounts, then reload this page.")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        user = db.verify_user(email, password)
        if user:
            st.session_state["user"] = user
            st.rerun()
        st.error("Invalid email or password.")
    return False


def require_login() -> dict:
    """Block the rest of the app until the visitor has signed in; return the user."""
    if not show_login():
        st.stop()
    return st.session_state["user"]


def sidebar_account(user: dict) -> None:
    st.sidebar.write(f"Signed in as **{user.get('email') or user['username']}** "
                     f"({user['role'].replace('_', ' ')})")
    if st.sidebar.button("Sign out"):
        st.session_state.pop("user", None)
        st.rerun()


def allowed_pages(user: dict) -> list[str]:
    return ROLE_PAGES[user["role"]]