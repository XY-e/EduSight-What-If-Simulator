from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()

import os
import uuid
import pandas as pd
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

# --------------------- Config --------------------------------------------------------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "edusight")
CSV_PATH = os.getenv("CSV_PATH", "Maths.csv")

# -------------- Module-level client (initialised once) -------------------------------
_client: AsyncIOMotorClient | None = None

def get_collection(name: str = "students") -> AsyncIOMotorCollection:
    # Return a Motor collection handle. Call after init_db().
    if _client is None:
        raise RuntimeError("Database is not initialized. Call _init_db() first.")
    return _client[DB_NAME][name]

# -------------- Startup Initialization -----------------------------------------------
async def init_db() -> None:
    # Connect to MongoDB and seed the students collection from the CSV if empty.
    # Safe to call on every startup - seeds only once.
    global _client
    _client = AsyncIOMotorClient(MONGO_URI)

    collection = get_collection("students")
    count = await collection.count_documents({})

    if count == 0:
        print(f"[DB] Students collection empty - seeding from {CSV_PATH}...")
        await _seed_from_csv(collection)
    else:
        print(f"[DB] Students collection has {count} records - skipping seeding.")

async def _seed_from_csv(collection: AsyncIOMotorCollection) -> None:
    # Reads the Kaggle CSV and inserts all rows as student documents.
    # Each document gets a student_ID (STU-0001, STU-0002, and so on...)
    # Malaysian names and grades are generated for prototype.
    try:
        df = _load_csv(CSV_PATH)
    except FileNotFoundError:
        print(f"[DB] CSV file not found at '{CSV_PATH}'."
              f"Students collection will remain empty.\n"
              f"Place the Kaggle CSV file at '{CSV_PATH}' and restart.")
        return

    records = []
    for index, row in df.iterrows():
        doc = row.to_dict()

        # Assigning student ID
        doc["student_id"] = f"STU-{str(index + 1).zfill(4)}"

        # Generate a realistic Malaysian name for prototype purposes
        doc["name"] = _generate_name(index)
        doc["grade"] = _assign_grade(index)

        # Counselling and welfare defaults to 0 - adjusted via simulation
        doc["counselling"] = 0
        doc["welfare"] = 0.0

        records.append(doc)

    await collection.insert_many(records)
    print(f"[DB] Seeded {len(records)} student records.")

def _load_csv(path: str) -> pd.DataFrame:
    # Try multiple separators and encodings
    encodings = ["utf-8", "iso-8859-1", "latin-1", "cp1252"]
    for sep in (";", ","):
        for enc in encodings:
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc)
                if len(df.columns) > 3:
                    print(f"[DB] Loaded CSV with sep='{sep}' encoding='{enc}'")
                    return df
            except Exception:
                pass
    return pd.read_excel(path)

# -------------- Prototype name & grade generators -----------------------------------------------
_malay_names = [
    "Ahmad Farid bin Ali", "Siti Aishah binti Razak", "Muhammad Hasziq bin Zukri",
    "Nurul Huda binti Hassan", "Fatimah Roslan binti Yusof", "Wan Syafiq bin Wan Ismail",
    "Muhammad Kamil bin Kamal", "Nurul Izzati binti Hamid", "Farhan bin Othman",
    "Razali bin Mansor", "Nabila binti Mustafa", "Umairah binti Zakaria"
]

_chinese_names = [
    "Tan Wei Xin", "Wong Jia Hui", "Ng Kai Yap", "Tan Mei Ling"
    "Lee Chun Hong", "Chong Yi Ting", "Ong Chuang Hong", "Ling Xing Yi"
]

_indian_names = [
    "Kevin Kumar", "Siva Raja", "Arjun Krishnan", "Priya Nair",
    "Saresh Pillai", "Anita Raj", "Ram Chandra", "Kavitha Menon"
]

_all_names = _malay_names + _chinese_names  + _indian_names

_grades = ["Form 1", "Form 2", "Form 3", "Form 4", "Form 5"]

def _generate_name(index: int) -> str:
    return _all_names[index % len(_all_names)]

def _assign_grade(index: int) -> str:
    return _grades[index % len(_grades)]

# --------------------- Shutdown --------------------------------------------------------
async def close_db() -> None:
    global _client
    if _client:
        _client.close()
        _client = None
        print("[DB] Connection closed.")