/** @type {import('next').NextConfig} */
const isGithubPages = process.env.GITHUB_PAGES === "true";
const repositoryName = process.env.GITHUB_REPOSITORY?.split("/")[1] || "bengaluru-civic-truth-engine";
const configuredBasePath = process.env.NEXT_PUBLIC_BASE_PATH || (isGithubPages ? `/${repositoryName}` : "");

const localApiConfig = {
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

const githubPagesConfig = {
  output: "export",
  trailingSlash: true,
  basePath: configuredBasePath,
  assetPrefix: configuredBasePath,
  images: {
    unoptimized: true
  }
};

const nextConfig = {
  devIndicators: false,
  ...(isGithubPages ? githubPagesConfig : localApiConfig)
};

export default nextConfig;
