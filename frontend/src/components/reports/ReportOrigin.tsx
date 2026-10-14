import Link from "next/link";
import type { ReportOriginLabel } from "@/lib/api/reports";

export function ReportOrigin({ report }: { report: ReportOriginLabel }) {
  if (!report.origin_label) return null;
  return report.origin_href
    ? <Link href={report.origin_href} className="text-accent-text underline underline-offset-4">{report.origin_label}</Link>
    : <span>{report.origin_label}</span>;
}
