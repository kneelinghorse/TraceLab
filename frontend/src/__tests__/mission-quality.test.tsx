import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import fixtures from "../../tests/fixtures/mission-quality.json";
import { MissionFailureDetails, MissionQualitySummary, RawQualityData } from "@/components/missions/MissionQuality";
import type { ApiMission } from "@/types/mission";

afterEach(cleanup);
const mission = (value: unknown) => structuredClone(value) as ApiMission;

it("describes a supported sample without turning six supported claims into report-wide accuracy", () => {
  const { container } = render(<MissionQualitySummary mission={mission(fixtures.supported_sample)} />);
  expect(screen.getByText("No detected material issue")).toBeVisible();
  expect(screen.getByText("Sampled verification; report-wide accuracy unknown")).toBeVisible();
  expect(container.textContent).not.toMatch(/%|percent|100|6/);
});

it("separates missing cited evidence from operational retrieval counts", () => {
  const item = mission(fixtures.missing_cited_body);
  const { container } = render(<><MissionQualitySummary mission={item} /><RawQualityData mission={item} /></>);
  expect(screen.getByText("Usable with warnings")).toBeVisible();
  expect(screen.getByText("1 cited source is missing.")).toBeVisible();
  expect(screen.getByText("1 cited source has no readable body.")).toBeVisible();
  expect(screen.getByText("Raw quality data").closest("details")).not.toHaveAttribute("open");
  expect(container.querySelector("pre")?.textContent).toContain('"retrieval_state"');
  expect(container.querySelector("pre")?.textContent).toContain('"citation_surface"');
  expect(container.textContent).not.toContain("%");
});

it("keeps legacy uncertainty even when an old field says clean", () => {
  render(<MissionQualitySummary mission={mission(fixtures.legacy_uncertainty)} />);
  expect(screen.getByText("Quality not assessed for this run")).toBeVisible();
  expect(screen.queryByText("No detected material issue")).toBeNull();
});

it("renders the live unassessed-claims warning in plain language", () => {
  render(<MissionQualitySummary mission={mission(fixtures.live_warning)} />);
  expect(screen.getByText("3 claims were not assessed.")).toBeVisible();
  expect(screen.queryByText(/critique_unassessed/)).toBeNull();
});

it("retains unknown reason data while giving the reader a generic explanation", () => {
  const item = mission(fixtures.live_warning);
  item.execution_metadata.final_outcome = { quality_gate_failures: ["future_reason_v9"] };
  const { container } = render(<><MissionQualitySummary mission={item} /><RawQualityData mission={item} /></>);
  expect(screen.getByText("Additional quality issue reported; see Raw quality data in Details.")).toBeVisible();
  expect(container.querySelector("pre")?.textContent).toContain("future_reason_v9");
});

it("uses the forensic copy only when the execution quality record is absent", () => {
  const item = mission(fixtures.supported_sample);
  delete item.execution_metadata.quality_record;
  render(<MissionQualitySummary mission={item} />);
  expect(screen.getByText("No detected material issue")).toBeVisible();
});

it("discloses unknown verification scope without turning a legacy schema5 record into clean", () => {
  render(<MissionQualitySummary mission={mission(fixtures.legacy_schema5_unknown)} />);
  expect(screen.getByText("Usable with warnings")).toBeVisible();
  expect(screen.getByText("Verification scope unknown; report-wide accuracy unknown")).toBeVisible();
  expect(screen.getByText("Claim assessment is unavailable or incomplete.")).toBeVisible();
});

it("explains a second provider failure with its classification source and request-shape availability", () => {
  const { container } = render(<MissionFailureDetails mission={mission(fixtures.failed_retained_memory)} />);
  expect(screen.getByText("Provider failed again during retained-memory finalization.")).toBeVisible();
  expect(screen.getByText("Invalid message structure")).toBeVisible();
  expect(screen.getByText("Provider message pattern")).toBeVisible();
  expect(screen.getByText("Request shape available.")).toBeVisible();
  expect(container.textContent).not.toContain("%");
});

it("distinguishes an unknown finish from another provider failure", () => {
  const item = mission(fixtures.failed_retained_memory);
  item.execution_metadata.synthesis_telemetry = { generation_recovery_result: "unknown_finish", provider_attempts: [] };
  render(<MissionFailureDetails mission={item} />);
  expect(screen.getByText("Finalization returned a response without a proven finish reason.")).toBeVisible();
  expect(screen.queryByText(/Provider failed again/)).toBeNull();
});

it.each(["future_subtype", "constructor"])("keeps unknown subtype %s in raw data without exposing provider error text", subtype => {
  const item = mission(fixtures.failed_retained_memory);
  item.execution_metadata.synthesis_telemetry = { generation_recovery_result: "future_result", provider_attempts: [{ failure: { message: "private provider error", rejection: { version: 1, subtype, subtype_source: "future_source" }, request_shape: { version: 1, available: false } } }] };
  const { container } = render(<><MissionFailureDetails mission={item} /><RawQualityData mission={item} /></>);
  expect(screen.getByText("Unknown rejection subtype")).toBeVisible();
  expect(screen.getByText("Unknown classification source")).toBeVisible();
  expect(screen.getByText("Request shape unavailable.")).toBeVisible();
  expect(container.querySelector("pre")?.textContent).toContain(subtype);
  expect(container.querySelector("pre")?.textContent).toContain("future_result");
  expect(container.textContent).not.toContain("private provider error");
});

