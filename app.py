import os
import time
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from db import (
    init_db,
    get_all_atms,
    get_atm_by_id,
    insert_atm,
    delete_atm_record,
    verify_atm_record,
    get_reviews,
    add_review,
    toggle_bookmark,
    is_bookmarked,
    get_user_bookmarks,
    get_user_reported_atms,
    add_notification,
    broadcast_notification,
    get_notifications,
    mark_notifications_read,
    get_all_users,
    get_admin_stats,
    get_connection,
)
from auth import (
    register_user,
    authenticate_user,
    get_user_by_id,
    update_user_profile,
    update_user_password,
    login_required,
    admin_required,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "feefree-atm-secret-key-2026")

init_db()


# ================= 1. 로그인 / 회원가입 =================

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if "user" in session:
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = authenticate_user(username, password)
        if user:
            session["user"] = user
            return redirect(url_for("index"))
        error = "아이디 또는 비밀번호가 올바르지 않습니다."

    return render_template("login.html", error=error, mode="login")


@app.route("/register", methods=["POST"])
def register_page():
    username = request.form.get("username", "")
    password = request.form.get("password", "")
    nickname = request.form.get("nickname", "")
    preferred_card = request.form.get("preferred_card", "트래블로그")

    ok, msg = register_user(username, password, nickname, preferred_card)
    if ok:
        session["user"] = authenticate_user(username, password)
        return redirect(url_for("index"))

    return render_template("login.html", error=msg, mode="register")


@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login_page"))


# ================= 2. 메인 화면 =================

@app.route("/")
@login_required
def index():
    return render_template("index.html", user=session["user"])


# ================= 3. 상세 화면 =================

@app.route("/atm/<atm_id>")
@login_required
def atm_detail(atm_id):
    atm = get_atm_by_id(atm_id)
    if not atm:
        return redirect(url_for("index"))
    reviews = get_reviews(atm_id)
    bookmarked = is_bookmarked(session["user"]["id"], atm_id)
    return render_template(
        "detail.html",
        user=session["user"],
        atm=atm,
        reviews=reviews,
        bookmarked=bookmarked,
    )


@app.route("/atm/<atm_id>/review", methods=["POST"])
@login_required
def post_review(atm_id):
    comment = (request.form.get("comment") or "").strip()
    rating = request.form.get("rating", 5)
    if comment:
        add_review(atm_id, session["user"]["id"], session["user"]["nickname"], rating, comment)
    return redirect(url_for("atm_detail", atm_id=atm_id))


@app.route("/api/atms/<atm_id>/bookmark", methods=["POST"])
@login_required
def api_toggle_bookmark(atm_id):
    state = toggle_bookmark(session["user"]["id"], atm_id)
    return jsonify({"atm_id": atm_id, "bookmarked": state})


# ================= 4. 마이페이지 (사용자 관리) =================

@app.route("/mypage")
@login_required
def mypage():
    uid = session["user"]["id"]
    fresh_user = get_user_by_id(uid)
    if fresh_user:
        session["user"] = fresh_user
    bookmarks = get_user_bookmarks(uid)
    reported = get_user_reported_atms(uid)
    msg = request.args.get("msg")
    err = request.args.get("err")
    return render_template(
        "mypage.html",
        user=session["user"],
        bookmarks=bookmarks,
        reported=reported,
        msg=msg,
        err=err,
    )


@app.route("/mypage/update", methods=["POST"])
@login_required
def mypage_update():
    uid = session["user"]["id"]
    nickname = request.form.get("nickname", "").strip()
    preferred_card = request.form.get("preferred_card", "트래블로그")
    push_enabled = request.form.get("push_enabled") == "on"
    if not nickname:
        return redirect(url_for("mypage", err="닉네임을 입력해주세요."))
    update_user_profile(uid, nickname, preferred_card, push_enabled)
    session["user"] = get_user_by_id(uid)
    return redirect(url_for("mypage", msg="프로필 정보가 저장되었습니다."))


@app.route("/mypage/password", methods=["POST"])
@login_required
def mypage_password():
    uid = session["user"]["id"]
    ok, message = update_user_password(
        uid,
        request.form.get("current_password", ""),
        request.form.get("new_password", ""),
    )
    if ok:
        return redirect(url_for("mypage", msg=message))
    return redirect(url_for("mypage", err=message))


@app.route("/mypage/atm/<atm_id>/delete", methods=["POST"])
@login_required
def mypage_delete_atm(atm_id):
    atm = get_atm_by_id(atm_id)
    if atm and (atm["reporterId"] == session["user"]["id"] or session["user"]["role"] == "admin"):
        delete_atm_record(atm_id)
        return redirect(url_for("mypage", msg="제보한 ATM이 삭제되었습니다."))
    return redirect(url_for("mypage", err="삭제 권한이 없습니다."))


# ================= 5. 관리자 화면 =================

@app.route("/admin")
@admin_required
def admin_page():
    return render_template(
        "admin.html",
        user=session["user"],
        stats=get_admin_stats(),
        users=get_all_users(),
        atms=get_all_atms(),
        msg=request.args.get("msg"),
    )


