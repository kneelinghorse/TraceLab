import type { ActivityItemState } from "@/lib/api/activity";

export function activityTitleClass(state?: Pick<ActivityItemState, "viewed">) {
  return state?.viewed ? "font-normal text-secondary" : "font-semibold text-foreground";
}

export function ActivityDot({ isNew }: { isNew?: boolean }) {
  return isNew ? <span aria-hidden="true" data-testid="new-activity-dot" className="mr-2 inline-block h-2 w-2 shrink-0 rounded-full bg-accent align-middle" /> : null;
}
