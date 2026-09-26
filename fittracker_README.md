# FitTracker 💪 — AI-Powered Gamified Fitness Tracker

> A multi-user AI fitness platform that makes tracking workouts engaging through gamification, personalized AI coaching, and progress analytics — backed by a real relational database with account-based authentication.

🔗 **Live Demo:** [fittracker-guexskmwm5pjjyzbu69nto.streamlit.app](https://fittracker-guexskmwm5pjjyzbu69nto.streamlit.app)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔐 **Accounts** | Username + bcrypt-hashed password login/signup — real multi-user isolation, not just a shared demo profile |
| 🏋️ **Workout Logger** | Log exercises with sets, reps, weight, and duration |
| 🏆 **Gamification** | Earn XP, level up, maintain streaks, unlock badges |
| 🤖 **AI Coach** | Personalized workout suggestions via Groq (`openai/gpt-oss-20b`), with automatic retry + a graceful static fallback if the API is unreachable |
| 📊 **Analytics** | 5 interactive Plotly charts tracking progress over time |
| 💾 **Persistent Storage** | MySQL-backed (TiDB Cloud Starter in the hosted demo) — relational schema, per-user data isolation |

---

## 🎯 How to Use the Live Demo

1. Open the **[Live Demo](https://fittracker-guexskmwm5pjjyzbu69nto.streamlit.app)**
2. Sign up with any username + password (no email needed)
3. Pick your fitness goal on the first-time setup screen
4. If the AI Coach tab asks for a key, get a **free Groq API key** at [console.groq.com](https://console.groq.com) (takes 2 min, no credit card)
5. Start logging workouts and exploring!

> **Note:** The Groq key is only needed for the AI Coach tab — logging, badges, and analytics all work without it.

---

## 🏗️ Architecture

```
User
  │
  ├── Auth (Log In / Sign Up)
  │     └── bcrypt password hashing → users table (MySQL)
  │
  ├── Log Workout Tab
  │     └── MySQL storage layer (db.py)
  │           └── XP Engine → Level + Streak + Badge checks
  │
  ├── Dashboard Tab
  │     └── Reads from MySQL (scoped to session's user_id) → renders metrics + badges
  │
  ├── AI Coach Tab
  │     └── Context Builder (reads recent workouts)
  │           └── Groq API (openai/gpt-oss-20b) → personalized plan
  │                 └── retry w/ backoff → static fallback plan if still unreachable
  │
  └── Analytics Tab
        └── Pandas DataFrames → Plotly charts
              ├── Weekly frequency bar chart
              ├── Volume progression line chart
              ├── Muscle group distribution donut chart
              ├── XP history area chart
              └── Exercise-specific progression chart
```

**Storage layer (`db.py`)** rebuilds the exact same in-memory dict shape the original JSON version used, so the entire gamification engine, AI Coach, and chart code above it needed **zero changes** when the storage backend was swapped — only what sits underneath `load_data()`/`save_data()` changed.

---

## 🛠️ Tech Stack

| Component | Tool |
|---|---|
| UI | Streamlit |
| Auth | bcrypt-hashed passwords, session-based identity via `st.session_state` |
| Database | MySQL (TiDB Cloud Starter — free, MySQL-wire-compatible — in the hosted demo; any real MySQL works locally) |
| AI Coach | Groq API — `openai/gpt-oss-20b` |
| Charts | Plotly |
| Data processing | Pandas |
| Deployment | Streamlit Community Cloud + TiDB Cloud Starter |

---

## 🎮 Gamification System

**XP Formula per workout:**
```
XP = 10 (base)
   + 1 per 5 minutes of session
   + 1 per 500kg total volume lifted
   + 5 bonus if streak ≥ 3 days
```

**Level Formula:**
```
Level = floor(total_xp / 50) + 1
```

**Streak Logic:**
- Worked out yesterday → streak +1
- Worked out today already → streak unchanged
- Missed a day → streak resets to 1

**Badges (5 total):**
| Badge | Condition |
|---|---|
| 🏆 First Step | Complete your first workout |
| 🔥 Week Warrior | 7-day streak |
| ⭐ Century Club | Earn 100 XP |
| 🏋️ Iron Will | Complete 10 workouts |
| ⚡ Level Up | Reach Level 5 |

---

## 🤖 AI Coach — How it works

1. Reads the user's goal and last 3 workout sessions from MySQL
2. Identifies rested muscle groups (not trained in recent sessions)
3. Builds a structured text context — not raw data, but a readable summary — before sending it to the LLM
4. Sends a carefully engineered prompt to Groq (`openai/gpt-oss-20b`)
5. Parses the response into sections: warm-up, main workout, cool-down, coach note

Temperature is set to `0.7` so suggestions vary slightly each session — avoids the same plan every time.

**Reliability:** every Groq call is wrapped in a retry-with-backoff helper (`call_with_retry`). If the API is still unreachable after retries, the tab falls back to a static, safe default plan instead of erroring out — so a flaky network never breaks the AI Coach tab, it just degrades gracefully.

---

## 🔐 Accounts & Multi-User Support

- Sign up with a username + password — password is hashed with **bcrypt** before it's ever written to the database, never stored in plaintext
- Login errors are deliberately worded identically for "wrong username" and "wrong password," so a login attempt can't be used to check which usernames exist
- Each browser session's active user lives in `st.session_state.user_id`; every database read/write is scoped to that user, so accounts are fully isolated from one another
- This is **identity, not full production security** — there's no rate limiting on login attempts, no email verification, and no password reset flow. Fine for a portfolio demo; a production version would add those plus a real connection pool (see below).

---

## 💻 Run Locally

```bash
git clone https://github.com/anchalKatira/fittracker
cd fittracker
pip install -r requirements.txt
```

Set up a local MySQL database, then export your connection details:
```bash
export MYSQL_HOST=localhost
export MYSQL_USER=root
export MYSQL_PASSWORD=your_password
export MYSQL_DATABASE=fittracker
streamlit run fittracker_app.py
```

For the AI Coach tab, also set your Groq key:
```bash
export GROQ_API_KEY="gsk_your_key_here"
```

Tables are created automatically on first run — no manual schema setup needed.

---

## ☁️ Deployment

Deployed on **Streamlit Community Cloud**, backed by **TiDB Cloud Starter** (a free, MySQL-wire-compatible database — genuinely free unlike some alternatives, e.g. PlanetScale, which dropped its free tier).

Credentials are supplied via Streamlit's **Secrets** manager (`st.secrets`), with a fallback to environment variables for local development — same `db.py` code works in both places. TiDB Cloud requires a TLS connection, toggled with a single `MYSQL_SSL = "true"` secret.

---

## 🔑 Key Design Decisions

**Why MySQL and not JSON?**
The original version used a single JSON file — fine for one person, but it can't support multiple users, has no real querying, and risks corruption on concurrent writes. MySQL gives proper relational structure (`users`, `workouts`, `workout_exercises`, `badges`, `latest_suggestion`, linked by `user_id`), real per-user isolation, and safe concurrent access.

**Why open a fresh connection per call instead of one shared connection?**
An earlier version cached a single MySQL connection for the whole app's lifetime for performance. But `pymysql` connections aren't thread-safe — sharing one across concurrent Streamlit sessions let queries interleave on the same socket, corrupting reads. Opening a short-lived connection per call costs a little latency but eliminates that entire class of bug — the right tradeoff at this app's scale. (The textbook next step for a busier app: a real connection pool.)

**Why bcrypt for passwords?**
Bcrypt is a slow, salted hashing algorithm purpose-built for passwords — resistant to brute-force and rainbow-table attacks in a way a plain hash (e.g. SHA-256 alone) isn't.

**Why Groq and not OpenAI?**
Groq's free tier gives access to strong open models with no billing setup, and fast inference via custom LPU hardware.

**Why Plotly and not Matplotlib?**
Streamlit renders Plotly as interactive widgets — users can hover, zoom, and filter. For a fitness tracker where users want to inspect specific session values, interactivity is significantly better UX than static images.

**Why temperature 0.7 for AI Coach suggestions?**
Workout suggestions benefit from variety — the same user asking twice should get a slightly different session. Controlled randomness improves the experience here, unlike a factual QA system where you'd want low temperature for consistency instead.
