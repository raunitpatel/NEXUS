const nextConfig = {
  // Standalone output for Railway Docker deployment (AGNT-028)
  output: 'standalone',

  // Allow images from NEXUS backend services
  images: {
    remotePatterns: [],
  },

  // Environment variable validation at build time
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8080',
  },
}

module.exports = nextConfig