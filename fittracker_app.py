"""
FitTracker — Day 4: Complete Streamlit App
==========================================
Tabs:
  1. 🏋️ Log Workout
  2. 🏆 Dashboard (XP, streak, badges)
  3. 🤖 AI Coach (Groq suggestions)
  4. 📊 Analytics (Plotly charts)

Run locally:
  streamlit run app.py

Deploy on HuggingFace Spaces:
  - Upload app.py + requirements.txt
  - Add GROQ_API_KEY as a Secret
"""

import os
import json
import math
import copy
import tempfile
import streamlit as st
from datetime import datetime, date, timedelta
from typing import Optional

# ── Third-party ───────────────────────────────────────────────
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from groq import Groq

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FitTracker",
    page_icon="💪",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=DM+Mono&display=swap');

:root {
  --bg:#0f0f11; --surface:#18181c; --border:#2a2a32;
  --accent:#6c63ff; --accent2:#a78bfa;
  --text:#e8e8f0; --muted:#72728a;
  --green:#34d399; --yellow:#fbbf24; --red:#f87171; --blue:#60a5fa;
}

html,body,[class*="css"]{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text)}
#MainMenu,footer,header{visibility:hidden}
.main .block-container{padding-top:1.25rem;padding-bottom:2rem;max-width:1000px}

/* Metric cards */
.metric-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:1.25rem}
.metric-card{background:var(--surface);border:0.5px solid var(--border);border-radius:12px;padding:.85rem 1rem;text-align:center}
.metric-val{font-size:1.6rem;font-weight:600;color:var(--text);line-height:1.1}
.metric-label{font-size:.72rem;color:var(--muted);margin-top:3px;text-transform:uppercase;letter-spacing:.06em}

/* XP bar */
.xp-bar-wrap{background:var(--surface);border:0.5px solid var(--border);border-radius:12px;padding:1rem 1.25rem;margin-bottom:12px}
.xp-bar-track{height:10px;background:var(--border);border-radius:5px;overflow:hidden;margin:8px 0 4px}
.xp-bar-fill{height:100%;border-radius:5px;background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width .4s}
.xp-label{display:flex;justify-content:space-between;font-size:.78rem;color:var(--muted)}

/* Badge grid */
.badge-grid{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:1rem}
.badge-card{background:var(--surface);border:0.5px solid var(--border);border-radius:10px;padding:.65rem .9rem;display:flex;align-items:center;gap:8px;font-size:13px}
.badge-card.unlocked{border-color:var(--yellow)}
.badge-icon{font-size:1.25rem}
.badge-name{font-weight:500;color:var(--text)}
.badge-desc{font-size:.72rem;color:var(--muted)}

/* Section headers */
.section-title{font-size:1rem;font-weight:500;color:var(--text);margin:1rem 0 .6rem;border-bottom:.5px solid var(--border);padding-bottom:.4rem}
.divider{height:1px;background:var(--border);margin:.9rem 0}

/* Coach box */
.coach-box{background:var(--surface);border:0.5px solid var(--accent);border-radius:12px;padding:1rem 1.25rem;margin:10px 0;font-size:.9rem;line-height:1.75;white-space:pre-wrap}
.coach-label{font-size:.72rem;font-weight:600;color:var(--accent2);text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px}

/* Buttons */
.stButton>button{background:var(--surface);border:.5px solid var(--border);color:var(--text);border-radius:8px;font-family:'DM Sans',sans-serif;transition:all .15s}
.stButton>button:hover{border-color:var(--accent);color:var(--accent2)}

/* Streak flame */
.streak-display{font-size:2.5rem;text-align:center;margin:.3rem 0}
.streak-num{font-size:2rem;font-weight:600;color:var(--yellow)}
.streak-label{font-size:.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em}

