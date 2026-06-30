"use client";

import { ArrowUpRight, Filter, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { formatDate, sourceStatusLabel, type SourceStatusRow } from "@/lib/data";

export function SourceExplorer({ sources }: { sources: SourceStatusRow[] }) {
  const [query, setQuery] = useState("");
  const [domain, setDomain] = useState("all");
  const [status, setStatus] = useState("all");
  const domains = useMemo(() => Array.from(new Set(sources.map((source) => source.domain))).sort(), [sources]);
  const statuses = useMemo(() => Array.from(new Set(sources.map((source) => source.latest_fetch_status))).sort(), [sources]);
  const filtered = sources.filter((source) => {
    const haystack = `${source.source_id} ${source.name} ${source.publisher} ${source.domain}`.toLowerCase();
    return (
      haystack.includes(query.toLowerCase()) &&
      (domain === "all" || source.domain === domain) &&
      (status === "all" || source.latest_fetch_status === status)
    );
  });

  return (
    <div>
      <div className="grid gap-3 border-y border-line py-4 md:grid-cols-[1fr_220px_220px]">
        <label className="flex items-center gap-3 border border-line bg-paper px-3 py-2">
          <Search size={17} className="text-muted" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search source, publisher, domain"
            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
        </label>
        <label className="flex items-center gap-3 border border-line bg-paper px-3 py-2">
          <Filter size={17} className="text-muted" />
          <select value={domain} onChange={(event) => setDomain(event.target.value)} className="min-w-0 flex-1 bg-transparent text-sm outline-none">
            <option value="all">All domains</option>
            {domains.map((item) => (
              <option key={item} value={item}>{sourceStatusLabel(item)}</option>
            ))}
          </select>
        </label>
        <select value={status} onChange={(event) => setStatus(event.target.value)} className="border border-line bg-paper px-3 py-2 text-sm outline-none">
          <option value="all">All fetch statuses</option>
          {statuses.map((item) => (
            <option key={item} value={item}>{sourceStatusLabel(item)}</option>
          ))}
        </select>
      </div>

      <div className="mt-6 divide-y divide-line border-y border-line">
        {filtered.map((source) => (
          <Link key={source.source_id} href={`/sources/${source.source_id}`} className="grid gap-4 py-5 transition hover:bg-line/20 md:grid-cols-[1fr_160px_160px_24px]">
            <div>
              <div className="flex flex-wrap gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted">
                <span>{sourceStatusLabel(source.domain)}</span>
                <span>tier {source.source_tier}</span>
                <span>{sourceStatusLabel(source.normalized_usage_status)}</span>
              </div>
              <h2 className="mt-2 text-xl font-semibold text-ink">{source.name}</h2>
              <p className="mt-1 break-all text-sm text-muted">{source.source_id}</p>
            </div>
            <div className="text-sm">
              <p className="font-semibold text-ink">{sourceStatusLabel(source.latest_fetch_status)}</p>
              <p className="text-muted">fetch status</p>
            </div>
            <div className="text-sm">
              <p className="font-semibold text-ink">{formatDate(source.latest_fetched_at)}</p>
              <p className="text-muted">latest fetch</p>
            </div>
            <ArrowUpRight size={19} className="self-center text-civic" />
          </Link>
        ))}
      </div>
    </div>
  );
}
