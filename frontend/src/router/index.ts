import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'overview',
      component: () => import('@/views/OverviewView.vue'),
      meta: { title: 'Overview Dashboard' },
    },
    {
      path: '/projects',
      name: 'projects',
      component: () => import('@/views/projects/ProjectsListView.vue'),
      meta: { title: 'Projects' },
    },
    {
      path: '/projects/:id',
      component: () => import('@/views/projects/ProjectDetailView.vue'),
      meta: { title: 'Project Detail' },
      children: [
        {
          path: '',
          name: 'project-detail',
          redirect: (to) => {
            // Ensure path ends without trailing slash before appending
            const base = to.path.replace(/\/$/, '')
            return { path: `${base}/overview` }
          },
        },
        {
          path: 'overview',
          name: 'project-overview',
          component: () => import('@/views/projects/tabs/ProjectOverviewTab.vue'),
        },
        {
          path: 'performance',
          name: 'project-performance',
          component: () => import('@/views/projects/tabs/ProjectPerformanceTab.vue'),
        },
        {
          path: 'team',
          name: 'project-team',
          component: () => import('@/views/projects/tabs/ProjectTeamTab.vue'),
        },
        {
          path: 'budget',
          name: 'project-budget',
          component: () => import('@/views/projects/tabs/ProjectBudgetTab.vue'),
        },
        {
          path: 'planner',
          name: 'project-planner',
          component: () => import('@/views/projects/tabs/ProjectAllocationPlannerTab.vue'),
        },
        {
          path: 'timeline',
          name: 'project-timeline',
          component: () => import('@/views/projects/tabs/ProjectTimelineTab.vue'),
        },
        {
          path: 'review',
          name: 'project-review',
          component: () => import('@/views/projects/tabs/ProjectReviewTab.vue'),
        },
        {
          path: 'analytics',
          name: 'project-analytics',
          component: () => import('@/views/projects/tabs/ProjectAnalyticsTab.vue'),
        },
        {
          path: 'edit',
          name: 'project-edit',
          component: () => import('@/views/projects/tabs/ProjectEditTab.vue'),
        },
      ],
    },
    {
      path: '/employees',
      component: () => import('@/views/employees/EmployeesPage.vue'),
      meta: { title: 'Employees' },
      children: [
        {
          path: '',
          name: 'employees',
          component: () => import('@/views/employees/EmployeesListView.vue'),
        },
        {
          path: 'allocation_overview',
          name: 'employees-allocation',
          component: () => import('@/views/employees/AllocationOverviewView.vue'),
        },
        {
          path: 'utilization_overview',
          name: 'employees-utilization',
          component: () => import('@/views/employees/UtilizationOverviewView.vue'),
        },
      ],
    },
    {
      path: '/employees/:id',
      component: () => import('@/views/employees/EmployeeDetailView.vue'),
      meta: { title: 'Employee Detail' },
      children: [
        {
          path: '',
          name: 'employee-detail',
          redirect: (to) => {
            const base = to.path.replace(/\/$/, '')
            return { path: `${base}/allocation` }
          },
        },
        {
          path: 'details',
          name: 'employee-details',
          component: () => import('@/views/employees/tabs/EmployeeDetailsTab.vue'),
        },
        {
          path: 'allocation',
          name: 'employee-allocation',
          component: () => import('@/views/employees/tabs/EmployeeAllocationTab.vue'),
        },
        {
          path: 'utilization',
          name: 'employee-utilization',
          component: () => import('@/views/employees/tabs/EmployeeUtilizationTab.vue'),
        },
      ],
    },
    {
      path: '/timesheets',
      name: 'timesheets',
      component: () => import('@/views/TimesheetsView.vue'),
      meta: { title: 'Timesheets' },
    },
    {
      path: '/utilization',
      name: 'utilization',
      component: () => import('@/views/UtilizationView.vue'),
      meta: { title: 'Utilization' },
    },
    {
      path: '/financial',
      name: 'financial',
      component: () => import('@/views/FinancialView.vue'),
      meta: { title: 'Financial Analysis' },
    },
    {
      path: '/reports',
      name: 'reports',
      component: () => import('@/views/ReportsView.vue'),
      meta: { title: 'Reports' },
    },
    {
      path: '/months',
      name: 'months',
      component: () => import('@/views/MonthsView.vue'),
      meta: { title: 'Months' },
    },
    {
      path: '/data-management',
      name: 'data-management',
      component: () => import('@/views/DataManagementView.vue'),
      meta: { title: 'Data Management' },
    },
    {
      path: '/what-if',
      name: 'what-if',
      component: () => import('@/views/WhatIfView.vue'),
      meta: { title: 'What-If Scenarios' },
    },
    {
      path: '/budget-mockup',
      name: 'budget-mockup',
      component: () => import('@/views/BudgetMockupView.vue'),
      meta: { title: 'Budget Mockup' },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      redirect: '/',
    },
  ],
})

router.beforeEach((to) => {
  const title = (to.meta.title as string) || 'Project Dashboard'
  document.title = `${title} | Project Dashboard`
})

export default router
