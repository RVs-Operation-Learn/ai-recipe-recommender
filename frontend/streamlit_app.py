import streamlit as st
import requests
from datetime import date, timedelta

API_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="AI Recipe Recommender",
    page_icon="🍲",
    layout="wide"
)

# -------------------------------
# SESSION STATE INITIALIZATION
# -------------------------------
if "recommendation_result" not in st.session_state:
    st.session_state.recommendation_result = None

# Meal planner (persistent across searches)
if "meal_plan" not in st.session_state:
    st.session_state.meal_plan = {}

# Replace confirmation
if "pending_replace" not in st.session_state:
    st.session_state.pending_replace = None

# Clear confirmation
if "pending_clear_all" not in st.session_state:
    st.session_state.pending_clear_all = False

# Remove meal confirmation
if "pending_remove_meal" not in st.session_state:
    st.session_state.pending_remove_meal = None


# -------------------------------
# BACKWARD COMPATIBILITY HELPER
# -------------------------------
def normalize_meal_entry(info):
    if isinstance(info, dict):
        return info
    return {
        "name": info,
        "cuisine": "Unknown",
        "missing": [],
        "required": [],
        "total_time": None
    }


# -------------------------------
# DATA FETCH
# -------------------------------
@st.cache_data
def fetch_cuisines():
    resp = requests.get(f"{API_URL}/metadata/cuisines")
    resp.raise_for_status()
    return resp.json()["cuisines"]

cuisine_options = fetch_cuisines()


# -------------------------------
# API CALL
# -------------------------------
def call_recommend_api(
    image_file,
    cuisine,
    diet,
    cooking_time,
    persons,
    meal,
    optional_vegetables=""
):
    files = {"file": (image_file.name, image_file, image_file.type)}
    data = {
        "optional_vegetables": optional_vegetables,
        "cuisine": cuisine,
        "diet": diet,
        "cooking_time": cooking_time,
        "persons": persons,
        "meal": meal
    }
    resp = requests.post(f"{API_URL}/recommend-from-image", files=files, data=data)
    resp.raise_for_status()
    return resp.json()


# -------------------------------
# SIDEBAR
# -------------------------------
st.sidebar.title("🧾 Preferences")

uploaded_file = st.sidebar.file_uploader(
    "Upload vegetable image",
    type=["jpg", "jpeg", "png"]
)

cuisine = st.sidebar.selectbox(
    "Cuisine style",
    options=cuisine_options,
    format_func=lambda x: x["label"]
)["value"]

diet = st.sidebar.radio("Diet", ["veg", "non-veg"])
meal = st.sidebar.selectbox("Meal", ["breakfast", "lunch", "dinner"])
cooking_time = st.sidebar.selectbox("Cooking time (minutes)", [15, 30, 45, 60])
persons = st.sidebar.selectbox("Servings", [1, 2, 3, 4])

optional_vegetables = st.sidebar.text_input(
    "Optional vegetables (comma-separated)",
    placeholder="onion, tomato"
)


# -------------------------------
# MAIN ACTION
# -------------------------------
st.title("🍲 AI Recipe Recommender")
st.caption("Upload a vegetable image and get personalized recipe suggestions")

st.info(
    "📌 **Your meal plan is preserved across searches.** "
    "You can search with different vegetables and cuisines and keep adding meals."
)

st.divider()

if st.button("🔍 Recommend Recipes", use_container_width=True):
    if not uploaded_file:
        st.error("Please upload an image first.")
    else:
        with st.spinner("Detecting vegetables and finding recipes..."):
            st.session_state.recommendation_result = call_recommend_api(
                uploaded_file,
                cuisine,
                diet,
                cooking_time,
                persons,
                meal,
                optional_vegetables
            )


# -------------------------------
# RENDER RESULTS
# -------------------------------
result = st.session_state.recommendation_result

