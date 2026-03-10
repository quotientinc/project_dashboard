<script setup lang="ts">
import { ref, inject, watch, type Ref } from 'vue'
import { useApi } from '@/composables/useApi'
import type { Employee, EmployeeUpdate } from '@/types'

const { put, error } = useApi()

const employee = inject<Ref<Employee | null>>('employee', ref(null))

// Form state
const form = ref<EmployeeUpdate>({})
const formValid = ref(false)
const snackbar = ref(false)
const snackbarText = ref('')
const snackbarColor = ref('success')
const saving = ref(false)

// Skills options
const skillsOptions = [
  'jr. developer',
  'sr. developer',
  'sr. consultant',
  'technical SME',
  'project lead',
  'project manager',
  'scheduler',
]

const selectedSkills = ref<string[]>([])

// Pay type options
const payTypeOptions = ['Hourly', 'Salary']

// Initialize form from employee data
function initForm(emp: Employee) {
  form.value = {
    name: emp.name,
    role: emp.role ?? '',
    skills: emp.skills ?? '',
    hire_date: emp.hire_date ?? undefined,
    term_date: emp.term_date ?? undefined,
    pay_type: emp.pay_type ?? 'Hourly',
    cost_rate: emp.cost_rate ?? 0,
    annual_salary: emp.annual_salary ?? 0,
    pto_accrual: emp.pto_accrual ?? 120,
    holidays: emp.holidays ?? 0,
    billable: emp.billable ?? 0,
    overhead_allocation: emp.overhead_allocation ?? 0,
    target_allocation: emp.target_allocation ?? 0.3,
  }

  // Parse skills
  if (emp.skills) {
    selectedSkills.value = emp.skills.split(',').map((s) => s.trim()).filter(Boolean)
  } else {
    selectedSkills.value = []
  }
}

watch(
  employee,
  (emp) => {
    if (emp) initForm(emp)
  },
  { immediate: true }
)

// Sync selected skills to form
watch(selectedSkills, (skills) => {
  form.value.skills = skills.join(', ')
})

// Computed calculated rate for salary employees
function calculatedHourlyRate(): string {
  if (form.value.pay_type === 'Salary' && form.value.annual_salary && form.value.annual_salary > 0) {
    return '$' + (form.value.annual_salary / 2080).toFixed(2) + '/hour'
  }
  return '-'
}

// Save employee
async function saveEmployee() {
  if (!employee.value) return

  saving.value = true
  try {
    const updates: EmployeeUpdate = { ...form.value }

    // For salary employees, compute cost_rate from annual salary
    if (updates.pay_type === 'Salary' && updates.annual_salary && updates.annual_salary > 0) {
      updates.cost_rate = updates.annual_salary / 2080
    }

    // Clear annual salary for hourly employees
    if (updates.pay_type === 'Hourly') {
      updates.annual_salary = undefined
    }

    const updated = await put<Employee>(`/employees/${employee.value.id}`, updates)
    employee.value = updated
    snackbarText.value = 'Employee updated successfully'
    snackbarColor.value = 'success'
    snackbar.value = true
  } catch (err) {
    snackbarText.value = error.value || 'Failed to update employee'
    snackbarColor.value = 'error'
    snackbar.value = true
  } finally {
    saving.value = false
  }
}

// Cancel / reset form
function cancelEdit() {
  if (employee.value) {
    initForm(employee.value)
  }
}

// Validation rules
const requiredRule = [(v: string) => !!v || 'Required']
const positiveNumberRule = [(v: number) => v >= 0 || 'Must be 0 or greater']
</script>

