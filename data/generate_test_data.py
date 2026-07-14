"""
테스트용 고객불만/장애 접수 데이터 생성기 (전부 가상 데이터)
실제 CRM/장애관리시스템에서 넘어오는 원본(raw) 데이터를 흉내낸다.
PII(성명/연락처/IMEI/IMSI/고객ID)가 구조화 필드와 자유텍스트(complaint_text) 양쪽에 섞여 들어간다.
"""
import json
import random
from datetime import datetime, timedelta

random.seed(42)

SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임"]
GIVEN1 = ["민", "서", "지", "현", "예", "도", "하", "유", "성", "재"]
GIVEN2 = ["준", "우", "은", "아", "훈", "빈", "율", "진", "원", "경"]

CATEGORIES = [
    "네트워크장애",
    "요금청구",
    "개통/해지",
    "단말기불량",
    "데이터속도저하",
    "고객센터응대",
    "명의도용/보안",
]

CHANNELS = ["콜센터", "앱채팅", "매장방문", "이메일", "SNS"]
SEVERITIES = ["낮음", "보통", "높음", "긴급"]
STATUSES = ["접수", "처리중", "완료", "보류"]

# 카테고리별 불만 텍스트 템플릿. {name}/{phone}/{imei}/{imsi} 자리에 실제 값이 들어가
# 자유텍스트 안에도 PII가 섞이는 상황을 재현한다.
TEMPLATES = {
    "네트워크장애": [
        "{name} 고객님 댁 주소 인근에서 어제 저녁부터 5G 신호가 전혀 안 잡힙니다. 연락처 {phone}로 회신 부탁드립니다.",
        "강남 지역 기지국 장애로 통화 끊김이 반복됩니다. IMEI {imei} 단말기에서 계속 재현됩니다.",
        "실외에서도 LTE가 3G로 자꾸 전환됩니다. 가입자 {imsi} 회선입니다.",
    ],
    "요금청구": [
        "이번 달 요금이 평소보다 3만원 더 청구됐습니다. {name}입니다, {phone}로 확인 연락 주세요.",
        "해외 로밍을 쓴 적이 없는데 로밍 요금이 부과됐습니다. IMEI {imei} 단말기 기준으로 확인 부탁드립니다.",
        "부가서비스를 해지했는데 계속 청구되고 있어요. 고객명 {name}, 연락처 {phone}.",
    ],
    "개통/해지": [
        "온라인으로 신청한 개통이 3일째 지연되고 있습니다. {name} / {phone} 확인 부탁드립니다.",
        "해지 신청 후에도 요금이 계속 청구됩니다. 가입자식별번호 {imsi} 입니다.",
        "명의변경 절차가 안내와 다르게 진행됐습니다. {phone}로 다시 연락 주세요.",
    ],
    "단말기불량": [
        "구매한 지 한 달도 안 된 단말기가 자꾸 재부팅됩니다. IMEI {imei}, 연락처 {phone}.",
        "배터리가 비정상적으로 빨리 닳습니다. {name} 고객이며 단말기 IMEI는 {imei}입니다.",
        "충전 중 발열이 심합니다. 안전 관련 이슈로 빠른 확인 부탁드립니다. IMEI {imei}.",
    ],
    "데이터속도저하": [
        "매일 저녁 7~9시 사이에 데이터 속도가 급격히 느려집니다. IMSI {imsi} 회선입니다.",
        "테더링 시 속도 제한이 안내보다 빨리 걸립니다. {name}, {phone}로 연락 바랍니다.",
        "특정 앱에서만 속도가 느려지는 현상이 있습니다. 단말 IMEI {imei}.",
    ],
    "고객센터응대": [
        "상담원 연결까지 40분 이상 대기했습니다. 응대 개선 요청드립니다. {name} / {phone}.",
        "이전 상담 내용이 기록에 전혀 남아있지 않아 같은 설명을 반복했습니다.",
        "상담원의 설명이 안내마다 달라서 혼란스럽습니다. {phone}로 콜백 요청합니다.",
    ],
    "명의도용/보안": [
        "제 명의로 모르는 회선이 추가 개통된 것을 발견했습니다. 즉시 확인 부탁드립니다. {name}, {phone}.",
        "본인인증 없이 유심이 재발급된 정황이 있습니다. IMSI {imsi} 확인 요청합니다.",
        "타인이 제 계정으로 로그인한 이력이 있습니다. 보안 조치 부탁드립니다.",
    ],
}


def rand_name():
    return random.choice(SURNAMES) + random.choice(GIVEN1) + random.choice(GIVEN2)


def rand_phone():
    return f"010-{random.randint(1000,9999)}-{random.randint(1000,9999)}"


def rand_imei():
    return "".join(str(random.randint(0, 9)) for _ in range(15))


def rand_imsi():
    mnc = random.choice(["05", "02", "08", "06"])  # 가상의 통신사 코드
    return "450" + mnc + "".join(str(random.randint(0, 9)) for _ in range(10))


def rand_customer_id(i):
    return f"CUST-{i:06d}"


def generate(n=150):
    records = []
    base_date = datetime(2026, 7, 14)
    for i in range(1, n + 1):
        category = random.choice(CATEGORIES)
        template = random.choice(TEMPLATES[category])
        name = rand_name()
        phone = rand_phone()
        imei = rand_imei()
        imsi = rand_imsi()
        text = template.format(name=name, phone=phone, imei=imei, imsi=imsi)
        days_ago = random.randint(0, 89)
        created = base_date - timedelta(days=days_ago, hours=random.randint(0, 23))
        status = random.choices(STATUSES, weights=[0.15, 0.25, 0.55, 0.05])[0]

        records.append(
            {
                "ticket_id": f"TCK-{i:05d}",
                "created_at": created.strftime("%Y-%m-%d %H:%M"),
                "category": category,
                "channel": random.choice(CHANNELS),
                "severity": random.choices(SEVERITIES, weights=[0.3, 0.4, 0.22, 0.08])[0],
                "status": status,
                "customer_id": rand_customer_id(i),
                "customer_name": name,
                "phone": phone,
                "imei": imei,
                "imsi": imsi,
                "complaint_text": text,
            }
        )
    return records


if __name__ == "__main__":
    data = generate(150)
    out_path = "/Users/1109701/workspace/study/claude-project/data/raw_complaints.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"generated {len(data)} records -> {out_path}")
