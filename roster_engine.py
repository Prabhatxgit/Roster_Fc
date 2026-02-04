import pandas as pd
from ortools.sat.python import cp_model
import datetime
import calendar

def load_and_analyze_data(file_source):
    """
    Loads the roster data and determines the Shift DNA for each employee.
    Accepts a file path (str) or a file-like object.
    """
    try:
        # Load data - check if it's a string (path) or object
        if isinstance(file_source, str):
            if file_source.endswith('.csv'):
                 df = pd.read_csv(file_source)
            else:
                 df = pd.read_excel(file_source)
        else:
            # File-like object (Streamlit uploader)
            # Try excel first, then csv
            # We can rely on the uploaded file name to guess, but st.file_uploader returns a BytesIO with a .name attribute
            if hasattr(file_source, 'name') and file_source.name.endswith('.csv'):
                df = pd.read_csv(file_source)
            else:
                df = pd.read_excel(file_source)
                
    except Exception as e:
        return None, f"Error loading file: {e}"

    # Metadata columns as per prompt
    metadata_cols = ['Employee ID', 'User ID', 'NAME', 'Status', 'Department']
    
    # Identify date columns (columns that are not metadata and not 'Unnamed' or 'Remarks')
    date_cols = []
    for col in df.columns:
        if col not in metadata_cols and not str(col).startswith("Unnamed") and col != "Remarks":
            date_cols.append(col)
            
    employee_dna = {}
    
    for _, row in df.iterrows():
        emp_id = row['Employee ID']
        name = row['NAME']
        
        day_count = 0
        night_count = 0
        
        for col in date_cols:
            val = str(row[col]).strip().upper()
            if val == 'DAY':
                day_count += 1
            elif val == 'NIGHT':
                night_count += 1
        
        # Determine DNA
        if day_count > 0 and night_count == 0:
            dna = 'Fixed_Day'
        elif night_count > 0 and day_count == 0:
            dna = 'Fixed_Night'
        else:
            # If mixed or no data (e.g. new joiner or all WO), default to Rotating
            # Prompt: "If they have both... tag them as Rotating"
            dna = 'Rotating' 
            
        employee_dna[emp_id] = {
            'Name': name,
            'DNA': dna,
            'Day_Count': day_count,
            'Night_Count': night_count,
            'Status': row['Status'],
            'Department': row['Department']
        }
        
    return df, employee_dna

