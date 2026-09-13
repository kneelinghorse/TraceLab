import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { useAuth } from "@/contexts/AuthContext";
import { homeApi } from "@/lib/api/home";

export function ProjectFavorite({ projectId }: { projectId: string }) {
  const { user } = useAuth();
  const { data, error, mutate } = useSWR(["favorites", user?.user_id, projectId], () => homeApi.favorites({ project_id: projectId }));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState(false);
  const pinned = (data?.total ?? 0) > 0;
  async function toggle() {
    setBusy(true); setFailure(false);
    try {
      await (pinned ? homeApi.unpinProject(projectId) : homeApi.pinProject(projectId));
      await mutate();
      await globalMutate(key => Array.isArray(key) && key[0] === "home" && key[1] === user?.user_id);
    } catch { setFailure(true); } finally { setBusy(false); }
  }
  return <div className="space-y-2">
    <button className="rounded-lg border border-line-strong px-3 py-2 text-sm" disabled={!data || busy} aria-pressed={pinned} onClick={() => void toggle()}>{busy ? "Saving…" : pinned ? "Unfavorite project" : "Favorite project"}</button>
    {(error || failure) && <p role="alert" className="text-sm text-danger">Favorite could not be saved or loaded. <button className="underline" onClick={() => void mutate()}>Retry favorite</button></p>}
  </div>;
}
