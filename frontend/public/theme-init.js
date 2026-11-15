// Applies the saved theme before first paint (kept external for a strict CSP).
try {
  var t = localStorage.getItem('ams-theme') || 'system'
  var dark = t === 'dark' || (t === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  document.documentElement.classList.toggle('dark', dark)
} catch (e) { /* storage unavailable */ }
