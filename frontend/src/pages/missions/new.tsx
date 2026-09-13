import { useRouter } from "next/router";
import Link from "next/link";
import useSWR from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { collectionsApi } from "@/lib/api/collections";

import { AuthGate } from "@/components/AuthGate";
import { MissionForm } from "@/components/missions";
import { useApiMission } from "@/lib/hooks/useMissions";
import { PageState } from "@/components/ui/PageState";
import type { ApiMission } from "@/types/mission";

function NewMissionContent() {
  const router = useRouter();
  const { user } = useAuth();
  const sourceId = typeof router.query.from === "string" ? router.query.from : undefined;
  const { mission: source, isLoading, error, refresh } = useApiMission(sourceId);
  const collectionId = typeof router.query.collection === "string" ? router.query.collection : undefined;
  const seed = useSWR(collectionId && !sourceId ? ["collection-seed", user?.user_id, collectionId] : null, () => collectionsApi.missionSeed(collectionId!));

  const handleSuccess = (mission: ApiMission) => {
    // Redirect to the mission detail page
    router.push(`/missions/${mission.id}`);
  };

  const handleCancel = () => {
    router.push(collectionId ? `/collections/${collectionId}` : "/missions");
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <header className="mb-8">
          <nav className="text-sm text-muted mb-4">
            <Link href="/missions" className="hover:text-secondary">
              Missions
            </Link>
            <span className="mx-2">/</span>
            <span className="text-foreground">New Mission</span>
          </nav>

          <h1 className="text-3xl font-bold text-foreground">
            Create New Mission
          </h1>
          <p className="mt-2 text-secondary">
            Define a research mission for DeepSearch to execute. Fill in the required
            fields and optionally add context, deliverables, and tags.
          </p>
        </header>

        {collectionId && sourceId ? <PageState state="error" title="Choose a collection or an earlier mission as the source, not both." /> : collectionId && seed.isLoading ? <PageState state="loading" title="Loading collection context…" /> : collectionId && (seed.error || !seed.data) ? <PageState state="error" title="Collection context could not load." onRetry={() => void seed.mutate().catch(() => {})} /> : sourceId && isLoading ? <PageState state="loading" title="Loading inputs for the new run…" /> : sourceId && (error || !source) ? <PageState state="error" title="The original mission could not load." onRetry={() => void refresh()} /> : <>
          {source && <p className="mb-4 text-sm text-secondary">New run from <Link className="underline" href={`/missions/${source.id}`}>{source.mission_id}</Link>. Review the inputs before submitting.</p>}
          {seed.data && <section className="panel mb-6 space-y-3 p-5" aria-label="Seeded collection context"><p>Context from <Link className="text-accent-text underline" href={`/collections/${seed.data.collection_id}`}>{seed.data.title.replace(/^Research: /, "")}</Link>. Review the objective, success criteria and destination project before submitting.</p><details><summary className="cursor-pointer text-sm font-medium">Review {seed.data.references.length.toLocaleString()} source documents</summary><ul className="mt-3 max-h-64 space-y-2 overflow-y-auto">{seed.data.references.map(reference => <li key={reference.document_id}><Link className="break-words text-sm text-accent-text underline" href={reference.href}>{reference.title}</Link></li>)}</ul></details><p className="text-sm text-secondary">These are reference documents for the research. Access is checked whenever a source is opened.</p></section>}
          <MissionForm key={source?.id ?? seed.data?.collection_id ?? "new"} source={source} seed={seed.data} onSuccess={handleSuccess} onCancel={handleCancel} />
        </>}
      </div>
    </div>
  );
}

export default function NewMissionPage() {
  return (
    <AuthGate>
      <NewMissionContent />
    </AuthGate>
  );
}
