import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# 1. Page Configuration
st.set_page_config(
    page_title="IDOT Bid Item Report - Parquet Version",
    layout="wide",
    initial_sidebar_state="expanded",
)


# 2. Parquet Data Loader
@st.cache_data
def load_parquet_data(file_path):  # <-- KEEP THIS EXACTLY AS "file_path"
    try:
        # Reads the highly optimized Parquet file
        df = pd.read_parquet(file_path, engine="pyarrow")
        return df
    except Exception as e:
        st.error(
            f"Error loading Parquet file '{file_path}': {e}. Please check the file path and name."
        )
        return pd.DataFrame()


# THIS IS WHERE YOU PUT YOUR ACTUAL FILE NAME (with quotes)
PARQUET_FILE = "openbidzdata.parquet"
df_all = load_parquet_data(PARQUET_FILE)


# Only build the app if data successfully loaded
if not df_all.empty:

    # 3. Sidebar Filters
    st.sidebar.header("Filter Options")

    # Pay Item selector
    unique_vals = df_all["Pay Item #"].dropna().unique()
    pay_item_options = sorted([str(x) for x in unique_vals])
    selected_pay_code = st.sidebar.selectbox(
        "Select Pay Item #", options=pay_item_options, index=0
    )

    # Grab description safely
    desc_series = df_all[df_all["Pay Item #"] == selected_pay_code][
        "Pay Item Description"
    ]
    selected_desc = (
        desc_series.iloc[0] if not desc_series.empty else "No description available"
    )
    st.sidebar.markdown(f"**Description:**\n*{selected_desc}*")

    # County & District Filters
    county_options = ["County (All)"] + sorted(
        df_all["County"].dropna().unique().tolist()
    )
    selected_county = st.sidebar.selectbox(
        "County", options=county_options, index=0
    )

    district_options = ["District (Any)"] + sorted(
        [str(d) for d in df_all["Dist"].dropna().unique()]
    )
    selected_district = st.sidebar.selectbox(
        "District", options=district_options, index=0
    )

    # Quantity Filters
    max_qty_dataset = (
        int(df_all["Quantity"].max()) if "Quantity" in df_all.columns else 100000
    )
    mnq = st.sidebar.number_input("Minimum Quantity (mnq)", min_value=0, value=0)
    mxq = st.sidebar.number_input(
        "Maximum Quantity (mxq)", min_value=0, value=max_qty_dataset
    )

    # 4. Filter Logic Implementation
    filtered_df = df_all[df_all["Pay Item #"] == selected_pay_code]

    if selected_county != "County (All)":
        filtered_df = filtered_df[filtered_df["County"] == selected_county]

    if selected_district != "District (Any)":
        # Supports both string and integer matching
        filtered_df = filtered_df[
            filtered_df["Dist"].astype(str) == selected_district
        ]

    if mxq > mnq:
        filtered_df = filtered_df[
            (filtered_df["Quantity"] >= mnq) & (filtered_df["Quantity"] <= mxq)
        ]

    # 5. Main UI Header
    st.title("IDOT Bid Item Report")
    st.markdown(
        f"### Current Pay Item: `{selected_pay_code}` — **{selected_desc}**"
    )

    # 6. Metrics & Calculation Block (Weighted Average Tool)
    if not filtered_df.empty:
        col1, col2, col3 = st.columns(3)

        # Safeguard: Drop rows where Quantity or Price might be empty/NaN to prevent math crashes
        math_df = filtered_df.dropna(subset=["Quantity", "Award Unit Price"])

        # Core math calculations using our clean data
        total_qty = math_df["Quantity"].sum()
        total_cost = (
            math_df["Quantity"] * math_df["Award Unit Price"]
        ).sum()
        weighted_avg = total_cost / total_qty if total_qty > 0 else 0
        unit_type = (
            filtered_df["Unit"].iloc[0]
            if "Unit" in filtered_df.columns
            else "Units"
        )

        with col1:
            st.metric(
                label="Weighted Average Price", value=f"${weighted_avg:,.2f}"
            )
        with col2:
            st.metric(
                label="Total Bidded Quantity", value=f"{total_qty:,} {unit_type}"
            )
        with col3:
            st.metric(
                label="Total Contracts Found", value=str(len(filtered_df))
            )

        st.markdown("---")

        # Price Sliders for Ad-hoc adjustment
        st.subheader("Interactive Price Filter & Analysis")
        min_p = float(filtered_df["Award Unit Price"].min())
        max_p = float(filtered_df["Award Unit Price"].max())

        if min_p != max_p:
            price_range = st.slider(
                "Adjust price range bounds:", min_p, max_p, (min_p, max_p)
            )
            final_df = filtered_df[
                (filtered_df["Award Unit Price"] >= price_range[0])
                & (filtered_df["Award Unit Price"] <= price_range[1])
            ]
        else:
            st.info(f"All items are identically priced at ${min_p}")
            final_df = filtered_df

        # 7. Data Visualization: Quantity vs Unit Price Plot
        st.subheader("Plot: Quantity vs Unit Price")

        # Safely determine hover features based on what columns exist in your file
        hover_features = [
            col for col in ["Contract", "Date", "Dist"] if col in final_df.columns
        ]

        fig = px.scatter(
            final_df,
            x="Quantity",
            y="Award Unit Price",
            color="County" if "County" in final_df.columns else None,
            hover_data=hover_features,
            size="Quantity",
            size_max=25,
            title=f"Price vs Volume Structure for Code {selected_pay_code}",
        )
        fig.update_layout(
            xaxis_title="Quantity", yaxis_title="Award Unit Price ($)"
        )
        st.plotly_chart(fig, use_container_width=True)

        # 8. Results Data Table View
        st.subheader("Bid Results Details Table")

        all_cols = final_df.columns.tolist()
        visible_cols = st.multiselect(
            "Show/Hide Columns", options=all_cols, default=all_cols
        )

        sort_col = "Date" if "Date" in final_df.columns else all_cols[0]
        st.dataframe(
            final_df[visible_cols].sort_values(by=sort_col, ascending=False),
            use_container_width=True,
        )

    else:
        st.warning(
            "No historical letting items matched your exact selection criteria. Try widening your filters."
        )
else:
    st.info("Awaiting structural loading from the Parquet sheet dataset.")

