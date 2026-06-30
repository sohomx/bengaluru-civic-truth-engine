import { readFileSync } from "node:fs";
import { join } from "node:path";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getPlaces } from "@/lib/data";

export function generateStaticParams() {
  return getPlaces().map((place) => ({ place: place.slug }));
}

export default async function DossierPage({ params }: { params: Promise<{ place: string }> }) {
  const { place } = await params;
  const record = getPlaces().find((item) => item.slug === place);
  if (!record) notFound();
  const markdown = readDossier(place);
  if (!markdown) notFound();

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-5 py-8">
      <nav className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-4">
        <Link href={`/places/${place}`} className="text-sm font-semibold uppercase tracking-[0.22em] text-ink">
          {record.label} dossier
        </Link>
        <Link href="/" className="text-sm text-muted hover:text-ink">Home</Link>
      </nav>

      <article className="prose-lite py-10">
        {markdown.split("\n").map((line, index) => renderLine(line, index))}
      </article>
    </main>
  );
}

function readDossier(slug: string): string | null {
  try {
    return readFileSync(join(process.cwd(), "src", "data", "generated", "dossiers", `${slug}.md`), "utf8");
  } catch {
    return null;
  }
}

function renderLine(line: string, index: number) {
  if (line.startsWith("# ")) {
    return <h1 key={index} className="mb-6 text-5xl font-semibold leading-tight text-ink">{line.slice(2)}</h1>;
  }
  if (line.startsWith("## ")) {
    return <h2 key={index} className="mb-3 mt-8 border-t border-line pt-6 text-2xl font-semibold text-ink">{line.slice(3)}</h2>;
  }
  if (line.startsWith("- ")) {
    return <p key={index} className="border-l border-line pl-4 text-sm leading-7 text-muted">{line.slice(2)}</p>;
  }
  if (!line.trim()) {
    return <div key={index} className="h-3" />;
  }
  return <p key={index} className="text-sm leading-7 text-muted">{line}</p>;
}
