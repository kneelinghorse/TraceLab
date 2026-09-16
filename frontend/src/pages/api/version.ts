// ABOUTME: Serves the commit sha this frontend bundle was BUILT from.
// ABOUTME: The post-deploy check polls it to prove a deployment is actually live (CI-6).

import type { NextApiRequest, NextApiResponse } from "next";

/**
 * NEXT_PUBLIC_COMMIT_SHA is inlined by next.config.ts at build time, so this returns the
 * commit the served assets were compiled from rather than whatever the running container's
 * environment happens to say now. Railway reports a deployment SUCCESS before the new process
 * serves traffic, so the served sha is the only trustworthy "the deploy landed" signal.
 */
export default function handler(_req: NextApiRequest, res: NextApiResponse) {
  res.setHeader("Cache-Control", "no-store");
  res.status(200).json({ commit: process.env.NEXT_PUBLIC_COMMIT_SHA ?? "unknown" });
}
