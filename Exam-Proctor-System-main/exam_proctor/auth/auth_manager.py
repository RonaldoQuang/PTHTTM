"""
auth/auth_manager.py
---------------------
Handles admin authentication: secure password hashing (Werkzeug's
PBKDF2-SHA256 by default), user lookup/creation, and login validation.
Session lifecycle (cookies) is managed by Flask directly in app.py /
the auth blueprint; this class only deals with credential logic.
"""

from werkzeug.security import generate_password_hash, check_password_hash


class AuthManager:
    """CRUD + verification for admin_users."""

    def __init__(self, db_manager):
        self.db = db_manager

    def create_user(self, username: str, password: str, full_name: str = "", role: str = "invigilator"):
        """Create a new admin/invigilator account with a hashed password."""
        password_hash = generate_password_hash(password)
        return self.db.execute(
            """INSERT INTO admin_users (username, password_hash, full_name, role)
               VALUES (?, ?, ?, ?)""",
            (username, password_hash, full_name, role),
        )

    def get_user_by_username(self, username: str):
        return self.db.fetch_one(
            "SELECT * FROM admin_users WHERE username = ?", (username,)
        )

    def get_user_by_id(self, user_id: int):
        return self.db.fetch_one(
            "SELECT * FROM admin_users WHERE id = ?", (user_id,)
        )

    def verify_credentials(self, username: str, password: str):
        """Return the user record if valid, else None."""
        user = self.get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            self.db.execute(
                "UPDATE admin_users SET last_login = datetime('now') WHERE id = ?",
                (user["id"],),
            )
            return user
        return None

    def change_password(self, user_id: int, new_password: str):
        password_hash = generate_password_hash(new_password)
        self.db.execute(
            "UPDATE admin_users SET password_hash = ? WHERE id = ?",
            (password_hash, user_id),
        )
