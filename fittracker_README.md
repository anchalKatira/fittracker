# FitTracker  — AI-Powered Gamified Fitness Tracker

> An AI fitness platform that makes tracking workouts engaging through gamification, personalized AI coaching, and progress analytics.

🔗 **Live Demo:** [fittracker-guexskmwm5pjjyzbu69nto.streamlit.app](https://fittracker-guexskmwm5pjjyzbu69nto.streamlit.app)

---

##  Features

| Feature | Description |
|---|---|
|  **Workout Logger** | Log exercises with sets, reps, weight, and duration |
|  **Gamification** | Earn XP, level up, maintain streaks, unlock badges |
|  **AI Coach** | Personalized workout suggestions via Groq (Llama 3) |
|  **Analytics** | 5 interactive Plotly charts tracking progress over time |
|  **Persistent Storage** | JSON-based data store — no database setup needed |

---

##  How to Use the Live Demo

1. Open the **[Live Demo](https://fittracker-guexskmwm5pjjyzbu69nto.streamlit.app)**
2. Enter your name and fitness goal on the setup screen
3. Get a **free Groq API key** at [console.groq.com](https://console.groq.com) (takes 2 min, no credit card)
4. Paste your key at the top of the app
5. Start logging workouts and exploring!

> **Note:** Groq's free tier gives you access to Llama 3 at no cost.
> The app needs your key for the AI Coach tab only — logging and analytics work without it.

---

##  Architecture

```
User
  │
  ├── Log Workout Tab
  │     └── JSON Storage Engine
  │           └── XP Engine → Level + Streak + Badge checks
  │
  ├── Dashboard Tab
  │     └── Reads from JSON → renders metrics + badges
  │
  ├── AI Coach Tab
  │     └── Context Builder (reads recent workouts)
  │           └── Groq API (Llama 3.1 8B) → personalized plan
  │
  └── Analytics Tab
        └── Pandas DataFrames → Plotly charts
              ├── Weekly frequency bar chart
              ├── Volume progression line chart
              ├── Muscle group distribution donut chart
              ├── XP history area chart
              └── Exercise-specific progression chart
```

---

##  Tech Stack

| Component | Tool |
|---|---|
| UI | Streamlit |
| AI Coach | Groq API — Llama 3.1 8B (free) |
| Charts | Plotly |
| Data processing | Pandas |
| Storage | JSON file (no database) |
| Deployment | Streamlit Community Cloud |

---

##  Gamification System

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
|  First Step | Complete your first workout |
|  Week Warrior | 7-day streak |
|  Century Club | Earn 100 XP |
|  Iron Will | Complete 10 workouts |
|  Level Up | Reach Level 5 |

---

##  AI Coach — How it works

1. Reads the user's goal and last 3 workout sessions from JSON
2. Identifies rested muscle groups (not trained in recent sessions)
3. Builds a structured text context — not raw JSON, but readable summary
4. Sends a carefully engineered prompt to Groq (Llama 3.1 8B)
5. Parses the response into sections: warm-up, main workout, cool-down, coach note

Temperature is set to `0.7` so suggestions vary slightly each session — avoids the same plan every time.

---

##  Run Locally

```bash
git clone https://github.com/anchalKatira/fittracker
cd fittracker
pip install -r requirements.txt
streamlit run app.py
```

For the AI Coach tab, add your Groq key:
```bash
export GROQ_API_KEY="gsk_your_key_here"   # Mac/Linux
set GROQ_API_KEY=gsk_your_key_here        # Windows
```

---

##  Key Design Decisions

**Why JSON and not a database?**
Single-user personal app with no concurrent writes. JSON needs no setup and works on serverless platforms. For multi-user production, I'd use SQLite or PostgreSQL.

**Why Groq and not OpenAI?**
Groq's free tier gives access to Llama 3.1 with no billing setup. Fast inference via custom LPU hardware. Quality is comparable to GPT-3.5 for fitness coaching tasks.

**Why Plotly and not Matplotlib?**
Streamlit renders Plotly as interactive widgets — users can hover, zoom, and filter. For a fitness tracker where users want to inspect specific session values, interactivity is significantly better UX than static images.

**Why temperature 0.7 for suggestions?**
Workout suggestions benefit from variety — the same user asking twice should get a slightly different session. Unlike a document QA system where factual consistency matters, here controlled randomness improves the experience.
