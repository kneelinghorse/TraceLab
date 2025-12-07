import { httpClient } from "@/lib/api/http";
import type { Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";

export type ListProjectsParams = {
  page?: number;
  pageSize?: number;
  search?: string;
};

export type ProjectStats = {
  project_id: string;
  name: string;
  document_count: number;
  chunk_count: number;
  report_count: number;
  total_tokens: number;
  last_updated?: string;
};

export const projectsApi = {
  listProjects(params: ListProjectsParams = {}): Promise<PaginatedResponse<Project>> {
    const query = {
      page: params.page,
      page_size: params.pageSize,
      search: params.search,
    };
    return httpClient.get("/projects", { params: query });
  },

  getProject(projectId: string): Promise<Project> {
    return httpClient.get(`/projects/${projectId}`);
  },

  createProject(data: { name: string; description?: string; research_type?: string }): Promise<Project> {
    return httpClient.post("/projects", data);
  },

  updateProject(projectId: string, data: { name?: string; description?: string; research_type?: string; status?: string }): Promise<Project> {
    return httpClient.put(`/projects/${projectId}`, data);
  },

  deleteProject(projectId: string): Promise<void> {
    return httpClient.delete(`/projects/${projectId}`);
  },

  getProjectStats(projectId: string): Promise<ProjectStats> {
    return httpClient.get(`/projects/${projectId}/stats`);
  },
};
