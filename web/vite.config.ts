import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const apiProxy = env.VITE_API_PROXY || "http://127.0.0.1:8001";

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": apiProxy
      }
    }
  };
});
