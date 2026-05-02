/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for Docker multi-stage: copies only the minimal files needed to run
  output: 'standalone',
};

module.exports = nextConfig;
