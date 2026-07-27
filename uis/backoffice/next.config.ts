import type { NextConfig } from "next";
import path from "path";

const appDir = process.cwd();

const nextConfig: NextConfig = {
  reactStrictMode: true,
  experimental: {
    externalDir: true,
  },
  turbopack: {
    root: path.resolve(appDir, "../.."),
    resolveAlias: {
      "@legacy": path.resolve(appDir, "../../src"),
    },
  },
};

export default nextConfig;
