import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBase = (env.VITE_API_BASE_URL || "").trim();
  const proxyTarget = (env.VITE_DEV_API_PROXY_TARGET || "https://fifa2026.zeabur.app").trim();

  return {
    plugins: [react()],
    server: apiBase
      ? undefined
      : {
          proxy: {
            "/api": {
              target: proxyTarget,
              changeOrigin: true,
              secure: true,
            },
          },
        },
  };
});
