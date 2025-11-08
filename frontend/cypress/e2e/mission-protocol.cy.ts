describe("Mission Protocol UI", () => {
  const missionsUrl = "http://localhost:8000/api/v1/missions";
  const missionId = "11111111-1111-1111-1111-111111111111";

  it("renders backlog view and validates new mission workflow", () => {
    cy.intercept("GET", missionsUrl, { fixture: "missions.json" }).as("listMissions");
    cy.visit("/missions");
    cy.wait("@listMissions");
    cy.contains("Mission Protocol Backlog").should("be.visible");
    cy.contains("UI Integration + Quality Gates").should("be.visible");

    cy.contains("Start New Mission").click();
    cy.contains("Create Mission").click();
    cy.contains("Project ID must be a valid UUID").should("be.visible");
    cy.contains("Mission ID is required").should("be.visible");

    cy.contains("Mission Protocol Backlog").parent().within(() => {
      cy.contains("View details").first().should("have.attr", "href");
    });
  });

  it("renders mission detail view with quality gates", () => {
    cy.intercept("GET", missionsUrl, { fixture: "missions.json" }).as("listMissions");
    cy.intercept("GET", `${missionsUrl}/${missionId}`, { fixture: "mission-detail.json" }).as("missionDetail");
    cy.intercept("GET", `http://localhost:8000/api/v1/quality/missions/${missionId}/quality`, {
      fixture: "quality-report.json",
    }).as("qualityReport");

    cy.visit(`/missions/${missionId}`);
    cy.wait(["@missionDetail", "@qualityReport"]);

    cy.contains("Mission ID: B3.4").should("be.visible");
    cy.contains("Research Readiness").should("be.visible");
    cy.contains("traceability").parent().within(() => {
      cy.contains("fail").should("be.visible");
    });
    cy.contains("Update Mission").should("be.visible");
  });
});
