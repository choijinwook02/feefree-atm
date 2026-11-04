from flask import Flask, render_template, request, jsonify
import json
import os
import math

app = Flask(__name__)

DATA_FILE = "atm_data.json"

# 초기 데이터 (평택 실시간 LBS + 서울 + 해외 5대 여행지 시연 데이터)
INITIAL_ATMS = [
    # 📍 [경기도 평택시]
    {"id": 1, "region": "korea", "city": "pyeongtaek", "name": "하나은행 ATM (평택대학교 학생회관)", "lat": 36.9958, "lng": 127.1338, "feeType": "FREE", "feeAmount": "0원 (수수료 면제)", "cards": "하나 트래블로그, 하나체크, 일반카드", "tip": "평택대학교 교내 학생회관 1층 위치! 트래블로그 및 재학생 인출 수수료 완전 무료입니다.", "verified": 480},
    {"id": 2, "region": "korea", "city": "pyeongtaek", "name": "KB국민은행 ATM (평택대 정문 앞 상가)", "lat": 36.9948, "lng": 127.1325, "feeType": "FREE", "feeAmount": "0원 (면제, 영업시간 내)", "cards": "KB 트래블러스, 국민체크", "tip": "평택대 정문 횡단보도 앞 상가 위치. KB 트래블러스 카드 및 자행 출금 수수료 0원!", "verified": 350},
    {"id": 3, "region": "korea", "city": "pyeongtaek", "name": "신한은행 ATM (평택대 남문 원룸촌 드림빌 앞)", "lat": 36.9936, "lng": 127.1312, "feeType": "FREE", "feeAmount": "0원 (SOL트래블 면제)", "cards": "신한 SOL트래블 체크, 신한카드", "tip": "평택대 남문 원룸촌 인근. 신한 SOL트래블 체크카드 기기 이용료 0원 적용 기기입니다.", "verified": 290},
    {"id": 4, "region": "korea", "city": "pyeongtaek", "name": "NH농협은행 용이지점 ATM (용이동 먹자골목 입구)", "lat": 36.9965, "lng": 127.1362, "feeType": "FREE", "feeAmount": "0원 (자행 면제)", "cards": "농협 체크/신용, 일반카드", "tip": "용이동 상가 중심 도로변 위치. 농협 및 제휴카드 수수료 무료.", "verified": 210},
    {"id": 5, "region": "korea", "city": "pyeongtaek", "name": "GS25 평택대점 나이스ATM (용이동 후문길)", "lat": 36.9968, "lng": 127.1320, "feeType": "MODERATE", "feeAmount": "1,100원 ~ 1,300원", "cards": "국내외 모든 카드", "tip": "24시간 편의점 제휴 ATM으로 타행 출금 시 1,200원의 표준 수수료가 발생합니다.", "verified": 95},
    {"id": 6, "region": "korea", "city": "pyeongtaek", "name": "세븐일레븐 롯데ATM (평택 소사벌/용이DT점)", "lat": 36.9982, "lng": 127.1350, "feeType": "MODERATE", "feeAmount": "1,200원", "cards": "롯데카드, 트래블월렛, 일반카드", "tip": "편의점 내 설치 기기로 야간/주말 출금 시 소액 수수료가 부과됩니다.", "verified": 82},
    {"id": 7, "region": "korea", "city": "pyeongtaek", "name": "우리은행 평택역 금융센터 ATM (평택역 1번 출구 광장)", "lat": 36.9912, "lng": 127.0875, "feeType": "FREE", "feeAmount": "0원 (수수료 면제)", "cards": "우리 EXK, 트래블월렛, 일반카드", "tip": "평택역사 1번 출구 앞. 해외 체크카드 및 트래블월렛 출금 우대 기기입니다.", "verified": 420},
    {"id": 8, "region": "korea", "city": "pyeongtaek", "name": "IBK기업은행 평택지점 ATM (평택역 오거리 중앙로)", "lat": 36.9925, "lng": 127.0890, "feeType": "FREE", "feeAmount": "0원 (면제)", "cards": "기업은행, 일반 체크카드", "tip": "평택역 중심상가 위치. 영업시간 내 출금 수수료 0원.", "verified": 180},
    {"id": 9, "region": "korea", "city": "pyeongtaek", "name": "신협 소사벌지점 ATM (평택 소사벌 상업지구)", "lat": 37.0018, "lng": 127.1125, "feeType": "FREE", "feeAmount": "0원 ~ 800원", "cards": "신협, 일반 체크카드", "tip": "소사벌 중심상가 내 위치하여 조합원 및 제휴카드 수수료 면제.", "verified": 140},
    {"id": 10, "region": "korea", "city": "pyeongtaek", "name": "Euronet 글로벌 사설 ATM (평택 팽성/안정리 로데오거리)", "lat": 36.9720, "lng": 127.0510, "feeType": "HIGH", "feeAmount": "5,000원 + 12% DCC 환율 마진", "cards": "모든 카드 주의", "tip": "⚠️ 미군부대(캠프 험프리스) 앞 사설 독립 ATM으로 강제 환율 마진이 붙어 고액 수수료 발생 주의!", "verified": 590},

    # 📍 [서울특별시]
    {"id": 21, "region": "korea", "city": "seoul", "name": "하나은행 트래블로그 외화 ATM (명동 본점)", "lat": 37.5663, "lng": 126.9828, "feeType": "FREE", "feeAmount": "0원 (수수료 면제)", "cards": "하나 트래블로그, 해외카드", "tip": "트래블로그 외화/원화 현금 인출 수수료 0원 기기입니다.", "verified": 620},
    {"id": 22, "region": "korea", "city": "seoul", "name": "신한은행 SOL트래블 외화 ATM (명동지점)", "lat": 37.5645, "lng": 126.9850, "feeType": "FREE", "feeAmount": "0원 (수수료 면제)", "cards": "신한 SOL트래블, Visa", "tip": "SOL트래블 체크카드 수수료 0원 기기.", "verified": 490},
    {"id": 23, "region": "korea", "city": "seoul", "name": "우리은행 글로벌 데스크 ATM (명동역점)", "lat": 37.5612, "lng": 126.9862, "feeType": "FREE", "feeAmount": "0원 (면제)", "cards": "우리 EXK, 트래블월렛", "tip": "명동역 6번 출구 앞. 해외카드 인출 우대.", "verified": 310},
    {"id": 24, "region": "korea", "city": "seoul", "name": "하나은행 외화 ATM (홍대입구역 9번 출구)", "lat": 37.5568, "lng": 126.9238, "feeType": "FREE", "feeAmount": "0원 (수수료 면제)", "cards": "트래블로그, 트래블월렛", "tip": "홍대 관광 중심지 내 트래블로그 인출 수수료 0원 기기입니다.", "verified": 410},
    {"id": 25, "region": "korea", "city": "seoul", "name": "KB국민은행 강남중앙지점 ATM (강남역 11번 출구)", "lat": 37.4985, "lng": 127.0275, "feeType": "FREE", "feeAmount": "0원 (영업시간 내)", "cards": "KB 트래블러스, 국민체크", "tip": "강남역 메인 도로변 위치.", "verified": 550},
    {"id": 26, "region": "korea", "city": "seoul", "name": "신한은행 글로벌 ATM (인천공항 T1 입국장)", "lat": 37.4602, "lng": 126.4407, "feeType": "FREE", "feeAmount": "0원 (수수료 면제)", "cards": "SOL트래블, 트래블로그", "tip": "인천공항 1터미널 1층 입국장 정규 은행 ATM.", "verified": 680},

    # 📍 [수업 시연용: 해외 도시]
    {"id": 101, "region": "overseas", "city": "tokyo", "name": "Seven Bank ATM (신주쿠 세븐일레븐)", "lat": 35.6909, "lng": 139.7005, "feeType": "FREE", "feeAmount": "0 JPY (완전 무료)", "cards": "트래블로그, 트래블월렛, Visa, Master", "tip": "일본 세븐일레븐 내 세븐뱅크 기기는 트래블카드 출금 시 수수료 0엔입니다!", "verified": 342},
    {"id": 102, "region": "overseas", "city": "tokyo", "name": "AEON Bank ATM (신주쿠 미니스톱)", "lat": 35.6922, "lng": 139.7025, "feeType": "FREE", "feeAmount": "0 JPY (완전 무료)", "cards": "트래블로그(Master), JCB", "tip": "미니스톱 및 이온몰 내 이온뱅크 기기는 수수료 완전 무료입니다.", "verified": 189},
    {"id": 103, "region": "overseas", "city": "tokyo", "name": "Lawson Bank ATM (가부키초 편의점)", "lat": 35.6938, "lng": 139.7012, "feeType": "MODERATE", "feeAmount": "110~220 JPY (약 1,500원)", "cards": "일반 해외체크카드", "tip": "로손 편의점 ATM은 시간대 및 카드에 따라 110~220엔 부과될 수 있습니다.", "verified": 74},

    {"id": 201, "region": "overseas", "city": "danang", "name": "VPBank ATM (다낭 한시장/박당 거리)", "lat": 16.0678, "lng": 108.2235, "feeType": "FREE", "feeAmount": "0 VND (수수료 면제)", "cards": "트래블월렛(Visa), 트래블로그", "tip": "★다낭 배낭여행 필수 성지! 초록색 VPBank는 현지 기기 수수료 0원!", "verified": 276},
    {"id": 202, "region": "overseas", "city": "danang", "name": "TPBank ATM (다낭 보라색 은행)", "lat": 16.0692, "lng": 108.2218, "feeType": "FREE", "feeAmount": "0 VND (수수료 면제)", "cards": "트래블월렛, 트래블로그, EXK", "tip": "VPBank와 함께 베트남 수수료 완전 무료 양대 산맥 은행입니다.", "verified": 195},
    {"id": 203, "region": "overseas", "city": "danang", "name": "Vietcombank ATM (다낭 대성당 앞)", "lat": 16.0664, "lng": 108.2232, "feeType": "MODERATE", "feeAmount": "50,000 VND (약 2,700원)", "cards": "Visa, Mastercard 공통", "tip": "국영은행으로 안정적이나 1회 인출 시 5만 동의 현지 수수료가 부과됩니다.", "verified": 82},

    {"id": 301, "region": "overseas", "city": "bangkok", "name": "AEON Bank ATM (센트럴월드 4층)", "lat": 13.7469, "lng": 100.5393, "feeType": "FREE", "feeAmount": "0 THB (완전 무료)", "cards": "트래블로그(Master), JCB", "tip": "태국 로컬은행 220바트 수수료를 피할 수 있는 방콕 쇼핑몰 내 귀한 무료 기기!", "verified": 215},
    {"id": 302, "region": "overseas", "city": "bangkok", "name": "Bangkok Bank ATM (시암 파라곤)", "lat": 13.7462, "lng": 100.5348, "feeType": "MODERATE", "feeAmount": "220 THB (약 8,500원)", "cards": "Visa, Mastercard, GLN", "tip": "태국 표준 220바트 부과. 화면에서 'Continue without conversion(DCC 거부)' 필수!", "verified": 134},
    {"id": 303, "region": "overseas", "city": "bangkok", "name": "Euronet ATM (시암 스퀘어 사설기기)", "lat": 13.7450, "lng": 100.5335, "feeType": "HIGH", "feeAmount": "250 THB + 13% 환율 마진", "cards": "모든 카드 주의", "tip": "⚠️ 사설 독립 ATM으로 불리한 자체 환율을 강제 적용하므로 절대 비추천!", "verified": 412},

    {"id": 401, "region": "overseas", "city": "taipei", "name": "국태세화은행 ATM (시먼딩 세븐일레븐)", "lat": 25.0425, "lng": 121.5075, "feeType": "FREE", "feeAmount": "0 TWD (수수료 면제)", "cards": "트래블로그, 트래블월렛", "tip": "대만 세븐일레븐 및 지하철역에 있는 국태세화 ATM은 출금 수수료 0원!", "verified": 290},
    {"id": 402, "region": "overseas", "city": "taipei", "name": "대만은행 ATM (Bank of Taiwan 시먼점)", "lat": 25.0412, "lng": 121.5088, "feeType": "FREE", "feeAmount": "0 TWD (수수료 면제)", "cards": "트래블카드 및 EXK", "tip": "국영 대만은행 지점 기기로 수수료 무료 및 환율 우대 적용.", "verified": 118},
    {"id": 403, "region": "overseas", "city": "taipei", "name": "Mega Bank ATM (시먼역 6번 출구)", "lat": 25.0433, "lng": 121.5065, "feeType": "MODERATE", "feeAmount": "100 TWD (약 4,200원)", "cards": "일반 해외겸용 카드", "tip": "일부 해외 카드 인출 시 100대만달러 수수료가 부과될 수 있습니다.", "verified": 53},

    {"id": 501, "region": "overseas", "city": "paris", "name": "BNP Paribas ATM (파리 오페라 지점)", "lat": 48.8710, "lng": 2.3320, "feeType": "FREE", "feeAmount": "0 EUR (완전 무료)", "cards": "트래블로그, 트래블월렛", "tip": "유럽 최대 은행 지점 내부 ATM으로 현지 기기 인출 수수료가 0유로입니다.", "verified": 167},
    {"id": 502, "region": "overseas", "city": "paris", "name": "Société Générale ATM (루브르 지점)", "lat": 48.8625, "lng": 2.3350, "feeType": "FREE", "feeAmount": "0 EUR (완전 무료)", "cards": "트래블로그, 트래블월렛", "tip": "정규 프랑스 시중은행 ATM으로 안전하고 수수료 없이 인출 가능.", "verified": 122},
    {"id": 503, "region": "overseas", "city": "paris", "name": "Euronet ATM (에펠탑 광장 앞)", "lat": 48.8584, "lng": 2.2945, "feeType": "HIGH", "feeAmount": "4.95 EUR + 13% 마크업", "cards": "절대 이용 주의", "tip": "⚠️ 유럽 관광지 앞 노란색/파란색 Euronet 기기는 약 12,000원 수수료 폭탄 발생!", "verified": 530}
]