@app.route("/admin/notify", methods=["POST"])
@admin_required
def admin_notify():
    title = (request.form.get("title") or "").strip()
    message = (request.form.get("message") or "").strip()
    if title and message:
        count = broadcast_notification(title, message)
        return redirect(url_for("admin_page", msg=f"전체 회원 {count}명에게 공지 알림을 발송했습니다."))
    return redirect(url_for("admin_page", msg="제목과 내용을 모두 입력해주세요."))


@app.route("/admin/users/<int:user_id>/role", methods=["POST"])
@admin_required
def admin_toggle_role(user_id):
    if user_id == session["user"]["id"]:
        return redirect(url_for("admin_page", msg="본인 권한은 변경할 수 없습니다."))
    conn = get_connection()
    row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
    if row:
        new_role = "user" if row["role"] == "admin" else "admin"
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        conn.commit()
    conn.close()
    return redirect(url_for("admin_page", msg="회원 권한이 변경되었습니다."))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    if user_id == session["user"]["id"]:
        return redirect(url_for("admin_page", msg="현재 로그인된 관리자 계정은 삭제할 수 없습니다."))
    conn = get_connection()
    conn.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM bookmarks WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_page", msg="회원이 삭제되었습니다."))


@app.route("/admin/atms/<atm_id>/delete", methods=["POST"])
@admin_required
def admin_delete_atm(atm_id):
    delete_atm_record(atm_id)
    return redirect(url_for("admin_page", msg="ATM 데이터가 삭제되었습니다."))


# ================= 6. REST API (ATM & 알림) =================

@app.route("/api/atms", methods=["GET"])
@login_required
def api_get_atms():
    return jsonify(get_all_atms())


@app.route("/api/atms", methods=["POST"])
@login_required
def api_add_atm():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "기기명을 입력해주세요."}), 400

    fee_type = data.get("feeType", "FREE")
    fee_amount = (data.get("feeAmount") or "").strip()
    if not fee_amount:
        fee_amount = (
            "무료 (제보)" if fee_type == "FREE"
            else "고액 주의 (제보)" if fee_type == "EXPENSIVE"
            else "소액 수수료 (제보)"
        )
    tip = (data.get("tip") or "").strip() or "사용자 실시간 제보 데이터"
    reporter = session["user"]["nickname"]
    reporter_id = session["user"]["id"]
    atm_id = f"report_{int(time.time() * 1000)}"

    insert_atm(
        atm_id=atm_id,
        name=name,
        lat=float(data["lat"]),
        lng=float(data["lng"]),
        fee_type=fee_type,
        fee_amount=fee_amount,
        tip=tip,
        reporter=reporter,
        reporter_id=reporter_id,
    )
    add_notification(
        reporter_id,
        "ATM 제보 등록 완료",
        f"'{name}' 정보가 서버 DB에 정상 등록되었습니다.",
    )

    return jsonify({
        "id": atm_id,
        "name": name,
        "lat": float(data["lat"]),
        "lng": float(data["lng"]),
        "feeType": fee_type,
        "feeAmount": fee_amount,
        "tip": tip,
        "verified": 1,
        "reporter": reporter,
        "reporterId": reporter_id,
    }), 201


@app.route("/api/atms/ensure", methods=["POST"])
@login_required
def api_ensure_atm():
    """OSM 실시간 수집 ATM을 상세 화면으로 열기 전에 DB에 안전하게 보관"""
    data = request.get_json() or {}
    atm_id = data.get("id")
    if not atm_id:
        return jsonify({"error": "ID 필요"}), 400
    if not get_atm_by_id(atm_id):
        insert_atm(
            atm_id=atm_id,
            name=data.get("name", "현지 ATM"),
            lat=float(data["lat"]),
            lng=float(data["lng"]),
            fee_type=data.get("feeType", "MODERATE"),
            fee_amount=data.get("feeAmount", "수수료 확인 필요"),
            tip=data.get("tip", "OSM 실시간 수집 데이터"),
            reporter=data.get("reporter", "OSM"),
        )
    return jsonify({"ok": True, "url": url_for("atm_detail", atm_id=atm_id)})


@app.route("/api/atms/verify", methods=["POST"])
@login_required
def api_verify_atm():
    data = request.get_json() or {}
    atm_id = data.get("id")
    if not atm_id:
        return jsonify({"error": "ATM ID가 필요합니다."}), 400

    new_count = verify_atm_record(
        atm_id, payload=data, voter_nickname=session["user"]["nickname"]
    )
    if new_count is None:
        return jsonify({"error": "ATM 정보를 찾을 수 없습니다."}), 404

    return jsonify({"id": atm_id, "verified": new_count})


@app.route("/api/notifications", methods=["GET"])
@login_required
def api_get_notifications():
    items = get_notifications(session["user"]["id"])
    unread = sum(1 for n in items if not n["is_read"])
    return jsonify({"unread": unread, "items": items})


@app.route("/api/notifications/read-all", methods=["POST"])
@login_required
def api_read_all_notifications():
    mark_notifications_read(session["user"]["id"])
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
