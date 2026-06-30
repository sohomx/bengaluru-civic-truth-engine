/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const backend = process.env.CIVIC_API_BASE || "http://127.0.0.1:8000";
    return [
      {
        source: "/rag/:path*",
        destination: `${backend}/rag/:path*`
      }
    ];
  }
};

export default nextConfig;
