import { beforeEach, describe, expect, it, vi } from "vitest";

const storage = vi.hoisted(() => ({ getStoredAuth: vi.fn(() => ({ token: "fixture-token" })), clearStoredAuth: vi.fn() }));
vi.mock("@/lib/auth/storage", () => storage);
import { documentsApi } from "@/lib/api/documents";
import { AUTH_EXPIRED_EVENT } from "@/lib/api/http";

class UploadRequest {
  static last: UploadRequest;
  constructor() { UploadRequest.last = this; }
  open = vi.fn(); setRequestHeader = vi.fn(); send = vi.fn();
  upload = { onprogress: null as ((event: { loaded: number; total: number; lengthComputable: boolean }) => void) | null };
  onload: (() => void) | null = null; onerror: (() => void) | null = null;
  status = 200; responseText = '{"id":"saved-document"}';
}
beforeEach(() => { vi.clearAllMocks(); vi.stubGlobal("XMLHttpRequest", UploadRequest); });

describe("authenticated upload transport", () => {
  it("sends multipart bytes and keeps progress distinct from server acceptance", async () => {
    const progress = vi.fn();
    const result = documentsApi.uploadDocument("project", new File(["source"], "source.txt"), progress);
    const request = UploadRequest.last;
    expect(request.open).toHaveBeenCalledWith("POST", expect.stringContaining("/documents/upload?project_id=project"));
    expect(request.setRequestHeader).toHaveBeenCalledWith("Authorization", "Bearer fixture-token");
    expect(request.send.mock.calls[0][0]).toBeInstanceOf(FormData);
    request.upload.onprogress?.({ loaded: 5, total: 10, lengthComputable: true });
    expect(progress).toHaveBeenLastCalledWith(5, 10);
    request.upload.onprogress?.({ loaded: 6, total: 0, lengthComputable: false });
    expect(progress).toHaveBeenLastCalledWith(6, null);
    request.onload?.();
    await expect(result).resolves.toEqual({ id: "saved-document" });
  });
  it("expires the in-memory auth session when an upload receives 401", async () => {
    const expired = vi.fn(); window.addEventListener(AUTH_EXPIRED_EVENT, expired);
    const result = documentsApi.uploadDocument("project", new File(["source"], "source.txt"));
    const request = UploadRequest.last; request.status = 401; request.responseText = '{"detail":"Sign in again"}'; request.onload?.();
    await expect(result).rejects.toMatchObject({ status: 401 });
    expect(storage.clearStoredAuth).toHaveBeenCalledOnce(); expect(expired).toHaveBeenCalledOnce();
    window.removeEventListener(AUTH_EXPIRED_EVENT, expired);
  });
  it("preserves a rejection and does not retry a possibly accepted upload after network loss", async () => {
    const result = documentsApi.uploadDocument("project", new File(["source"], "source.txt"));
    UploadRequest.last.status = 400; UploadRequest.last.responseText = '{"detail":"Unsupported file format"}'; UploadRequest.last.onload?.();
    await expect(result).rejects.toThrow("Unsupported file format");
    const interrupted = documentsApi.uploadDocument("project", new File(["source"], "source.txt"));
    UploadRequest.last.onerror?.();
    await expect(interrupted).rejects.toThrow("Check the document list before retrying");
    expect(UploadRequest.last.send).toHaveBeenCalledOnce();
  });
});
