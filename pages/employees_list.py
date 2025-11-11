"""
Employee List tab - displays all employees in table or card view.
"""
import streamlit as st
import pandas as pd


def render_employee_list_tab(db, processor):
    """Render the Employee List tab with table and card views."""
    st.markdown("#### Employee List")

    employees_df = db.get_employees()

    if not employees_df.empty:
        # Display options
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("#### All Employees")
        with col2:
            view_mode = st.selectbox("View", ["Table", "Cards"], label_visibility="collapsed")

        if view_mode == "Table":
            # Table view - no filters, just display all data
            # The dataframe itself has built-in sorting and filtering
            display_df = employees_df.copy()

            st.dataframe(display_df, width='stretch', hide_index=True)

        else:
            # Card view with role filter only
            role_filter = st.selectbox("Filter by Role", ["All"] + sorted(employees_df['role'].dropna().unique().tolist()), key="card_role_filter")

            # Apply filter
            filtered_df = employees_df.copy()
            if role_filter != "All":
                filtered_df = filtered_df[filtered_df['role'] == role_filter]

            # Sort by name
            filtered_df = filtered_df.sort_values('name')

            # Display cards
            cols = st.columns(3)
            for idx, (_, emp) in enumerate(filtered_df.iterrows()):
                with cols[idx % 3]:
                    with st.container():
                        st.markdown(f"### 👤 {emp['name']}")
                        st.write(f"**Role:** {emp['role'] if pd.notna(emp['role']) else 'N/A'}")
                        st.write(f"**Hire Date:** {emp['hire_date'] if pd.notna(emp['hire_date']) else 'N/A'}")

                        if pd.notna(emp.get('skills')) and emp['skills']:
                            st.write(f"**Skills:** {emp['skills']}")

                        # Show current allocations with FTE
                        allocations = db.get_allocations(employee_id=emp['id'])
                        if not allocations.empty:
                            total_fte = allocations['allocated_fte'].sum() if 'allocated_fte' in allocations.columns else 0
                            st.write(f"**Total FTE:** {total_fte:.2f}")

                            with st.expander("Current Projects"):
                                for _, alloc in allocations.iterrows():
                                    fte = alloc.get('allocated_fte', 0)
                                    st.write(f"• {alloc['project_name']} ({fte * 100:.0f}%)")

                        st.markdown("---")
    else:
        st.info("No employees found")
