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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <header className="mb-8">
          <nav className="text-sm text-gray-500 dark:text-gray-400 mb-4">
            <Link href="/missions" className="hover:text-gray-700 dark:hover:text-gray-200">
              Missions
            </Link>
            <span className="mx-2">/</span>
            <span className="text-gray-900 dark:text-white">New Mission</span>
          </nav>

          <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
            Create New Mission
          </h1>
          <p className="mt-2 text-gray-600 dark:text-gray-400">
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
