/**
 * API client for Operator Console endpoints.
 * Handles relationships, corrections, and console-specific data fetching.
 */

import { httpClient } from "@/lib/api/http";
import type {
  CorrectionStatusResponse,
  CorrectionTelemetry,
} from "@/types/console";

// ==================== Corrections API ====================

export async function getCorrectionStatus(
  limit: number = 20
): Promise<CorrectionStatusResponse> {
  return httpClient.get<CorrectionStatusResponse>("/deepsearch/corrections", {
    params: { limit },
  });
}

export async function getCorrectionTelemetry(): Promise<CorrectionTelemetry> {
  return httpClient.get<CorrectionTelemetry>("/deepsearch/corrections/telemetry");
}

export interface TriggerCorrectionParams {
  missionUuid?: string;
  evidenceIds?: string[];
  forceRetry?: boolean;
  callbackUrl?: string;
}

export interface TriggerCorrectionResponse {
  triggered: number;
  skipped: number;
  correction_ids: string[];
  message: string;
}

export async function triggerCorrections(
  params: TriggerCorrectionParams = {}
): Promise<TriggerCorrectionResponse> {
  return httpClient.post<TriggerCorrectionResponse>("/deepsearch/corrections", {
    mission_uuid: params.missionUuid,
    evidence_ids: params.evidenceIds,
    force_retry: params.forceRetry,
    callback_url: params.callbackUrl,
  });
}

export async function processCorrections(
  limit: number = 50
): Promise<{ processed: number; message: string; stats: Record<string, number> }> {
  return httpClient.post("/deepsearch/corrections/process", undefined, {
    params: { limit },
  });
}

export async function clearCompletedCorrections(): Promise<{
  cleared: number;
  message: string;
  stats: Record<string, number>;
}> {
  return httpClient.delete("/deepsearch/corrections/completed");
}

export interface DeadLetterItem {
  url: string;
  payload: Record<string, unknown>;
  error: string;
  attempts: number;
  last_attempt: string;
}

export async function getDeadLetterQueue(
  limit: number = 50
): Promise<{ count: number; items: DeadLetterItem[] }> {
  return httpClient.get("/deepsearch/corrections/dead-letter", {
    params: { limit },
  });
}

/**
 * Trigger file download in the browser.
 */
export function downloadFile(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
