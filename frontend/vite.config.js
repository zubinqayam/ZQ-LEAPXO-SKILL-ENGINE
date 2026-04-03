import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/execute": "http://localhost:4000",
      "/skills": "http://localhost:4000"
    }
  }
});
