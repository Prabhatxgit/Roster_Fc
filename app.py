import streamlit as st
import pandas as pd
import plotly.express as px
import os
from roster_engine import load_and_analyze_data, generate_roster

# Page Configuration
st.set_page_config(
    page_title="Inbound Roster AI",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Look
st.markdown("""
    <style>
    /* Main Background */
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
        color: #e2e8f0;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #0f172a;
        border-right: 1px solid #334155;
    }
    
    /* Metrics */
    div[data-testid="metric-container"] {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        padding: 15px;
        backdrop-filter: blur(10px);
    }
    
    /* Headers */
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
        color: #f8fafc;
        font-weight: 600;
    }
    
    h1 {
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    /* Dataframe */
    .stDataFrame {
         border: 1px solid #334155;
         border-radius: 10px;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(90deg, #38bdf8, #818cf8);
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: all 0.2s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    
    </style>
    """, unsafe_allow_html=True)

# Helper Function to Load/Generate Data
# Cache must be handled carefully with uploader. We'll use session state or simple caching on the generator.
@st.cache_data(show_spinner=True)
def cached_generate_roster(file_source):
    df, dna = load_and_analyze_data(file_source)
    if df is None:
        return None, dna # dna contains error msg here
        
    roster_df, err = generate_roster(dna)
    return roster_df, err

# Header
st.title("Inbound AI Roster Manager")
st.markdown("### Smart Workforce Scheduling for March 2026")

# Sidebar - Configuration & Upload
st.sidebar.title("Configuration")

uploaded_file = st.sidebar.file_uploader("Upload Roster Data (Excel/CSV)", type=['xlsx', 'xls', 'csv'])

# Data Logic
roster_df = None
error_msg = None

try:
    if uploaded_file is not None:
        # Use uploaded file
        roster_df, error_msg = cached_generate_roster(uploaded_file)
    else:
        # Check for default file
        default_file = "Inbound Rooster.xlsx"
        if os.path.exists(default_file):
            roster_df, error_msg = cached_generate_roster(default_file)
        else:
            st.info("👋 Welcome! Please upload your 'Inbound Rooster' Excel/CSV file to get started.")
            
    if error_msg:
        st.error(f"Generation Failed: {error_msg}")

except Exception as e:
    st.error(f"An unexpected error occurred: {e}")


# Main App Display
if roster_df is not None:
    # Sidebar - Absence Manager (Only show if data is loaded)
    st.sidebar.markdown("---")
    st.sidebar.title("Absence Manager")
    st.sidebar.markdown("Find the best replacement for an absent employee.")
    
    # 1. Select Date
    # Get date columns from roster_df (exclude metadata)
    metadata_cols = ['Employee ID', 'Name', 'Dept', 'Status', 'Shift DNA', 'Total Shifts', 'Total_Work_Hours']
    date_cols = [c for c in roster_df.columns if c not in metadata_cols]
    
    selected_date = st.sidebar.selectbox("Select Date", date_cols)
    
    # 2. Select Employee (who is absent)
    # Filter only employees who are working on that day (Day or Night)
    working_on_date = roster_df[roster_df[selected_date].isin(['Day', 'Night'])]
    selected_emp_name = st.sidebar.selectbox("Absent Employee", working_on_date['Name'].unique())
    
    # Find Replacement Logic
    if st.sidebar.button("Find Replacement"):
        # Get Absent Employee Details
        absent_emp_row = roster_df[roster_df['Name'] == selected_emp_name].iloc[0]
        absent_shift = absent_emp_row[selected_date]
        
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Request:** Replace **{selected_emp_name}** ({absent_shift}) on **{selected_date}**")
        
        # Candidate Logic
        # 1. Must be on WO this day
        candidates = roster_df[roster_df[selected_date] == 'WO'].copy()
        
        # 2. DNA Match
        # If absent_shift is 'Night', Candidate cannot be 'Fixed_Day'
        # If absent_shift is 'Day', Candidate cannot be 'Fixed_Night'
        if absent_shift == 'Night':
            candidates = candidates[candidates['Shift DNA'] != 'Fixed_Day']
        elif absent_shift == 'Day':
            candidates = candidates[candidates['Shift DNA'] != 'Fixed_Night']
            
        # 3. Sort by Total Shifts (Fairness - lowest first)
        candidates = candidates.sort_values(by='Total Shifts', ascending=True)
        
        if not candidates.empty:
            best_fit = candidates.iloc[0]
            st.sidebar.success(f"**Best Fit:** {best_fit['Name']}")
            st.sidebar.info(f"Shift DNA: {best_fit['Shift DNA']}")
            st.sidebar.info(f"Total Shifts: {best_fit['Total Shifts']}")
            
            # Show top 5
            st.sidebar.markdown("#### Top Alternatives")
            st.sidebar.dataframe(candidates[['Name', 'Shift DNA', 'Total Shifts']].head(5), hide_index=True)
        else:
            st.sidebar.error("No suitable replacement found!")

    # Main Dashboard
    
    # Tabs
    tab1, tab2 = st.tabs(["📋 Roster View", "📊 Analytics"])
    
    # Define Styling Function (Shared for UI and Excel)
    def color_roster(val):
        # Colors: 
        # WO -> Red (#ff4b4b)
        # Day -> Yellow (#facc15)
        # Night -> Steel (#94a3b8)
        val_str = str(val).strip()
        if val_str == 'WO':
            return 'background-color: #ff4b4b; color: white; font-weight: bold;'
        elif val_str == 'Day':
            return 'background-color: #facc15; color: black; font-weight: bold;'
        elif val_str == 'Night':
            return 'background-color: #94a3b8; color: white; font-weight: bold;'
        return ''

    with tab1:
        # Search/Filter
        col1, col2 = st.columns([2, 1])
        with col1:
            search_term = st.text_input("Search Employee (ID or Name)")
        with col2:
            shift_filter = st.multiselect("Filter by Shift DNA", roster_df['Shift DNA'].unique(), default=roster_df['Shift DNA'].unique())
            
        # Apply Filters
        display_df = roster_df.copy()
        if search_term:
            display_df = display_df[
                display_df['Name'].str.contains(search_term, case=False) | 
                display_df['Employee ID'].astype(str).str.contains(search_term)
            ]
        
        if shift_filter:
            display_df = display_df[display_df['Shift DNA'].isin(shift_filter)]
            
        # Apply to date columns only
        styled_df = display_df.style.map(color_roster, subset=date_cols)
        
        st.dataframe(styled_df, use_container_width=True, height=600)
        
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                "Download Roster CSV",
                roster_df.to_csv(index=False).encode('utf-8'),
                "March_2026_Roster.csv",
                "text/csv",
                key='download-csv'
            )
        
        with col_dl2:
            import io
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                # Apply styling to the full roster_df before exporting
                roster_df.style.map(color_roster, subset=date_cols).to_excel(writer, index=False, sheet_name='Sheet1')
                
            st.download_button(
                label="Download Roster Excel",
                data=buffer.getvalue(),
                file_name="March_2026_Roster.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key='download-excel'
            )
        
    with tab2:
        st.markdown("### Workforce Balance & Fairness")
        
        # 1. Balance Chart
        # Histogram of Total Shifts
        fig = px.histogram(roster_df, x='Total Shifts', nbins=10, 
                           title="Distribution of Workload (Total Shifts)",
                           color_discrete_sequence=['#818cf8'])
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white")
        st.plotly_chart(fig, use_container_width=True)
        
        # 2. Shift Type Breakdown
        col1, col2 = st.columns(2)
        with col1:
            dna_counts = roster_df['Shift DNA'].value_counts().reset_index()
            dna_counts.columns = ['Shift DNA', 'Count']
            fig2 = px.pie(dna_counts, values='Count', names='Shift DNA', title="Shift DNA Distribution",
                          color_discrete_sequence=px.colors.sequential.Bluyl)
            fig2.update_layout(paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig2, use_container_width=True)
            
        with col2:
            # Average Shifts by DNA
            avg_shifts = roster_df.groupby('Shift DNA')['Total Shifts'].mean().reset_index()
            fig3 = px.bar(avg_shifts, x='Shift DNA', y='Total Shifts', title="Avg Shifts by DNA Type",
                          color='Shift DNA', color_discrete_sequence=px.colors.sequential.Bluyl)
            fig3.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig3, use_container_width=True)
