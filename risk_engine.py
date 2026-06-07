
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────
#  Domain types
# ─────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW    = "low"       # 0–39
    MEDIUM = "medium"    # 40–64
    HIGH   = "high"      # 65–100


class Trend(str, Enum):
    IMPROVING  = "improving"
    STABLE     = "stable"
    WORSENING  = "worsening"


# ─────────────────────────────────────────────
#  Input / Output schemas
#  (plain dataclasses — easy to swap for
#   Pydantic models once Person 3 wires FastAPI)
# ─────────────────────────────────────────────

@dataclass
class StudentProfile:
    """
    Core student data consumed by the risk engine.

    Fields
    ------
    student_id      : unique identifier (maps to GET /students/:id)
    name            : display name
    grade           : e.g. "Form 4"
    attendance_rate : percentage 0–100  (from e-Kehadiran)
    academic_score  : percentage 0–100  (from PBD / UASA)
    socio_score     : 0–100; higher = more disadvantaged
                      (derived from RMT/BAP/KWAPM enrolment flags)
    family_support  : 0–100; higher = stronger support
                      (optional survey / counsellor assessment)
    trend           : historical trajectory over last 3 months
    """
    student_id     : str
    name           : str
    grade          : str
    attendance_rate: float          # 0–100
    academic_score : float          # 0–100
    socio_score    : float          # 0–100
    family_support : float = 60.0   # 0–100 (default neutral)
    trend          : Trend = Trend.STABLE


@dataclass
class SimulationInput:
    """
    Intervention adjustments from the What-If Simulator sliders.
    All deltas are *additions* to the student's current values.

    Maps directly to the four sliders shown in the UI prototype:
      - attendance_boost    → 'attendance rate' slider  (0–30 pp)
      - academic_boost      → 'academic grades' slider  (0–25 pts)
      - counselling_sessions → 'counselling sessions'  (0–10)
      - welfare_support     → 'welfare support'        (0=none / 0.5=partial / 1=full)
    """
    attendance_boost    : float = 0.0   # percentage points added
    academic_boost      : float = 0.0   # score points added
    counselling_sessions: int   = 0     # number of sessions
    welfare_support     : float = 0.0   # 0.0 / 0.5 / 1.0


@dataclass
class RiskScore:
    """Computed risk profile for a single student."""
    student_id      : str
    total_score     : float          # 0–100
    risk_level      : RiskLevel
    factor_weights  : dict[str, float]  # breakdown shown in UI panel
    dropout_prob_3m : float          # 0–1 probability at 3 months
    dropout_prob_6m : float          # 0–1 probability at 6 months
    trend           : Trend
    explanation     : str            # human-readable summary


@dataclass
class SimulationResult:
    """
    Returned by simulate(); consumed by:
      - Projected Risk Score card (centre panel)
      - 3-month dropout probability card (bottom-left)
      - Recommended Next Steps (fed into RecommendationEngine)
    """
    baseline_score      : float
    projected_score     : float
    score_delta         : float          # negative = improvement
    baseline_prob_3m    : float
    projected_prob_3m   : float
    risk_level_baseline : RiskLevel
    risk_level_projected: RiskLevel
    factor_weights      : dict[str, float]
    dominant_factor     : str
    summary             : str


# ─────────────────────────────────────────────
#  Weight configuration
#  (matches the bar chart in the UI prototype)
# ─────────────────────────────────────────────

DEFAULT_WEIGHTS: dict[str, float] = {
    "attendance"          : 0.45,
    "academic_performance": 0.30,
    "socioeconomic_status": 0.13,
    "family_support"      : 0.12,
}


# ─────────────────────────────────────────────
#  Core engine
# ─────────────────────────────────────────────

