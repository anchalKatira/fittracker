"""
db.py — MySQL storage layer for FitTracker
===========================================
Drop-in replacement for the old JSON load_data()/save_data() pair.

Design goal: keep the exact same in-memory dict shape the rest of
app.py already expects (user / workouts / badges / latest_suggestion).
That means calculate_xp, log_workout, check_badges, build_context,
and every chart function in app.py needs ZERO changes — only the
storage layer underneath them changed.

Multi-user model: real accounts — username + bcrypt-hashed password
(see signup_user()/login_user() below). Whichever user_id that
resolves to gets stored in st.session_state.user_id, and
load_data()/save_data() read it from there — so callers don't need
to pass a user_id around at all; the "current user" is just whoever's
session it is.

Config source: checks st.secrets first (how Streamlit Community Cloud
supplies credentials via its Secrets manager), falling back to
os.environ (how you supply them locally / via `export`). Same code
works in both places.
"""

import os
import ssl as ssl_module
import pymysql
import pymysql.cursors
import bcrypt
import streamlit as st


def _cfg(key: str, default: str = "") -> str:
    """st.secrets first (Streamlit Cloud), then os.environ (local)."""
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass  # no secrets.toml at all — fine for local dev with env vars
    return os.environ.get(key, default)


def _build_db_config() -> dict:
    cfg = dict(
        host=_cfg("MYSQL_HOST", "localhost"),
        port=int(_cfg("MYSQL_PORT", "3306")),
        user=_cfg("MYSQL_USER", "root"),
        password=_cfg("MYSQL_PASSWORD", ""),
        database=_cfg("MYSQL_DATABASE", "fittracker"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    # Hosted MySQL (e.g. TiDB Cloud Starter) requires TLS. Local MySQL
    # doesn't, so this only kicks in when MYSQL_SSL=true is set.
    if _cfg("MYSQL_SSL", "false").lower() == "true":
        ctx = ssl_module.create_default_context()
        cfg["ssl"] = ctx
    return cfg


DB_CONFIG = _build_db_config()

# Badge metadata (name/description/icon) stays in code, same as before —
# only the "unlocked" state lives in the DB.
BADGE_DEFS = {
    "first_workout": {"name": "First Step",  "description": "Complete your first workout", "icon": "🏆"},
    "week_warrior":  {"name": "Week Warrior", "description": "Work out 7 days in a row",     "icon": "🔥"},
    "century_club":  {"name": "Century Club", "description": "Earn 100 total XP",            "icon": "⭐"},
    "iron_will":     {"name": "Iron Will",    "description": "Complete 10 workouts",          "icon": "🏋️"},
    "level_up":      {"name": "Level Up",     "description": "Reach Level 5",                 "icon": "⚡"},
}


@st.cache_resource
def get_connection():
    """
    One connection cached per Streamlit session (via cache_resource),
    instead of opening a new MySQL connection on every rerun/tab switch.
    """
    return pymysql.connect(**DB_CONFIG)


def init_schema():
    """Create tables if they don't exist yet. No default user is seeded —
    accounts are created via signup_user() below."""
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT PRIMARY KEY AUTO_INCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL DEFAULT '',
                goal VARCHAR(50) NOT NULL DEFAULT '',
                created_at DATE,
                total_xp INT DEFAULT 0,
                level INT DEFAULT 1,
                current_streak INT DEFAULT 0,
                longest_streak INT DEFAULT 0,
                total_workouts INT DEFAULT 0,
                last_workout_date DATE
            )
        """)
        # Migration guard: if an earlier version of this app already created
        # the users table without password_hash, add it now. Safe to run
        # every startup — the duplicate-column error is just swallowed.
        try:
            cur.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NOT NULL DEFAULT ''")
        except pymysql.err.Error as e:
            if e.args and e.args[0] == 1060:  # ER_DUP_FIELDNAME
                pass
            else:
                raise
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workouts (
                id VARCHAR(50) PRIMARY KEY,
                user_id INT NOT NULL,
                date DATE NOT NULL,
                timestamp DATETIME NOT NULL,
                duration_minutes INT,
                notes TEXT,
                xp_earned INT,
                total_volume_kg FLOAT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workout_exercises (
                id INT PRIMARY KEY AUTO_INCREMENT,
                workout_id VARCHAR(50) NOT NULL,
                name VARCHAR(100),
                muscle_group VARCHAR(50),
                sets INT,
                reps INT,
                weight_kg FLOAT,
                duration_minutes INT,
                FOREIGN KEY (workout_id) REFERENCES workouts(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS badges (
                user_id INT NOT NULL,
                badge_key VARCHAR(50) NOT NULL,
                unlocked BOOLEAN DEFAULT FALSE,
                unlocked_at DATETIME,
                PRIMARY KEY (user_id, badge_key),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS latest_suggestion (
                user_id INT PRIMARY KEY,
                text TEXT,
                generated_at DATETIME,
                duration INT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def signup_user(username: str, password: str) -> int:
    """
    Create a new account with a bcrypt-hashed password. Raises ValueError
    (safe to show directly to the user) if the username is taken.
    """
    init_schema()
    conn = get_connection()
    username = username.strip()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE LOWER(name) = LOWER(%s)", (username,))
        if cur.fetchone():
            raise ValueError("That username is already taken — try logging in instead.")

        pw_hash = hash_password(password)
        cur.execute("INSERT INTO users (name, password_hash) VALUES (%s, %s)", (username, pw_hash))
        user_id = cur.lastrowid
        for bkey in BADGE_DEFS:
            cur.execute(
                "INSERT INTO badges (user_id, badge_key, unlocked) VALUES (%s, %s, FALSE)",
                (user_id, bkey),
            )
        return user_id


def login_user(username: str, password: str) -> int:
    """
    Verify credentials and return the user_id on success. Raises
    ValueError on any failure — deliberately the SAME message whether the
    username doesn't exist or the password is wrong, so a login attempt
    can't be used to enumerate which usernames exist.
    """
    init_schema()
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, password_hash FROM users WHERE LOWER(name) = LOWER(%s)", (username.strip(),))
        row = cur.fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            raise ValueError("Incorrect username or password.")
        return row["id"]


def load_data() -> dict:
    """Rebuild the same nested dict shape the old JSON version returned,
    for whichever user is currently active in this session."""
    init_schema()
    user_id = st.session_state.user_id
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        u = cur.fetchone()

        cur.execute("SELECT * FROM workouts WHERE user_id = %s ORDER BY timestamp", (user_id,))
        workout_rows = cur.fetchall()

        workouts = []
        for w in workout_rows:
            cur.execute("SELECT * FROM workout_exercises WHERE workout_id = %s", (w["id"],))
            ex_rows = cur.fetchall()
            workouts.append({
                "id": w["id"],
                "date": w["date"].isoformat(),
                "timestamp": w["timestamp"].isoformat(),
                "duration_minutes": w["duration_minutes"],
                "notes": w["notes"] or "",
                "exercises": [
                    {
                        "name": e["name"],
                        "muscle_group": e["muscle_group"],
                        "sets": e["sets"],
                        "reps": e["reps"],
                        "weight_kg": e["weight_kg"],
                        "duration_minutes": e["duration_minutes"] or 0,
                    }
                    for e in ex_rows
                ],
                "xp_earned": w["xp_earned"],
                "total_volume_kg": w["total_volume_kg"],
            })

        cur.execute("SELECT * FROM badges WHERE user_id = %s", (user_id,))
        badge_rows = {b["badge_key"]: b for b in cur.fetchall()}
        badges = {}
        for bkey, meta in BADGE_DEFS.items():
            row = badge_rows.get(bkey, {})
            badges[bkey] = {
                **meta,
                "unlocked": bool(row.get("unlocked", False)),
                "unlocked_at": row["unlocked_at"].isoformat() if row.get("unlocked_at") else None,
            }

        cur.execute("SELECT * FROM latest_suggestion WHERE user_id = %s", (user_id,))
        sug = cur.fetchone()
        latest_suggestion = None
        if sug:
            latest_suggestion = {
                "text": sug["text"],
                "generated_at": sug["generated_at"].isoformat(),
                "duration": sug["duration"],
            }

    return {
        "user": {
            "name": u["name"],
            "goal": u["goal"],
            "created_at": u["created_at"].isoformat() if u["created_at"] else "",
            "total_xp": u["total_xp"],
            "level": u["level"],
            "current_streak": u["current_streak"],
            "longest_streak": u["longest_streak"],
            "total_workouts": u["total_workouts"],
            "last_workout_date": u["last_workout_date"].isoformat() if u["last_workout_date"] else None,
        },
        "workouts": workouts,
        "badges": badges,
        "latest_suggestion": latest_suggestion,
    }


def save_data(data: dict) -> None:
    """
    Persist the full in-memory dict back to MySQL, for the current
    session's user. Workouts are treated as append-only (never edited),
    so we only insert ones not already in the DB — everything else is
    an update.
    """
    conn = get_connection()
    user_id = st.session_state.user_id
    u = data["user"]
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE users SET name=%s, goal=%s, created_at=%s, total_xp=%s, level=%s,
                current_streak=%s, longest_streak=%s, total_workouts=%s, last_workout_date=%s
            WHERE id=%s
        """, (
            u["name"], u["goal"], u["created_at"] or None, u["total_xp"], u["level"],
            u["current_streak"], u["longest_streak"], u["total_workouts"],
            u["last_workout_date"], user_id,
        ))

        cur.execute("SELECT id FROM workouts WHERE user_id = %s", (user_id,))
        existing_ids = {r["id"] for r in cur.fetchall()}

        for w in data["workouts"]:
            if w["id"] in existing_ids:
                continue
            cur.execute("""
                INSERT INTO workouts (id, user_id, date, timestamp, duration_minutes,
                    notes, xp_earned, total_volume_kg)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                w["id"], user_id, w["date"], w["timestamp"], w["duration_minutes"],
                w["notes"], w["xp_earned"], w["total_volume_kg"],
            ))
            for ex in w["exercises"]:
                cur.execute("""
                    INSERT INTO workout_exercises (workout_id, name, muscle_group,
                        sets, reps, weight_kg, duration_minutes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                """, (
                    w["id"], ex["name"], ex["muscle_group"], ex["sets"], ex["reps"],
                    ex["weight_kg"], ex.get("duration_minutes", 0),
                ))

        for bkey, b in data["badges"].items():
            cur.execute("""
                UPDATE badges SET unlocked=%s, unlocked_at=%s
                WHERE user_id=%s AND badge_key=%s
            """, (b["unlocked"], b["unlocked_at"], user_id, bkey))

        ls = data.get("latest_suggestion")
        if ls:
            cur.execute("""
                INSERT INTO latest_suggestion (user_id, text, generated_at, duration)
                VALUES (%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE text=%s, generated_at=%s, duration=%s
            """, (
                user_id, ls["text"], ls["generated_at"], ls["duration"],
                ls["text"], ls["generated_at"], ls["duration"],
            ))
