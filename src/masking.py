"""
LLM에 전달되기 전 고객 PII를 마스킹하는 모듈.

원칙
- 구조화 필드(customer_name, phone, imei, imsi, customer_id)는 결정적 가명처리(pseudonymize)로
  치환한다. 같은 값은 항상 같은 토큰이 되므로 "같은 고객의 반복 민원" 같은 군집 분석은
  가능하되, 실제 식별정보는 LLM/로그/모델 학습 데이터에 절대 노출되지 않는다.
- 자유텍스트(complaint_text)는 정규식으로 전화번호/15자리 단말식별번호/이름 패턴을 탐지해
  같은 토큰으로 치환한다. LLM에 넘기는 것은 항상 이 마스킹 결과물뿐이어야 한다.
- 가명처리 salt(MASK_SALT)는 운영 환경에서는 반드시 비밀관리시스템에서 주입해야 한다.
  여기서는 테스트 데이터용 기본값을 둔다.
"""
import hashlib
import hmac
import json
import os
import re
from typing import Optional, Tuple

MASK_SALT = os.environ.get("MASK_SALT", "dev-only-salt-change-me").encode()

PHONE_RE = re.compile(r"01[016789]-?\d{3,4}-?\d{4}")
FIFTEEN_DIGIT_RE = re.compile(r"\b\d{15}\b")
CUSTOMER_ID_RE = re.compile(r"\bCUST-\d{6}\b")
# 흔한 한글 이름 뒤에 붙는 존칭 패턴 (예: "김민준님", "박서연 고객")
NAME_HONORIFIC_RE = re.compile(r"[가-힣]{2,4}(?=\s?(님|고객))")

KOREAN_MCC = "450"  # 국내 IMSI는 450으로 시작 (자유텍스트에서 IMEI/IMSI 구분용 휴리스틱)


def _token(value: str, prefix: str) -> str:
    """HMAC 기반 결정적 가명 토큰. 같은 value는 항상 같은 토큰을 반환한다."""
    digest = hmac.new(MASK_SALT, value.encode("utf-8"), hashlib.sha256).hexdigest()[:8]
    return f"[{prefix}_{digest}]"


def mask_name(value: str) -> str:
    return _token(value, "NAME")


def mask_phone(value: str) -> str:
    return _token(re.sub(r"-", "", value), "PHONE")


def mask_imei(value: str) -> str:
    return _token(value, "IMEI")


def mask_imsi(value: str) -> str:
    return _token(value, "IMSI")


def mask_customer_id(value: str) -> str:
    return _token(value, "CUSTID")


def mask_structured_record(record: dict) -> dict:
    """구조화 PII 필드를 가명 토큰으로 치환한 새 dict 반환 (원본은 변경하지 않음)."""
    masked = dict(record)
    if "customer_name" in masked:
        masked["customer_name"] = mask_name(masked["customer_name"])
    if "phone" in masked:
        masked["phone"] = mask_phone(masked["phone"])
    if "imei" in masked:
        masked["imei"] = mask_imei(masked["imei"])
    if "imsi" in masked:
        masked["imsi"] = mask_imsi(masked["imsi"])
    if "customer_id" in masked:
        masked["customer_id"] = mask_customer_id(masked["customer_id"])
    return masked


def mask_free_text(text: str, known_pii: Optional[dict] = None) -> Tuple[str, int]:
    """
    자유텍스트 안에 섞인 PII를 탐지해 토큰으로 치환한다.
    known_pii(해당 레코드의 원본 성명/전화/IMEI/IMSI)를 넘기면 구조화 필드와
    동일한 토큰으로 일관되게 치환된다. 반환값은 (마스킹된 텍스트, 치환 개수).
    """
    known_pii = known_pii or {}
    count = 0

    def sub_phone(m):
        nonlocal count
        count += 1
        return mask_phone(m.group(0))

    def sub_15digit(m):
        nonlocal count
        count += 1
        raw = m.group(0)
        return mask_imsi(raw) if raw.startswith(KOREAN_MCC) else mask_imei(raw)

    def sub_custid(m):
        nonlocal count
        count += 1
        return mask_customer_id(m.group(0))

    def sub_name(m):
        nonlocal count
        count += 1
        return mask_name(m.group(0))

    text = PHONE_RE.sub(sub_phone, text)
    text = FIFTEEN_DIGIT_RE.sub(sub_15digit, text)
    text = CUSTOMER_ID_RE.sub(sub_custid, text)

    # known_pii에 있는 실제 성명이 텍스트에 그대로 등장하면 우선 치환 (동일 토큰 보장)
    name = known_pii.get("customer_name")
    if name and name in text:
        count += text.count(name)
        text = text.replace(name, mask_name(name))

    # 그 외 일반적인 "OO님/OO 고객" 패턴도 방어적으로 마스킹
    def sub_honorific(m):
        nonlocal count
        count += 1
        return mask_name(m.group(0))

    text = NAME_HONORIFIC_RE.sub(sub_honorific, text)

    return text, count


def mask_record(record: dict) -> Tuple[dict, int]:
    """레코드 전체(구조화 필드 + complaint_text)를 마스킹해 반환. 두 번째 값은 마스킹 건수."""
    masked_text, n = mask_free_text(record.get("complaint_text", ""), known_pii=record)
    masked = mask_structured_record(record)
    masked["complaint_text"] = masked_text
    # 구조화 필드 5개(name/phone/imei/imsi/customer_id)도 마스킹 건수에 포함
    n += sum(1 for k in ("customer_name", "phone", "imei", "imsi", "customer_id") if k in record)
    return masked, n


if __name__ == "__main__":
    in_path = "/Users/1109701/workspace/study/claude-project/data/raw_complaints.json"
    out_path = "/Users/1109701/workspace/study/claude-project/data/masked_complaints.json"
    audit_path = "/Users/1109701/workspace/study/claude-project/data/masking_audit.json"
    sample_path = "/Users/1109701/workspace/study/claude-project/data/masking_sample.json"

    with open(in_path, encoding="utf-8") as f:
        raw = json.load(f)

    masked_records = []
    total_masked = 0
    for rec in raw:
        m, n = mask_record(rec)
        masked_records.append(m)
        total_masked += n

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(masked_records, f, ensure_ascii=False, indent=2)

    audit = {
        "records_processed": len(raw),
        "pii_fields_masked": total_masked,
        "avg_pii_per_record": round(total_masked / len(raw), 2) if raw else 0,
    }
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    sample_fields = ("customer_name", "phone", "imei", "imsi", "complaint_text")
    sample = {
        "before": {k: raw[0][k] for k in sample_fields},
        "after": {k: masked_records[0][k] for k in sample_fields},
    }
    with open(sample_path, "w", encoding="utf-8") as f:
        json.dump(sample, f, ensure_ascii=False, indent=2)

    print(f"masked {len(raw)} records, {total_masked} PII fields redacted -> {out_path}")
    print("\n--- 마스킹 전/후 샘플 ---")
    print("BEFORE:", raw[0]["complaint_text"])
    print("AFTER :", masked_records[0]["complaint_text"])
    print("BEFORE customer_name/phone/imei/imsi:", raw[0]["customer_name"], raw[0]["phone"], raw[0]["imei"], raw[0]["imsi"])
    print("AFTER  customer_name/phone/imei/imsi:", masked_records[0]["customer_name"], masked_records[0]["phone"], masked_records[0]["imei"], masked_records[0]["imsi"])
