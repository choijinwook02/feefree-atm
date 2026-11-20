import os
import sqlite3
from werkzeug.security import generate_password_hash

try:
    import psycopg
    from psycopg.rows import dict_row
    PG_INTEGRITY_ERROR = psycopg.errors.UniqueViolation
except ImportError:
    psycopg = None
    dict_row = None
    PG_INTEGRITY_ERROR = None

INTEGRITY_ERRORS = tuple(
    e for e in (sqlite3.IntegrityError, PG_INTEGRITY_ERROR) if e is not None
)

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


def _get_database_url():
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def is_postgres(db_path=None):
    return bool(_get_database_url()) and db_path is None


class _PgCursorWrapper:
    def __init__(self, cur):
        self._cur = cur

    def __getattr__(self, name):
        return getattr(self._cur, name)

    def execute(self, sql, params=None):
        pg_sql = sql.replace("?", "%s")
        if params is None:
            self._cur.execute(pg_sql)
        else:
            self._cur.execute(pg_sql, params)
        return self

    def executemany(self, sql, seq):
        pg_sql = sql.replace("?", "%s")
        self._cur.executemany(pg_sql, seq)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return getattr(self._cur, "rowcount", -1)

    @property
    def lastrowid(self):
        return getattr(self._cur, "lastrowid", None)

    def close(self):
        return self._cur.close()


