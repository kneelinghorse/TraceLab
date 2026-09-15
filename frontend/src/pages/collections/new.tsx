import Link from "next/link";
import { useRouter } from "next/router";
import { useState } from "react";
import { mutate as globalMutate } from "swr";

import { AuthGate } from "@/components/AuthGate";
import { collectionsApi } from "@/lib/api/collections";

function NewCollectionContent() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!name.trim()) {
      setFormError("Name is required");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const collection = await collectionsApi.create({ name: name.trim(), description: description.trim() || undefined });
      globalMutate((key) => Array.isArray(key) && key[0] === "collections", undefined, { revalidate: true });
      router.push(`/collections/${collection.id}`);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Failed to create collection");
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <header className="mb-8">
          <nav className="text-sm text-muted mb-4">
            <Link href="/collections" className="hover:text-secondary">Collections</Link>
            <span className="mx-2">/</span>
            <span className="text-foreground">New collection</span>
          </nav>
          <h1 className="text-3xl font-bold text-foreground">Create a collection</h1>
          <p className="mt-2 text-secondary">Keep instructions, documents and excerpts together to guide your next mission.</p>
        </header>
        <form onSubmit={handleSubmit} className="bg-surface border border-line rounded-lg p-6 space-y-4">
          <div>
            <label htmlFor="collection-name" className="block text-sm font-medium text-secondary mb-1">Name *</label>
            <input id="collection-name" type="text" aria-label="Collection name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g., Key Research Findings" className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground" required autoFocus />
          </div>
          <div>
            <label htmlFor="collection-description" className="block text-sm font-medium text-secondary mb-1">Description (optional)</label>
            <textarea id="collection-description" aria-label="Collection description" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional description..." rows={3} className="w-full px-4 py-2 border border-line-strong rounded-lg bg-surface text-foreground" />
          </div>
          {formError && <p role="alert" className="text-sm text-danger">{formError}</p>}
          <div className="flex gap-3">
            <button type="submit" disabled={submitting} className="px-6 py-2 bg-accent text-on-accent rounded-lg hover:bg-accent disabled:opacity-50">{submitting ? "Creating..." : "Create collection"}</button>
            <Link href="/collections" className="px-4 py-2 text-secondary hover:text-foreground">Cancel</Link>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function NewCollectionPage() {
  return <AuthGate><NewCollectionContent /></AuthGate>;
}
