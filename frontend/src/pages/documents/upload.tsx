import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { AuthGate } from "@/components/AuthGate";
import { DocumentUpload } from "@/components/documents/DocumentUpload";
import { PageState } from "@/components/ui/PageState";
import { useAuth } from "@/contexts/AuthContext";
import { projectsApi } from "@/lib/api/projects";

export default function DocumentUploadPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const requested = typeof router.query.project_id === "string" ? router.query.project_id : "";
  const projects = useSWR(["projects", "upload", user?.user_id], projectsApi.listAllProjects);
  const projectId = selected ?? requested;
  const valid = projects.data?.some(project => project.id === projectId);
  return <AuthGate><div className="mx-auto max-w-4xl space-y-6 px-4 py-8 sm:px-6">
    <header><h1 className="text-3xl font-semibold">Upload documents</h1><p className="mt-2 text-secondary">Add sources to a research project and follow each file through upload and processing.</p></header>
    {projects.error ? <PageState state="error" title="Projects could not load." onRetry={() => void projects.mutate()} /> : projects.isLoading ? <PageState state="loading" title="Loading projects…" /> : projects.data?.length === 0 ? <p>No accessible projects. <Link href="/projects" className="text-accent-text underline">Create a project</Link> to upload sources.</p> : <label className="block space-y-2 text-sm"><span>Project</span><select aria-label="Project" disabled={busy} value={valid ? projectId : ""} onChange={event => setSelected(event.target.value)} className="w-full min-w-0 rounded-lg border border-line-strong bg-surface p-3"><option value="">Choose a project</option>{projects.data?.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>}
    <DocumentUpload key={projectId} projectId={valid ? projectId : ""} onBusyChange={setBusy} onComplete={async () => { await globalMutate(key => Array.isArray(key) && ["documents", "project-stats", "project-resources"].includes(key[0])); }} />
    {valid && <Link className="inline-block text-accent-text underline" href={`/projects/${projectId}?tab=Documents`}>Return to project documents</Link>}
  </div></AuthGate>;
}
