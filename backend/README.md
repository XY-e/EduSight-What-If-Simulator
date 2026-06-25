# EduSight Backend

FastAPI backend for the EduSight dropout risk prediction platform.

## Setup

```bash
# 1. Clone and navigate to the backend folder
cd backend

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment variables
cp .env.example .env
# Edit .env with your MongoDB URI and CSV path

# 5. Place the Kaggle CSV in this folder
# Download from: https://www.kaggle.com/datasets/whenamancodes/student-performance
# Rename to Maths.csv (or update CSV_PATH in .env)

# 6. Place ML engine files alongside main.py
#    ml_engine.py
#    risk_engine.py
#    recommendation_engine.py
#    edusight_ml_model.joblib  (train first if not generated)

# 7. Run the server
uvicorn main:app --reload --port 8000
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/students` | List all students with risk scores |
| GET | `/students/{id}` | Single student profile + risk score |
| POST | `/simulate` | What-If simulation + recommendations |

## Interactive docs

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc:       http://localhost:8000/redoc

## File structure

```
backend/
├── main.py                   # FastAPI app + all endpoints
├── database.py               # MongoDB connection + CSV seeding
├── mapper.py                 # Kaggle columns → StudentProfile
├── models.py                 # Pydantic request/response schemas
├── requirements.txt
├── .env.example
│
│   # ML files — place these here:
├── ml_engine.py
├── risk_engine.py
├── recommendation_engine.py
└── edusight_ml_model.joblib
```

## Dataset column mapping

| Kaggle column | Maps to | How |
|---------------|---------|-----|
| `absences` | `attendance_rate` | `100 - (absences/30)*90`, clamped to [10,100] |
| `G2` | `academic_score` (0–100) | `(G2/20)*100` |
| `Medu`, `Fedu` | `socio_score` | `(1 - avg_edu/4)*100` |
| `famrel` | `family_support` | `((famrel-1)/4)*100` |
| `G1`, `G2`, `failures` | `trend` | momentum + failure count |
| `counselling` | `counselling` | defaults to 0, set via simulation |
| `welfare` | `welfare` | defaults to 0.0, set via simulation |
