import type { NextConfig } from "next";

// The browser calls /api/*; Next proxies it to FastAPI, so the backend needs no CORS setup.
const API_URL = process.env.NEUROSIM_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