/* Success toast */
.toast{background:#052e16;border:.5px solid #065f46;border-radius:10px;padding:.75rem 1rem;color:var(--green);font-size:.9rem;margin:8px 0}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
DATA_FILE        = "fittracker_data.json"
MODEL            = "openai/gpt-oss-120b"
XP_PER_LEVEL     = 50
XP_PER_WORKOUT   = 10
XP_PER_5_MINS    = 1
XP_PER_500KG     = 1
XP_STREAK_BONUS  = 5

VALID_GOALS = {
    "muscle_gain":     "Muscle Gain",
    "weight_loss":     "Weight Loss",
    "endurance":       "Endurance",
    "general_fitness": "General Fitness",
}

MUSCLE_GROUPS = ["chest","back","legs","shoulders","arms","core","cardio"]

COLORS = {
    "primary":"#6c63ff","success":"#34d399","warning":"#fbbf24",
    "danger":"#f87171","muted":"#72728a","bg":"#0f0f11",
    "surface":"#18181c","border":"#2a2a32","text":"#e8e8f0",
}

MUSCLE_COLORS = {
    "chest":"#6c63ff","back":"#34d399","legs":"#fbbf24",
    "shoulders":"#f87171","arms":"#60a5fa","core":"#a78bfa","cardio":"#fb923c",
}

EMPTY_DB = {
    "user":{
        "name":"","goal":"","created_at":"",
        "total_xp":0,"level":1,
        "current_streak":0,"longest_streak":0,
        "total_workouts":0,"last_workout_date":None,
    },
    "workouts":[],
    "badges":{
        "first_workout": {"name":"First Step",   "description":"Complete your first workout","icon":"🏆","unlocked":False,"unlocked_at":None},
        "week_warrior":  {"name":"Week Warrior",  "description":"Work out 7 days in a row",  "icon":"🔥","unlocked":False,"unlocked_at":None},
        "century_club":  {"name":"Century Club",  "description":"Earn 100 total XP",         "icon":"⭐","unlocked":False,"unlocked_at":None},
        "iron_will":     {"name":"Iron Will",     "description":"Complete 10 workouts",       "icon":"🏋️","unlocked":False,"unlocked_at":None},
        "level_up":      {"name":"Level Up",      "description":"Reach Level 5",             "icon":"⚡","unlocked":False,"unlocked_at":None},
    },
    "latest_suggestion": None,
}


# ─────────────────────────────────────────────────────────────
# STORAGE
# ─────────────────────────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    data = copy.deepcopy(EMPTY_DB)
    save_data(data)
    return data


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ─────────────────────────────────────────────────────────────
# GAMIFICATION ENGINE
# ─────────────────────────────────────────────────────────────
def calculate_volume(exercises: list) -> float:
    return round(sum(ex["weight_kg"] * ex["sets"] * ex["reps"] for ex in exercises), 2)


def calculate_xp(duration: int, exercises: list, streak: int) -> dict:
    base    = XP_PER_WORKOUT
    dur_xp  = (duration // 5) * XP_PER_5_MINS
    vol_xp  = int(calculate_volume(exercises) // 500) * XP_PER_500KG
    str_xp  = XP_STREAK_BONUS if streak >= 3 else 0
    return {"base":base,"duration":dur_xp,"volume":vol_xp,"streak":str_xp,
            "total":base+dur_xp+vol_xp+str_xp}


def calculate_level(xp: int) -> int:
    return math.floor(xp / XP_PER_LEVEL) + 1


def xp_to_next(xp: int) -> int:
    return calculate_level(xp) * XP_PER_LEVEL - xp


def update_streak(last_date_str: Optional[str], current: int) -> dict:
    today = date.today()
    if last_date_str is None:
        return {"new":1,"msg":"First workout! Streak started 🔥","extended":True}
    gap = (today - date.fromisoformat(last_date_str)).days
    if gap == 0:
        return {"new":current,"msg":"Already logged today.","extended":False}
    elif gap == 1:
        return {"new":current+1,"msg":f"Streak extended to {current+1} days! 🔥","extended":True}
    else:
        return {"new":1,"msg":f"Streak reset — missed {gap-1} day(s). Starting fresh!","extended":False}


def check_badges(user: dict, data: dict) -> list:
    conditions = {
        "first_workout": lambda u: u["total_workouts"] >= 1,
        "week_warrior":  lambda u: u["current_streak"] >= 7,
        "century_club":  lambda u: u["total_xp"] >= 100,
        "iron_will":     lambda u: u["total_workouts"] >= 10,
        "level_up":      lambda u: u["level"] >= 5,
    }
    newly = []
    for bid, cond in conditions.items():
        if not data["badges"][bid]["unlocked"] and cond(user):
            data["badges"][bid]["unlocked"]    = True
            data["badges"][bid]["unlocked_at"] = datetime.now().isoformat()
            newly.append(data["badges"][bid]["name"])
    return newly


def log_workout(data: dict, exercises: list, duration: int, notes: str = "") -> dict:
    user   = data["user"]
    xp_d   = calculate_xp(duration, exercises, user["current_streak"])
    new_xp = user["total_xp"] + xp_d["total"]
    str_d  = update_streak(user["last_workout_date"], user["current_streak"])
    new_lv = calculate_level(new_xp)
    now    = datetime.now()

    workout = {
        "id":               f"workout_{now.strftime('%Y%m%d_%H%M%S')}",
        "date":             date.today().isoformat(),
        "timestamp":        now.isoformat(),
        "duration_minutes": duration,
        "notes":            notes,
        "exercises":        exercises,
        "xp_earned":        xp_d["total"],
        "total_volume_kg":  calculate_volume(exercises),
    }
    data["workouts"].append(workout)

    new_total = user["total_workouts"] + 1
    data["user"].update({
        "total_xp":          new_xp,
        "level":             new_lv,
        "current_streak":    str_d["new"],
        "longest_streak":    max(user["longest_streak"], str_d["new"]),
        "total_workouts":    new_total,
        "last_workout_date": date.today().isoformat(),
    })

    newly = check_badges(data["user"], data)
    save_data(data)

    return {
        "xp_earned":       xp_d["total"],
        "xp_breakdown":    xp_d,
        "new_total_xp":    new_xp,
        "level":           new_lv,
        "xp_to_next":      xp_to_next(new_xp),
        "streak":          str_d["new"],
        "streak_msg":      str_d["msg"],
        "badges_unlocked": newly,
        "volume_kg":       workout["total_volume_kg"],
    }


# ─────────────────────────────────────────────────────────────
# AI COACH
# ─────────────────────────────────────────────────────────────
def get_groq_key() -> str:
    return os.environ.get("GROQ_API_KEY","")


def build_context(data: dict) -> str:
    user     = data["user"]
    workouts = list(reversed(data["workouts"]))
    goal_map = {
        "muscle_gain":"building muscle through progressive overload",
        "weight_loss":"burning calories and reducing body fat",
        "endurance":"improving cardiovascular stamina",
        "general_fitness":"maintaining balanced overall fitness",
    }
    ctx  = f"USER: {user['name']} | Goal: {user['goal'].replace('_',' ').title()} ({goal_map.get(user['goal'],'fitness')})\n"
    ctx += f"Level: {user['level']} | XP: {user['total_xp']} | Streak: {user['current_streak']} days | Workouts: {user['total_workouts']}\n\n"

    if workouts:
        ctx += "RECENT SESSIONS (last 3):\n"
        for i,w in enumerate(workouts[:3]):
            muscles = list(dict.fromkeys(ex["muscle_group"] for ex in w["exercises"]))
            ctx += f"  {w['date']} ({w['duration_minutes']}min) — {', '.join(muscles)}\n"
            for ex in w["exercises"]:
                if ex["weight_kg"] > 0:
                    ctx += f"    · {ex['name']}: {ex['sets']}×{ex['reps']} @ {ex['weight_kg']}kg\n"

        recent_muscles = set(ex["muscle_group"] for w in workouts[:3] for ex in w["exercises"])
        rested = set(MUSCLE_GROUPS) - recent_muscles
        ctx += f"\nRESTED MUSCLES: {', '.join(sorted(rested)) if rested else 'all trained recently'}\n"
    else:
        ctx += "No workouts logged yet.\n"

    return ctx


def get_suggestion(data: dict, duration: int, api_key: str) -> str:
    client = Groq(api_key=api_key)
    ctx    = build_context(data)
    prompt = f"""You are an expert personal trainer.

{ctx}

Suggest a complete {duration}-minute workout for the NEXT session.
Focus on rested muscles. Match the user's goal.
For muscle_gain: include progressive overload notes.

FORMAT:
SESSION FOCUS: [muscles]

WARM UP (5 mins):
- [exercise]: [duration]

MAIN WORKOUT:
- [Exercise]: [sets]×[reps] @ [weight]kg — [Easy/Medium/Hard] — [tip]

COOL DOWN (5 mins):
- [stretch]

COACH NOTE:
[2-3 sentences of personalized advice]"""

    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":"You are an expert personal trainer. Follow the format exactly."},
            {"role":"user","content":prompt}
        ],
        max_tokens=700,
        temperature=0.7,
    )
    suggestion = resp.choices[0].message.content
    data["latest_suggestion"] = {"text":suggestion,"generated_at":datetime.now().isoformat(),"duration":duration}
    save_data(data)
    return suggestion


def get_tip(data: dict, api_key: str) -> str:
    user   = data["user"]
    client = Groq(api_key=api_key)
    resp   = client.chat.completions.create(
        model=MODEL,
        messages=[{"role":"user","content":
            f"Give ONE fitness tip (2 sentences). "
            f"User goal: {user['goal'].replace('_',' ')}. "
            f"Streak: {user['current_streak']} days. Level: {user['level']}. "
            f"Be specific and actionable."}],
        max_tokens=100,
        temperature=0.8,
    )
    return resp.choices[0].message.content


# ─────────────────────────────────────────────────────────────
# ANALYTICS CHARTS
# ─────────────────────────────────────────────────────────────
BASE_LAYOUT = dict(
    paper_bgcolor=COLORS["bg"], plot_bgcolor=COLORS["surface"],
    font=dict(color=COLORS["text"],family="DM Sans",size=12),
    margin=dict(l=40,r=20,t=50,b=40),
)


def workouts_df(workouts: list) -> pd.DataFrame:
    if not workouts:
        return pd.DataFrame()
    rows, cum_xp = [], 0
    for w in sorted(workouts, key=lambda x: x["date"]):
        cum_xp += w["xp_earned"]
        rows.append({"date":pd.to_datetime(w["date"]),
                     "duration_minutes":w["duration_minutes"],
                     "xp_earned":w["xp_earned"],
                     "cumulative_xp":cum_xp,
                     "total_volume_kg":w["total_volume_kg"]})
    df = pd.DataFrame(rows)
    df["week"]     = df["date"].dt.strftime("Wk %W")
    df["day_name"] = df["date"].dt.strftime("%d %b")
    return df


def exercises_df(workouts: list) -> pd.DataFrame:
    rows = []
    for w in workouts:
        for ex in w["exercises"]:
            rows.append({"date":pd.to_datetime(w["date"]),"name":ex["name"],
                         "muscle_group":ex["muscle_group"],"sets":ex["sets"],
                         "reps":ex["reps"],"weight_kg":ex["weight_kg"],
                         "volume":ex["sets"]*ex["reps"]*ex["weight_kg"]})
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def fig_frequency(df: pd.DataFrame):
    if df.empty: return None
    wk = df.groupby("week").size().reset_index(name="sessions")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=wk["week"],y=wk["sessions"],
        marker_color=COLORS["primary"],text=wk["sessions"],textposition="outside",
        hovertemplate="<b>%{x}</b><br>Sessions: %{y}<extra></extra>"))
    fig.add_hline(y=4,line_dash="dash",line_color=COLORS["success"],
        annotation_text="Goal: 4/week",annotation_font_color=COLORS["success"])
    fig.update_layout(**BASE_LAYOUT,title="Weekly Workout Frequency",showlegend=False,
        xaxis=dict(gridcolor=COLORS["border"],showgrid=False),
        yaxis=dict(title="Sessions",gridcolor=COLORS["border"],dtick=1))
    return fig


