"""
mapper.py
─────────
Maps a raw Kaggle student-performance dataset row (dict or pd.Series)
to the StudentProfile and API response shapes expected by the frontend.

Kaggle dataset columns used:
  absences  → attendance_rate   (more absences = lower attendance)
  G2        → academic_score    (penultimate grade, best available predictor)
  Medu/Fedu → socio_score       (parental education as socioeconomic proxy)
  famrel    → family_support    (family relationship quality, 1–5)
  failures  → used in trend
  G1, G2    → trend             (grade momentum)
"""

from __future__ import annotations
import math
from typing import Any

from risk_engine import StudentProfile, Trend


# ----- Attendance Mapping --------------------------------------------------------
# Dataset absences range: 0–93.  We cap at 30 for a sensible scale.
# attendance_rate = 100 - (absences / 30) * 100, clamped to [10, 100]

max_absences = 30.0

def absences_to_attendance(absences: float) -> float:
    ratio = min(absences, max_absences) / max_absences
    return round(max(10.0, 100.0 - ratio * 90.0), 1)

# ----- Academic score mapping ----------------------------------------------------
# G2 is out of 20. Convert to 0-100.
def g2_to_academic(g2: float) -> float:
    return round(min(100.0, max(0.0, (g2 / 20.0) * 100.0)), 1)

# ----- Socioeconomic score Mapping -----------------------------------------------
# Medu/Fedu: 0 (none) - 4 (higher education).
# Higher parental education -> lower socioeconomic risk.
# socio_score = (1 - avg_edu/4) * 100, mapped to [0, 100].
def edu_to_socio(medu: float, fedu: float) -> float:
    avg = (medu + fedu) / 2.0
    return round(max(0.0, min(100.0, (1.0 - avg / 4.0) * 100.0)), 1)

# ----- Family support Mapping ----------------------------------------------------
# famrel: 1 (very bad) - 5 (excellent). Convert to 0-100.
def famrel_to_support(famrel: float) -> float:
    return round(((famrel - 1) / 4.0) * 100.0, 1)

# ----- Trend Mapping -------------------------------------------------------------
# Compare G1 -> G2 momentum and failure count
def derive_trend(g1: float, g2: float, failures: int) -> Trend:
    momentum = g2 - g1
    if failures >= 2 or momentum <= -2:
        return Trend.WORSENING
    if momentum >= 2:
        return Trend.IMPROVING
    return Trend.STABLE

# ----- Counselling / welfare -----------------------------------------------------
default_counselling = 0
default_welfare = 0.0

# ----- Main mapper ---------------------------------------------------------------
def row_to_student_profile(row: dict[str, Any], student_id: str) -> StudentProfile:
    # Convert one dataset row to a StudentProfile
    absences = float(row.get('absences', 0))
    g1 = float(row.get('G1', 10))
    g2 = float(row.get('G2', 10))
    medu = float(row.get('Medu', 2))
    fedu = float(row.get('Fedu', 2))
    famrel = float(row.get('famrel', 3))
    failures = int(row.get('failures', 0))

    # Build the raw feature dict for optional ML blend
    ml_data = {k: row[k] for k in row if k not in ("_id", "student_id")}

    return StudentProfile(
        student_id = student_id,
        name = row.get("name", f"Student {student_id}"),
        grade = row.get("grade", "Form 4"),
        attendance_rate = absences_to_attendance(absences),
        academic_score = g2_to_academic(g2),
        socio_score = edu_to_socio(medu, fedu),
        family_support = famrel_to_support(famrel),
        trend = derive_trend(g1, g2, failures),
        ml_data = ml_data,
    )

def profile_to_api_response(
    profile: StudentProfile,
    risk_score,
    row: dict,
) -> dict:
    # Shape a StudentProfile + RiskScore into GET /students/:id response the frontend expects.
    return {
        "id" : profile.student_id,
        "name" : profile.name,
        "form": profile.grade,
        "school": row.get("school", "GP"),
        "attendance": profile.attendance_rate,
        "grades": profile.academic_score,
        "counselling": int(row.get("counselling", default_counselling)),
        "welfare": float(row.get("welfare", default_welfare)),
        "currentScore": risk_score.total_score,
        "currentRisk": risk_score.risk_level.value,
    }