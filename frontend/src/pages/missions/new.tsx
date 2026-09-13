import { useRouter } from "next/router";
import Link from "next/link";

import { AuthGate } from "@/components/AuthGate";
import { MissionForm } from "@/components/missions";
import type { ApiMission } from "@/types/mission";

function NewMissionContent() {
  const router = useRouter();

  const handleSuccess = (mission: ApiMission) => {
    // Redirect to the mission detail page
    router.push(`/missions/${mission.id}`);
  };

  const handleCancel = () => {
    router.push("/missions");
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

        <MissionForm onSuccess={handleSuccess} onCancel={handleCancel} />
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