class RiskEngine:
    """
    Stateless risk scoring and What-If simulation engine.

    Usage
    -----
    engine = RiskEngine()

    # Score a student
    score = engine.score(student_profile)

    # Run a What-If simulation
    result = engine.simulate(student_profile, simulation_input)
    """

    def __init__(self, weights: Optional[dict[str, float]] = None):
        self.weights = weights or DEFAULT_WEIGHTS
        self._validate_weights()

    # ── public ──────────────────────────────

    def score(self, student: StudentProfile) -> RiskScore:
        """
        Compute the current dropout risk score for a student.

        Algorithm
        ---------
        Each factor is inverted/normalised to a 0–100 *risk contribution*
        (higher = worse), then multiplied by its weight.

          attendance_risk   = (100 − attendance_rate)
          academic_risk     = (100 − academic_score)
          socio_risk        = socio_score                 (already risk-oriented)
          family_risk       = (100 − family_support)

        Total score is the weighted sum, clamped to [1, 99].
        """
        raw = self._raw_factors(
            student.attendance_rate,
            student.academic_score,
            student.socio_score,
            student.family_support,
        )
        total = self._weighted_total(raw)
        factor_weights = self._factor_percentages(raw)

        prob_3m = self._dropout_probability(total, student.trend, months=3)
        prob_6m = self._dropout_probability(total, student.trend, months=6)
        level   = self._level(total)

        explanation = self._explain(
            student.name, total, level, factor_weights, student.trend
        )

        return RiskScore(
            student_id      = student.student_id,
            total_score     = total,
            risk_level      = level,
            factor_weights  = factor_weights,
            dropout_prob_3m = prob_3m,
            dropout_prob_6m = prob_6m,
            trend           = student.trend,
            explanation     = explanation,
        )

    def simulate(
        self,
        student: StudentProfile,
        inputs : SimulationInput,
    ) -> SimulationResult:
        """
        Apply intervention deltas and return the projected risk.

        Intervention effect mapping
        ---------------------------
        Each intervention maps to one or more factor improvements:

        attendance_boost (pp)
          → attendance_rate += boost

        academic_boost (pts)
          → academic_score += boost

        counselling_sessions (count)
          → family_support += sessions × 3   (capped at 100)
            attendance_rate += sessions × 0.8 (capped at 100)

        welfare_support (0 / 0.5 / 1.0)
          → socio_score    -= support × 18   (floored at 0)
            academic_score += support × 4
        """
        # Baseline
        baseline_risk  = self.score(student)
        baseline_score = baseline_risk.total_score
        baseline_3m    = baseline_risk.dropout_prob_3m

        # Apply interventions to a modified student profile
        modified = StudentProfile(
            student_id      = student.student_id,
            name            = student.name,
            grade           = student.grade,
            attendance_rate = min(100.0, student.attendance_rate
                                  + inputs.attendance_boost
                                  + inputs.counselling_sessions * 0.8),
            academic_score  = min(100.0, student.academic_score
                                  + inputs.academic_boost
                                  + inputs.welfare_support * 4),
            socio_score     = max(0.0, student.socio_score
                                  - inputs.welfare_support * 18),
            family_support  = min(100.0, student.family_support
                                  + inputs.counselling_sessions * 3),
            trend           = student.trend,
        )

        projected_risk  = self.score(modified)
        projected_score = projected_risk.total_score
        projected_3m    = projected_risk.dropout_prob_3m

        delta           = projected_score - baseline_score
        dominant        = max(
            projected_risk.factor_weights,
            key=projected_risk.factor_weights.get,
        )

        summary = self._sim_summary(
            student.name, baseline_score, projected_score,
            baseline_3m, projected_3m, inputs,
        )

        return SimulationResult(
            baseline_score       = round(baseline_score, 1),
            projected_score      = round(projected_score, 1),
            score_delta          = round(delta, 1),
            baseline_prob_3m     = round(baseline_3m, 3),
            projected_prob_3m    = round(projected_3m, 3),
            risk_level_baseline  = self._level(baseline_score),
            risk_level_projected = self._level(projected_score),
            factor_weights       = projected_risk.factor_weights,
            dominant_factor      = dominant,
            summary              = summary,
        )

    # ── private helpers ──────────────────────

    def _validate_weights(self) -> None:
        total = sum(self.weights.values())
        if not math.isclose(total, 1.0, abs_tol=0.01):
            raise ValueError(
                f"Weights must sum to 1.0; got {total:.3f}. "
                f"Adjust DEFAULT_WEIGHTS."
            )

    def _raw_factors(
        self,
        attendance: float,
        academic  : float,
        socio     : float,
        family    : float,
    ) -> dict[str, float]:
        """Convert raw student values into 0–100 risk contributions."""
        return {
            "attendance"         : 100.0 - attendance,
            "academic_performance": 100.0 - academic,
            "socioeconomic_status": socio,
            "family_support"     : 100.0 - family,
        }

    def _weighted_total(self, raw: dict[str, float]) -> float:
        total = sum(raw[k] * self.weights[k] for k in self.weights)
        return round(max(1.0, min(99.0, total)), 1)

    def _factor_percentages(self, raw: dict[str, float]) -> dict[str, float]:
        """
        Return each factor's share of the total weighted score (0–100).
        Used by the 'simulated risk factor weights' bar chart in the UI.
        """
        weighted = {k: raw[k] * self.weights[k] for k in self.weights}
        total    = sum(weighted.values()) or 1.0
        return {
            k: round((v / total) * 100, 1)
            for k, v in weighted.items()
        }

    def _dropout_probability(
        self,
        score : float,
        trend : Trend,
        months: int,
    ) -> float:
        """
        Logistic-based probability estimate.

        The trend modifier shifts the midpoint:
          worsening → risk grows faster over time
          improving → risk decays over time

        This is an interpretable proxy model; replace with
        a trained classifier once labelled historical data
        is available from Person 3's database.
        """
        trend_shift = {"worsening": 8, "stable": 0, "improving": -8}[trend]
        time_factor  = (months / 3) * trend_shift
        adjusted     = score + time_factor
        # logistic: P = 1 / (1 + e^(-(x-50)/12))
        prob = 1.0 / (1.0 + math.exp(-(adjusted - 50) / 12))
        return round(max(0.01, min(0.99, prob)), 3)

    @staticmethod
    def _level(score: float) -> RiskLevel:
        if score >= 65:
            return RiskLevel.HIGH
        if score >= 40:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    @staticmethod
    def _explain(
        name        : str,
        score       : float,
        level       : RiskLevel,
        factors     : dict[str, float],
        trend       : Trend,
    ) -> str:
        dominant = max(factors, key=factors.get)
        label_map = {
            "attendance"         : "poor attendance",
            "academic_performance": "low academic performance",
            "socioeconomic_status": "socioeconomic hardship",
            "family_support"     : "limited family support",
        }
        return (
            f"{name} has a risk score of {score:.0f} ({level.value} risk). "
            f"The primary driver is {label_map[dominant]} "
            f"({factors[dominant]:.0f}% of total risk weight). "
            f"Current trend: {trend.value}."
        )

    @staticmethod
    def _sim_summary(
        name          : str,
        baseline      : float,
        projected     : float,
        baseline_3m   : float,
        projected_3m  : float,
        inputs        : SimulationInput,
    ) -> str:
        delta    = baseline - projected
        pct_drop = (delta / baseline * 100) if baseline else 0
        actions  = []
        if inputs.attendance_boost    > 0: actions.append("attendance improvement")
        if inputs.academic_boost      > 0: actions.append("academic tutoring")
        if inputs.counselling_sessions > 0: actions.append("counselling")
        if inputs.welfare_support     > 0: actions.append("welfare support")

        if delta <= 0:
            return (
                f"No interventions applied. "
                f"{name}'s projected risk remains at {projected:.0f}."
            )

        action_str = ", ".join(actions) if actions else "combined interventions"
        return (
            f"With {action_str}, {name}'s risk score drops from "
            f"{baseline:.0f} → {projected:.0f} (−{pct_drop:.0f}% reduction). "
            f"3-month dropout probability: {baseline_3m*100:.0f}% → "
            f"{projected_3m*100:.0f}%."
        )


