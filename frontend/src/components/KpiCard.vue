<script setup lang="ts">
/**
 * Reusable KPI card component for dashboard metrics.
 *
 * Displays a single metric with a title, formatted value, optional subtitle,
 * icon, and color accent via a left border stripe.
 */

defineProps<{
  title: string
  value: string
  subtitle?: string
  icon?: string
  color?: string
  loading?: boolean
}>()
</script>

<template>
  <v-card
    class="kpi-card pa-4"
    :style="{ borderLeft: `4px solid ${color || '#1976D2'}` }"
  >
    <v-skeleton-loader v-if="loading" type="text, text" />
    <template v-else>
      <div class="d-flex align-center mb-1">
        <v-icon
          v-if="icon"
          :icon="icon"
          :color="color || 'primary'"
          size="20"
          class="mr-2"
        />
        <span class="text-caption text-medium-emphasis text-uppercase font-weight-medium">
          {{ title }}
        </span>
      </div>
      <div class="text-h5 font-weight-bold" :style="{ color: color || undefined }">
        {{ value }}
      </div>
      <div v-if="subtitle" class="text-caption text-medium-emphasis mt-1">
        {{ subtitle }}
      </div>
    </template>
  </v-card>
</template>

<style scoped>
.kpi-card {
  transition: box-shadow 0.2s ease;
}
.kpi-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1) !important;
}
</style>
