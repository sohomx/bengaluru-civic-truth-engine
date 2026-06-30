import { AskCivicRecord } from "@/components/ask-civic-record";

export default async function AskPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const params = await searchParams;

  return (
    <main className="min-h-screen px-4 py-4">
      <AskCivicRecord initialQuery={params.q ?? ""} autoFocus />
    </main>
  );
}
