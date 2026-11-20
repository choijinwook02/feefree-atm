import os
import tempfile
import unittest

# 테스트용 임시 DB 설정
tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp_db.close()
os.environ["FEEFREE_DB_PATH"] = tmp_db.name

import app as app_module
from db import init_db


class FeeFreeATMTestCase(unittest.TestCase):
    def setUp(self):
        init_db()
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def login(self, username, password):
        return self.client.post(
            "/login",
            data={"username": username, "password": password},
            follow_redirects=True,
        )

    def test_01_security_unauthenticated_access(self):
        """[보안 테스트] 비로그인 접근 차단 및 API 401 반환"""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 302)
        api_res = self.client.get("/api/atms")
        self.assertEqual(api_res.status_code, 401)

    def test_02_register_and_login(self):
        """[기능 테스트] 신규 회원가입 및 로그인/로그아웃"""
        res = self.client.post(
            "/register",
            data={
                "username": "tester01",
                "password": "password123",
                "nickname": "테스터",
                "preferred_card": "트래블로그",
            },
            follow_redirects=True,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("FeeFree ATM", res.get_data(as_text=True))

        logout_res = self.client.get("/logout", follow_redirects=True)
        self.assertEqual(logout_res.status_code, 200)

    def test_03_atm_report_and_db_persistence(self):
        """[통합 테스트] 신규 ATM 제보 DB 영구 저장 및 조회"""
        self.login("admin", "1234")
        res = self.client.post(
            "/api/atms",
            json={
                "name": "테스트 세븐뱅크 ATM",
                "lat": 35.69,
                "lng": 139.70,
                "feeType": "FREE",
                "tip": "트래블로그 무료 확인",
            },
        )
        self.assertEqual(res.status_code, 201)
        created = res.get_json()
        self.assertEqual(created["name"], "테스트 세븐뱅크 ATM")

        list_res = self.client.get("/api/atms")
        names = [a["name"] for a in list_res.get_json()]
        self.assertIn("테스트 세븐뱅크 ATM", names)

    def test_04_verify_and_detail_review_bookmark(self):
        """[기능 테스트] 검증 투표(+1), 상세 화면, 후기 작성 및 즐겨찾기"""
        self.login("user1", "1234")
        v_res = self.client.post("/api/atms/verify", json={"id": "seed_1"})
        self.assertEqual(v_res.status_code, 200)
        self.assertGreaterEqual(v_res.get_json()["verified"], 153)

        detail_res = self.client.get("/atm/seed_1")
        self.assertEqual(detail_res.status_code, 200)

        rev_res = self.client.post(
            "/atm/seed_1/review",
            data={"rating": 5, "comment": "수수료 없이 잘 뽑았습니다!"},
            follow_redirects=True,
        )
        self.assertIn("수수료 없이 잘 뽑았습니다!", rev_res.get_data(as_text=True))

        bm_res = self.client.post("/api/atms/seed_1/bookmark")
        self.assertEqual(bm_res.status_code, 200)
        self.assertTrue(bm_res.get_json()["bookmarked"])

    def test_05_mypage_profile_update(self):
        """[기능 테스트] 마이페이지 프로필 및 알림 설정 수정"""
        self.login("user1", "1234")
        res = self.client.post(
            "/mypage/update",
            data={"nickname": "수정된여행러", "preferred_card": "신한 SOL트래블", "push_enabled": "on"},
            follow_redirects=True,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("수정된여행러", res.get_data(as_text=True))

    def test_06_notifications_and_admin_access_control(self):
        """[보안/관리자 테스트] 일반 회원 관리자 접근 차단(403) 및 관리자 공지 발송"""
        self.login("user1", "1234")
        forbidden = self.client.get("/admin")
        self.assertEqual(forbidden.status_code, 403)

        self.client.get("/logout")
        self.login("admin", "1234")
        admin_res = self.client.get("/admin")
        self.assertEqual(admin_res.status_code, 200)

        notify_res = self.client.post(
            "/admin/notify",
            data={"title": "테스트 공지", "message": "전체 알림 테스트입니다."},
            follow_redirects=True,
        )
        self.assertEqual(notify_res.status_code, 200)

        n_res = self.client.get("/api/notifications")
        titles = [n["title"] for n in n_res.get_json()["items"]]
        self.assertIn("테스트 공지", titles)

    def test_07_input_validation_and_safety(self):
        """[안정성 테스트] 비정상 좌표(NaN/Inf/범위초과) 차단 및 평점 예외 처리"""
        self.login("admin", "1234")

        # 1. NaN 위도 좌표 차단
        nan_res = self.client.post(
            "/api/atms",
            json={"name": "비정상 좌표 ATM", "lat": "NaN", "lng": 127.0},
        )
        self.assertEqual(nan_res.status_code, 400)

        # 2. 범위 벗어난 좌표 차단 (lat > 90)
        out_res = self.client.post(
            "/api/atms",
            json={"name": "범위 초과 ATM", "lat": 95.0, "lng": 127.0},
        )
        self.assertEqual(out_res.status_code, 400)

        # 3. OSM 수집 API에서도 잘못된 범위 차단
        osm_res = self.client.post(
            "/api/osm/collect",
            json={"south": "NaN", "west": 100.0, "north": 40.0, "east": 140.0},
        )
        self.assertEqual(osm_res.status_code, 400)

        # 4. 숫자가 아닌 평점 문자열 전송 시 500 에러 없이 정상 처리
        rev_res = self.client.post(
            "/atm/seed_1/review",
            data={"rating": "not-a-number", "comment": "평점 예외 방어 테스트"},
            follow_redirects=True,
        )
        self.assertEqual(rev_res.status_code, 200)

    def test_08_get_register_page_allowed(self):
        """[접근성 테스트] GET /register 요청 시 405 없이 정상 렌더링"""
        res = self.client.get("/register")
        self.assertEqual(res.status_code, 200)
        self.assertIn("FeeFree ATM", res.get_data(as_text=True))

    @classmethod
    def tearDownClass(cls):
        try:
            if os.path.exists(tmp_db.name):
                os.remove(tmp_db.name)
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
