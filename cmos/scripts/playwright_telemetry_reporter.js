const fs = require('fs');
const path = require('path');

class PlaywrightTelemetryReporter {
  constructor(options = {}) {
    this.repoRoot = options.repoRoot
      ? path.resolve(options.repoRoot)
      : path.resolve(__dirname, '..', '..');

    const configuredOutput = options.output || process.env.PLAYWRIGHT_TELEMETRY_OUTPUT;
    const defaultOutput = path.join('telemetry', 'events', '.artifacts', 'playwright-latest.json');
    const resolvedOutput = configuredOutput || defaultOutput;

    this.outputPath = path.isAbsolute(resolvedOutput)
      ? resolvedOutput
      : path.resolve(this.repoRoot, resolvedOutput);

    this.results = [];
    this.startedAt = null;
    this.config = null;
    this.debug = ['1', 'true', 'yes'].includes(String(process.env.TELEMETRY_DEBUG).toLowerCase());
  }

  onBegin(config, suite) {
    this.config = config;
    this.startedAt = new Date();
    this.expectedTests = suite.allTests().length;
  }

  onTestEnd(test, result) {
    const relFile = this._relativePath(test.location.file);
    this.results.push({
      title: test.title,
      file: relFile,
      line: test.location.line,
      column: test.location.column,
      project: result.projectName,
      status: result.status,
      durationMs: result.duration,
      retries: result.retries,
      annotations: result.annotations,
      attachments: result.attachments?.map((attachment) => ({
        name: attachment.name,
        contentType: attachment.contentType,
        path: attachment.path ? this._relativePath(attachment.path) : undefined,
      })),
      errors: (result.errors || []).map((error) => ({
        message: error.error?.message,
        stack: error.error?.stack,
        value: error.error?.value,
      })),
    });
  }

  async onEnd(result) {
    const completedAt = new Date();
    const summary = this._buildSummary(completedAt - this.startedAt);
    const payload = {
      tool: 'playwright',
      generatedAt: this.startedAt?.toISOString(),
      completedAt: completedAt.toISOString(),
      status: result.status,
      summary,
      environment: this._environmentBlock(),
      tests: this.results,
      artifactPath: this._relativePath(this.outputPath),
    };

    await fs.promises.mkdir(path.dirname(this.outputPath), { recursive: true });
    this._log(`Playwright telemetry reporter writing ${this.outputPath}`);
    await fs.promises.writeFile(this.outputPath, JSON.stringify(payload, null, 2));
  }

  _buildSummary(durationMs) {
    const counters = {
      total: this.results.length,
      expected: this.expectedTests,
      passed: 0,
      failed: 0,
      skipped: 0,
      interrupted: 0,
    };

    for (const test of this.results) {
      if (test.status in counters) {
        counters[test.status] += 1;
      } else if (test.status === 'timedOut') {
        counters.failed += 1;
      } else {
        counters.failed += 1;
      }
    }

    return {
      ...counters,
      durationSeconds: Number((durationMs / 1000).toFixed(3)),
      retries: this.results.reduce((sum, test) => sum + (test.retries || 0), 0),
    };
  }

  _environmentBlock() {
    return {
      node: process.version,
      ci: {
        provider: process.env.GITHUB_ACTIONS ? 'github-actions' : null,
        runId: process.env.GITHUB_RUN_ID,
        runNumber: process.env.GITHUB_RUN_NUMBER,
      },
      projects: this.config?.projects?.map((project) => project.name),
      browsers: this.config?.projects?.map((project) => project.use?.browserName).filter(Boolean),
    };
  }

  _relativePath(target) {
    if (!target) {
      return target;
    }

    const absolute = path.isAbsolute(target) ? target : path.resolve(process.cwd(), target);
    if (absolute.startsWith(this.repoRoot)) {
      return path.relative(this.repoRoot, absolute);
    }
    return absolute;
  }

  _log(message) {
    if (this.debug) {
      console.log(`[telemetry] ${message}`);
    }
  }
}

module.exports = PlaywrightTelemetryReporter;