it("treats an unknown delivery tier as unknown, including prototype property names", () => {
  const item = mission(fixtures.supported_sample);
  item.execution_metadata.final_outcome = { delivery_quality: "constructor" };
  render(<MissionQualitySummary mission={item} />);
  expect(screen.getByText("Quality outcome unknown")).toBeVisible();
});

it.each([
  ["context_limit", "Context limit exceeded"], ["unsupported_parameter", "Unsupported parameter"],
  ["unsupported_value", "Unsupported parameter value"], ["content_rejection", "Content rejected"],
  ["invalid_json", "Invalid JSON"], ["invalid_message_structure", "Invalid message structure"], ["unknown", "Unknown rejection subtype"],
])("keeps %s distinct without deriving it from the error message", (subtype, label) => {
  const item = mission(fixtures.failed_retained_memory);
  item.execution_metadata.synthesis_telemetry = { provider_attempts: [{ failure: { rejection: { version: 1, subtype, subtype_source: "code" } } }] };
  const { container } = render(<MissionFailureDetails mission={item} />);
  expect(screen.getByText(label)).toBeVisible();
  expect(screen.getByText("Provider error code")).toBeVisible();
  expect(screen.getByText("Request shape availability not recorded.")).toBeVisible();
  expect(container.textContent).not.toContain("%");
});

it.each([["degraded", "Degraded result"], ["failed", "Failed quality checks"]])("names the %s tier without losing independent reasons", (delivery, label) => {
  const item = mission(fixtures.live_warning);
  item.execution_metadata.final_outcome = { delivery_quality: delivery, quality_gate_failures: ["critique_unassessed_claims_3"] };
  const { container } = render(<MissionQualitySummary mission={item} />);
  expect(screen.getByText(label)).toBeVisible();
  expect(screen.getByText("3 claims were not assessed.")).toBeVisible();
  expect(container.textContent).not.toContain("%");
});

it.each([null, [], { schema_version: 5, delivery_quality: "clean", verification: {} }])("does not infer assessment from malformed quality data %j", raw => {
  const item = mission(fixtures.supported_sample);
  item.execution_metadata.quality_record = raw;
  item.result_protocol = null;
  render(<MissionQualitySummary mission={item} />);
  expect(screen.getByText("Quality not assessed for this run")).toBeVisible();
});


it("schema 6 keeps unassessed sample coverage distinct from a detected issue", () => {
  const item = mission(fixtures.supported_sample);
  item.execution_metadata.quality_record = {
    ...item.execution_metadata.quality_record as object,
    schema_version: 6,
    claim_assessment: { version: 2, assessed: 11, supported: 11, unassessed: 1, declared_context: 1, contradicted: 0, unverified_contradicted: 0, inconsistent: 0, unknown_verdicts: 0 },
  };
  const { container } = render(<MissionQualitySummary mission={item} />);
  expect(screen.getByText("No detected material issue")).toBeVisible();
  expect(screen.getByText("Sampled verification; report-wide accuracy unknown")).toBeVisible();
  expect(screen.queryByRole("list")).toBeNull();
  expect(container.textContent).not.toMatch(/%|percent/);
});

it.each([
  ["critique_unverified_contradiction_1", "1 possible contradiction could not be verified."],
  ["critique_unverified_contradiction_2", "2 possible contradictions could not be verified."],
  ["critique_internal_inconsistency_1", "1 claim was flagged as inconsistent within the report."],
  ["critique_internal_inconsistency_2", "2 claims were flagged as inconsistent within the report."],
  ["critique_unknown_verdicts_1", "The verification verdict for 1 claim could not be read."],
  ["critique_unknown_verdicts_2", "The verification verdict for 2 claims could not be read."],
  ["critique_assessment_provenance_error", "Detailed verification provenance is unavailable; an earlier assessment format was retained."],
])("explains schema 6 warning %s without claiming a verified contradiction", (reason, explanation) => {
  const item = mission(fixtures.supported_sample);
  item.execution_metadata.quality_record = { ...item.execution_metadata.quality_record as object, schema_version: 6 };
  item.execution_metadata.final_outcome = { delivery_quality: "usable_with_warning", quality_gate_failures: [reason] };
  const { container } = render(<><MissionQualitySummary mission={item} /><RawQualityData mission={item} /></>);
  expect(screen.getByText("Usable with warnings")).toBeVisible();
  expect(screen.getByText(explanation)).toBeVisible();
  expect(screen.getByText("Sampled verification; report-wide accuracy unknown")).toBeVisible();
  expect(container.querySelector("pre")?.textContent).toContain(reason);
  expect(screen.queryByText(/assessed claims? (was|were) contradicted/)).toBeNull();
});
