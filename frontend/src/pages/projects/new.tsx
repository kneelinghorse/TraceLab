import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import { mutate as globalMutate } from "swr";

import { AuthGate } from "@/components/AuthGate";
import { projectsApi } from "@/lib/api/projects";

function NewProjectContent() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) {
      setFormError("Project name is required.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const project = await projectsApi.createProject({ name: name.trim(), description: description.trim() || undefined });
      globalMutate((key) => Array.isArray(key) && key[0] === "projects", undefined, { revalidate: true });
      router.push(`/projects/${project.id}`);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Failed to create project");
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <header className="mb-8">
          <nav className="text-sm text-muted mb-4">
            <Link href="/projects" className="hover:text-secondary">Projects</Link>
            <span className="mx-2">/</span>
            <span className="text-foreground">New project</span>
          </nav>
          <h1 className="text-3xl font-bold text-foreground">Create a project</h1>
          <p className="mt-2 text-secondary">Projects hold documents, missions and evidence. Uploads and missions need one.</p>
        </header>
        <form onSubmit={handleSubmit} className="bg-surface border border-line rounded-lg p-6 space-y-4">
          <div>
            <label htmlFor="project-name" className="block text-sm font-medium text-secondary mb-1">Name *</label>
            <input id="project-name" type="text" aria-label="Project name" value={name} onChange={(e) => setName(e.target.value)} className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground" placeholder="E.g., 2025 Field Insights" required autoFocus />
          </div>
          <div>
            <label htmlFor="project-description" className="block text-sm font-medium text-secondary mb-1">Description (optional)</label>
            <textarea id="project-description" aria-label="Project description" value={description} onChange={(e) => setDescription(e.target.value)} className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground" rows={3} placeholder="Brief description of the project..." />
          </div>
          {formError && <p role="alert" className="text-sm text-danger">{formError}</p>}
          <div className="flex gap-3">
            <button type="submit" disabled={submitting} className="px-6 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:opacity-50">{submitting ? "Creating..." : "Create project"}</button>
            <Link href="/projects" className="px-4 py-2 text-secondary hover:text-foreground">Cancel</Link>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function NewProjectPage() {
  return <AuthGate><NewProjectContent /></AuthGate>;
}
