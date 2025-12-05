import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';
import transformPlugin from 'vite-plugin-transform';
import { resolve, join } from 'path';

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [
      vue(),
      transformPlugin({
        tStart: '%{',
        tEnd: '}%',
        replaceFiles: [resolve(join(__dirname, 'dist/manifest.json'))],
        replace: {
          'CHROME_EXTENSION_ID': env.VITE_CHROME_EXTENSION_ID
        }
      })
    ],
    publicDir: 'public',
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      rollupOptions: {
        input: {
          main: resolve(__dirname, 'index.html'),
          background: resolve(__dirname, 'public/js/background.js'),
          utils: resolve(__dirname, 'public/js/composables/utils.js')
        },
        output: {
          entryFileNames: 'js/[name].js',
          chunkFileNames: 'js/[name].js',
          assetFileNames: ({name}) => {
            return name.endsWith('.js') ? 'js/[name][extname]' : 'assets/[name][extname]';
          }
        }
      }
    },
    define: {
      'import.meta.env.VITE_BASE_URL': JSON.stringify(env.VITE_BASE_URL),
      'process.env': {}
    },
    envPrefix: 'VITE_'
  };
});