<template>
  <div>
    <v-form v-model="formValid" @submit.prevent="saveEmployee">
      <v-row>
        <!-- Basic Information -->
        <v-col cols="12">
          <v-card>
            <v-card-title class="text-subtitle-1 font-weight-bold">
              <v-icon class="mr-2" size="small">mdi-account</v-icon>
              Basic Information
            </v-card-title>
            <v-card-text>
              <v-row>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="form.name"
                    label="Name *"
                    :rules="requiredRule"
                    density="compact"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="form.role"
                    label="Role"
                    density="compact"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="form.hire_date"
                    label="Hire Date"
                    type="date"
                    density="compact"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model="form.term_date"
                    label="Term Date"
                    type="date"
                    density="compact"
                    hint="Leave empty if employee is active"
                    persistent-hint
                  />
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Compensation -->
        <v-col cols="12">
          <v-card>
            <v-card-title class="text-subtitle-1 font-weight-bold">
              <v-icon class="mr-2" size="small">mdi-currency-usd</v-icon>
              Compensation
            </v-card-title>
            <v-card-text>
              <v-row>
                <v-col cols="12" md="4">
                  <v-select
                    v-model="form.pay_type"
                    label="Pay Type"
                    :items="payTypeOptions"
                    density="compact"
                  />
                </v-col>
                <v-col cols="12" md="4" v-if="form.pay_type === 'Hourly'">
                  <v-text-field
                    v-model.number="form.cost_rate"
                    label="Cost Rate ($/hour) *"
                    type="number"
                    :rules="positiveNumberRule"
                    prefix="$"
                    density="compact"
                  />
                </v-col>
                <v-col cols="12" md="4" v-if="form.pay_type === 'Salary'">
                  <v-text-field
                    v-model.number="form.annual_salary"
                    label="Annual Salary *"
                    type="number"
                    :rules="positiveNumberRule"
                    prefix="$"
                    density="compact"
                  />
                </v-col>
                <v-col cols="12" md="4" v-if="form.pay_type === 'Salary'">
                  <v-text-field
                    :model-value="calculatedHourlyRate()"
                    label="Calculated Hourly Rate"
                    density="compact"
                    readonly
                    hint="Based on 2080 hours/year"
                    persistent-hint
                  />
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Benefits -->
        <v-col cols="12">
          <v-card>
            <v-card-title class="text-subtitle-1 font-weight-bold">
              <v-icon class="mr-2" size="small">mdi-gift-outline</v-icon>
              Benefits
            </v-card-title>
            <v-card-text>
              <v-row>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model.number="form.pto_accrual"
                    label="PTO Accrual (hours/year)"
                    type="number"
                    :rules="positiveNumberRule"
                    density="compact"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field
                    v-model.number="form.holidays"
                    label="Holidays (hours/year)"
                    type="number"
                    :rules="positiveNumberRule"
                    density="compact"
                    hint="Typically 88 for Salary, 0 for Hourly"
                    persistent-hint
                  />
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Allocation Settings -->
        <v-col cols="12">
          <v-card>
            <v-card-title class="text-subtitle-1 font-weight-bold">
              <v-icon class="mr-2" size="small">mdi-chart-pie</v-icon>
              Allocation Settings
            </v-card-title>
            <v-card-text>
              <v-row>
                <v-col cols="12" md="4">
                  <v-checkbox
                    v-model="form.billable"
                    label="Billable Employee"
                    :true-value="1"
                    :false-value="0"
                    density="compact"
                    hint="Check if this employee's time is billable to clients"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <v-text-field
                    v-model.number="form.overhead_allocation"
                    label="Overhead Allocation"
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    density="compact"
                    hint="Percentage of time allocated to overhead (0-1)"
                    persistent-hint
                  />
                </v-col>
                <v-col cols="12" md="4">
                  <v-text-field
                    v-model.number="form.target_allocation"
                    label="Target Allocation"
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    density="compact"
                    hint="Target FTE allocation (0-1). Billable Salary: 1.0, Billable Hourly: 0.3"
                    persistent-hint
                  />
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Skills -->
        <v-col cols="12">
          <v-card>
            <v-card-title class="text-subtitle-1 font-weight-bold">
              <v-icon class="mr-2" size="small">mdi-star-outline</v-icon>
              Skills
            </v-card-title>
            <v-card-text>
              <v-select
                v-model="selectedSkills"
                label="Skills"
                :items="skillsOptions"
                multiple
                chips
                closable-chips
                density="compact"
                hint="Select one or more skills"
                persistent-hint
              />
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Action Buttons -->
        <v-col cols="12">
          <div class="d-flex ga-3 justify-end">
            <v-btn
              variant="outlined"
              @click="cancelEdit"
              :disabled="saving"
            >
              Cancel
            </v-btn>
            <v-btn
              color="primary"
              type="submit"
              :loading="saving"
              :disabled="!formValid"
              prepend-icon="mdi-content-save"
            >
              Save Changes
            </v-btn>
          </div>
        </v-col>
      </v-row>
    </v-form>

    <!-- Snackbar -->
    <v-snackbar
      v-model="snackbar"
      :color="snackbarColor"
      :timeout="3000"
    >
      {{ snackbarText }}
      <template #actions>
        <v-btn variant="text" @click="snackbar = false">Close</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>
