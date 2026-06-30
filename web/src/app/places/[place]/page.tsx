import { notFound } from "next/navigation";
import { PlaceDossier } from "@/components/place-dossier";
import { getPlace, getPlaces } from "@/lib/data";

export function generateStaticParams() {
  return getPlaces().map((place) => ({ place: place.slug }));
}

export default async function PlacePage({ params }: { params: Promise<{ place: string }> }) {
  const { place } = await params;
  const record = getPlace(place);
  if (!record) notFound();
  return <PlaceDossier place={record} />;
}