def generate_roster(employee_dna, year=2026, month=3):
    """
    Generates a roster for the given month using OR-Tools.
    """
    model = cp_model.CpModel()
    
    # 1. Define Dates and Structure
    num_days = calendar.monthrange(year, month)[1]
    dates = [datetime.date(year, month, day) for day in range(1, num_days + 1)]
    days_indices = range(num_days)
    
    employees = list(employee_dna.keys())
    emp_indices = range(len(employees))
    
    # Shifts: 0: WO, 1: Day, 2: Night
    shifts = [0, 1, 2] # WO, Day, Night
    
    # Variables: roster[(e, d)] = shift
    roster = {}
    for e in emp_indices:
        for d in days_indices:
            roster[(e, d)] = model.NewIntVar(0, 2, f'shift_e{e}_d{d}')
            
    # 2. Hard Constraints
    
    # DNA Constraints
    for e in emp_indices:
        emp_id = employees[e]
        dna = employee_dna[emp_id]['DNA']
        
        for d in days_indices:
            if dna == 'Fixed_Day':
                # Cannot be Night (2)
                model.Add(roster[(e, d)] != 2)
            elif dna == 'Fixed_Night':
                # Cannot be Day (1)
                model.Add(roster[(e, d)] != 1)
                
    # Weekly Offs: Exactly 2 WOs per week (Sunday to Saturday)
    # Identify weeks in March 2026
    # March 1, 2026 is a Sunday. 
    # Weeks: 
    # 1: Mar 1 - Mar 7 (Sun-Sat)
    # 2: Mar 8 - Mar 14
    # 3: Mar 15 - Mar 21
    # 4: Mar 22 - Mar 28
    # 5: Mar 29 - Mar 31 (Partial week) - Handling partial weeks? 
    # Prompt says: "Within any single Sunday–Saturday week... Each employee must be assigned exactly 2 'WO' days per week"
    # For the last partial week (3 days), forcing 2 WOs might be too strict or wrong. 
    # Standard logic: Pro-rate or just apply loosely. OR-Tools handles this. 
    # Let's apply 2 WOs for full weeks. For partial, let's relax or ensure at least 0-1 depending on length.
    # Actually, March 29(Sun), 30(Mon), 31(Tue). That's 3 days. 
    # If we force 2 WOs in 3 days, they only work 1 day. Acceptable? Maybe.
    # Let's stick to strict 2 WOs for full 7-day weeks. For the partial week, maybe 1 WO?
    # Let's calculate weeks dynamically.
    
    current_date = dates[0]
    # Find start of the first week (Sunday). dates[0] is March 1, 2026, which IS a Sunday.
    # So weeks are aligned perfectly from day 0.
    
    # Group indices by week
    weeks = []
    current_week = []
    for d in days_indices:
        current_week.append(d)
        # Check if next day is Sunday (i.e. if current day is Saturday)
        # weekday(): Mon=0, Sun=6. But here we want Sun-Sat week.
        # dates[d].weekday() -> Sun=6, Mon=0... Sat=5.
        if dates[d].weekday() == 5: # Saturday
            weeks.append(current_week)
            current_week = []
            
    if current_week:
        weeks.append(current_week)
        
    for w_idx, week_days in enumerate(weeks):
        for e in emp_indices:
            # Count WOs (shift == 0)
            is_wo = [model.NewBoolVar(f'is_wo_e{e}_d{d}') for d in week_days]
            for i, d in enumerate(week_days):
                model.Add(roster[(e, d)] == 0).OnlyEnforceIf(is_wo[i])
                model.Add(roster[(e, d)] != 0).OnlyEnforceIf(is_wo[i].Not())
            
            if len(week_days) == 7:
                model.Add(sum(is_wo) == 2)
            else:
                # Partial week logic (Mar 29-31, 3 days). 
                # Let's say at least 0 WOs, max 1 WO? Or just leave unconstrained for soft optimization?
                # User said "Each employee must be assigned exactly 2 'WO' days per week."
                # I will assume this applies to full weeks. For < 7 days, I'll allow 0-2.
                model.Add(sum(is_wo) <= 2) 

    # Shift Lock: Within a Sunday-Saturday week, employee cannot mix Day (1) and Night (2).
    # sum(Day) > 0 => sum(Night) == 0
    for week_days in weeks:
        for e in emp_indices:
            has_day = model.NewBoolVar(f'has_day_e{e}_w{week_days[0]}')
            has_night = model.NewBoolVar(f'has_night_e{e}_w{week_days[0]}')
            
            # Indicator variables for day/night presence in the week
            day_vars = []
            night_vars = []
            for d in week_days:
                is_day = model.NewBoolVar(f'is_day_e{e}_d{d}')
                is_night = model.NewBoolVar(f'is_night_e{e}_d{d}')
                
                model.Add(roster[(e, d)] == 1).OnlyEnforceIf(is_day)
                model.Add(roster[(e, d)] != 1).OnlyEnforceIf(is_day.Not())
                
                model.Add(roster[(e, d)] == 2).OnlyEnforceIf(is_night)
                model.Add(roster[(e, d)] != 2).OnlyEnforceIf(is_night.Not())
                
                day_vars.append(is_day)
                night_vars.append(is_night)
                
            # Link has_day / has_night to individual days
            model.AddMaxEquality(has_day, day_vars)
            model.AddMaxEquality(has_night, night_vars)
            
            # Constraint: Cannot have both
            # has_day + has_night <= 1
            model.Add(has_day + has_night <= 1)

    # 3. Soft Constraints (Objectives)
    # Equitable Distribution: Balanced total Day and Night shifts across employees.
    # We want to minimize the variance or difference from the mean.
    # Linearizing variance is hard. We can minimize the range (Max - Min).
    
    total_days = [model.NewIntVar(0, num_days, f'total_days_e{e}') for e in emp_indices]
    total_nights = [model.NewIntVar(0, num_days, f'total_nights_e{e}') for e in emp_indices]
    
    for e in emp_indices:
        d_vars = []
        n_vars = []
        for d in days_indices:
            is_d = model.NewBoolVar(f'obj_is_d_e{e}_d{d}')
            is_n = model.NewBoolVar(f'obj_is_n_e{e}_d{d}')
            model.Add(roster[(e, d)] == 1).OnlyEnforceIf(is_d)
            model.Add(roster[(e, d)] != 1).OnlyEnforceIf(is_d.Not())
            model.Add(roster[(e, d)] == 2).OnlyEnforceIf(is_n)
            model.Add(roster[(e, d)] != 2).OnlyEnforceIf(is_n.Not())
            d_vars.append(is_d)
            n_vars.append(is_n)
        
        model.Add(total_days[e] == sum(d_vars))
        model.Add(total_nights[e] == sum(n_vars))

    # Minimize spread of total workings shifts (Day + Night)
    total_work = [model.NewIntVar(0, num_days, f'total_work_e{e}') for e in emp_indices]
    for e in emp_indices:
        model.Add(total_work[e] == total_days[e] + total_nights[e])
        
    min_work = model.NewIntVar(0, num_days, 'min_work')
    max_work = model.NewIntVar(0, num_days, 'max_work')
    model.AddMinEquality(min_work, total_work)
    model.AddMaxEquality(max_work, total_work)
    
    # We also want to balance Day/Night specific assignments if possible, 
    # but Total Work balance is the primary "burnout" prevention.
    model.Minimize(max_work - min_work)
    
    # Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30.0
    status = solver.Solve(model)
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Build Result DataFrame
        data = []
        shift_map = {0: 'WO', 1: 'Day', 2: 'Night'}
        
        for e in emp_indices:
            row = {
                'Employee ID': employees[e],
                'Name': employee_dna[employees[e]]['Name'],
                'Dept': employee_dna[employees[e]]['Department'],
                'Status': employee_dna[employees[e]]['Status'],
                'Shift DNA': employee_dna[employees[e]]['DNA']
            }
            for d in days_indices:
                s_val = solver.Value(roster[(e, d)])
                row[str(dates[d])] = shift_map[s_val]
            
            # Add counts
            t_d = solver.Value(total_days[e])
            t_n = solver.Value(total_nights[e])
            row['Total_Work_Hours'] = (t_d + t_n) * 9 # Assuming 9h shift, or just count. Using Count for now.
            row['Total Shifts'] = t_d + t_n
            data.append(row)
            
        result_df = pd.DataFrame(data)
        return result_df, None
    else:
        return None, "No feasible roster found. Constraints might be too strict."

if __name__ == "__main__":
    df, dna = load_and_analyze_data("Inbound Rooster.xlsx")
    
    if df is not None:
        print(f"Loaded DNA for {len(dna)} employees.")
        print("Generating Roster for March 2026...")
        roster_df, err = generate_roster(dna)
        if roster_df is not None:
            print("Roster Generated Successfully!")
            print(roster_df.head())
            roster_df.to_csv("March_2026_Roster.csv", index=False)
        else:
            print(f"Failed: {err}")
    else:
        # dna contains the error message in this case
        print(f"Failed to load data: {dna}")