def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(INITIAL_ATMS, f, ensure_ascii=False, indent=2)
        return INITIAL_ATMS
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return INITIAL_ATMS

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def calc_haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # 미터 단위
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(delta_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return int(R * c)

@app.route("/")
def index():
    return render_template("index.html")

# LBS 위치기반 ATM 반경 검색 API (위도, 경도, 반경 수신)
@app.route("/api/atms", methods=["GET"])
def get_atms():
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    radius = request.args.get("radius", default=3000, type=int)
    city = request.args.get("city", default=None, type=str)
    fee_type = request.args.get("feeType", default="ALL", type=str)

    data = load_data()

    # 시연 모드일 때
    if city:
        results = [a for a in data if a.get("city") == city]
    else:
        results = data

    # 거리 계산 및 필터링
    output = []
    for item in results:
        atm_lat = item.get("lat")
        atm_lng = item.get("lng")
        dist = calc_haversine(lat, lng, atm_lat, atm_lng) if (lat and lng) else 0

        # 반경 조건 체크
        if radius and radius < 900000 and lat and lng:
            if dist > radius:
                continue

        # 수수료 유형 필터
        if fee_type == "FREE" and item.get("feeType") != "FREE":
            continue
        elif fee_type == "TRAVEL" and ("트래블" not in item.get("cards", "") and item.get("feeType") != "FREE"):
            continue

        item_copy = dict(item)
        item_copy["distance"] = dist
        output.append(item_copy)

    # 거리순 정렬
    if lat and lng:
        output.sort(key=lambda x: x["distance"])

    return jsonify({"status": "success", "count": len(output), "data": output})

# 신규 ATM 수수료 제보 API
@app.route("/api/report", methods=["POST"])
def report_atm():
    req = request.get_json()
    data = load_data()
    new_atm = {
        "id": int(request.environ.get("REQUEST_TIME", 1700000000) * 1000),
        "region": "user",
        "city": req.get("city", "user_reported"),
        "name": req.get("name", "신규 제보 ATM"),
        "lat": float(req.get("lat")),
        "lng": float(req.get("lng")),
        "feeType": req.get("feeType", "FREE"),
        "feeAmount": req.get("feeAmount", "0원 (면제)"),
        "cards": req.get("cards", "트래블로그, 트래블월렛"),
        "tip": req.get("tip", "사용자 실시간 제보로 등록된 기기입니다."),
        "verified": 1
    }
    data.insert(0, new_atm)
    save_data(data)
    return jsonify({"status": "success", "item": new_atm})

# 신뢰도 투표 (+1) API
@app.route("/api/verify/<int:atm_id>", methods=["POST"])
def verify_atm(atm_id):
    data = load_data()
    for item in data:
        if item.get("id") == atm_id:
            item["verified"] = item.get("verified", 0) + 1
            save_data(data)
            return jsonify({"status": "success", "verified": item["verified"]})
    return jsonify({"status": "fail", "message": "Item not found"}), 404

if __name__ == "__main__":
    # 스마트폰 및 외부 접속 허용 (0.0.0.0, 포트 5000)
    print("FeeFree ATM 플라스크 서버가 시작되었습니다.")
    print("스마트폰에서 접속하려면 같은 Wi-Fi에 연결하고 PC의 IP 주소(예: http://192.168.0.X:5000)로 접속하세요.")
    app.run(host="0.0.0.0", port=5000, debug=True)
