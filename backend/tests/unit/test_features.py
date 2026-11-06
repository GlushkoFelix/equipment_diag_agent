"""特征校验、派生特征与 input_fingerprint 测试（ARCH §4.1 / §5.4.6）。"""

from __future__ import annotations

import pytest

from app import features

VALID = {
    "device_id": "3号机",
    "product_type": "M",
    "air_temp_k": 298.1,
    "process_temp_k": 305.3,
    "rotational_speed_rpm": 1250,
    "torque_nm": 30,
    "tool_wear_min": 100,
}


def test_normalize_complete_input_ok():
    result = features.normalize_input("form", VALID)
    assert result.ok is True
    assert result.missing_fields == []
    assert result.normalized["product_type"] == "M"
    assert result.completeness == 1.0


def test_device_id_required_and_validated():
    result = features.normalize_input("nl", {"text": "异响", "torque_nm": 55})
    assert result.ok is False
    assert result.error_code == "DEVICE_ID_INVALID"
    assert result.fields[0]["field"] == "device_id"


@pytest.mark.parametrize("device_id", ["", "  ", "a" * 65, "3号机!", None])
def test_device_id_invalid_values(device_id):
    payload = dict(VALID, device_id=device_id)
    result = features.normalize_input("form", payload)
    assert result.ok is False
    assert result.error_code == "DEVICE_ID_INVALID"


def test_nl_partial_missing_fields_excludes_device_id():
    result = features.normalize_input(
        "nl", {"text": "3号机异响，扭矩 55", "device_id": "3号机", "torque_nm": 55}
    )
    assert result.ok is True
    fields = [f["field"] for f in result.missing_fields]
    assert fields == [
        "product_type",
        "air_temp_k",
        "process_temp_k",
        "rotational_speed_rpm",
        "tool_wear_min",
    ]
    assert result.fingerprint is None


def test_form_missing_is_field_error_not_clarification():
    payload = dict(VALID)
    payload.pop("torque_nm")
    result = features.normalize_input("form", payload)
    assert result.ok is False
    assert result.error_code == "VALIDATION_FAILED"
    assert result.missing_fields[0]["reason"] == "MISSING"


def test_out_of_range_rejected():
    payload = dict(VALID, torque_nm=500)
    result = features.normalize_input("form", payload)
    assert result.ok is False
    assert result.error_code == "FEATURE_OUT_OF_RANGE"
    assert result.fields[0]["field"] == "torque_nm"


def test_machine_stopped_blocked():
    payload = dict(VALID, rotational_speed_rpm=0, torque_nm=0)
    result = features.normalize_input("form", payload)
    assert result.ok is False
    assert result.error_code == "MACHINE_STOPPED"


def test_data_contradiction_blocked():
    payload = dict(VALID, rotational_speed_rpm=0, torque_nm=10)
    result = features.normalize_input("form", payload)
    assert result.ok is False
    assert result.error_code == "DATA_CONTRADICTION"


def test_zero_load_is_quality_flag_not_blocking():
    payload = dict(VALID, torque_nm=0)
    result = features.normalize_input("form", payload)
    assert result.ok is True
    assert "ZERO_LOAD" in result.data_quality_flags


def test_temp_inversion_is_quality_flag():
    payload = dict(VALID, air_temp_k=308.6, process_temp_k=298.1)
    result = features.normalize_input("form", payload)
    assert result.ok is True
    assert "TEMP_INVERSION" in result.data_quality_flags


def test_derived_features_match_reference_values():
    result = features.normalize_input("form", VALID)
    assert result.derived["temp_diff"] == pytest.approx(7.2)
    assert result.derived["power_w"] == pytest.approx(3927.0, abs=0.01)
    assert result.derived["wear_torque"] == 3000


def test_fingerprint_is_stable_and_order_independent():
    a = features.compute_fingerprint(1, "form", VALID, "")
    b = features.compute_fingerprint(1, "form", dict(reversed(list(VALID.items()))), "")
    assert a == b
    assert a.startswith("sha256:") and len(a) == 71


def test_fingerprint_normalizes_whitespace_and_unicode():
    a = features.compute_fingerprint(1, "nl", VALID, "  3号机   异响 ")
    b = features.compute_fingerprint(1, "nl", VALID, "3号机 异响")
    assert a == b


def test_fingerprint_differs_by_input_type_and_user():
    form_fp = features.compute_fingerprint(1, "form", VALID, "")
    nl_fp = features.compute_fingerprint(1, "nl", VALID, "")
    other_user = features.compute_fingerprint(2, "form", VALID, "")
    assert form_fp != nl_fp
    assert form_fp != other_user


def test_fingerprint_none_when_incomplete():
    payload = dict(VALID)
    payload.pop("tool_wear_min")
    assert features.compute_fingerprint(1, "nl", payload, "") is None
