import os
import time
import json
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from db import (
    init_db,
    get_all_atms,
    get_atm_by_id,
    insert_atm,
    bulk_insert_atms,
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


def classify_osm_atm(name, amenity="", operator=""):
    raw_name = (name or operator or "").strip()
    if not raw_name:
        raw_name = "현지 은행 ATM" if amenity == "bank" else "현지 ATM (편의점/기기)"
    lower = raw_name.lower()

    if any(k in lower for k in ["seven", "7-eleven", "7-bank"]) or any(k in raw_name for k in ["セブン", "세븐"]):
        return "세븐뱅크 ATM", "FREE", "무료 (트래블카드 면제)", "트래블로그·트래블월렛 인출 수수료 0원"
    if "aeon" in lower or "イオン" in raw_name or "이온" in raw_name:
        return "이온뱅크 ATM", "FREE", "무료 (트래블카드 면제)", "트래블월렛·트래블로그 무료 인출 지원"
    if "lawson" in lower or "ローソン" in raw_name or "로손" in raw_name:
        return "로손 은행 ATM", "MODERATE", "110~220엔", "편의점 기기 이용료 소액 부과"
    if "familymart" in lower or "ファミリーマート" in raw_name or "패밀리마트" in raw_name:
        return "패밀리마트 E-net ATM", "MODERATE", "110~220엔", "편의점 기기 이용료 소액 부과"

    if any(k in raw_name for k in ["하나은행", "국민은행", "KB", "신한은행", "우리은행", "농협", "NH", "기업은행", "IBK", "우체국", "새마을금고", "신협"]):
        return raw_name, "FREE", "0원 (자행/제휴 면제)", "자행 카드 및 제휴 트래블카드 수수료 면제"

    if any(k in lower for k in ["kasikorn", "krungsri", "scb", "bangkok bank", "krungthai", "ttb"]):
        return raw_name, "EXPENSIVE", "220바트 (약 8,500원)", "태국 현지 ATM 고정 수수료 220바트 부과 주의"

    if any(k in lower for k in ["vpbank", "tpbank", "cathay", "ctbc", "bank of taiwan", "taiwan"]):
        return raw_name, "FREE", "무료 (트래블카드 면제)", "트래블월렛·트래블로그 수수료 면제 은행"

    tip = "OSM 은행 지점 내 ATM" if amenity == "bank" else "OSM 실시간 수집 ATM"
    return raw_name, "MODERATE", "수수료 확인 필요", tip


def _query_single_overpass(url, body, headers):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=7) as resp:
        if resp.status == 200:
            payload = json.loads(resp.read().decode("utf-8"))
            elements = payload.get("elements")
            if isinstance(elements, list):
                return elements, url
    return None, url


