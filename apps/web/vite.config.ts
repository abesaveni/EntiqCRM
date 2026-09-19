import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const apiTarget = env.VITE_API_PROXY_TARGET || 'http://localhost:8000';

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': path.resolve(__dirname, './src') },
    },
    build: {
      emptyOutDir: true,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) return;
            if (/[\\/]node_modules[\\/](react|react-dom|scheduler|react-is)[\\/]/.test(id)) return 'vendor-react';
            if (id.includes('/@radix-ui/') || id.includes('/cmdk/') || id.includes('/vaul/')) return 'vendor-ui';
            if (id.includes('/lucide-react/')) return 'vendor-icons';
            if (id.includes('/react-router')) return 'vendor-router';
            if (id.includes('/recharts/')) return 'vendor-viz';
            return 'vendor';
          },
        },
      },
    },
    server: {
      proxy: {
        '/api': { target: apiTarget, changeOrigin: true },
      },
    },
  };
});
