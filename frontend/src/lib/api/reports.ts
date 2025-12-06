/**
 * Reports API client
 */

import { httpClient } from "./http";

export type ReportStatus = "draft" | "final";
export type ReportFormat = "summary" | "report" | "bullets" | "markdown";

export type Citation = {
  chunk_id: string;
  document_id: string | null;
  excerpt: string;
};

export type ReportSource = {
  id: string;
  report_id: string;
  source_type: "collection" | "chunk";
  source_id: string;
  added_at: string;
};

export type Report = {
  id: string;
  title: string;
  content: string;
  citations: Citation[];
  tokens_used: number;
  status: ReportStatus;
  created_at: string;
};

export type ReportDetail = Report & {
  project_id: string | null;
  report_type: string;
  prompt: string | null;
  chunk_count: number;
  sources: ReportSource[];
  updated_at: string;
};

export type ReportListItem = {
  id: string;
  title: string;
  status: ReportStatus;
  report_type: string;
  tokens_used: number;
  chunk_count: number;
  project_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ReportListResponse = {
  items: ReportListItem[];
  total: number;
  page: number;
  page_size: number;
};

export type CreateReportParams = {
  title: string;
  collection_id?: string;
  chunk_ids?: string[];
  project_id?: string;
  prompt?: string;
  format?: ReportFormat;
};

export type UpdateReportParams = {
  title?: string;
  status?: ReportStatus;
};

export type ListReportsParams = {
  project_id?: string;
  status?: ReportStatus;
  page?: number;
  page_size?: number;
};

export const reportsApi = {
  /**
   * List all reports with optional filtering and pagination
   */
  async list(params?: ListReportsParams): Promise<ReportListResponse> {
    return httpClient.get("/reports", { params });
  },

  /**
   * Create a new report by synthesizing content from a collection or chunks
   */
  async create(params: CreateReportParams): Promise<Report> {
    return httpClient.post("/reports", params);
  },

  /**
   * Get a single report with full details including sources
   */
  async get(reportId: string): Promise<ReportDetail> {
    return httpClient.get(`/reports/${reportId}`);
  },

  /**
   * Update report title or status
   */
  async update(reportId: string, params: UpdateReportParams): Promise<ReportDetail> {
    return httpClient.put(`/reports/${reportId}`, params);
  },

  /**
   * Delete a report
   */
  async delete(reportId: string): Promise<void> {
    return httpClient.delete(`/reports/${reportId}`);
  },
};
