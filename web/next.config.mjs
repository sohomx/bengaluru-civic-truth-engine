/** @type {import('next').NextConfig} */
const nextConfig = {
  devIndicators: false,
  async rewrites() {
    const backend = process.env.CIVIC_API_BASE || "http://127.0.0.1:8017";
    return [
      {
        source: "/rag/:path*",
        destination: `${backend}/rag/:path*`
      },
      {
        source: "/diagnostics/:path*",
        destination: `${backend}/diagnostics/:path*`
      },
      {
        source: "/packets/:path*",
        destination: `${backend}/packets/:path*`
      }
    ];
  }
};

export default nextConfig;
