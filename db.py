import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get(
    "FEEFREE_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "feefree.db"),
)

INITIAL_ATMS = [
    ("seed_1", "세븐일레븐 세븐뱅크 ATM (신주쿠)", 35.6895, 139.6917, "FREE", "무료", "트래블로그 무료 인출 가능", 152, "시스템"),
    ("seed_2", "이온뱅크 ATM (아키하바라)", 35.6985, 139.7717, "FREE", "무료", "트래블월렛 무료 인출 가능", 98, "시스템"),
    ("seed_3", "로손 ATM (시부야)", 35.6580, 139.7016, "MODERATE", "110~220엔", "소액 기기 수수료 부과", 45, "시스템"),
    ("seed_4", "VP Bank ATM (다낭 시내)", 16.0544, 108.2022, "FREE", "무료", "트래블월렛 무료 인출", 310, "시스템"),
    ("seed_5", "TP Bank ATM (다낭)", 16.0620, 108.2210, "FREE", "무료", "트래블월렛·트래블로그 지원", 215, "시스템"),
    ("seed_6", "Krungsri Bank ATM (카오산로드)", 13.7563, 100.5018, "EXPENSIVE", "220바트", "태국은 대부분 220바트 부과 (주의)", 420, "시스템"),
    ("seed_7", "타이완은행 ATM (타이베이 메인역)", 25.0450, 121.5154, "FREE", "무료", "대만은 대부분 은행 ATM 무료", 180, "시스템"),
    ("seed_8", "국태세화은행 ATM (타이베이 101)", 25.0330, 121.5654, "FREE", "무료", "세븐일레븐 내 위치", 120, "시스템"),
    ("seed_9", "Credit Agricole ATM (파리 샹젤리제)", 48.8655, 2.3125, "FREE", "무료", "트래블페이 이용 시 면제", 75, "시스템"),
    ("seed_10", "하나은행 ATM (평택대학교 학생회관)", 36.9958, 127.1338, "FREE", "0원 (수수료 면제)", "트래블로그 및 재학생 인출 수수료 무료", 480, "시스템"),
    ("seed_11", "KB국민은행 ATM (평택대 정문 앞 상가)", 36.9948, 127.1325, "FREE", "0원 (면제, 영업시간 내)", "KB 트래블러스 카드 및 자행 무료", 350, "시스템"),
    ("seed_12", "신한은행 ATM (평택대 남문 원룸촌)", 36.9936, 127.1312, "FREE", "0원 (SOL트래블 면제)", "신한 SOL트래블 체크카드 이용료 0원", 290, "시스템"),
]