def fetch_overpass_parallel(south, west, north, east):
    """4개 Overpass 미러에 병렬 요청 → 가장 먼저 응답한 서버 채택 (최대 7~8초 내 완료, Gunicorn 타임아웃 원천 차단)"""
    bbox = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"
    query = (
        f"[out:json][timeout:8];"
        f'(node["amenity"="atm"]({bbox});'
        f'node["atm"="yes"]({bbox});'
        f'way["atm"="yes"]({bbox});'
        f'node["amenity"="bank"]({bbox});'
        f'way["amenity"="bank"]({bbox}););'
        f"out center 250;"
    )
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://z.overpass-api.de/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
    ]
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    headers = {
        "User-Agent": "FeeFreeATM-AcademicProject/1.0 (https://feefree-atm.onrender.com)",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    executor = ThreadPoolExecutor(max_workers=len(endpoints))
    try:
        futures = [executor.submit(_query_single_overpass, u, body, headers) for u in endpoints]
        for fut in as_completed(futures, timeout=9):
            try:
                elements, used_url = fut.result()
                if elements is not None:
                    return elements, used_url
            except Exception:
                continue
    except Exception:
        pass
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return None, None


def fetch_photon_fallback(center_lat, center_lng, south, west, north, east):
    """Overpass 전체 혼잡/차단 시 OpenStreetMap 기반 Photon API 2차 백업"""
    items = []
    seen = set()
    headers = {"User-Agent": "FeeFreeATM-AcademicProject/1.0"}
    for kw in ["ATM", "bank"]:
        try:
            params = urllib.parse.urlencode({
                "q": kw,
                "lat": f"{center_lat:.5f}",
                "lon": f"{center_lng:.5f}",
                "limit": 40,
            })
            url = f"https://photon.komoot.io/api/?{params}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for feat in data.get("features", []):
                    coords = feat.get("geometry", {}).get("coordinates", [])
                    props = feat.get("properties", {})
                    if len(coords) >= 2:
                        lng, lat = float(coords[0]), float(coords[1])
                        if south <= lat <= north and west <= lng <= east:
                            oid = str(props.get("osm_id", int(abs(lat * 100000 + lng * 100000))))
                            if oid in seen:
                                continue
                            seen.add(oid)
                            items.append({
                                "type": props.get("osm_type", "n"),
                                "id": oid,
                                "lat": lat,
                                "lon": lng,
                                "tags": {
                                    "name": props.get("name", ""),
                                    "amenity": props.get("osm_value", kw.lower()),
                                },
                            })
        except Exception:
            continue
    return items


def fetch_nominatim_fallback(south, west, north, east):
    """3차 백업: OpenStreetMap Nominatim 영역 검색"""
    items = []
    headers = {"User-Agent": "FeeFreeATM-AcademicProject/1.0 (https://feefree-atm.onrender.com)"}
    for kw in ["atm", "bank"]:
        try:
            params = urllib.parse.urlencode({
                "q": kw,
                "format": "json",
                "bounded": 1,
                "viewbox": f"{west:.5f},{north:.5f},{east:.5f},{south:.5f}",
                "limit": 30,
            })
            url = f"https://nominatim.openstreetmap.org/search?{params}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
                for r in rows:
                    items.append({
                        "type": r.get("osm_type", "node"),
                        "id": r.get("osm_id", r.get("place_id")),
                        "lat": float(r["lat"]),
                        "lon": float(r["lon"]),
                        "tags": {
                            "name": r.get("name") or (r.get("display_name", "").split(",")[0]),
                            "amenity": kw,
                        },
                    })
        except Exception:
            continue
    return items


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


# ================= 4. 마이페이지 =================

@app.route("/mypage")
@login_required
def mypage():
    uid = session["user"]["id"]
    fresh_user = get_user_by_id(uid)
    if fresh_user:
        session["user"] = fresh_user
    bookmarks = get_user_bookmarks(uid)
    reported = get_user_reported_atms(uid)
    return render_template(
        "mypage.html",
        user=session["user"],
        bookmarks=bookmarks,
        reported=reported,
        msg=request.args.get("msg"),
        err=request.args.get("err"),
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
    conn.execute("DELETE FROM reviews WHERE user_id = ?", (user_id,))
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


# ================= 6. REST API (고속 병렬 OSM 백엔드 수집 + 단일 트랜잭션 DB 저장) =================

@app.route("/api/osm/collect", methods=["POST"])
@login_required
def api_osm_collect():
    data = request.get_json() or {}
    try:
        south = float(data["south"])
        west = float(data["west"])
        north = float(data["north"])
        east = float(data["east"])
        center_lat = float(data.get("centerLat", (south + north) / 2))
        center_lng = float(data.get("centerLng", (west + east) / 2))
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "지도 좌표 범위가 올바르지 않습니다."}), 400

    # 너무 넓은 국가/대륙 단위 화면일 경우 중심 기준 ±0.08도(약 9km)로 자동 보정
    if (north - south) > 0.25 or (east - west) > 0.25:
        south = center_lat - 0.08
        north = center_lat + 0.08
        west = center_lng - 0.08
        east = center_lng + 0.08

    try:
        elements, _ = fetch_overpass_parallel(south, west, north, east)
    except Exception:
        elements = None
    source_label = "Overpass OSM"

    if not elements:
        elements = fetch_photon_fallback(center_lat, center_lng, south, west, north, east)
        source_label = "Photon OSM"

    if not elements:
        elements = fetch_nominatim_fallback(south, west, north, east)
        source_label = "Nominatim OSM"

    records = []
    for el in elements or []:
        lat = el.get("lat")
        lng = el.get("lon")
        if lat is None or lng is None:
            center = el.get("center") or {}
            lat = center.get("lat")
            lng = center.get("lon")
        if lat is None or lng is None:
            continue

        el_type = el.get("type", "node")
        osm_id = f"osm_{el_type}_{el['id']}"
        tags = el.get("tags") or {}
        raw_name = tags.get("name") or tags.get("name:ko") or tags.get("brand") or ""
        amenity = tags.get("amenity", "")
        operator = tags.get("operator", "")
        name, fee_type, fee_amount, tip = classify_osm_atm(raw_name, amenity, operator)

        records.append((
            osm_id, name, float(lat), float(lng),
            fee_type, fee_amount, tip, 0, source_label,
        ))

    added = bulk_insert_atms(records)
    all_atms = get_all_atms()
    return jsonify({
        "added": added,
        "fetched": len(records),
        "total": len(all_atms),
        "source": source_label,
        "atms": all_atms,
    })


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

    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
    except (KeyError, ValueError, TypeError):
        return jsonify({"error": "올바른 위도/경도 좌표가 필요합니다."}), 400

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
        lat=lat,
        lng=lng,
        fee_type=fee_type,
        fee_amount=fee_amount,
        tip=tip,
        reporter=reporter,
        reporter_id=reporter_id,
        verified=1,
    )
    add_notification(
        reporter_id,
        "ATM 제보 등록 완료",
        f"'{name}' 정보가 서버 DB에 정상 등록되었습니다.",
    )

    return jsonify({
        "id": atm_id,
        "name": name,
        "lat": lat,
        "lng": lng,
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
    data = request.get_json() or {}
    atm_id = data.get("id")
    if not atm_id:
        return jsonify({"error": "ID 필요"}), 400
    if not get_atm_by_id(atm_id):
        try:
            lat = float(data["lat"])
            lng = float(data["lng"])
        except (KeyError, ValueError, TypeError):
            return jsonify({"error": "좌표가 누락되었습니다."}), 400
        insert_atm(
            atm_id=atm_id,
            name=data.get("name", "현지 ATM"),
            lat=lat,
            lng=lng,
            fee_type=data.get("feeType", "MODERATE"),
            fee_amount=data.get("feeAmount", "수수료 확인 필요"),
            tip=data.get("tip", "OSM 실시간 수집 데이터"),
            reporter=data.get("reporter", "OSM"),
            verified=0,
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
