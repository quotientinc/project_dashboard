<script setup lang="ts">
/**
 * Reusable Plotly chart wrapper component.
 *
 * Handles mounting, reactive data updates, responsive resizing,
 * and displays a skeleton loader while data is loading.
 */
import type Plotly from 'plotly.js-dist-min'
import { ref, shallowRef, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'

type PlotlyModule = typeof import('plotly.js-dist-min')

const props = withDefaults(
  defineProps<{
    data: Plotly.Data[]
    layout?: Partial<Plotly.Layout>
    config?: Partial<Plotly.Config>
    loading?: boolean
  }>(),
  {
    layout: () => ({}),
    config: () => ({}),
    loading: false,
  }
)

const chartRef = ref<HTMLDivElement>()
const PlotlyLib = shallowRef<PlotlyModule | null>(null)
const plotlyLoading = ref(true)
let resizeObserver: ResizeObserver | null = null

const defaultConfig: Partial<Plotly.Config> = {
  responsive: true,
  displayModeBar: false,
}

const baseLayout: Partial<Plotly.Layout> = {
  margin: { t: 20, r: 20, b: 40, l: 50 },
  paper_bgcolor: 'transparent',
  plot_bgcolor: 'transparent',
  font: { family: 'Roboto, sans-serif', size: 12 },
}

function renderChart() {
  if (!PlotlyLib.value) return
  if (!chartRef.value || props.loading || props.data.length === 0) return

  const mergedLayout = { ...baseLayout, ...props.layout }
  const mergedConfig = { ...defaultConfig, ...props.config }

  PlotlyLib.value.react(chartRef.value, props.data, mergedLayout, mergedConfig)
}

onMounted(async () => {
  const mod = await import('plotly.js-dist-min')
  PlotlyLib.value = mod.default
  plotlyLoading.value = false

  await nextTick()
  renderChart()

  if (chartRef.value) {
    resizeObserver = new ResizeObserver(() => {
      if (PlotlyLib.value && chartRef.value && chartRef.value.offsetParent !== null) {
        PlotlyLib.value.Plots.resize(chartRef.value)
      }
    })
    resizeObserver.observe(chartRef.value)
  }
})

onBeforeUnmount(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  if (PlotlyLib.value && chartRef.value) {
    PlotlyLib.value.purge(chartRef.value)
  }
})

watch(
  () => [props.data, props.layout],
  () => {
    nextTick(() => {
      renderChart()
    })
  },
  { deep: true }
)
</script>

<template>
  <div class="plotly-chart-wrapper">
    <v-skeleton-loader v-if="loading || plotlyLoading" type="image" height="300" />
    <div
      v-show="!loading && !plotlyLoading && data.length > 0"
      ref="chartRef"
      class="plotly-chart"
    />
    <div
      v-if="!loading && !plotlyLoading && data.length === 0"
      class="d-flex align-center justify-center text-medium-emphasis"
      style="min-height: 200px"
    >
      No data available
    </div>
  </div>
</template>

<style scoped>
.plotly-chart-wrapper {
  width: 100%;
  min-height: 200px;
}
.plotly-chart {
  width: 100%;
}
</style>
