"""指标采集：当前用例上下文 + 数据记录 + 会话汇总。

- pytest 插件为每个用例建立 TestRecord（begin / finish）
- 客户端、断言、评测函数通过 tracker 把延迟 / 幻觉率 / Judge 分等写入"当前活动用例"
- 会话结束 summarize() 聚合出看板指标
"""

from __future__ import annotations

import contextvars
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..specs import HallucinationReport, JudgeResult

# 延迟来源标记（与 clients/base.py 保持一致）
SOURCE_APP = "app"
SOURCE_FRAMEWORK = "framework"


def _mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


@dataclass
class MetricEntry:
    name: str
    value: float
    unit: str = ""
    meta: str = ""


@dataclass
class AssertionEntry:
    name: str
    passed: bool
    message: str = ""
    score: Optional[float] = None
    threshold: Optional[float] = None


@dataclass
class TestRecord:
    """单个测试用例的完整记录。"""

    nodeid: str
    name: str
    outcome: str = "pending"  # pending | passed | failed | skipped | error
    duration: float = 0.0
    failure: str = ""
    traceback: str = ""
    started_at: float = 0.0
    app_latency_ms: List[float] = field(default_factory=list)
    framework_latency_ms: List[float] = field(default_factory=list)
    metrics: List[MetricEntry] = field(default_factory=list)
    judge_results: List[JudgeResult] = field(default_factory=list)
    hallucination_reports: List[HallucinationReport] = field(default_factory=list)
    assertions: List[AssertionEntry] = field(default_factory=list)

    # ---- 便捷聚合 ----

    @property
    def avg_app_latency(self) -> Optional[float]:
        return _mean(self.app_latency_ms)

    @property
    def avg_judge_normalized(self) -> Optional[float]:
        return _mean([r.normalized for r in self.judge_results])

    @property
    def avg_judge_raw(self) -> Optional[float]:
        return _mean([r.score for r in self.judge_results])

    @property
    def hallucination_rate(self) -> Optional[float]:
        return _mean([r.hallucination_rate for r in self.hallucination_reports])

    @property
    def last_hallucination_report(self) -> Optional[HallucinationReport]:
        return self.hallucination_reports[-1] if self.hallucination_reports else None

    def record_metric(self, name: str, value: float, unit: str = "", meta: str = "") -> None:
        self.metrics.append(MetricEntry(name=name, value=value, unit=unit, meta=meta))

    def add_judge(self, result: JudgeResult) -> None:
        self.judge_results.append(result)

    def add_hallucination(self, report: HallucinationReport) -> None:
        self.hallucination_reports.append(report)

    def add_assertion(
        self,
        name: str,
        passed: bool,
        message: str = "",
        score: Optional[float] = None,
        threshold: Optional[float] = None,
    ) -> None:
        self.assertions.append(
            AssertionEntry(name=name, passed=passed, message=message, score=score, threshold=threshold)
        )


@dataclass
class Summary:
    """看板聚合指标。"""

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    error: int = 0
    duration: float = 0.0
    accuracy: Optional[float] = None          # Judge 归一化平均（0~1）
    hallucination_rate: Optional[float] = None  # 幻觉率平均
    avg_app_latency_ms: Optional[float] = None
    env: Dict[str, str] = field(default_factory=dict)

    @property
    def pass_rate(self) -> Optional[float]:
        attempted = self.passed + self.failed + self.error
        if attempted == 0:
            return None
        return self.passed / attempted


class _Tracker:
    """全局指标采集器（单例）。"""

    def __init__(self) -> None:
        self.records: List[TestRecord] = []
        self._by_nodeid: Dict[str, TestRecord] = {}
        self._active: contextvars.ContextVar[Optional[TestRecord]] = contextvars.ContextVar(
            "llmtest_active_record", default=None
        )
        self.session_started_at = time.time()

    # ---- 生命周期 ----

    @property
    def active(self) -> Optional[TestRecord]:
        return self._active.get()

    def begin(self, nodeid: str, name: str) -> TestRecord:
        rec = TestRecord(nodeid=nodeid, name=name, started_at=time.time())
        self.records.append(rec)
        self._by_nodeid[nodeid] = rec
        self._active.set(rec)
        return rec

    def finish(self, nodeid: str, outcome: str, duration: float, failure: str = "", traceback: str = "") -> None:
        rec = self._by_nodeid.get(nodeid)
        if rec is None:
            return
        rec.outcome = outcome
        rec.duration = duration
        rec.failure = failure
        rec.traceback = traceback
        self._active.set(None)

    def by_nodeid(self, nodeid: str) -> Optional[TestRecord]:
        return self._by_nodeid.get(nodeid)

    # ---- 记录 ----

    def record_latency(self, ms: float, source: str) -> None:
        rec = self.active
        if rec is None:
            return
        if source == SOURCE_APP:
            rec.app_latency_ms.append(ms)
        else:
            rec.framework_latency_ms.append(ms)

    def record_metric(self, name: str, value: float, unit: str = "", meta: str = "") -> None:
        rec = self.active
        if rec is not None:
            rec.record_metric(name, value, unit, meta)

    def add_judge(self, result: JudgeResult) -> None:
        rec = self.active
        if rec is not None:
            rec.add_judge(result)

    def add_hallucination(self, report: HallucinationReport) -> None:
        rec = self.active
        if rec is not None:
            rec.add_hallucination(report)

    def add_assertion(
        self,
        name: str,
        passed: bool,
        message: str = "",
        score: Optional[float] = None,
        threshold: Optional[float] = None,
    ) -> None:
        rec = self.active
        if rec is not None:
            rec.add_assertion(name, passed, message, score, threshold)

    # ---- 汇总 ----

    def summarize(self, env: Optional[Dict[str, str]] = None) -> Summary:
        summary = Summary(
            total=len(self.records),
            duration=time.time() - self.session_started_at,
            env=env or {},
        )
        judge_norm: List[float] = []
        hallu: List[float] = []
        app_lat: List[float] = []
        for rec in self.records:
            if rec.outcome == "passed":
                summary.passed += 1
            elif rec.outcome == "failed":
                summary.failed += 1
            elif rec.outcome == "skipped":
                summary.skipped += 1
            elif rec.outcome == "error":
                summary.error += 1
            if rec.avg_judge_normalized is not None:
                judge_norm.append(rec.avg_judge_normalized)
            if rec.hallucination_rate is not None:
                hallu.append(rec.hallucination_rate)
            if rec.avg_app_latency is not None:
                app_lat.append(rec.avg_app_latency)
        summary.accuracy = _mean(judge_norm)
        summary.hallucination_rate = _mean(hallu)
        summary.avg_app_latency_ms = _mean(app_lat)
        return summary


# 进程级单例
tracker = _Tracker()


@contextmanager
def track_latency(source: str = SOURCE_APP):
    """计时任意自定义调用，把延迟记入当前用例指标（看板「平均延迟」数据来源）。

    用于被测应用的适配器 / 自定义调用：把 requests、gRPC 等真实调用包进去即可自动采集。

    用法：
        from llmtest import track_latency
        with track_latency():
            resp = requests.post(url, json=body)   # 耗时自动写入报告
    """
    t0 = time.perf_counter()
    try:
        yield
    finally:
        tracker.record_latency((time.perf_counter() - t0) * 1000.0, source)
