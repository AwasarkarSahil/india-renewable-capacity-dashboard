"""
MNRE Renewable Energy Dashboard
--------------------------------
Interactive Streamlit dashboard for India's state-wise renewable energy
capacity data (2014-2026), sourced from MNRE.

Run locally:
    pip install -r requirements.txt
    streamlit run app.py
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------
# Page config
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="MNRE Renewable Energy Dashboard",
    page_icon="🌞",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_PATH = "data.xlsx"
SHEET_NAME = "Consolidated Data"


# --------------------------------------------------------------------------
# Data loading (cached so the file is only read once per session)
# --------------------------------------------------------------------------
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=SHEET_NAME)
    df.columns = [c.strip() for c in df.columns]
    df["Capacity (MW)"] = pd.to_numeric(df["Capacity (MW)"], errors="coerce").fillna(0)
    df["Year"] = df["Year"].astype(int)
    # Drop "Total" / roll-up category rows so charts don't double count,
    # but keep them available for a toggle if the user wants official totals.
    return df


df_raw = load_data(DATA_PATH)

# Some rows are pre-aggregated "Total" categories or "*-Power Total" sub-categories.
# We treat Category == "Total" as a state-level grand total row, and separately
# flag sub-category rows that end with "Total" as category-level roll-ups.
is_grand_total = df_raw["Category"].eq("Total")
is_subcat_rollup = df_raw["Sub-Category"].astype(str).str.endswith("Total") & ~is_grand_total

df_detail = df_raw[~is_grand_total & ~is_subcat_rollup].copy()      # cleanest, most granular
df_with_rollups = df_raw[~is_grand_total].copy()                    # detail + category roll-up rows


# --------------------------------------------------------------------------
# Sidebar filters
# --------------------------------------------------------------------------
st.sidebar.title("🌞 MNRE Dashboard")
st.sidebar.caption("Filter the data to update every chart below.")

all_years = sorted(df_detail["Year"].unique())
year_range = st.sidebar.select_slider(
    "Year range",
    options=all_years,
    value=(all_years[0], all_years[-1]),
)

all_states = sorted(df_detail["State/UT"].unique())
selected_states = st.sidebar.multiselect(
    "State / UT",
    options=all_states,
    default=[],
    help="Leave empty to include all states/UTs.",
)

all_categories = sorted(df_detail["Category"].unique())
selected_categories = st.sidebar.multiselect(
    "Energy category",
    options=all_categories,
    default=[],
    help="Leave empty to include all categories.",
)

st.sidebar.markdown("---")
data_mode = st.sidebar.radio(
    "Granularity",
    options=["Detailed sub-categories", "Include category roll-up rows"],
    index=0,
    help=(
        "'Detailed sub-categories' excludes rows like 'Bio-Power Total' to avoid "
        "double-counting. Use the other option only if you specifically want those "
        "roll-up rows included."
    ),
)

st.sidebar.markdown("---")
top_n = st.sidebar.slider("Show top N states in rankings", 5, 36, 10)

base_df = df_detail if data_mode == "Detailed sub-categories" else df_with_rollups

# Apply filters
mask = base_df["Year"].between(year_range[0], year_range[1])
if selected_states:
    mask &= base_df["State/UT"].isin(selected_states)
if selected_categories:
    mask &= base_df["Category"].isin(selected_categories)

filtered = base_df[mask].copy()

st.sidebar.markdown("---")
st.sidebar.download_button(
    "⬇️ Download filtered data (CSV)",
    data=filtered.to_csv(index=False).encode("utf-8"),
    file_name="mnre_filtered_data.csv",
    mime="text/csv",
)


# --------------------------------------------------------------------------
# Header + KPIs
# --------------------------------------------------------------------------
st.title("India Renewable Energy Capacity Dashboard")
st.caption(
    f"Data source: MNRE • Years {year_range[0]}–{year_range[1]} • "
    f"{len(selected_states) or 'All'} state(s) • {len(selected_categories) or 'All'} category(ies)"
)

if filtered.empty:
    st.warning("No data matches the current filters. Try widening your selection.")
    st.stop()

latest_year = filtered["Year"].max()
earliest_year = filtered["Year"].min()

total_capacity = filtered["Capacity (MW)"].sum()
latest_year_capacity = filtered.loc[filtered["Year"] == latest_year, "Capacity (MW)"].sum()
earliest_year_capacity = filtered.loc[filtered["Year"] == earliest_year, "Capacity (MW)"].sum()

if earliest_year_capacity > 0 and latest_year != earliest_year:
    cagr_years = latest_year - earliest_year
    cagr = ((latest_year_capacity / earliest_year_capacity) ** (1 / cagr_years) - 1) * 100
else:
    cagr = None

top_state_latest = (
    filtered[filtered["Year"] == latest_year]
    .groupby("State/UT")["Capacity (MW)"]
    .sum()
    .sort_values(ascending=False)
)
top_state_name = top_state_latest.index[0] if not top_state_latest.empty else "N/A"
top_state_value = top_state_latest.iloc[0] if not top_state_latest.empty else 0

top_category_latest = (
    filtered[filtered["Year"] == latest_year]
    .groupby("Category")["Capacity (MW)"]
    .sum()
    .sort_values(ascending=False)
)
top_category_name = top_category_latest.index[0] if not top_category_latest.empty else "N/A"

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total capacity (selected range)", f"{total_capacity:,.0f} MW")
k2.metric(f"Capacity in {latest_year}", f"{latest_year_capacity:,.0f} MW")
k3.metric(
    "CAGR" if cagr is not None else "Growth",
    f"{cagr:,.1f}%" if cagr is not None else "N/A",
    help="Compound annual growth rate from earliest to latest selected year.",
)
k4.metric(f"Top state ({latest_year})", top_state_name, f"{top_state_value:,.0f} MW")
k5.metric(f"Top category ({latest_year})", top_category_name)

st.markdown("---")


# --------------------------------------------------------------------------
# Tabs for different views
# --------------------------------------------------------------------------
tab_trend, tab_states, tab_mix, tab_table = st.tabs(
    ["📈 Trend Over Time", "🗺️ State Comparison", "🥧 Category Mix", "📋 Data Table"]
)

# ---- Tab 1: Trend over time ----------------------------------------------
with tab_trend:
    st.subheader("Capacity growth over time")

    trend_group_by = st.radio(
        "Break trend line down by:",
        ["Total (no breakdown)", "Category", "State/UT"],
        horizontal=True,
        key="trend_group",
    )

    if trend_group_by == "Total (no breakdown)":
        trend_df = filtered.groupby("Year", as_index=False)["Capacity (MW)"].sum()
        fig = px.area(
            trend_df,
            x="Year",
            y="Capacity (MW)",
            markers=True,
            title="Total renewable capacity by year",
        )
    elif trend_group_by == "Category":
        trend_df = filtered.groupby(["Year", "Category"], as_index=False)["Capacity (MW)"].sum()
        fig = px.line(
            trend_df,
            x="Year",
            y="Capacity (MW)",
            color="Category",
            markers=True,
            title="Capacity by category over time",
        )
    else:
        # Limit to top N states by total capacity to keep the chart readable
        top_states_list = (
            filtered.groupby("State/UT")["Capacity (MW)"].sum().sort_values(ascending=False).head(top_n).index
        )
        trend_df = (
            filtered[filtered["State/UT"].isin(top_states_list)]
            .groupby(["Year", "State/UT"], as_index=False)["Capacity (MW)"]
            .sum()
        )
        fig = px.line(
            trend_df,
            x="Year",
            y="Capacity (MW)",
            color="State/UT",
            markers=True,
            title=f"Capacity over time — top {top_n} states",
        )

    fig.update_layout(hovermode="x unified", legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Year-on-year change")
    yoy = filtered.groupby("Year", as_index=False)["Capacity (MW)"].sum()
    yoy["YoY Change (MW)"] = yoy["Capacity (MW)"].diff()
    yoy_fig = px.bar(
        yoy.dropna(),
        x="Year",
        y="YoY Change (MW)",
        title="Year-on-year absolute change in total capacity",
        color="YoY Change (MW)",
        color_continuous_scale="RdYlGn",
    )
    st.plotly_chart(yoy_fig, use_container_width=True)

# ---- Tab 2: State comparison ----------------------------------------------
with tab_states:
    st.subheader(f"State/UT ranking — {latest_year}")

    state_latest = (
        filtered[filtered["Year"] == latest_year]
        .groupby("State/UT", as_index=False)["Capacity (MW)"]
        .sum()
        .sort_values("Capacity (MW)", ascending=False)
        .head(top_n)
    )
    bar_fig = px.bar(
        state_latest,
        x="Capacity (MW)",
        y="State/UT",
        orientation="h",
        title=f"Top {top_n} states by capacity in {latest_year}",
        color="Capacity (MW)",
        color_continuous_scale="Greens",
        text_auto=".0f",
    )
    bar_fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(bar_fig, use_container_width=True)

    st.subheader("Compare two states side-by-side")
    c1, c2 = st.columns(2)
    with c1:
        state_a = st.selectbox("State A", all_states, index=all_states.index("Gujarat") if "Gujarat" in all_states else 0)
    with c2:
        default_b_idx = all_states.index("Tamil Nadu") if "Tamil Nadu" in all_states else min(1, len(all_states) - 1)
        state_b = st.selectbox("State B", all_states, index=default_b_idx)

    compare_df = filtered[filtered["State/UT"].isin([state_a, state_b])]
    compare_trend = compare_df.groupby(["Year", "State/UT"], as_index=False)["Capacity (MW)"].sum()
    compare_fig = px.line(
        compare_trend,
        x="Year",
        y="Capacity (MW)",
        color="State/UT",
        markers=True,
        title=f"{state_a} vs {state_b} — capacity over time",
    )
    st.plotly_chart(compare_fig, use_container_width=True)

    # Category breakdown for the two states in the latest year
    compare_cat = (
        compare_df[compare_df["Year"] == latest_year]
        .groupby(["State/UT", "Category"], as_index=False)["Capacity (MW)"]
        .sum()
    )
    compare_cat_fig = px.bar(
        compare_cat,
        x="Category",
        y="Capacity (MW)",
        color="State/UT",
        barmode="group",
        title=f"Category mix — {state_a} vs {state_b} ({latest_year})",
    )
    st.plotly_chart(compare_cat_fig, use_container_width=True)

# ---- Tab 3: Category mix ---------------------------------------------------
with tab_mix:
    st.subheader(f"Category mix — {latest_year}")

    mix_df = filtered[filtered["Year"] == latest_year].groupby("Category", as_index=False)["Capacity (MW)"].sum()
    pie_fig = px.pie(
        mix_df,
        names="Category",
        values="Capacity (MW)",
        title=f"Share of total capacity by category ({latest_year})",
        hole=0.4,
    )
    pie_fig.update_traces(textinfo="percent+label")
    st.plotly_chart(pie_fig, use_container_width=True)

    st.subheader("Category share evolution over time")
    stacked_df = filtered.groupby(["Year", "Category"], as_index=False)["Capacity (MW)"].sum()
    stacked_fig = px.area(
        stacked_df,
        x="Year",
        y="Capacity (MW)",
        color="Category",
        groupnorm="percent",
        title="Category share of total capacity, by year (%)",
    )
    stacked_fig.update_layout(yaxis_title="Share (%)")
    st.plotly_chart(stacked_fig, use_container_width=True)

    st.subheader("Top sub-categories")
    subcat_df = (
        filtered[filtered["Year"] == latest_year]
        .groupby("Sub-Category", as_index=False)["Capacity (MW)"]
        .sum()
        .sort_values("Capacity (MW)", ascending=False)
        .head(15)
    )
    subcat_fig = px.bar(
        subcat_df,
        x="Capacity (MW)",
        y="Sub-Category",
        orientation="h",
        title=f"Top sub-categories by capacity ({latest_year})",
        text_auto=".0f",
    )
    subcat_fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(subcat_fig, use_container_width=True)

# ---- Tab 4: Raw data table --------------------------------------------------
with tab_table:
    st.subheader("Filtered data")
    st.dataframe(
        filtered.sort_values(["Year", "State/UT", "Category"]).reset_index(drop=True),
        use_container_width=True,
        height=500,
    )
    st.caption(f"{len(filtered):,} rows shown out of {len(base_df):,} in the selected granularity mode.")

st.markdown("---")
st.caption("Built with Streamlit • Data: Ministry of New and Renewable Energy (MNRE), Government of India")
