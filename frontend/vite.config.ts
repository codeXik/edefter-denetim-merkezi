import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 950,
    rollupOptions: {
      output: {
        manualChunks: {
          aggrid: [
            "@ag-grid-community/react",
            "@ag-grid-community/core",
            "@ag-grid-community/client-side-row-model",
          ],
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
});