# ─────────────────────────────────────────────
#  Quick smoke-test  (python risk_engine.py)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    engine = RiskEngine()

    student = StudentProfile(
        student_id      = "STU-001",
        name            = "Muhammad Ali bin Faisal",
        grade           = "Form 4",
        attendance_rate = 62.0,
        academic_score  = 49.0,
        socio_score     = 55.0,
        family_support  = 40.0,
        trend           = Trend.WORSENING,
    )

    score = engine.score(student)
    print("=== Baseline Risk Score ===")
    print(f"Total Score     : {score.total_score}")
    print(f"Risk Level      : {score.risk_level.value}")
    print(f"Factor Weights  : {score.factor_weights}")
    print(f"Dropout Prob 3m : {score.dropout_prob_3m * 100:.1f}%")
    print(f"Dropout Prob 6m : {score.dropout_prob_6m * 100:.1f}%")
    print(f"Explanation     : {score.explanation}")

    sim_input = SimulationInput(
        attendance_boost     = 18.0,
        academic_boost       = 10.0,
        counselling_sessions = 5,
        welfare_support      = 1.0,
    )

    result = engine.simulate(student, sim_input)
    print("\n=== Simulation Result ===")
    print(f"Baseline Score   : {result.baseline_score}")
    print(f"Projected Score  : {result.projected_score}")
    print(f"Delta            : {result.score_delta}")
    print(f"Baseline 3m Prob : {result.baseline_prob_3m * 100:.1f}%")
    print(f"Projected 3m Prob: {result.projected_prob_3m * 100:.1f}%")
    print(f"Dominant Factor  : {result.dominant_factor}")
    print(f"Summary          : {result.summary}")
