import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# 1. Page Configuration
st.set_page_config(
    page_title="Openbidz - Open Source IDOT Cost Estimate Tool",
    layout="wide",
    initial_sidebar_state="expanded",
)


# 2. Parquet Data Loader
@st.cache_data
def load_parquet_data(file_path):  # <-- KEEP THIS EXACTLY AS "file_path"
    try:
        df = pd.read_parquet(file_path, engine="pyarrow")
        if "Pay Item #" in df.columns:
            df["Pay Item #"] = df["Pay Item #"].astype(str).str.strip()
        if "Pay Item Description" in df.columns:
            df["Pay Item Description"] = (
                df["Pay Item Description"].astype(str).str.strip()
            )
        return df
    except Exception as e:
        st.error(
            f"Error loading Parquet file '{file_path}': {e}. Please check the file path and name."
        )
        return pd.DataFrame()


# Load Data
PARQUET_FILE = "openbidzdata.parquet"
df_all = load_parquet_data(PARQUET_FILE)


# Only build the app if data successfully loaded
if not df_all.empty:

    # Extract unique mapping of items to preserve relationships
    df_unique_items = (
        df_all[["Pay Item #", "Pay Item Description"]].dropna().drop_duplicates()
    )

    # 3. Sidebar Filters
    st.sidebar.header("Filter Options")

    # Extended Search Bar supporting Code fragments or Keyword chunks
    search_query = st.sidebar.text_input(
        "🔍 Search Pay Items",
        placeholder="Type code or phrase (e.g., 501 or concrete)",
    )

    # Filter available options matching ANY fragment (OR logic)
    if search_query:
        # Case-insensitive substring query applied over Code and Text structures
        matched_items = df_unique_items[
            df_unique_items["Pay Item Description"].str.contains(
                search_query, case=False, na=False
            )
            | df_unique_items["Pay Item #"].str.contains(
                search_query, case=False, na=False
            )
        ]
    else:
        matched_items = df_unique_items

    # 4. Pay Item Selection Dropdown (Dynamically updated by partial match engine)
    if not matched_items.empty:
        # Generate user-friendly lookup tags
        matched_items["Dropdown Label"] = (
            matched_items["Pay Item #"] + " - " + matched_items["Pay Item Description"]
        )
        choice_options = sorted(matched_items["Dropdown Label"].tolist())

        selected_choice = st.sidebar.selectbox(
            "Select Matching Item", options=choice_options, index=0
        )

        # Safely split exact code back out using maximum array split constraints
        selected_pay_code = selected_choice.split(" - ", 1)[0]
        selected_desc = df_unique_items[
            df_unique_items["Pay Item #"] == selected_pay_code
        ]["Pay Item Description"].iloc[0]
    else:
        st.sidebar.error("❌ No pay item numbers or descriptions match your query.")
        selected_pay_code = None
        selected_desc = None

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

    # 5. Filter Logic Implementation
    if selected_pay_code:
        filtered_df = df_all[df_all["Pay Item #"] == selected_pay_code]

        if selected_county != "County (All)":
            filtered_df = filtered_df[filtered_df["County"] == selected_county]

        if selected_district != "District (Any)":
            filtered_df = filtered_df[
                filtered_df["Dist"].astype(str) == selected_district
            ]

        if mxq > mnq:
            filtered_df = filtered_df[
                (filtered_df["Quantity"] >= mnq) & (filtered_df["Quantity"] <= mxq)
            ]

        # 6. Main UI Header
        st.title("Openbidz - IDOT Bid Tab Analysis")
        st.markdown(
            f"### Current Pay Item: `{selected_pay_code}` — **{selected_desc}**"
        )

        # 7. Metrics & Calculation Block (Weighted Average Tool)
        if not filtered_df.empty:
            col1, col2, col3 = st.columns(3)

            math_df = filtered_df.dropna(subset=["Quantity", "Award Unit Price"])
            total_qty = math_df["Quantity"].sum()
            total_cost = (math_df["Quantity"] * math_df["Award Unit Price"]).sum()
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

            # 8. Data Visualization: Quantity vs Unit Price Plot
            st.subheader("Plot: Quantity vs Unit Price")
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
                template="plotly_white",
            )
            fig.update_layout(
                xaxis_title="Quantity", yaxis_title="Award Unit Price ($)"
            )
            st.plotly_chart(fig, use_container_width=True)

            # 9. Results Data Table View
            st.subheader("Bid Results Details Table")
            all_cols = final_df.columns.tolist()
            visible_cols = st.multiselect(
                "Show/Hide Columns", options=all_cols, default=all_cols
            )

            if not visible_cols:
                visible_cols = all_cols

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
        st.info(
            "Please clear or adjust your partial keyword search criteria in the sidebar to populate items."
        )
else:
    st.info("Awaiting structural loading from the Parquet sheet dataset.")
