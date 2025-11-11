import { httpClient } from "@/lib/api/http";
import type { Project } from "@/types/document";
import type { PaginatedResponse } from "@/types/pagination";

export type ListProjectsParams = {
  page?: number;
  pageSize?: number;
  search?: string;
};

export const projectsApi = {
  listProjects(params: ListProjectsParams = {}): Promise<PaginatedResponse<Project>> {
    const query = {
      page: params.page,
      page_size: params.pageSize,
      search: params.search,
    };
    return httpClient.get("/api/v1/projects", { params: query });
  },

  getProject(projectId: string): Promise<Project> {
    return httpClient.get(`/api/v1/projects/${projectId}`);
  },

  createProject(data: { name: string; description?: string; research_type?: string }): Promise<Project> {
    return httpClient.post("/api/v1/projects", data);
  },
};
