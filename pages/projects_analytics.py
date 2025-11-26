"""
Project Analytics tab - compare multiple projects with budget analysis.
"""
import streamlit as st
import plotly.graph_objects as go


def render_project_analytics_tab(db, processor):
    """Render the Project Analytics tab with multi-project comparison."""
    projects_df = db.get_projects()

    if not projects_df.empty:
        # Project comparison
        st.markdown("#### Project Comparison")

        selected_projects = st.multiselect(
            "Select projects to compare",
            options=projects_df['name'].tolist(),
            default=projects_df['name'].tolist()[:5]
        )

        if selected_projects:
            comparison_df = projects_df[projects_df['name'].isin(selected_projects)].copy()

            # Budget comparison chart
            st.markdown("#### Budget Comparison")

            fig = go.Figure()
            fig.add_trace(go.Bar(
                name='Quoted Value',
                x=comparison_df['name'],
                y=comparison_df['quoted_value']
            ))
            fig.add_trace(go.Bar(
                name='Awarded Value',
                x=comparison_df['name'],
                y=comparison_df['awarded_value']
            ))
            fig.add_trace(go.Bar(
                name='Accrued to Date',
                x=comparison_df['name'],
                y=comparison_df['budget_used']
            ))
            fig.update_layout(
                title="Quoted vs Awarded vs Accrued Amount",
                barmode='group',
                height=400
            )
            st.plotly_chart(fig, width='stretch')
    else:
        st.info("No projects available for analysis")
