"""Matrix engine — orchestrates (rubric × datasets × candidates) → MatrixRun.

The engine is the only consumer of binding + evaluator plugins together; it
owns concurrency, retry policy, error isolation, and LangSmith tracing. The
shapes it produces (`MatrixRun`, `MatrixRunResult`, `EvaluatorScore`) live in
`mmfp.models.matrix_run`.
"""

from mmfp.engine.matrix import MatrixEngine
from mmfp.engine.scoring import ScoringEngine

__all__ = ["MatrixEngine", "ScoringEngine"]
