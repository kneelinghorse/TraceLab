import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { PlannedScopeSummary, ScopeOutcomePanel } from "@/components/missions/AuthoredScope";
import type { ApiMission } from "@/types/mission";

const fixture = path.resolve("../tests/fixtures/authored_scope_v1");
const contract = JSON.parse(readFileSync(path.join(fixture, "canonical-contract.json"), "utf8"));
const manifest = JSON.parse(readFileSync(path.join(fixture, "manifest.json"), "utf8"));
const auditFor = (name: string) => JSON.parse(readFileSync(path.join(fixture, `${name}-expected.json`), "utf8"));
function mission(name: string): ApiMission {
  const audit = auditFor(name);
  const output = manifest.outputs.find((item: { name: string }) => item.name === name);
  return { status: output.mission_outcome === "complete" ? "completed" : "validation_failed", execution_metadata: { final_outcome: { authored_scope_validation: audit, delivery_quality: output.delivery_quality, quality_gate_failures: ["independent_quality_warning"] }, quality_record: { report_word_count: 9999 } }, result_protocol: { report_metadata: { forensic: { authored_scope: { policy: contract.authored_scope, policy_sha256: audit.policy_sha256 } }, references: 2 } } } as unknown as ApiMission;
}
afterEach(cleanup);

it.each(["compliant", "partial", "too_long", "22_sources"])("uses the immutable %s persisted audit, never legacy word or final-citation counts", name => {
  render(<ScopeOutcomePanel mission={mission(name)} />);
  const audit = auditFor(name);
  expect(screen.getByText(`${audit.persisted.words} words · 300–500 words requested`)).toBeVisible();
  expect(screen.getByText(`${audit.consulted_count} · maximum 2`)).toBeVisible();
  expect(screen.queryByText(/9999/)).not.toBeInTheDocument();
  expect(screen.getByText(/Independent research quality warning/)).toBeVisible();
  expect(screen.getByText("independent quality warning")).toBeVisible();
  expect(screen.getByRole("heading", { name: audit.verdict === "partial" ? "Partial result — source availability warning" : audit.verdict === "violated" ? "Scope validation failed" : "Recorded scope limits met" })).toBeVisible();
  if (name === "partial") expect(screen.getByText("timeout")).toBeVisible();
  if (name === "22_sources") expect(screen.getByText("The run consulted more source pages than allowed.")).toBeVisible();
});

it.each([undefined, {}, { ...auditFor("compliant"), counter_version: "legacy" }, { ...auditFor("compliant"), persisted: { words: "370" } }, { ...auditFor("compliant"), violations: ["contradiction"] }])("does not infer compliance from missing, older or malformed audit %j", value => {
  const item = mission("compliant");
  item.execution_metadata = { final_outcome: { authored_scope_validation: value } };
  render(<ScopeOutcomePanel mission={item} />);
  expect(screen.getByRole("heading", { name: "Scope outcome unknown" })).toBeVisible();
});

it("does not pair an audit with a different stored scope policy", () => {
  const item = mission("compliant");
  item.result_protocol = { report_metadata: { forensic: { authored_scope: { policy: contract.authored_scope, policy_sha256: "different" } } } };
  render(<ScopeOutcomePanel mission={item} />);
  expect(screen.getByText(/requested bounds unavailable/)).toBeVisible();
});

it("distinguishes exact pages from reference seeds without implying deployed enforcement", () => {
  render(<PlannedScopeSummary scope={contract.authored_scope} />);
  expect(screen.getByText(/Only these exact pages/)).toBeVisible();
  expect(screen.getByText(/300–500 words/)).toBeVisible();
  expect(screen.getByText(/does not verify the deployed worker/)).toBeVisible();
  cleanup();
  render(<PlannedScopeSummary scope={{ ...contract.authored_scope, restriction: "unrestricted", allowed_urls: [], allowed_domains: [] }} />);
  expect(screen.getByText("Sources are unrestricted.")).toBeVisible();
  expect(screen.queryByText(/Only these exact pages/)).not.toBeInTheDocument();
});