def fig_volume(df: pd.DataFrame):
    if df.empty: return None
    ds = df.sort_values("date")
    rolling = ds["total_volume_kg"].rolling(3,min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=ds["day_name"],y=ds["total_volume_kg"],name="Volume",
        marker_color=COLORS["primary"],opacity=0.55,
        hovertemplate="<b>%{x}</b><br>Volume: %{y:.0f} kg<extra></extra>"))
    fig.add_trace(go.Scatter(x=ds["day_name"],y=rolling,name="3-session avg",
        mode="lines+markers",line=dict(color=COLORS["success"],width=2.5),
        marker=dict(size=6,color=COLORS["success"]),
        hovertemplate="<b>%{x}</b><br>Avg: %{y:.0f} kg<extra></extra>"))
    fig.update_layout(**BASE_LAYOUT,title="Volume Progression (kg lifted)",
        xaxis=dict(tickangle=-30,gridcolor=COLORS["border"]),
        yaxis=dict(title="Volume (kg)",gridcolor=COLORS["border"]))
    return fig


def fig_muscle(df_ex: pd.DataFrame):
    if df_ex.empty: return None
    mc = df_ex["muscle_group"].value_counts().reset_index()
    mc.columns = ["muscle","count"]
    colors = [MUSCLE_COLORS.get(m,COLORS["muted"]) for m in mc["muscle"]]
    fig = go.Figure(go.Pie(labels=mc["muscle"].str.title(),values=mc["count"],
        hole=0.45,marker=dict(colors=colors,line=dict(color=COLORS["bg"],width=2)),
        hovertemplate="<b>%{label}</b><br>Exercises: %{value}<br>%{percent}<extra></extra>"))
    fig.update_layout(**BASE_LAYOUT,title="Muscle Group Distribution",showlegend=True)
    return fig