if result:
    detected = result.get("detected_vegetables", [])
    recipes = result.get("recipes", [])

    st.success(f"🥕 Detected vegetables: {', '.join(detected) if detected else 'None'}")

    # Unlock suggestion (unchanged)
    missing_counter = {}
    for r in recipes[:5]:
        for ing in r.get("missing_ingredients", []):
            missing_counter[ing] = missing_counter.get(ing, 0) + 1

    suggested = sorted(missing_counter.items(), key=lambda x: x[1], reverse=True)[:3]
    if suggested:
        st.info(
            f"💡 Add {', '.join([x[0] for x in suggested])} to unlock more recipes"
        )

    st.header(f"🍽️ Recommended Recipes ({len(recipes)})")

    for recipe in recipes:
        recipe_id = recipe["id"]
        recipe_name = recipe["name"]
        recipe_cuisine = recipe.get("cuisine")
        missing = recipe.get("missing_ingredients", [])
        required = recipe.get("required_ingredients", [])
        total_time = recipe.get("cooking_time") or recipe.get("meta", {}).get("total_time")

        with st.container(border=True):

            st.markdown(f"## {recipe_name}")
            st.caption(f"🍽️ {recipe_cuisine} | ⏱️ {total_time} mins")

            if missing:
                st.warning(f"⚠️ Missing: {', '.join(missing)}")

            st.progress(recipe.get("coverage_percent", 0) / 100)
            st.caption(f"{recipe.get('coverage_percent', 0)}% ingredients available")

            st.info(
                "💡 **Why this recipe?**\n\n"
                f"- Matches your selected cuisine\n"
                f"- Fits your cooking time\n"
                f"- Only {len(missing)} more ingredients needed"
            )

            # ✅ Restored Instructions + Full Recipe
            with st.expander("📖 View Instructions"):
                st.write(recipe.get("meta", {}).get("instructions", "No instructions available."))

            if recipe.get("meta", {}).get("recipe_url"):
                st.link_button("🔗 Open Full Recipe", recipe["meta"]["recipe_url"])

            # Add to Meal Plan
            st.markdown("### 🍱 Add to Meal Plan")
            plan_date = st.date_input("Date", value=date.today(), key=f"d_{recipe_id}")
            plan_meal = st.selectbox(
                "Meal", ["breakfast", "lunch", "dinner"], key=f"m_{recipe_id}"
            )

            if st.button("➕ Add to Meal Plan", key=f"add_{recipe_id}"):

                d = str(plan_date)
                snapshot = {
                    "name": recipe_name,
                    "cuisine": recipe_cuisine,
                    "missing": missing,
                    "required": required,
                    "total_time": total_time
                }

                existing = st.session_state.meal_plan.get(d, {}).get(plan_meal)

                if existing:
                    st.session_state.pending_replace = {
                        "date": d,
                        "meal": plan_meal,
                        "new": snapshot,
                        "old": normalize_meal_entry(existing)
                    }
                else:
                    st.session_state.meal_plan.setdefault(d, {})[plan_meal] = snapshot
                    st.success("Added to meal plan")

    # -------------------------------
    # REPLACE CONFIRMATION
    # -------------------------------
    if st.session_state.pending_replace:
        p = st.session_state.pending_replace

        st.warning(
            f"⚠️ Replace planned meal?\n\n"
            f"{p['meal'].title()} on {p['date']} already has:\n"
            f"{p['old']['name']}\n\n"
            f"Replace with:\n"
            f"{p['new']['name']}"
        )

        col1, col2 = st.columns(2)

        if col1.button("Cancel"):
            st.session_state.pending_replace = None

        if col2.button("Confirm Replace"):
            st.session_state.meal_plan.setdefault(p["date"], {})[p["meal"]] = p["new"]
            st.session_state.pending_replace = None
            st.success("Meal replaced successfully")
            st.rerun()


    # -------------------------------
    # MEAL PLANNER VIEW
    # -------------------------------
    st.divider()
    st.header("📅 Meal Planner")
    st.caption("🧠 Independent of current search")

    # Clear All Button
    if st.button("🧹 Clear Meal Plan"):
        st.session_state.pending_clear_all = True

    if st.session_state.pending_clear_all:
        st.warning("⚠️ This will remove ALL planned meals. Are you sure?")
        c1, c2 = st.columns(2)

        if c1.button("Yes, Clear All"):
            st.session_state.meal_plan = {}
            st.session_state.pending_clear_all = False
            st.success("Meal plan cleared")
            st.rerun()

        if c2.button("Cancel"):
            st.session_state.pending_clear_all = False

    # Render Meals
    for d, meals in sorted(st.session_state.meal_plan.items()):
        st.subheader(d)

        for m, raw in meals.items():
            info = normalize_meal_entry(raw)

            col1, col2 = st.columns([6, 1])

            with col1:
                st.markdown(
                    f"**{m.title()}**: {info['name']}  \n"
                    f"• Cuisine: {info['cuisine']}"
                )

            with col2:
                if st.button("❌", key=f"remove_{d}_{m}"):
                    st.session_state.pending_remove_meal = (d, m)

    # Remove Confirmation
    if st.session_state.pending_remove_meal:
        d, m = st.session_state.pending_remove_meal

        st.warning(f"Remove {m.title()} on {d}?")

        r1, r2 = st.columns(2)

        if r1.button("Yes Remove"):
            del st.session_state.meal_plan[d][m]
            if not st.session_state.meal_plan[d]:
                del st.session_state.meal_plan[d]
            st.session_state.pending_remove_meal = None
            st.success("Meal removed")
            st.rerun()

        if r2.button("Cancel"):
            st.session_state.pending_remove_meal = None


    # -------------------------------
    # WEEKLY OVERVIEW (UNCHANGED)
    # -------------------------------
    st.divider()
    st.header("📆 Weekly Meal Overview")

    today = date.today()
    start = today - timedelta(days=today.weekday())

    for i in range(7):
        day = start + timedelta(days=i)
        meals = st.session_state.meal_plan.get(str(day), {})

        with st.expander(day.strftime("%A, %d %b")):
            for m in ["breakfast", "lunch", "dinner"]:
                raw = meals.get(m)
                if raw:
                    info = normalize_meal_entry(raw)
                    st.write(f"**{m.title()}**: {info['name']} ({info['cuisine']})")
                else:
                    st.write(f"**{m.title()}**: —")


    # -------------------------------
    # SHOPPING LIST (UNCHANGED)
    # -------------------------------
    st.divider()
    st.header("🛒 Shopping List (from Meal Plan)")

    for d, meals in sorted(st.session_state.meal_plan.items()):
        st.subheader(d)

        for m, raw in meals.items():
            info = normalize_meal_entry(raw)

            if info["missing"]:
                st.markdown(f"**{m.title()}**")
                for ing in info["missing"]:
                    st.checkbox(ing, key=f"{d}_{m}_{ing}")