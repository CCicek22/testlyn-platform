"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/components/auth/auth-provider";
import type { Project, MeResponse } from "@testlyn/shared";

function ProjectCard({ project }: { project: Project }) {
  return (
    <Link href={`/projects/${project.id}`}>
      <Card className="cursor-pointer border-zinc-800 bg-zinc-900 transition-colors hover:border-zinc-700 hover:bg-zinc-800/80">
        <CardHeader className="pb-2">
          <CardTitle className="text-base text-zinc-100">{project.name}</CardTitle>
        </CardHeader>
        <CardContent>
          {project.description && (
            <p className="mb-3 line-clamp-2 text-sm text-zinc-400">
              {project.description}
            </p>
          )}
          <p className="text-xs text-zinc-500">
            Created {new Date(project.created_at).toLocaleDateString()}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}

function NewProjectDialog({
  open,
  onClose,
  orgId,
}: {
  open: boolean;
  onClose: () => void;
  orgId: string;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.orgs.createProject(orgId, { name, description: description || undefined }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["projects", orgId] });
      setName("");
      setDescription("");
      setError(null);
      onClose();
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "Failed to create project");
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    mutation.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="border-zinc-800 bg-zinc-900 text-zinc-100">
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {error && (
            <div role="alert" className="rounded-md bg-alert/10 px-3 py-2 text-sm text-alert">
              {error}
            </div>
          )}
          <div>
            <label htmlFor="proj-name" className="mb-1 block text-sm font-medium text-zinc-300">
              Name
            </label>
            <Input
              id="proj-name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="My load tests"
              className="border-zinc-700 bg-zinc-800 text-zinc-100 placeholder:text-zinc-500"
            />
          </div>
          <div>
            <label htmlFor="proj-desc" className="mb-1 block text-sm font-medium text-zinc-300">
              Description <span className="text-zinc-500">(optional)</span>
            </label>
            <Input
              id="proj-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What are you testing?"
              className="border-zinc-700 bg-zinc-800 text-zinc-100 placeholder:text-zinc-500"
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              className="text-zinc-400 hover:text-zinc-100"
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending || !name.trim()}>
              {mutation.isPending ? "Creating…" : "Create project"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function ProjectsPage() {
  const { user } = useAuth();
  const [dialogOpen, setDialogOpen] = useState(false);

  // Resolve org id from auth context via /v1/me — never hardcode.
  const { data: me } = useQuery<MeResponse>({
    queryKey: ["me"],
    queryFn: () => api.me(),
    enabled: user != null,
    staleTime: 5 * 60_000,
  });
  const orgId = me?.memberships?.[0]?.org_id ?? null;

  const { data, isLoading, error } = useQuery<Project[]>({
    queryKey: ["projects", orgId],
    queryFn: () => api.orgs.projects(orgId!),
    enabled: orgId != null,
  });

  const projects = data ?? [];

  const projectsLoading = orgId == null || isLoading;

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-100">Projects</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Organize your load tests by project.
          </p>
        </div>
        <Button
          onClick={() => setDialogOpen(true)}
          disabled={orgId == null}
        >
          <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
          New project
        </Button>
      </div>

      {projectsLoading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-xl bg-zinc-800" />
          ))}
        </div>
      )}

      {error && (
        <div role="alert" className="rounded-md bg-alert/10 px-4 py-3 text-sm text-alert">
          Failed to load projects. Check your connection and try again.
        </div>
      )}

      {!projectsLoading && !error && projects.length === 0 && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-zinc-700 py-20 text-center">
          <svg
            className="mb-4 h-10 w-10 text-zinc-600"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
            <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg>
          <p className="text-sm font-medium text-zinc-300">No projects yet</p>
          <p className="mt-1 text-sm text-zinc-500">Create one to start running load tests.</p>
          <Button className="mt-6" onClick={() => setDialogOpen(true)}>
            New project
          </Button>
        </div>
      )}

      {!projectsLoading && !error && projects.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}

      {orgId != null && (
        <NewProjectDialog
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
          orgId={orgId}
        />
      )}
    </div>
  );
}