class _PgConnWrapper:
    """PostgreSQL 연결을 SQLite와 동일한 인터페이스(?, execute, cursor)로 통일"""
    def __init__(self, raw_conn):
        self._conn = raw_conn
        self.is_pg = True

    def cursor(self):
        return _PgCursorWrapper(self._conn.cursor(row_factory=dict_row))

    def execute(self, sql, params=None):
        cur = self.cursor()
        return cur.execute(sql, params)

    def executemany(self, sql, seq):
        cur = self.cursor()
        return cur.executemany(sql, seq)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def get_connection(db_path=None):
    if is_postgres(db_path):
        if psycopg is None:
            raise RuntimeError("psycopg[binary] 패키지가 설치되어 있지 않습니다.")
        raw = psycopg.connect(_get_database_url(), connect_timeout=10)
        return _PgConnWrapper(raw)

    conn = sqlite3.connect(db_path or DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def _fmt_ts(val):
    if val is None:
        return ""
    return str(val)[:19]


def _ensure_sqlite_column(cur, table, column, definition):
    cols = [r["name"] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db(db_path=None):
    pg = is_postgres(db_path)
    conn = get_connection(db_path)
    cur = conn.cursor()

    if pg:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
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
                lat DOUBLE PRECISION NOT NULL,
                lng DOUBLE PRECISION NOT NULL,
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
                id SERIAL PRIMARY KEY,
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
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                atm_id TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, atm_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
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
        _ensure_sqlite_column(cur, "users", "preferred_card", "TEXT DEFAULT '트래블로그'")
        _ensure_sqlite_column(cur, "users", "push_enabled", "INTEGER DEFAULT 1")
        _ensure_sqlite_column(cur, "users", "role", "TEXT DEFAULT 'user'")
        _ensure_sqlite_column(cur, "atms", "reporter_id", "INTEGER")

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

    # 기본 관리자 계정 (admin / 1234) - 다중 워커 동시 실행 안전 처리
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        admin_id = None
        if pg:
            cur.execute(
                """
                INSERT INTO users (username, password_hash, nickname, preferred_card, role)
                VALUES (?, ?, ?, ?, 'admin')
                ON CONFLICT (username) DO NOTHING
                RETURNING id
                """,
                ("admin", generate_password_hash("1234"), "관리자(발표자)", "트래블로그"),
            )
            row = cur.fetchone()
            admin_id = row["id"] if row else None
        else:
            cur.execute(
                """
                INSERT OR IGNORE INTO users (username, password_hash, nickname, preferred_card, role)
                VALUES (?, ?, ?, ?, 'admin')
                """,
                ("admin", generate_password_hash("1234"), "관리자(발표자)", "트래블로그"),
            )
            admin_id = cur.lastrowid if cur.rowcount else None
        if admin_id:
            cur.execute(
                "INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)",
                (admin_id, "FeeFree ATM 시스템 가동", "외부 DB 연동이 활성화되었습니다. 관리자 페이지에서 회원·ATM·공지 알림을 관리할 수 있습니다."),
            )

    # 기본 일반 사용자 계정 (user1 / 1234)
    cur.execute("SELECT id FROM users WHERE username = ?", ("user1",))
    if not cur.fetchone():
        u1_id = None
        if pg:
            cur.execute(
                """
                INSERT INTO users (username, password_hash, nickname, preferred_card, role)
                VALUES (?, ?, ?, ?, 'user')
                ON CONFLICT (username) DO NOTHING
                RETURNING id
                """,
                ("user1", generate_password_hash("1234"), "여행러", "트래블월렛"),
            )
            row = cur.fetchone()
            u1_id = row["id"] if row else None
        else:
            cur.execute(
                """
                INSERT OR IGNORE INTO users (username, password_hash, nickname, preferred_card, role)
                VALUES (?, ?, ?, ?, 'user')
                """,
                ("user1", generate_password_hash("1234"), "여행러", "트래블월렛"),
            )
            u1_id = cur.lastrowid if cur.rowcount else None
        if u1_id:
            cur.execute(
                "INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)",
                (u1_id, "환영합니다!", "FeeFree ATM에서 전 세계 무료 ATM을 찾고 수수료를 절약해 보세요."),
            )

    cur.executemany(
        """
        INSERT INTO atms
        (id, name, lat, lng, fee_type, fee_amount, tip, verified, reporter)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO NOTHING
        """,
        INITIAL_ATMS,
    )

    cur.execute("SELECT COUNT(*) AS cnt FROM reviews")
    if cur.fetchone()["cnt"] == 0:
        cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
        admin_row = cur.fetchone()
        admin_uid = admin_row["id"] if admin_row else 1
        cur.execute(
            "INSERT INTO reviews (atm_id, user_id, nickname, rating, comment) VALUES (?, ?, ?, ?, ?)",
            ("seed_1", admin_uid, "관리자(발표자)", 5, "신주쿠역 동쪽 출구 세븐일레븐에서 트래블로그로 수수료 0원 출금 확인했습니다."),
        )

    conn.commit()
    conn.close()


def format_atm_row(r):
    return {
        "id": r["id"],
        "name": r["name"],
        "lat": float(r["lat"]),
        "lng": float(r["lng"]),
        "feeType": r["fee_type"],
        "feeAmount": r["fee_amount"],
        "tip": r["tip"],
        "verified": r["verified"],
        "reporter": r["reporter"],
        "reporterId": r["reporter_id"],
        "createdAt": _fmt_ts(r["created_at"]),
    }


def get_all_atms(db_path=None):
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM atms ORDER BY created_at DESC").fetchall()
        return [format_atm_row(r) for r in rows]
    finally:
        conn.close()


def get_atm_by_id(atm_id, db_path=None):
    conn = get_connection(db_path)
    try:
        r = conn.execute("SELECT * FROM atms WHERE id = ?", (atm_id,)).fetchone()
        return format_atm_row(r) if r else None
    finally:
        conn.close()


def insert_atm(atm_id, name, lat, lng, fee_type, fee_amount, tip, reporter, reporter_id=None, verified=1, db_path=None):
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO atms (id, name, lat, lng, fee_type, fee_amount, tip, verified, reporter, reporter_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO NOTHING
            """,
            (atm_id, name, lat, lng, fee_type, fee_amount, tip, verified, reporter, reporter_id),
        )
        conn.commit()
    finally:
        conn.close()


def bulk_insert_atms(records, db_path=None):
    """대량 OSM 수집 데이터를 단일 트랜잭션으로 고속 일괄 저장"""
    if not records:
        return 0
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        before = cur.execute("SELECT COUNT(*) AS cnt FROM atms").fetchone()["cnt"]
        cur.executemany(
            """
            INSERT INTO atms (id, name, lat, lng, fee_type, fee_amount, tip, verified, reporter, reporter_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT (id) DO NOTHING
            """,
            records,
        )
        conn.commit()
        after = cur.execute("SELECT COUNT(*) AS cnt FROM atms").fetchone()["cnt"]
        return after - before
    finally:
        conn.close()


def delete_atm_record(atm_id, db_path=None):
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM reviews WHERE atm_id = ?", (atm_id,))
        conn.execute("DELETE FROM bookmarks WHERE atm_id = ?", (atm_id,))
        conn.execute("DELETE FROM atms WHERE id = ?", (atm_id,))
        conn.commit()
    finally:
        conn.close()


def verify_atm_record(atm_id, payload=None, voter_nickname=None, db_path=None):
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        row = cur.execute("SELECT verified, reporter_id, name FROM atms WHERE id = ?", (atm_id,)).fetchone()

        if row:
            new_count = (row["verified"] or 0) + 1
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
        elif payload and "lat" in payload and "lng" in payload:
            new_count = int(payload.get("verified", 0)) + 1
            cur.execute(
                """
                INSERT INTO atms (id, name, lat, lng, fee_type, fee_amount, tip, verified, reporter)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
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
            return None

        conn.commit()
        return new_count
    finally:
        conn.close()


def get_reviews(atm_id, db_path=None):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM reviews WHERE atm_id = ? ORDER BY created_at DESC", (atm_id,)
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["created_at"] = _fmt_ts(item.get("created_at"))
            result.append(item)
        return result
    finally:
        conn.close()


def add_review(atm_id, user_id, nickname, rating, comment, db_path=None):
    try:
        rating_val = max(1, min(5, int(rating)))
    except (ValueError, TypeError):
        rating_val = 5
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO reviews (atm_id, user_id, nickname, rating, comment) VALUES (?, ?, ?, ?, ?)",
            (atm_id, user_id, nickname, rating_val, (comment or "").strip()),
        )
        conn.commit()
    finally:
        conn.close()


def toggle_bookmark(user_id, atm_id, db_path=None):
    conn = get_connection(db_path)
    try:
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
        return bookmarked
    finally:
        conn.close()


def is_bookmarked(user_id, atm_id, db_path=None):
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM bookmarks WHERE user_id = ? AND atm_id = ?", (user_id, atm_id)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_user_bookmarks(user_id, db_path=None):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT a.* FROM atms a
            JOIN bookmarks b ON a.id = b.atm_id
            WHERE b.user_id = ?
            ORDER BY b.created_at DESC
            """,
            (user_id,),
        ).fetchall()
        return [format_atm_row(r) for r in rows]
    finally:
        conn.close()


def get_user_reported_atms(user_id, db_path=None):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM atms WHERE reporter_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return [format_atm_row(r) for r in rows]
    finally:
        conn.close()


def add_notification(user_id, title, message, db_path=None):
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)",
            (user_id, title, message),
        )
        conn.commit()
    finally:
        conn.close()


def broadcast_notification(title, message, db_path=None):
    conn = get_connection(db_path)
    try:
        users = conn.execute("SELECT id FROM users").fetchall()
        conn.executemany(
            "INSERT INTO notifications (user_id, title, message) VALUES (?, ?, ?)",
            [(u["id"], title, message) for u in users],
        )
        conn.commit()
        return len(users)
    finally:
        conn.close()


def get_notifications(user_id, db_path=None):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 30",
            (user_id,),
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["created_at"] = _fmt_ts(item.get("created_at"))
            result.append(item)
        return result
    finally:
        conn.close()


def mark_notifications_read(user_id, db_path=None):
    conn = get_connection(db_path)
    try:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()


def get_all_users(db_path=None):
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, username, nickname, preferred_card, push_enabled, role, created_at FROM users ORDER BY id ASC"
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["created_at"] = _fmt_ts(item.get("created_at"))
            result.append(item)
        return result
    finally:
        conn.close()


def get_admin_stats(db_path=None):
    conn = get_connection(db_path)
    try:
        stats = {
            "total_users": conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"],
            "total_atms": conn.execute("SELECT COUNT(*) AS cnt FROM atms").fetchone()["cnt"],
            "total_verifications": conn.execute("SELECT COALESCE(SUM(verified), 0) AS cnt FROM atms").fetchone()["cnt"],
            "total_reviews": conn.execute("SELECT COUNT(*) AS cnt FROM reviews").fetchone()["cnt"],
            "total_notifications": conn.execute("SELECT COUNT(*) AS cnt FROM notifications").fetchone()["cnt"],
        }
        return stats
    finally:
        conn.close()


def toggle_user_role(user_id, db_path=None):
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            new_role = "user" if row["role"] == "admin" else "admin"
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
            conn.commit()
            return new_role
        return None
    finally:
        conn.close()


def delete_user_record(user_id, db_path=None):
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM reviews WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM bookmarks WHERE user_id = ?", (user_id,))
        conn.execute("UPDATE atms SET reporter_id = NULL WHERE reporter_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
    return stats
