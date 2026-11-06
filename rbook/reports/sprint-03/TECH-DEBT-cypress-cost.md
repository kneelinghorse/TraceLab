# Tech Debt: Cypress Cost Dependency - Sprint 03

**Date Identified:** 2025-11-08  
**Sprint:** Sprint 03 - Mission Protocol Integration  
**Mission:** B3.4 - UI Integration (Completed)  
**Severity:** HIGH - Cost Impact  
**Status:** Documented for Sprint End Resolution

---

## Issue Summary

Cypress was introduced as E2E testing framework in B3.4 (UI Integration) without proper cost evaluation. Cypress paid tier is **$70/month**, which is inappropriate for solo builder deployment.

---

## Context

### What Happened
- **B3.4 mission deliverable:** "E2E tests: cypress/e2e/mission-protocol.cy.ts for critical user flows"
- Cypress implemented in `frontend/` for Next.js E2E testing
- Cost implication NOT flagged during mission planning
- User explicitly stated "solo builder" context from project start

### Current State
- B3.4 completed with Cypress integration
- Frontend tests written using Cypress
- Mid-sprint - NOT ripping out now
- Will address at sprint end

### Cost Structure (Cypress)
- **Open Source (Free):** Local testing only, unlimited tests
- **Team Plan:** $70/month - CI integration, parallelization, cloud recording
- **Business Plan:** $300/month - Advanced features, analytics
- **Enterprise:** Custom pricing

---

## Root Cause Analysis

### Planning Failure
1. **Cost review not performed** during B3.4 mission planning
2. **Tooling alternatives not evaluated** against solo builder constraints
3. **Roadmap template** (foundational-docs/roadmap.md) recommended Cypress without cost disclaimer
4. **No cost checklist** in mission validation protocol

### Why This Matters
- Solo builder budget constraints differ from enterprise/team deployments
- Open source ≠ free-to-operate (CI/CD, cloud features often paywalled)
- $70/month = $840/year for single-purpose E2E testing tool
- Other project costs: OpenAI API, Railway hosting, Qdrant - total budget matters

---

## Impact Assessment

### Immediate Impact
- ✅ **Tests work locally:** Cypress open source functional for development
- ⚠️ **CI/CD limited:** Cannot use Cypress Cloud features without paid tier
- ⚠️ **Parallelization blocked:** Free tier = single-threaded only
- ⚠️ **Recording/debugging limited:** No cloud test recordings without paid plan

### Sprint 03 Impact
- B3.4 deliverables met (tests exist and run)
- E2E validation functional for local development
- No immediate blocker to sprint completion
- Cost burden deferred to future deployment decisions

### Long-Term Impact
- **If keeping Cypress:** $840/year recurring cost or feature limitations
- **If migrating:** Engineering time to rewrite E2E tests
- **If skipping E2E:** Reduced test coverage, higher manual QA burden

---

## Alternative Solutions (Sprint End Evaluation)

### Option 1: Stay on Cypress Free Tier (No Action)
**Approach:** Use open source Cypress, accept limitations

**Pros:**
- ✅ Zero additional cost
- ✅ No code changes required
- ✅ Tests already written and working
- ✅ Local development fully functional

**Cons:**
- ❌ No CI/CD integration with Cypress Cloud
- ❌ No parallel test execution
- ❌ No test recording/replay for debugging
- ❌ Limited dashboard/analytics

**Cost:** $0/month  
**Engineering Time:** 0 hours

---

### Option 2: Migrate to Playwright (Recommended)
**Approach:** Replace Cypress with Playwright (Microsoft, truly free)

**Pros:**
- ✅ Completely free (no paid tiers, no feature gates)
- ✅ Better performance (faster execution)
- ✅ Native TypeScript support
- ✅ Better CI/CD integration (GitHub Actions)
- ✅ Cross-browser testing included
- ✅ API testing built-in
- ✅ Parallel execution free
- ✅ Trace viewer free (better than Cypress Cloud recordings)
- ✅ Industry standard for Next.js/React

**Cons:**
- ❌ Requires test rewrite (different API syntax)
- ❌ Learning curve for new tool

**Cost:** $0/month  
**Engineering Time:** 4-8 hours (rewrite ~10-15 E2E tests)

**Migration Path:**
```bash
# Install Playwright
npm install --save-dev @playwright/test

# Convert tests (example)
# Cypress:
cy.visit('/missions')
cy.get('[data-testid="create-button"]').click()

# Playwright:
await page.goto('/missions')
await page.getByTestId('create-button').click()
```

---

### Option 3: Use Testing Library + Happy DOM
**Approach:** Component testing only, skip true E2E

**Pros:**
- ✅ Completely free
- ✅ Faster test execution (no browser)
- ✅ Better integration with Next.js
- ✅ Testing Library = React standard