def fig_xp(df: pd.DataFrame):
    if df.empty: return None
    ds = df.sort_values("date")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ds["day_name"],y=ds["cumulative_xp"],name="Total XP",
        mode="lines",fill="tozeroy",line=dict(color=COLORS["warning"],width=2.5),
        fillcolor="rgba(251,191,36,0.12)",
        hovertemplate="<b>%{x}</b><br>Total XP: %{y}<extra></extra>"))
    max_xp = ds["cumulative_xp"].max()
    for lv in range(1, int(max_xp//50)+3):
        thr = lv*50
        if thr <= max_xp*1.25:
            fig.add_hline(y=thr,line_dash="dot",line_color=COLORS["success"],opacity=0.35,
                annotation_text=f"Lv {lv+1}",annotation_font_color=COLORS["success"],
                annotation_font_size=9)
    fig.update_layout(**BASE_LAYOUT,title="XP Progress",showlegend=False,
        xaxis=dict(tickangle=-30,gridcolor=COLORS["border"]),
        yaxis=dict(title="Cumulative XP",gridcolor=COLORS["border"]))
    return fig


def fig_exercise(df_ex: pd.DataFrame, name: str):
    if df_ex.empty or not name: return None
    filtered = df_ex[df_ex["name"].str.lower()==name.lower()]
    if filtered.empty: return None
    prog = filtered.groupby("date")["weight_kg"].max().reset_index().sort_values("date")
    prog["d"] = prog["date"].dt.strftime("%d %b")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=prog["d"],y=prog["weight_kg"],mode="lines+markers",
        name=name,line=dict(color=COLORS["danger"],width=2.5),
        marker=dict(size=9,color=COLORS["danger"],line=dict(color=COLORS["bg"],width=2)),
        fill="tozeroy",fillcolor="rgba(248,113,113,0.1)",
        hovertemplate="<b>%{x}</b><br>%{y} kg<extra></extra>"))
    fig.update_layout(**BASE_LAYOUT,title=f"{name} — Weight Progression",showlegend=False,
        xaxis=dict(gridcolor=COLORS["border"]),
        yaxis=dict(title="Weight (kg)",gridcolor=COLORS["border"]))
    return fig


