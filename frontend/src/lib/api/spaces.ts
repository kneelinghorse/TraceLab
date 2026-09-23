/**
 * The caller's Spaces (PERSONAL-2, decision #533).
 *
 * Mirrors GET /api/v1/spaces: the Spaces the caller may create a project in, their
 * own personal Space first. Members get the Spaces they belong to; owner and admin
 * get every Space. The server checks membership again on create, so this list only
 * shapes the picker.
 */

import { httpClient } from "./http";

export type Space = {
  id: string;
  name: string;
  created_at: string;
  // Set on a personal Space; the caller's own reads "My Space".
  personal_owner_id: string | null;
};

export const spacesApi = {
  list(): Promise<Space[]> {
    return httpClient.get("/spaces");
  },
};