**Cons:**
- ❌ Not true E2E (doesn't test full browser stack)
- ❌ Misses navigation/routing issues
- ❌ Can't test real user workflows

**Cost:** $0/month  
**Engineering Time:** 6-10 hours (rewrite as component tests)

---

### Option 4: Manual E2E Testing Only
**Approach:** Remove automated E2E, rely on manual QA

**Pros:**
- ✅ Zero tooling cost
- ✅ Minimal engineering time

**Cons:**
- ❌ Regression risk (no automated safety net)
- ❌ Manual QA time increases
- ❌ Not sustainable for rapid iteration

**Cost:** $0/month  
**Engineering Time:** 1 hour (remove Cypress)

---

## Recommendation

**For Sprint End: Migrate to Playwright**

### Rationale
1. **Cost:** Playwright is truly free (no hidden paywalls)
2. **Quality:** Better tool for Next.js/React (faster, more reliable)
3. **Solo builder aligned:** Built for CI/CD, no team features to pay for
4. **Industry standard:** Used by Vercel, Next.js team, major projects
5. **One-time cost:** 4-8 hours engineering vs $840/year recurring

### Migration Plan
1. **Sprint End (Sprint 03 Retrospective):**
   - Review this tech debt document
   - Approve Playwright migration
   - Add migration mission to Sprint 04 backlog

2. **Sprint 04 (or dedicated tech debt sprint):**
   - Create mission: "B4.X - Migrate E2E Tests from Cypress to Playwright"
   - Allocate 1 day engineering time
   - Deliverables:
     - Install Playwright
     - Migrate existing E2E tests (mission-protocol.cy.ts → mission-protocol.spec.ts)
     - Update CI/CD config
     - Remove Cypress dependencies
     - Update documentation

3. **Validation:**
   - All existing E2E tests pass with Playwright
   - CI/CD runs tests successfully
   - Trace viewer functional for debugging
   - Documentation updated

---

## Cost Comparison Table

| Tool | Monthly Cost | Annual Cost | CI/CD | Parallel | Recordings | Free Tier Limits |
|------|-------------|-------------|-------|----------|------------|------------------|
| **Cypress Free** | $0 | $0 | ❌ | ❌ | ❌ | Local only |
| **Cypress Team** | $70 | $840 | ✅ | ✅ | ✅ | 5 users |
| **Playwright** | $0 | $0 | ✅ | ✅ | ✅ | None |
| **Testing Library** | $0 | $0 | ✅ | ✅ | N/A | None |

---

## Lessons Learned

### For Future Mission Planning

1. **Add cost review checklist:**
   - Evaluate all new dependencies for cost implications
   - Check for free vs paid tiers
   - Consider solo builder vs team/enterprise pricing
   - Document cost in mission planning notes

2. **Update mission validation protocol:**
   - Add "Cost Review" validator for new tooling
   - Require alternatives analysis for paid tools
   - Flag budget impact in mission notes

3. **Update roadmap template:**
   - Add cost disclaimers for Cypress recommendation
   - Include Playwright as primary recommendation for solo builders
   - Clarify open source ≠ free-to-operate

4. **Enhance operations guide:**
   - Add "Tool Selection Criteria" section
   - Include budget considerations
   - Document approved tooling stack with cost analysis

---

## Action Items

### Immediate (Sprint 03 End)
- [ ] Review this tech debt document in sprint retrospective
- [ ] Approve migration strategy (recommend Playwright)
- [ ] Update Sprint 03 success criteria to note tech debt item
- [ ] Document in sprint retrospective report

### Sprint 04 (or Next Available)
- [ ] Create migration mission: "Migrate E2E Tests to Playwright"
- [ ] Allocate 1 day engineering time
- [ ] Execute migration
- [ ] Validate all tests pass
- [ ] Remove Cypress dependencies
- [ ] Close tech debt item

### Process Improvements
- [ ] Add cost review to mission planning template
- [ ] Update operations-guide.md with tool selection criteria
- [ ] Update roadmap.md with Playwright recommendation + cost context
- [ ] Add "Budget Impact" field to mission YAML template

---

## References

### Cypress Pricing
- Source: https://www.cypress.io/pricing
- Team Plan: $70/month (5 users, 500 monthly tests)
- Business Plan: $300/month (unlimited users, 500 monthly tests)
- Free tier limits: Local testing only, no CI/CD features

### Playwright (Recommended Alternative)
- Source: https://playwright.dev
- License: Apache 2.0 (truly open source)
- Cost: $0 (all features free)
- Maintained by: Microsoft
- CI/CD: GitHub Actions integration built-in
- Trace viewer: Free (better than Cypress Cloud)

### Testing Library
- Source: https://testing-library.com
- License: MIT
- Cost: $0
- Best for: Component testing (not full E2E)

---

## Sprint 03 Impact Statement

**For Sprint 03 Retrospective:**

> "B3.4 (UI Integration) introduced Cypress as E2E testing framework without cost evaluation. Cypress paid tier is $70/month, inappropriate for solo builder constraints. Tests functional on free tier but lack CI/CD integration. Recommend migration to Playwright (truly free) in Sprint 04. Engineering cost: 4-8 hours one-time vs $840/year recurring. Root cause: Missing cost review in mission planning validation protocol. Process improvement: Add cost checklist to mission template."

---

**Status:** OPEN - Awaiting Sprint End Resolution  
**Owner:** Solo Builder + AI Agent  
**Target Resolution:** Sprint 04 or Tech Debt Sprint  
**Cost Impact if No Action:** $0/month (stay on free tier) or $840/year (paid tier)  
**Cost Impact if Migrate:** $0/month + 4-8 hours engineering time

---

**Last Updated:** 2025-11-08  
**Next Review:** Sprint 03 Retrospective (End of Sprint)

