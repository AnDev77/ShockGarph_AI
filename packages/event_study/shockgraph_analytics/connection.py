"""연결 상태 메타데이터. 파일 경로·이용 기록 본문·시장 원본을 공개하지 않는다."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from shockgraph_analytics.scenarios import Record

INPUT_NAMES = ("release_csv", "asset_bar_csv", "consensus_json", "target_quotes_json")
REQUIRED_USES = {"storage", "statistical_analysis", "derived_publication"}
REQUIRED_SCOPES = {"cpi_releases", "asset_prices", "consensus", "event_probabilities"}
BLOCKER_LABELS = {
    "manifest_missing": "실제 데이터 파일 위치와 분석 대상 설정이 필요합니다.",
    "manifest_invalid": "연결 설정의 형식 또는 발표 시각을 확인해야 합니다.",
    "release_csv_missing": "사건별 최초 CPI 발표 자료가 없습니다.",
    "asset_bar_csv_missing": "사건별 SPY·TLT 가격 원본이 없습니다.",
    "consensus_json_missing": "발표 전에 보존한 사건별 컨센서스가 없습니다.",
    "target_quotes_json_missing": "분석 대상의 발표 전 다중 임계값 호가가 없습니다.",
    "authorization_missing": "자료의 보관·통계 분석·파생 결과 공개 이용 범위 기록이 필요합니다.",
    "authorization_invalid": "이용 범위 기록의 형식·유효기간·적용 자료를 확인해야 합니다.",
    "input_invalid": "입력 자료의 형식·중복·시점·계약 정의 검증을 통과하지 못했습니다.",
    "snapshot_missing": "검증된 실제 서비스 스냅샷이 연결되지 않았습니다.",
    "snapshot_invalid": "서비스 스냅샷의 내용 또는 출처 검증을 통과하지 못했습니다.",
    "readiness_invalid": "연결 상태 보고서 검증을 통과하지 못했습니다.",
    "scenario_sample_shortfall": "확률이 있는 시나리오의 과거 사건 표본이 부족합니다.",
}


class ServingManifest(Record):
    schema_version: Literal["cpi-serving-manifest-v1"] = "cpi-serving-manifest-v1"
    source_kind: Literal["synthetic", "licensed_historical"]
    source_reference: str = Field(min_length=1)
    target_event_id: str = Field(min_length=1)
    as_of: datetime
    release_at: datetime
    label_timing_policy: Literal["official_release_timestamp_proxy"]
    release_csv: Path
    asset_bar_csv: Path
    consensus_json: Path
    target_quotes_json: Path
    authorization_record: Path | None = None

    @model_validator(mode="after")
    def timeline(self) -> Self:
        if self.as_of >= self.release_at:
            raise ValueError("target cutoff must precede release")
        return self


class AuthorizationRecord(Record):
    schema_version: Literal["cpi-serving-authorization-v1"] = "cpi-serving-authorization-v1"
    reference: str = Field(min_length=1)
    data_scopes: set[str]
    uses: set[str]
    valid_until: datetime | None = None

    def covers(self, checked_at: datetime) -> bool:
        return (
            self.uses >= REQUIRED_USES
            and self.data_scopes >= REQUIRED_SCOPES
            and (self.valid_until is None or self.valid_until > checked_at)
        )


class InputState(Record):
    name: Literal[
        "release_csv",
        "asset_bar_csv",
        "consensus_json",
        "target_quotes_json",
        "authorization_record",
    ]
    status: Literal["missing", "present", "invalid", "not_required"]


class ConnectionBlocker(Record):
    code: str
    label: str

    @model_validator(mode="after")
    def known_label(self) -> Self:
        if self.code not in BLOCKER_LABELS or self.label != BLOCKER_LABELS[self.code]:
            raise ValueError("unknown connection blocker")
        return self


def blocker(code: str) -> ConnectionBlocker:
    return ConnectionBlocker(code=code, label=BLOCKER_LABELS[code])


class ConnectionAudit(Record):
    schema_version: Literal["cpi-serving-readiness-v1"] = "cpi-serving-readiness-v1"
    checked_at: datetime
    source_kind: Literal["synthetic", "licensed_historical"]
    status: Literal["blocked", "inputs_present", "snapshot_built"]
    inputs: list[InputState]
    blockers: list[ConnectionBlocker]
    event_counts: dict[
        Literal[
            "target_event",
            "not_historical",
            "missing_consensus",
            "late_consensus",
            "missing_price",
            "price_session_mismatch",
            "returns_not_available",
            "eligible",
        ],
        int,
    ] = Field(default_factory=dict)
    snapshot_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def consistency(self) -> Self:
        if len({i.name for i in self.inputs}) != len(self.inputs):
            raise ValueError("duplicate input status")
        if any(v < 0 for v in self.event_counts.values()):
            raise ValueError("negative event count")
        if (self.status == "blocked") != bool(self.blockers):
            raise ValueError("status and blockers differ")
        if self.status == "snapshot_built" and self.snapshot_sha256 is None:
            raise ValueError("built snapshot requires its hash")
        if self.status != "blocked":
            states = {i.name: i.status for i in self.inputs}
            if any(states.get(name) != "present" for name in INPUT_NAMES):
                raise ValueError("non-blocked status requires every financial input")
            expected = "present" if self.source_kind == "licensed_historical" else "not_required"
            if states.get("authorization_record") != expected:
                raise ValueError("authorization input state differs from source")
        return self
