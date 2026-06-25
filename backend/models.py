from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ----- POST /simulate — request ---------------------------------------------
class SimulationInputs(BaseModel):
    attendance  : float = Field(..., ge=0, le=100, description = "Attendance rate (0-100)")
    grades      : float = Field(..., ge=0, le=100, description="Academic score (0-100)")
    counselling : int   = Field(..., ge=0, le=10, description="Number of counselling sessions")
    welfare     : float = Field(..., ge=0.0, le=2.0, description="Welfare support level (0=none, 0.5=partial, 1=full")

class SimulateRequest(BaseModel):
    studentId: str
    inputs : SimulationInputs

# ----- POST /simulate — response --------------------------------------------
class RecommendationItem(BaseModel):
    category: str
    urgency: Literal["critical", "high", "medium", "routine"]
    title: str
    description: str
    expected_impact: str

class FactorWeights(BaseModel):
    attendance: float
    academic: float
    socioeconomic: float
    family: float

class SimulateResponse(BaseModel):
    baselineScore: float
    projectedScore: float
    riskLevel: str
    riskLabel: str
    scoreChangeText: str
    dropoutProbability: float
    insightText: str
    narrative: str
    weights: FactorWeights
    recommendations: list[RecommendationItem]

# ----- GET /students — response ---------------------------------------------
class StudentSummary(BaseModel):
    id: str
    name: str
    form: str
    school: str
    attendance: float
    grades: float
    counselling: int
    welfare: float
    currentScore: float
    currentRisk: str

# ----- GET /students/:id — response ----------------------------------------
StudentDetail = StudentSummary

# ----- Generic error response ----------------------------------------------
class ErrorResponse(BaseModel):
    detail: str