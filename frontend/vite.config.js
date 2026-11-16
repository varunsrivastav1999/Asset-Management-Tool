import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_PROXY_TARGET || 'http://localhost:2000'
  const appName = env.VITE_APP_NAME || 'Asset Management Tools'

  return {
    plugins: [
      { name: 'app-name-html', transformIndexHtml: (html) => html.replaceAll('%APP_NAME%', appName) },
      vue(),
      tailwindcss(),
      VitePWA({
        // 'prompt' + src/pwa.js: new versions are announced with a Reload button instead of staying cached.
        registerType: 'prompt',
        injectRegister: false,
        includeAssets: ['favicon.svg', 'apple-touch-icon.png'],
        manifest: {
          name: appName,
          short_name: appName.split(' ')[0],
          description: 'Track, issue and maintain every company asset.',
          theme_color: '#060912',
          background_color: '#060912',
          display: 'standalone',
          start_url: '/',
          scope: '/',
          icons: [
            { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
            { src: '/pwa-512.png', sizes: '512x512', type: 'image/png' },
            { src: '/pwa-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          ],
          shortcuts: [
            { name: 'Scan asset', url: '/scan', icons: [{ src: '/pwa-192.png', sizes: '192x192' }] },
            { name: 'New handover', url: '/handovers/new', icons: [{ src: '/pwa-192.png', sizes: '192x192' }] },
          ],
        },
        workbox: {
          navigateFallback: '/index.html',
          navigateFallbackDenylist: [/^\/api\//, /^\/ws\//, /^\/admin\//, /^\/media\//, /^\/static\//],
          globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
          runtimeCaching: [
            {
              urlPattern: ({ url }) => url.pathname.startsWith('/media/'),
              handler: 'CacheFirst',
              options: { cacheName: 'media', expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 } },
            },
          ],
        },
      }),
    ],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    server: {
      port: 2025,
      strictPort: true,
      host: true,
      proxy: {
        // VITE_PROXY_TARGET may point at the Docker stack (https://localhost:2025, self-signed in dev).
        '/api': { target, changeOrigin: false, secure: false },
        '/media': { target, changeOrigin: false, secure: false },
        '/ws': { target: target.replace(/^http/, 'ws'), ws: true, secure: false },
      },
    },
    build: {
      target: 'es2020',
      assetsDir: '_app', // keep clear of the SPA's /assets/* routes
      sourcemap: false,
      chunkSizeWarningLimit: 800,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined
            if (/[\\/]node_modules[\\/](chart\.js|vue-chartjs)[\\/]/.test(id)) return 'charts'
            if (/[\\/]node_modules[\\/](@vue|vue|vue-router|pinia)[\\/]/.test(id)) return 'vue'
            return undefined
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      css: false,
    },
  }
})
