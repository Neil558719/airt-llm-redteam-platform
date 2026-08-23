"""共享数据模型：评测结果、打分细则、幻觉检测报告。

放在独立模块，避免 clients / judge / hallucination 之间的循环导入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# 幻觉判定类别
SUPPORTED = "SUPPORTED"            # 上下文支持该断言
NOT_SUPPORTED = "NOT_SUPPORTED"    # 上下文不支持（无依据）→ 幻觉
CONTRADICTED = "CONTRADICTED"      # 与上下文矛盾 → 幻觉
_HALLUCINATED = (NOT_SUPPORTED, CONTRADICTED)


@dataclass
class SemanticResult:
    """语义等价性评估结果。"""

    equivalent: bool
    score: float  # 0~1
    reasoning: str = ""


@dataclass
class JudgeResult:
    """LLM-as-Judge 打分结果。score 取值 1~max_score。"""

    score: float
    max_score: float = 5.0
    reasoning: str = ""
    spec_name: str = ""

    @property
    def normalized(self) -> float:
        """归一化到 0~1，用于跨用例聚合准确率。"""
        if self.max_score <= 0:
            return 0.0
        return max(0.0, min(1.0, self.score / self.max_score))

    @property
    def passed(self, min_score: Optional[float] = None) -> bool:
        threshold = self.max_score if min_score is None else min_score
        return self.score >= threshold


@dataclass
class ClaimVerdict:
    """单条事实断言的核对结果。"""

    claim: str
    verdict: str  # SUPPORTED / NOT_SUPPORTED / CONTRADICTED
    confidence: float = 1.0
    evidence: str = ""

    @property
    def is_hallucinated(self) -> bool:
        return self.verdict in _HALLUCINATED


@dataclass
class HallucinationReport:
    """一次幻觉检测的完整报告。"""

    response: str = ""
    context: str = ""
    claims: List[ClaimVerdict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.claims)

    @property
    def hallucinated(self) -> List[ClaimVerdict]:
        return [c for c in self.claims if c.is_hallucinated]

    @property
    def supported(self) -> List[ClaimVerdict]:
        return [c for c in self.claims if c.verdict == SUPPORTED]

    @property
    def contradicted(self) -> List[ClaimVerdict]:
        return [c for c in self.claims if c.verdict == CONTRADICTED]

    @property
    def hallucination_rate(self) -> float:
        """幻觉率 = 幻觉断言数 / 总断言数。"""
        return len(self.hallucinated) / self.total if self.total else 0.0

    @property
    def support_rate(self) -> float:
        return len(self.supported) / self.total if self.total else 0.0

    @property
    def contradiction_rate(self) -> float:
        return len(self.contradicted) / self.total if self.total else 0.0

    def as_dict(self) -> dict:
        return {
            "response": self.response,
            "context": self.context,
            "claims": [
                {"claim": c.claim, "verdict": c.verdict,
                 "confidence": c.confidence, "evidence": c.evidence}
                for c in self.claims
            ],
            "total": self.total,
            "hallucination_rate": self.hallucination_rate,
            "support_rate": self.support_rate,
            "contradiction_rate": self.contradiction_rate,
        }


@dataclass
class AppResponse:
    """被测应用（RAG 助手）的结构化回答。

    - answer: 应用生成的最终回答文本
    - sources: 应用检索/生成时实际参考的上下文片段（幻觉检测用它核对事实）
    真实 RAG 应用通常把这两者一起返回；测试时请传入应用真正看到的 sources。
    """

    answer: str = ""
    sources: List[str] = field(default_factory=list)


@dataclass
class JudgeSpec:
    """打分细则（rubric）。

    - criteria: 评分的标准描述，真实模式下交给 LLM。
    - keywords: Mock 模式下的判定提示——响应包含这些关键词越多，分越高。
      真实模式下被忽略。
    - min_score: 该细则的通过线。
    """

    name: str
    criteria: str
    scale: int = 100
    min_score: float = 60.0
    keywords: Tuple[str, ...] = ()

    def describe(self) -> str:
        return self.criteria

    # ---- 预设 rubric ----

    @classmethod
    def accuracy(cls, **kw) -> "JudgeSpec":
        """准确率：答案是否正确、贴合事实。"""
        return cls(
            name="accuracy",
            criteria=(
                "评估回答的准确性：是否与已知事实一致、无错误信息、直接回答了用户问题。"
                "对于计算题或事实题，只要答案的数值/事实正确即为准确，简洁作答（如只给数字）不应扣分。"
                "1=完全错误或答非所问，60=基本正确但有小瑕疵，100=完全正确。"
            ),
            **kw,
        )

    @classmethod
    def relevance(cls, **kw) -> "JudgeSpec":
        """相关性：回答是否切题。"""
        return cls(
            name="relevance",
            criteria=(
                "评估回答的相关性：是否直接回应了用户问题，而非答非所问或包含无关信息。"
                "1=完全不相关，60=部分相关，100=高度相关。"
            ),
            **kw,
        )

    @classmethod
    def faithfulness(cls, **kw) -> "JudgeSpec":
        """忠实度：回答是否忠于给定上下文（RAG 场景）。"""
        return cls(
            name="faithfulness",
            criteria=(
                "评估回答的忠实度：回答中的所有主张是否都能由给定上下文支撑，"
                "是否存在编造或与上下文矛盾的内容。1=大量编造，60=基本忠实，100=完全忠实。"
            ),
            **kw,
        )

    @classmethod
    def helpfulness(cls, **kw) -> "JudgeSpec":
        """有用性：回答是否清晰有用。"""
        return cls(
            name="helpfulness",
            criteria=(
                "评估回答的有用性：是否清晰、完整、易理解，能否真正帮到用户。"
                "1=无价值，60=基本有用，100=非常有用。"
            ),
            **kw,
        )
