// ABOUTME: Tombstone for the /missions/queue alias retired in Sprint 54 (ALIAS-1).
// ABOUTME: Without it the sibling [id] dynamic route answers 200 and the retirement is fake.

import type { GetStaticProps } from "next";

/**
 * The alias used to re-export the missions index. Deleting that file was not enough: the
 * sibling `[id].tsx` matches /missions/queue with id="queue" and renders a mission detail
 * page for a mission that does not exist, answering 200. This returns a real 404 instead,
 * which is what the route-migration map now documents.
 */
export const getStaticProps: GetStaticProps = async () => ({ notFound: true });

export default function RetiredMissionQueue() {
  return null;
}
