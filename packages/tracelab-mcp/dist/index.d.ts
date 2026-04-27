#!/usr/bin/env node
/**
 * TraceLab MCP Server
 *
 * Provides 7 action-clustered tools for AI agents to perform complete
 * research-to-output loops against TraceLab's knowledge base. T41.7
 * (sprint-41) collapsed the prior ~24 flat tools into topical clusters
 * matching the cmos-mcp pattern. Each cluster dispatches by an `action`
 * parameter to the existing per-action handlers below.
 *
 * Clusters:
 * 1. tracelab_search           — actions: knowledge
 * 2. tracelab_project          — actions: list, create, update, stats
 * 3. tracelab_collection       — actions: list, get, export, create, add, synthesize
 * 4. tracelab_report           — actions: create, list, get, export
 * 5. tracelab_document         — actions: upload, get_content
 * 6. tracelab_mission          — actions: create, list, get, update (CRUD)
 * 7. tracelab_mission_execution — actions: submit, status, preview (DS-bound lifecycle)
 */
declare const LEGACY_TO_CLUSTER: Record<string, {
    tool: string;
    action: string;
}>;
export { LEGACY_TO_CLUSTER };
export declare function handleListMissions(args: unknown): Promise<{
    content: {
        type: string;
        text: string;
    }[];
}>;
export declare function handleGetMission(args: unknown): Promise<{
    content: {
        type: string;
        text: string;
    }[];
}>;
export declare function handleTracelabSearch(args: unknown): Promise<{
    content: {
        type: string;
        text: string;
    }[];
}>;
export declare function handleTracelabProject(args: unknown): Promise<{
    content: {
        type: string;
        text: string;
    }[];
}>;
export declare function handleTracelabCollection(args: unknown): Promise<{
    content: {
        type: string;
        text: string;
    }[];
}>;
export declare function handleTracelabReport(args: unknown): Promise<{
    content: {
        type: string;
        text: string;
    }[];
}>;
export declare function handleTracelabDocument(args: unknown): Promise<{
    content: {
        type: string;
        text: string;
    }[];
}>;
export declare function handleTracelabMission(args: unknown): Promise<{
    content: {
        type: string;
        text: string;
    }[];
}>;
export declare function handleTracelabMissionExecution(args: unknown): Promise<{
    content: {
        type: string;
        text: string;
    }[];
}>;
export declare const CLUSTER_ACTIONS: {
    readonly tracelab_search: readonly ["knowledge"];
    readonly tracelab_project: readonly ["list", "create", "update", "stats"];
    readonly tracelab_collection: readonly ["list", "get", "export", "create", "add", "synthesize"];
    readonly tracelab_report: readonly ["create", "list", "get", "export"];
    readonly tracelab_document: readonly ["upload", "get_content"];
    readonly tracelab_mission: readonly ["create", "list", "get", "update"];
    readonly tracelab_mission_execution: readonly ["submit", "status", "preview"];
};
//# sourceMappingURL=index.d.ts.map