import type { NextConfig } from "next";

// Static export (ADR 0001): the same build is served from the cloud and packaged by Tauri. No API routes, no server
// actions, no server rendering at request time. The build goes to non_build/, outside the repository; the dev server
// keeps its own .next/ so running both never mixes their files.
const config: NextConfig = {
  output: "export",
  distDir: process.env.NODE_ENV === "production" ? "non_build" : ".next",
  trailingSlash: true,
  reactStrictMode: true,
  images: { unoptimized: true },
};

export default config;
