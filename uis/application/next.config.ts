import type { NextConfig } from "next";

const apiUrl = (process.env.SUPPLIERS_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/auth/:path*", destination: `${apiUrl}/auth/:path*` },
      { source: "/api/suppliers/:path*", destination: `${apiUrl}/suppliers/:path*` },
    ];
  },
};

export default nextConfig;