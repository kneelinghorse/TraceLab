import { diag, DiagConsoleLogger, DiagLogLevel, metrics, trace } from '@opentelemetry/api';

import { AppConfig } from '../config.js';

/**
 * Lightweight telemetry facade that exposes OpenTelemetry meters and tracers.
 *
 * The pipeline records counters and histograms through this class. Exporters
 * can be configured externally by registering an OpenTelemetry SDK in the host
 * application. When no SDK is registered the global APIs operate as no-ops,
 * preserving zero-cost instrumentation while keeping the integration hooks.
 */
export class Telemetry {
  constructor(private readonly config: AppConfig) {
    const diagnosticLevel = process.env.OTEL_DIAGNOSTIC_LOG_LEVEL?.toUpperCase() as
      | keyof typeof DiagLogLevel
      | undefined;
    if (diagnosticLevel && DiagLogLevel[diagnosticLevel] !== undefined) {
      diag.setLogger(new DiagConsoleLogger(), DiagLogLevel[diagnosticLevel]);
    }
  }

  async start(): Promise<void> {
    if (this.config.telemetryEnabled) {
      diag.debug('Telemetry hooks active – ensure an OpenTelemetry SDK is installed to export data.');
    }
  }

  async shutdown(): Promise<void> {
    // No-op: exporters (if registered) manage their own lifecycle.
  }

  tracer(name: string) {
    return trace.getTracer(name);
  }

  meter(name: string) {
    return metrics.getMeter(name);
  }

  counter(
    name: string,
    options?: Parameters<ReturnType<typeof metrics.getMeter>['createCounter']>[1],
  ) {
    return this.meter('markdown-ingestion').createCounter(name, options);
  }

  histogram(
    name: string,
    options?: Parameters<ReturnType<typeof metrics.getMeter>['createHistogram']>[1],
  ) {
    return this.meter('markdown-ingestion').createHistogram(name, options);
  }
}
