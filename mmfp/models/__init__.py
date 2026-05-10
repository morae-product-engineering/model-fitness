"""MMFP runtime data contracts.

Pydantic v2 models that define the shapes the platform exchanges across
boundaries (UI, persistence, exports). Schema-versioned so older artefacts
remain re-scoreable under newer rubrics.
"""

from mmfp.models.candidate import (
    Candidate,
    CandidateBinding,
    CandidateFamily,
    CandidateStatus,
)
from mmfp.models.dataset import Dataset, DatasetExample
from mmfp.models.matrix_run import (
    EvaluatorScore,
    MatrixRun,
    MatrixRunResult,
    Scorecard,
    SourceField,
)
from mmfp.models.rubric import (
    Dimension,
    EvaluationMode,
    Gate,
    JudgeConfig,
    Method,
    ObservabilityConfig,
    PortfolioThresholds,
    Rubric,
    Tier,
    Weight,
)

__all__ = [
    "Candidate",
    "CandidateBinding",
    "CandidateFamily",
    "CandidateStatus",
    "Dataset",
    "DatasetExample",
    "Dimension",
    "EvaluationMode",
    "EvaluatorScore",
    "Gate",
    "JudgeConfig",
    "MatrixRun",
    "MatrixRunResult",
    "Method",
    "ObservabilityConfig",
    "PortfolioThresholds",
    "Rubric",
    "Scorecard",
    "SourceField",
    "Tier",
    "Weight",
]
