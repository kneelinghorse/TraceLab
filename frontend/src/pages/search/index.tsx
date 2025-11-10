import dynamic from "next/dynamic";

const SearchPage = dynamic(() => import("@/features/search/SearchExperience").then((mod) => mod.SearchPage), {
  ssr: false,
});

export default function SearchIndexPage() {
  return <SearchPage initialSection="search" />;
}
