/**
 * ExportButtons - Export mission data in JSON or YAML format.
 */

import { useState } from "react";
import type { ApiMission } from "@/types/mission";
import type { RelationshipContextResponse, ExportFormat } from "@/types/console";
import { exportMissionAsJson, exportMissionAsYaml, downloadFile } from "@/lib/api/console";

interface ExportButtonsProps {
  mission: ApiMission;
  relationships?: RelationshipContextResponse | null;
  className?: string;
}

export function ExportButtons({ mission, relationships, className = "" }: ExportButtonsProps) {
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async (format: ExportFormat) => {
    setIsExporting(true);
    try {
      const missionId = mission.mission_id ?? mission.id;
      const filename = `mission-${missionId}-${new Date().toISOString().split("T")[0]}`;

      if (format === "json") {
        const content = exportMissionAsJson(mission, relationships ?? undefined);
        downloadFile(content, `${filename}.json`, "application/json");
      } else {
        const content = exportMissionAsYaml(mission, relationships ?? undefined);
        downloadFile(content, `${filename}.yaml`, "text/yaml");
      }
    } catch (error) {
      console.error("Export failed:", error);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <span className="text-sm text-muted">Export:</span>
      <button
        onClick={() => handleExport("json")}
        disabled={isExporting}
        className="text-sm px-3 py-1.5 border border-line-strong text-secondary rounded hover:bg-background disabled:opacity-50 transition-colors"
      >
        JSON
      </button>
      <button
        onClick={() => handleExport("yaml")}
        disabled={isExporting}
        className="text-sm px-3 py-1.5 border border-line-strong text-secondary rounded hover:bg-background disabled:opacity-50 transition-colors"
      >
        YAML
      </button>
    </div>
  );
}