# ─────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────
if "data" not in st.session_state:
    st.session_state.data = load_data()
if "workout_result" not in st.session_state:
    st.session_state.workout_result = None
if "exercises" not in st.session_state:
    st.session_state.exercises = []
if "suggestion" not in st.session_state:
    st.session_state.suggestion = None


def refresh():
    st.session_state.data = load_data()


# ─────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────
data = st.session_state.data
user = data["user"]

col_title, col_key = st.columns([3, 1])
with col_title:
    name_display = user["name"] if user["name"] else "FitTracker"
    st.markdown(f"## 💪 {name_display}")
with col_key:
    env_key = get_groq_key()
    if env_key:
        api_key = env_key
    else:
        api_key = st.text_input("Groq API Key", type="password",
                                placeholder="gsk_...", label_visibility="collapsed")

st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# SETUP SCREEN (first time)
# ─────────────────────────────────────────────────────────────
if not user["name"]:
    st.markdown("### 👋 Welcome to FitTracker!")
    st.markdown("Let's set up your profile before we begin.")
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        new_name = st.text_input("Your name", placeholder="Anchal")
    with c2:
        new_goal = st.selectbox("Fitness goal", list(VALID_GOALS.values()))

    if st.button("Get Started 🚀", use_container_width=True):
        if new_name.strip():
            goal_key = [k for k,v in VALID_GOALS.items() if v==new_goal][0]
            data["user"].update({"name":new_name.strip(),"goal":goal_key,
                                 "created_at":date.today().isoformat()})
            save_data(data)
            st.session_state.data = data
            st.rerun()
        else:
            st.warning("Please enter your name.")
    st.stop()

