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

    # Search Bar supporting Code fragments or non-consecutive Keyword chunks
    search_query = st.sidebar.text_input(
        "🔍 Search Pay Items",
        placeholder="Type keywords (e.g., concrete pipe)",
    ).strip()

    # Advanced Non-Consecutive Multi-Word Filter Engine
    if search_query:
        # Split search query into individual lowercase word tokens
        search_words = search_query.split()
        
        # Start with all unique items
        matched_items = df_unique_items.copy()
        
        # Iteratively filter down: every single keyword typed must match either the code or description
        for word in search_words:
            matched_items = matched_items[
                matched_items["Pay Item Description"].str.contains(word, case=False, na=False) |
                matched_items["Pay Item #"].str.contains(word, case=False, na=False)
            ]
    else:
        matched_items = df_unique_items.copy()

    # 4. Pay Item Selection Dropdown
    if not matched_items.empty:
        # Create a clean label format: "CODE - DESCRIPTION"
        matched_items["Dropdown Label"] = (
            matched_items["Pay Item #"] + " - " + matched_items["Pay Item Description"]
        )
        choice_options = sorted(matched_items["Dropdown Label"].tolist())

        selected_choice = st.sidebar.selectbox(
            "Select Matching Item", options=choice_options, index=0
        )

        # Extract EXACTLY the code string by targeting index 0
        selected_pay_code = selected_choice.split(" - ", 1)[0]
        
        # Grab description safely
        desc_series = df_unique_items[df_unique_items["Pay Item #"] == selected_pay_code]["Pay Item Description"]
        selected_desc = desc_series.iloc[0] if not desc_series.empty else "No description available"
        
        # UI Help: Show user how many partial matches were found
        st.sidebar.caption(f"Found {len(matched_items)} matching items.")
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

    # 5. Filter Logic Implementation (Sidebar level parameters)
    if selected_pay_code:
        # Pre-filter by pay code, county, and district to find the exact quantity bounds for this subset
        filtered_df = df_all[df_all["Pay Item #"] == selected_pay_code]

        if selected_county != "County (All)":
            filtered_df = filtered_df[filtered_df["County"] == selected_county]

        if selected_district != "District (Any)":
            filtered_df = filtered_df[
                filtered_df["Dist"].astype(str) == selected_district
            ]

        # 6. Main UI Header
        st.title("Openbidz - IDOT Bid Tab Analysis")
        st.markdown(
            f"### Current Pay Item: `{selected_pay_code}` — **{selected_desc}**"
        )

        if not filtered_df.empty:
            # 7. Interactive QUANTITY Slider Section (Replaced Price Slider)
            st.subheader("Interactive Quantity Filter & Analysis")
            
            # Determine dynamic boundaries strictly based on the filtered item subset
            min_qty_dataset = int(filtered_df["Quantity"].min()) if "Quantity" in filtered_df.columns else 0
            max_qty_dataset = int(filtered_df["Quantity"].max()) if "Quantity" in filtered_df.columns else 100000

            if min_qty_dataset != max_qty_dataset:
                # Main page slider acts as the master quantity boundary tool
                quantity_range = st.slider(
                    "Adjust quantity range bounds:", 
                    min_value=min_qty_dataset, 
                    max_value=max_qty_dataset, 
                    value=(min_qty_dataset, max_qty_dataset)
                )
                
                # Apply the active slider limits to form final_df
                final_df = filtered_df[
                    (filtered_df["Quantity"] >= quantity_range[0])
                    & (filtered_df["Quantity"] <= quantity_range[1])
                ].copy()
                
                # Dynamically sync boundaries back to sidebar fields for readability
                st.sidebar.markdown("---")
                st.sidebar.markdown("### Active Quantity Boundaries")
                st.sidebar.info(f"**Minimum:** {quantity_range[0]:,}")
                st.sidebar.info(f"**Maximum:** {quantity_range[1]:,}")
            else:
                unit_type = filtered_df["Unit"].iloc[0] if "Unit" in filtered_df.columns else "Units"
                st.info(f"All matching items have an identical quantity volume of {min_qty_dataset:,} {unit_type}")
                final_df = filtered_df.copy()

            st.markdown("---")

            # 8. Dynamic Metrics Calculation Block (Uses final_df now filtered by quantity)
            if not final_df.empty:
                col1, col2, col3 = st.columns(3)

                # Safeguard: Drop empty values specifically from the filtered data
                math_df = final_df.dropna(subset=["Quantity", "Award Unit Price"])
                
                total_qty = math_df["Quantity"].sum()
                total_cost = (math_df["Quantity"] * math_df["Award Unit Price"]).sum()
                
                # Dynamic calculations based on active quantity boundaries
                weighted_avg = total_cost / total_qty if total_qty > 0 else 0
                avg_qty = math_df["Quantity"].mean() if len(math_df) > 0 else 0
                
                unit_type = (
                    final_df["Unit"].iloc[0]
                    if "Unit" in final_df.columns
                    else "Units"
                )

                with col1:
                    st.metric(
                        label="Weighted Average Price", value=f"${weighted_avg:,.2f}"
                    )
                with col2:
                    st.metric(
                        label="Average Bid Quantity", value=f"{avg_qty:,.1f} {unit_type}"
                    )
                with col3:
                    st.metric(
                        label="Total Contracts Found", value=str(len(final_df))
                    )
                
                st.markdown("---")

                # 9. Data Visualization: Quantity vs Unit Price Plot
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

                # 10. Results Data Table View
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
                st.warning("No contracts fit inside the custom quantity range boundaries you've chosen above.")
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
