import sqlite3
from functools import wraps
from flask import session, redirect, url_for, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_connection, add_notification


def register_user(username, password, nickname, preferred_card="트래블로그", db_path=None):
    username = username.strip()
    nickname = nickname.strip()
    if not username or not password or not nickname:
        return False, "아이디, 비밀번호, 닉네임을 모두 입력해주세요."
    if len(password) < 4:
        return False, "비밀번호는 4자 이상 입력해주세요."

    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO users (username, password_hash, nickname, preferred_card, role)
            VALUES (?, ?, ?, ?, 'user')
            """,
            (username, generate_password_hash(password), nickname, preferred_card or "트래블로그"),
        )
        new_uid = cur.lastrowid
        conn.commit()
        conn.close()
        add_notification(
            new_uid,
            "회원가입 환영",
            f"{nickname}님, FeeFree ATM에 오신 것을 환영합니다! 무료 ATM 제보와 검증에 참여해 보세요.",
            db_path=db_path,
        )
        return True, "회원가입이 완료되었습니다."
    except sqlite3.IntegrityError:
        conn.close()
        return False, "이미 사용 중인 아이디입니다."
    except Exception:
        conn.close()
        return False, "회원가입 처리 중 오류가 발생했습니다."


def authenticate_user(username, password, db_path=None):
    conn = get_connection(db_path)
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username.strip(),)
    ).fetchone()
    conn.close()

    if user and check_password_hash(user["password_hash"], password):
        return {
            "id": user["id"],
            "username": user["username"],
            "nickname": user["nickname"],
            "preferred_card": user["preferred_card"],
            "push_enabled": bool(user["push_enabled"]),
            "role": user["role"],
        }
    return None


def get_user_by_id(user_id, db_path=None):
    conn = get_connection(db_path)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if not user:
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "nickname": user["nickname"],
        "preferred_card": user["preferred_card"],
        "push_enabled": bool(user["push_enabled"]),
        "role": user["role"],
    }


def update_user_profile(user_id, nickname, preferred_card, push_enabled, db_path=None):
    conn = get_connection(db_path)
    conn.execute(
        "UPDATE users SET nickname = ?, preferred_card = ?, push_enabled = ? WHERE id = ?",
        (nickname.strip(), preferred_card, 1 if push_enabled else 0, user_id),
    )
    conn.commit()
    conn.close()


def update_user_password(user_id, current_password, new_password, db_path=None):
    conn = get_connection(db_path)
    user = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], current_password):
        conn.close()
        return False, "현재 비밀번호가 일치하지 않습니다."
    if len(new_password) < 4:
        conn.close()
        return False, "새 비밀번호는 4자 이상 입력해주세요."
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), user_id),
    )
    conn.commit()
    conn.close()
    return True, "비밀번호가 성공적으로 변경되었습니다."


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "로그인이 필요합니다."}), 401
            return redirect(url_for("login_page"))
        return view_func(*args, **kwargs)

    return wrapped


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login_page"))
        if session["user"].get("role") != "admin":
            return "관리자 권한이 필요합니다.", 403
        return view_func(*args, **kwargs)

    return wrapped