# ─────────────────────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🏋️ Log Workout","🏆 Dashboard","🤖 AI Coach","📊 Analytics"])


# ══════════════════════════════════════════════════════════════
# TAB 1 — LOG WORKOUT
# ══════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-title">Add Exercise</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        ex_name    = st.text_input("Exercise name", placeholder="Bench Press")
        muscle_grp = st.selectbox("Muscle group", MUSCLE_GROUPS)
    with c2:
        sets       = st.number_input("Sets",       min_value=1, max_value=20, value=3)
        reps       = st.number_input("Reps",       min_value=0, max_value=100, value=10)
    with c3:
        weight     = st.number_input("Weight (kg)", min_value=0.0, max_value=500.0,
                                     value=0.0, step=2.5)
        dur_ex     = st.number_input("Duration (min, for cardio)",
                                     min_value=0, max_value=120, value=0)

    if st.button("➕ Add Exercise", use_container_width=True):
        if ex_name.strip():
            st.session_state.exercises.append({
                "name":ex_name.strip(),"muscle_group":muscle_grp,
                "sets":sets,"reps":reps,"weight_kg":weight,"duration_minutes":dur_ex
            })

    # Exercise list
    if st.session_state.exercises:
        st.markdown('<div class="section-title">This Session</div>', unsafe_allow_html=True)
        for i, ex in enumerate(st.session_state.exercises):
            c_ex, c_rm = st.columns([5,1])
            with c_ex:
                if ex["weight_kg"] > 0:
                    st.markdown(f"**{ex['name']}** — {ex['sets']}×{ex['reps']} @ {ex['weight_kg']}kg _{ex['muscle_group']}_")
                elif ex["duration_minutes"] > 0:
                    st.markdown(f"**{ex['name']}** — {ex['duration_minutes']} mins _{ex['muscle_group']}_")
                else:
                    st.markdown(f"**{ex['name']}** — {ex['sets']}×{ex['reps']} bodyweight _{ex['muscle_group']}_")
            with c_rm:
                if st.button("🗑️", key=f"rm_{i}"):
                    st.session_state.exercises.pop(i)
                    st.rerun()

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
        c_dur, c_notes = st.columns(2)
        with c_dur:
            session_dur = st.number_input("Session duration (min)",
                                          min_value=5, max_value=300, value=45)
        with c_notes:
            notes = st.text_input("Notes (optional)", placeholder="Felt strong today")

        if st.button("✅ Log Workout", use_container_width=True, type="primary"):
            result = log_workout(data, st.session_state.exercises, session_dur, notes)
            st.session_state.workout_result = result
            st.session_state.exercises = []
            st.session_state.data = load_data()
            st.rerun()

    # Result display
    if st.session_state.workout_result:
        r = st.session_state.workout_result
        st.markdown(f"""
        <div class="toast">
        ✅ <b>Workout logged!</b><br>
        +{r['xp_earned']} XP
        (base {r['xp_breakdown']['base']}
        + duration {r['xp_breakdown']['duration']}
        + volume {r['xp_breakdown']['volume']}
        + streak {r['xp_breakdown']['streak']})<br>
        Level {r['level']} · {r['xp_to_next']} XP to next · Streak: {r['streak']} days<br>
        {r['streak_msg']}
        {('<br>🏅 Badge unlocked: ' + ', '.join(r['badges_unlocked'])) if r['badges_unlocked'] else ''}
        </div>
        """, unsafe_allow_html=True)
        if st.button("Clear"):
            st.session_state.workout_result = None
            st.rerun()

    if not st.session_state.exercises and not st.session_state.workout_result:
        st.markdown("""
        <div style='text-align:center;padding:2.5rem 0;color:#72728a'>
          <div style='font-size:2.5rem'>🏋️</div>
          <div style='margin:.5rem 0;color:#e8e8f0;font-size:1rem'>Add exercises to start logging</div>
          <div style='font-size:.85rem'>Fill in the form above and click Add Exercise</div>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TAB 2 — DASHBOARD
# ══════════════════════════════════════════════════════════════
with tab2:
    data = st.session_state.data
    user = data["user"]

    # XP bar
    xp_pct = ((user["total_xp"] % XP_PER_LEVEL) / XP_PER_LEVEL) * 100
    st.markdown(f"""
    <div class="xp-bar-wrap">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:1.1rem;font-weight:500">Level {user['level']}</span>
        <span style="font-size:.85rem;color:#72728a">{user['total_xp']} XP total</span>
      </div>
      <div class="xp-bar-track"><div class="xp-bar-fill" style="width:{xp_pct:.0f}%"></div></div>
      <div class="xp-label">
        <span>{user['total_xp'] % XP_PER_LEVEL} / {XP_PER_LEVEL} XP</span>
        <span>{xp_to_next(user['total_xp'])} XP to Level {user['level']+1}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Stats row
    st.markdown(f"""
    <div class="metric-row">
      <div class="metric-card"><div class="metric-val">{user['total_workouts']}</div><div class="metric-label">Workouts</div></div>
      <div class="metric-card"><div class="metric-val">{user['total_xp']}</div><div class="metric-label">Total XP</div></div>
      <div class="metric-card"><div class="metric-val">🔥 {user['current_streak']}</div><div class="metric-label">Day Streak</div></div>
      <div class="metric-card"><div class="metric-val">{user['longest_streak']}</div><div class="metric-label">Best Streak</div></div>
      <div class="metric-card"><div class="metric-val">{user['level']}</div><div class="metric-label">Level</div></div>
    </div>
    """, unsafe_allow_html=True)

    # Badges
    st.markdown('<div class="section-title">Badges</div>', unsafe_allow_html=True)
    unlocked = [b for b in data["badges"].values() if b["unlocked"]]
    locked   = [b for b in data["badges"].values() if not b["unlocked"]]

    badge_html = '<div class="badge-grid">'
    for b in unlocked:
        badge_html += f'<div class="badge-card unlocked"><div class="badge-icon">{b["icon"]}</div><div><div class="badge-name">{b["name"]}</div><div class="badge-desc">{b["description"]}</div></div></div>'
    for b in locked:
        badge_html += f'<div class="badge-card"><div class="badge-icon" style="opacity:.3">{b["icon"]}</div><div><div class="badge-name" style="color:#72728a">{b["name"]}</div><div class="badge-desc">{b["description"]}</div></div></div>'
    badge_html += '</div>'
    st.markdown(badge_html, unsafe_allow_html=True)

    # Recent workouts
    if data["workouts"]:
        st.markdown('<div class="section-title">Recent Workouts</div>', unsafe_allow_html=True)
        for w in list(reversed(data["workouts"]))[:5]:
            muscles = list(dict.fromkeys(ex["muscle_group"] for ex in w["exercises"]))
            with st.expander(f"📅 {w['date']} — {', '.join(muscles).title()} ({w['duration_minutes']} min · +{w['xp_earned']} XP)"):
                for ex in w["exercises"]:
                    if ex["weight_kg"] > 0:
                        st.markdown(f"- **{ex['name']}**: {ex['sets']}×{ex['reps']} @ {ex['weight_kg']}kg")
                    else:
                        st.markdown(f"- **{ex['name']}**: {ex['sets']}×{ex['reps']} bodyweight")
                if w.get("notes"):
                    st.caption(f"📝 {w['notes']}")

    if st.button("🔄 Refresh", use_container_width=False):
        st.session_state.data = load_data()
        st.rerun()


# ══════════════════════════════════════════════════════════════
# TAB 3 — AI COACH
# ══════════════════════════════════════════════════════════════
with tab3:
    data = st.session_state.data

    if not api_key:
        st.info("Enter your Groq API key at the top of the page to use the AI Coach.")
    else:
        # Daily tip
        st.markdown('<div class="section-title">💡 Daily Tip</div>', unsafe_allow_html=True)
        if st.button("Get Today's Tip", use_container_width=False):
            with st.spinner("Getting your tip..."):
                try:
                    tip = get_tip(data, api_key)
                    st.markdown(f'<div class="coach-box">{tip}</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error: {e}")

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

        # Workout suggestion
        st.markdown('<div class="section-title">🤖 Next Session Plan</div>', unsafe_allow_html=True)
        c1, c2 = st.columns([1,2])
        with c1:
            duration = st.slider("Session duration (min)", 20, 90, 45, step=5)
        with c2:
            st.markdown(f"""
            <div style="padding:.5rem 0;font-size:.85rem;color:#72728a">
            Goal: <b style="color:#e8e8f0">{VALID_GOALS.get(data['user']['goal'],'—')}</b><br>
            Streak: <b style="color:#e8e8f0">{data['user']['current_streak']} days</b>
            </div>""", unsafe_allow_html=True)

        if st.button("Generate Workout Plan 🚀", use_container_width=True, type="primary"):
            with st.spinner("Your AI coach is building your plan..."):
                try:
                    suggestion = get_suggestion(data, duration, api_key)
                    st.session_state.suggestion = suggestion
                    st.session_state.data = load_data()
                except Exception as e:
                    st.error(f"Error: {e}")

        # Show suggestion
        if st.session_state.suggestion:
            st.markdown('<div class="coach-label">Your Plan</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="coach-box">{st.session_state.suggestion}</div>',
                        unsafe_allow_html=True)
        elif data.get("latest_suggestion"):
            ls = data["latest_suggestion"]
            st.markdown('<div class="coach-label">Last Generated Plan</div>', unsafe_allow_html=True)
            st.markdown(f'<div class="coach-box">{ls["text"]}</div>', unsafe_allow_html=True)
            st.caption(f"Generated: {ls['generated_at'][:10]}")


# ══════════════════════════════════════════════════════════════
# TAB 4 — ANALYTICS
# ══════════════════════════════════════════════════════════════
with tab4:
    data     = st.session_state.data
    df_w     = workouts_df(data["workouts"])
    df_ex    = exercises_df(data["workouts"])

    if df_w.empty:
        st.markdown("""
        <div style='text-align:center;padding:3rem 0;color:#72728a'>
          <div style='font-size:2.5rem'>📊</div>
          <div style='color:#e8e8f0;font-size:1rem;margin:.5rem 0'>No data yet</div>
          <div style='font-size:.85rem'>Log some workouts to see your analytics</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Stats row
        total_vol = df_w["total_volume_kg"].sum()
        avg_dur   = df_w["duration_minutes"].mean()
        top_muscle = df_ex["muscle_group"].value_counts().index[0].title() if not df_ex.empty else "—"
        max_weight = df_ex[df_ex["weight_kg"]>0]["weight_kg"].max() if not df_ex.empty else 0

        st.markdown(f"""
        <div class="metric-row">
          <div class="metric-card"><div class="metric-val">{int(total_vol):,}</div><div class="metric-label">Total kg lifted</div></div>
          <div class="metric-card"><div class="metric-val">{avg_dur:.0f} min</div><div class="metric-label">Avg Duration</div></div>
          <div class="metric-card"><div class="metric-val">{top_muscle}</div><div class="metric-label">Top Muscle</div></div>
          <div class="metric-card"><div class="metric-val">{max_weight:.0f} kg</div><div class="metric-label">Heaviest Lift</div></div>
        </div>
        """, unsafe_allow_html=True)

        # Charts — 2 column layout
        c1, c2 = st.columns(2)
        with c1:
            f = fig_frequency(df_w)
            if f: st.plotly_chart(f, use_container_width=True)
        with c2:
            f = fig_muscle(df_ex)
            if f: st.plotly_chart(f, use_container_width=True)

        f = fig_volume(df_w)
        if f: st.plotly_chart(f, use_container_width=True)

        f = fig_xp(df_w)
        if f: st.plotly_chart(f, use_container_width=True)

        # Exercise progression picker
        if not df_ex.empty:
            weighted = df_ex[df_ex["weight_kg"]>0]["name"].unique().tolist()
            if weighted:
                st.markdown('<div class="section-title">Exercise Progression</div>',
                            unsafe_allow_html=True)
                chosen = st.selectbox("Pick an exercise", sorted(weighted))
                f = fig_exercise(df_ex, chosen)
                if f: st.plotly_chart(f, use_container_width=True)
