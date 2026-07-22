from pydantic import BaseModel
from typing import List, Optional


class RuleViolation(BaseModel):
    rule_name: str
    severity: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    file_path: str
    line: int
    message: str
    suggested_fix: Optional[str] = None
    code_snippet: Optional[str] = None


class ArchitectureReviewResponse(BaseModel):
    owner: str
    repo: str
    score: float  # Architectural health score from 0.0 to 100.0
    violations: List[RuleViolation]
