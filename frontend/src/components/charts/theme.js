import { ArcElement, BarElement, CategoryScale, Chart, Filler, Legend, LinearScale, LineElement, PointElement, Tooltip } from 'chart.js'
import { computed } from 'vue'
import { useThemeStore } from '@/stores/theme'

Chart.register(ArcElement, BarElement, CategoryScale, LinearScale, LineElement, PointElement, Tooltip, Legend, Filler)
Chart.defaults.font.family = "'Inter Variable', ui-sans-serif, system-ui"

export const PALETTE = ['#10b981', '#a78bfa', '#f472b6', '#fbbf24', '#34d399', '#22c55e', '#fb7185', '#c084fc']

/** Reactive chart colors that follow the light/dark theme. */
export function useChartTheme() {
  const theme = useThemeStore()
  return computed(() => {
    const dark = theme.isDark
    return {
      dark,
      text: dark ? '#8b95ad' : '#5b6478',
      grid: dark ? 'rgba(148,163,184,0.10)' : 'rgba(15,23,42,0.07)',
      tooltipBg: dark ? 'rgba(10,15,29,0.95)' : 'rgba(255,255,255,0.97)',
      tooltipText: dark ? '#e6ecff' : '#0b1220',
      border: dark ? '#0a0f1d' : '#ffffff',
    }
  })
}

export function baseOptions(t) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 700, easing: 'easeOutQuart' },
    plugins: {
      legend: { labels: { color: t.text, usePointStyle: true, pointStyle: 'circle', boxWidth: 6, padding: 14 } },
      tooltip: {
        backgroundColor: t.tooltipBg,
        titleColor: t.tooltipText,
        bodyColor: t.tooltipText,
        borderColor: t.grid,
        borderWidth: 1,
        padding: 10,
        cornerRadius: 10,
        usePointStyle: true,
      },
    },
  }
}
