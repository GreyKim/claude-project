"""
군집/집계 파이프라인.

중요: 군집/집계(분석) 로직은 masked_complaints.json만 읽는다 (raw_complaints.json은 절대
입력으로 쓰지 않는다). 실제 서비스에서 이 단계가 LLM 호출(임베딩/요약/군집 태깅)로 대체되더라도,
LLM에는 마스킹된 데이터만 전달된다는 원칙을 코드 구조로 강제하기 위함이다.

예외: build_masking_comparisons()만 raw_complaints.json을 읽는다. 이는 분석 파이프라인이 아니라
"마스킹이 제대로 됐는지 검수"하기 위한 감사(audit) 목적 전용 함수이며, 대시보드에서도 기본적으로
값이 가려진 채로 노출되고 명시적으로 펼쳐야만 보이도록 처리한다 (실제 운영에서는 권한 있는
검수자만 접근 가능해야 하는 화면이라는 의도).

sklearn 등 외부 의존성 없이 순수 파이썬 키워드 매칭으로 카테고리 내 세부 군집(subcluster)을
나누는 경량 버전이다. 실제 서비스로 확장 시 이 부분만 임베딩+KMeans 등으로 교체하면 된다.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime

RAW_PATH = "/Users/1109701/workspace/study/claude-project/data/raw_complaints.json"
MASKED_PATH = "/Users/1109701/workspace/study/claude-project/data/masked_complaints.json"
AUDIT_PATH = "/Users/1109701/workspace/study/claude-project/data/masking_audit.json"
SAMPLE_PATH = "/Users/1109701/workspace/study/claude-project/data/masking_sample.json"
OUT_PATH = "/Users/1109701/workspace/study/claude-project/data/dashboard_data.json"
COMPARISON_ROWS = 15

# 카테고리별 세부 군집 키워드 사전 (마스킹된 텍스트에서도 유지되는 일반 단어 기준)
SUBCLUSTER_KEYWORDS = {
    "네트워크장애": [
        ("5G 신호 불량", ["5G", "신호"]),
        ("통화 품질/끊김", ["통화", "끊김"]),
        ("LTE 전환 문제", ["LTE", "3G", "전환"]),
    ],
    "요금청구": [
        ("과금 오류", ["요금", "청구"]),
        ("로밍 요금 이슈", ["로밍"]),
        ("부가서비스 오청구", ["부가서비스", "해지"]),
    ],
    "개통/해지": [
        ("개통 지연", ["개통", "지연"]),
        ("해지 후 재청구", ["해지"]),
        ("명의변경 오류", ["명의변경"]),
    ],
    "단말기불량": [
        ("재부팅/발열", ["재부팅", "발열"]),
        ("배터리 이슈", ["배터리"]),
        ("충전 불량", ["충전"]),
    ],
    "데이터속도저하": [
        ("피크타임 속도저하", ["저녁", "속도"]),
        ("테더링 속도제한", ["테더링"]),
        ("특정앱 속도이슈", ["앱"]),
    ],
    "고객센터응대": [
        ("장시간 대기", ["대기"]),
        ("상담이력 미공유", ["상담", "기록"]),
        ("안내 불일치", ["안내"]),
    ],
    "명의도용/보안": [
        ("미인지 회선개통", ["회선", "개통"]),
        ("유심 무단재발급", ["유심", "재발급"]),
        ("계정 무단접근", ["로그인", "계정"]),
    ],
}


def assign_subcluster(category: str, text: str) -> str:
    for label, keywords in SUBCLUSTER_KEYWORDS.get(category, []):
        if any(kw in text for kw in keywords):
            return label
    return "기타"


def build_masking_comparisons(masked_records):
    """검수용 원본↔마스킹 비교 테이블. 최근 티켓 기준 상위 COMPARISON_ROWS건만 노출한다."""
    with open(RAW_PATH, encoding="utf-8") as f:
        raw_records = json.load(f)
    raw_by_id = {r["ticket_id"]: r for r in raw_records}

    fields = ("customer_name", "phone", "imei", "imsi", "complaint_text")
    recent = sorted(masked_records, key=lambda r: r["created_at"], reverse=True)[:COMPARISON_ROWS]

    comparisons = []
    for m in recent:
        raw = raw_by_id[m["ticket_id"]]
        comparisons.append(
            {
                "ticket_id": m["ticket_id"],
                "category": m["category"],
                "before": {k: raw[k] for k in fields},
                "after": {k: m[k] for k in fields},
            }
        )
    return comparisons


def build_dashboard_data():
    with open(MASKED_PATH, encoding="utf-8") as f:
        records = json.load(f)
    with open(AUDIT_PATH, encoding="utf-8") as f:
        audit = json.load(f)
    with open(SAMPLE_PATH, encoding="utf-8") as f:
        masking_sample = json.load(f)

    for r in records:
        r["cluster"] = assign_subcluster(r["category"], r["complaint_text"])

    total = len(records)
    by_category = Counter(r["category"] for r in records)
    by_status = Counter(r["status"] for r in records)
    by_severity = Counter(r["severity"] for r in records)
    by_channel = Counter(r["channel"] for r in records)

    # 카테고리 > 세부군집 집계 (건수 상위 정렬), 각 군집 대표(마스킹된) 예시 1건 포함
    cluster_rows = []
    grouped = defaultdict(list)
    for r in records:
        grouped[(r["category"], r["cluster"])].append(r)
    for (category, cluster), rows in grouped.items():
        cluster_rows.append(
            {
                "category": category,
                "cluster": cluster,
                "count": len(rows),
                "urgent_count": sum(1 for x in rows if x["severity"] == "긴급"),
                "example_text": rows[0]["complaint_text"],
            }
        )
    cluster_rows.sort(key=lambda x: x["count"], reverse=True)

    # 일자별 추이 (최근 90일)
    day_counter = Counter(r["created_at"][:10] for r in records)
    trend = [{"date": d, "count": c} for d, c in sorted(day_counter.items())]

    # 주간 추이
    def week_key(date_str):
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"

    week_counter = Counter(week_key(r["created_at"][:10]) for r in records)
    weekly_trend = [{"week": w, "count": c} for w, c in sorted(week_counter.items())]

    # 마스킹 토큰(가명) 기준 재문의 고객 탐지 - 원본 식별정보 없이도 반복 민원 파악 가능함을 보여줌
    customer_counter = Counter(r["customer_name"] for r in records)
    repeat_customers = sum(1 for c in customer_counter.values() if c > 1)

    open_count = by_status.get("접수", 0) + by_status.get("처리중", 0) + by_status.get("보류", 0)
    urgent_open = sum(1 for r in records if r["severity"] == "긴급" and r["status"] != "완료")

    dashboard = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "kpi": {
            "total_tickets": total,
            "open_tickets": open_count,
            "urgent_open": urgent_open,
            "repeat_customers": repeat_customers,
            "pii_fields_masked": audit["pii_fields_masked"],
            "avg_pii_per_ticket": audit["avg_pii_per_record"],
        },
        "by_category": [{"name": k, "count": v} for k, v in by_category.most_common()],
        "by_status": [{"name": k, "count": v} for k, v in by_status.items()],
        "by_severity": [{"name": k, "count": v} for k, v in by_severity.items()],
        "by_channel": [{"name": k, "count": v} for k, v in by_channel.most_common()],
        "clusters": cluster_rows,
        "daily_trend": trend,
        "weekly_trend": weekly_trend,
        "recent_tickets": sorted(records, key=lambda r: r["created_at"], reverse=True)[:20],
        "masking_sample": masking_sample,
        "masking_comparisons": build_masking_comparisons(records),
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)
    print(f"dashboard data -> {OUT_PATH} ({total} tickets, {len(cluster_rows)} clusters)")


if __name__ == "__main__":
    build_dashboard_data()