def get_connection(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            nickname TEXT NOT NULL,
            preferred_card TEXT DEFAULT '트래블로그',
            push_enabled INTEGER DEFAULT 1,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS atms (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            fee_type TEXT NOT NULL,
            fee_amount TEXT NOT NULL,
            tip TEXT NOT NULL,
            verified INTEGER DEFAULT 1,
            reporter TEXT DEFAULT '시스템',
            reporter_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            atm_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            nickname TEXT NOT NULL,
            rating INTEGER NOT NULL DEFAULT 5,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            atm_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, atm_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 기본 관리자 계정 (admin / 1234)
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        cur.execute(
            """
            INSERT INTO users (username, password_hash, nickname, preferred_card, role)
            VALUES (?, ?, ?, ?, 'admin')
            """,
            ("admin", generate_password_hash("1234"), "관리자(발표자)", "트래블로그"),
        )
        admin_id = cur.lastrowid
        cur.execute(
            "INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)",
            (admin_id, "FeeFree ATM 시스템 가동", "관리자 계정으로 로그인되었습니다. 관리자 페이지에서 회원·ATM·공지 알림을 관리할 수 있습니다."),
        )

    # 기본 일반 사용자 계정 (user1 / 1234)
    cur.execute("SELECT id FROM users WHERE username = ?", ("user1",))
    if not cur.fetchone():
        cur.execute(
            """
            INSERT INTO users (username, password_hash, nickname, preferred_card, role)
            VALUES (?, ?, ?, ?, 'user')
            """,
            ("user1", generate_password_hash("1234"), "여행러", "트래블월렛"),
        )
        u1_id = cur.lastrowid
        cur.execute(
            "INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)",
            (u1_id, "환영합니다!", "FeeFree ATM에서 전 세계 무료 ATM을 찾고 수수료를 절약해 보세요."),
        )

    for atm in INITIAL_ATMS:
        cur.execute(
            """
            INSERT OR IGNORE INTO atms
            (id, name, lat, lng, fee_type, fee_amount, tip, verified, reporter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            atm,
        )

    # 초기 샘플 리뷰
    cur.execute("SELECT COUNT(*) as cnt FROM reviews")
    if cur.fetchone()["cnt"] == 0:
        cur.execute(
            "INSERT INTO reviews (atm_id, user_id, nickname, rating, comment) VALUES (?, ?, ?, ?, ?)",
            ("seed_1", 1, "관리자(발표자)", 5, "신주쿠역 동쪽 출구 세븐일레븐에서 트래블로그로 수수료 0원 출금 확인했습니다."),
        )

    conn.commit()
    conn.close()


def format_atm_row(r):
    return {
        "id": r["id"],
        "name": r["name"],
        "lat": r["lat"],
        "lng": r["lng"],
        "feeType": r["fee_type"],
        "feeAmount": r["fee_amount"],
        "tip": r["tip"],
        "verified": r["verified"],
        "reporter": r["reporter"],
        "reporterId": r["reporter_id"],
        "createdAt": r["created_at"],
    }


def get_all_atms(db_path=None):
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM atms ORDER BY created_at DESC").fetchall()
    conn.close()
    return [format_atm_row(r) for r in rows]


def get_atm_by_id(atm_id, db_path=None):
    conn = get_connection(db_path)
    r = conn.execute("SELECT * FROM atms WHERE id = ?", (atm_id,)).fetchone()
    conn.close()
    return format_atm_row(r) if r else None


def insert_atm(atm_id, name, lat, lng, fee_type, fee_amount, tip, reporter, reporter_id=None, db_path=None):
    conn = get_connection(db_path)
    conn.execute(
        """
        INSERT OR IGNORE INTO atms (id, name, lat, lng, fee_type, fee_amount, tip, verified, reporter, reporter_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (atm_id, name, lat, lng, fee_type, fee_amount, tip, reporter, reporter_id),
    )
    conn.commit()
    conn.close()


def delete_atm_record(atm_id, db_path=None):
    conn = get_connection(db_path)
    conn.execute("DELETE FROM reviews WHERE atm_id = ?", (atm_id,))
    conn.execute("DELETE FROM bookmarks WHERE atm_id = ?", (atm_id,))
    conn.execute("DELETE FROM atms WHERE id = ?", (atm_id,))
    conn.commit()
    conn.close()


def verify_atm_record(atm_id, payload=None, voter_nickname=None, db_path=None):
    conn = get_connection(db_path)
    cur = conn.cursor()
    row = cur.execute("SELECT verified, reporter_id, name FROM atms WHERE id = ?", (atm_id,)).fetchone()

    if row:
        new_count = row["verified"] + 1
        cur.execute("UPDATE atms SET verified = ? WHERE id = ?", (new_count, atm_id))
        if row["reporter_id"] and voter_nickname:
            cur.execute(
                "INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)",
                (
                    row["reporter_id"],
                    "제보 검증 알림",
                    f"{voter_nickname}님이 회원님이 제보한 '{row['name']}'에 '정보 맞음(+1)'을 눌렀습니다.",
                ),
            )
    elif payload:
        new_count = int(payload.get("verified", 0)) + 1
        cur.execute(
            """
            INSERT INTO atms (id, name, lat, lng, fee_type, fee_amount, tip, verified, reporter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                atm_id,
                payload.get("name", "현지 ATM"),
                float(payload["lat"]),
                float(payload["lng"]),
                payload.get("feeType", "MODERATE"),
                payload.get("feeAmount", "수수료 확인 필요"),
                payload.get("tip", "OSM 수집 + 사용자 검증"),
                new_count,
                payload.get("reporter", "OSM"),
            ),
        )
    else:
        conn.close()
        return None

    conn.commit()
    conn.close()
    return new_count


def get_reviews(atm_id, db_path=None):
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM reviews WHERE atm_id = ? ORDER BY created_at DESC", (atm_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_review(atm_id, user_id, nickname, rating, comment, db_path=None):
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO reviews (atm_id, user_id, nickname, rating, comment) VALUES (?, ?, ?, ?, ?)",
        (atm_id, user_id, nickname, int(rating), comment.strip()),
    )
    conn.commit()
    conn.close()


def toggle_bookmark(user_id, atm_id, db_path=None):
    conn = get_connection(db_path)
    cur = conn.cursor()
    exists = cur.execute(
        "SELECT id FROM bookmarks WHERE user_id = ? AND atm_id = ?", (user_id, atm_id)
    ).fetchone()
    if exists:
        cur.execute("DELETE FROM bookmarks WHERE id = ?", (exists["id"],))
        bookmarked = False
    else:
        cur.execute("INSERT INTO bookmarks (user_id, atm_id) VALUES (?, ?)", (user_id, atm_id))
        bookmarked = True
    conn.commit()
    conn.close()
    return bookmarked


def is_bookmarked(user_id, atm_id, db_path=None):
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT id FROM bookmarks WHERE user_id = ? AND atm_id = ?", (user_id, atm_id)
    ).fetchone()
    conn.close()
    return row is not None


def get_user_bookmarks(user_id, db_path=None):
    conn = get_connection(db_path)
    rows = conn.execute(
        """
        SELECT a.* FROM atms a
        JOIN bookmarks b ON a.id = b.atm_id
        WHERE b.user_id = ?
        ORDER BY b.created_at DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [format_atm_row(r) for r in rows]


def get_user_reported_atms(user_id, db_path=None):
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM atms WHERE reporter_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    conn.close()
    return [format_atm_row(r) for r in rows]


def add_notification(user_id, title, message, db_path=None):
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)",
        (user_id, title, message),
    )
    conn.commit()
    conn.close()


def broadcast_notification(title, message, db_path=None):
    conn = get_connection(db_path)
    users = conn.execute("SELECT id FROM users").fetchall()
    for u in users:
        conn.execute(
            "INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)",
            (u["id"], title, message),
        )
    conn.commit()
    conn.close()
    return len(users)


def get_notifications(user_id, db_path=None):
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 30",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_notifications_read(user_id, db_path=None):
    conn = get_connection(db_path)
    conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_all_users(db_path=None):
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT id, username, nickname, preferred_card, push_enabled, role, created_at FROM users ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_admin_stats(db_path=None):
    conn = get_connection(db_path)
    stats = {
        "total_users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "total_atms": conn.execute("SELECT COUNT(*) FROM atms").fetchone()[0],
        "total_verifications": conn.execute("SELECT COALESCE(SUM(verified), 0) FROM atms").fetchone()[0],
        "total_reviews": conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0],
        "total_notifications": conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0],
    }
    conn.close()
    return stats
