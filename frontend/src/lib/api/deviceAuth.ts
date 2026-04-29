/**
 * Client helpers for the device-authorization (RFC 8628) endpoints.
 *
 * Used by the /device approval page so a logged-in web user can approve or
 * deny a device-code request the MCP client just initiated. T42.4.
 */
import { apiRequest } from "@/lib/api/http";

const DEVICE_PATH = "/auth/device";

export type DeviceGrantStatus = "pending" | "approved" | "denied" | "expired";

export interface DeviceGrantPreview {
  user_code: string;
  client_label: string;
  status: DeviceGrantStatus;
  expires_at: string;
}

export interface DeviceApproveResponse {
  user_code: string;
  label: string;
  key_id: string;
  client_label: string;
}

export interface DeviceDenyResponse {
  user_code: string;
  status: "denied";
}

export async function previewDeviceGrant(
  userCode: string
): Promise<DeviceGrantPreview> {
  const encoded = encodeURIComponent(userCode);
  return apiRequest<DeviceGrantPreview>(`${DEVICE_PATH}/grants/${encoded}`, {
    method: "GET",
  });
}

export async function approveDeviceGrant(
  userCode: string,
  label?: string
): Promise<DeviceApproveResponse> {
  return apiRequest<DeviceApproveResponse>(`${DEVICE_PATH}/approve`, {
    method: "POST",
    body: JSON.stringify({ user_code: userCode, label }),
  });
}

export async function denyDeviceGrant(
  userCode: string
): Promise<DeviceDenyResponse> {
  return apiRequest<DeviceDenyResponse>(`${DEVICE_PATH}/deny`, {
    method: "POST",
    body: JSON.stringify({ user_code: userCode }),
  });
}
