"""
web/auth_routes.py
--------------------
Login/logout routes and the `login_required` decorator used to
protect the rest of the dashboard.
"""

from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app

auth_bp = Blueprint("auth", __name__)


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)
    return wrapped


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        auth_manager = current_app.config["AUTH_MANAGER"]
        user = auth_manager.verify_credentials(username, password)

        if user:
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash(f"Welcome back, {user['full_name'] or user['username']}!", "success")
            return redirect(url_for("dashboard.index"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
