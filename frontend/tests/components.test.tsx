import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FindingsTable, SeverityCounts, sortFindings } from "@/components/findings/FindingsTable";
import { LimitStamp, SeverityStamp, VerdictStamp } from "@/components/ui/Stamp";

const finding = (code: string, severity: string, block: string | null = "A1") => ({
  code, severity, message: `${code} message`, block, product_id: null, ingredient: "pyraclostrobin", market: "EU",
  evidence: { regulation: "Commission Regulation (EU) 2026/140", snapshot: "eu_mrl:2026-10-27" },
});

describe("stamps", () => {
  it("label statuses and severities with their tone", () => {
    render(<><LimitStamp status="default" /><SeverityStamp severity="blocking" /><VerdictStamp verdict={null} /></>);
    expect(screen.getByText("Por defecto")).toHaveAttribute("data-tone", "risk");
    expect(screen.getByText("Bloquea")).toHaveAttribute("data-tone", "blocking");
    expect(screen.getByText("Sin hallazgos")).toHaveAttribute("data-tone", "ok");
  });
});

describe("findings", () => {
  it("sort by severity", () => {
    const sorted = sortFindings([finding("ROTATION_NOT_CHECKED", "info"), finding("PHI_NOT_MET", "blocking"), finding("DEFAULT_LIMIT", "risk")]);
    expect(sorted.map((f) => f.code)).toEqual(["PHI_NOT_MET", "DEFAULT_LIMIT", "ROTATION_NOT_CHECKED"]);
  });

  it("group by block with titles, messages and evidence", () => {
    render(<FindingsTable groupByBlock findings={[finding("PHI_NOT_MET", "blocking", "A1"), finding("DEFAULT_LIMIT", "risk", "B2")]} />);
    const rows = screen.getAllByRole("row");
    expect(within(rows[1]!).getByText("A1")).toBeInTheDocument();
    expect(screen.getByText("Carencia no cumplida")).toBeInTheDocument();
    expect(screen.getByText("PHI_NOT_MET message")).toBeInTheDocument();
    expect(screen.getAllByText("eu_mrl · 27/10/2026")).toHaveLength(2);
  });

  it("collapse the same finding repeated by two applications", () => {
    render(<FindingsTable findings={[finding("DEFAULT_LIMIT", "risk"), finding("DEFAULT_LIMIT", "risk")]} />);
    expect(screen.getAllByText("Sin LMR específico")).toHaveLength(1);
    expect(screen.getByText("×2")).toBeInTheDocument();
  });

  it("say so when there is nothing", () => {
    render(<FindingsTable findings={[]} />);
    expect(screen.getByText(/Sin hallazgos/)).toBeInTheDocument();
  });

  it("count by severity", () => {
    render(<SeverityCounts findings={[finding("A", "blocking"), finding("B", "blocking"), finding("C", "info")]} />);
    expect(screen.getByText("2 Bloquea")).toHaveAttribute("data-tone", "blocking");
    expect(screen.getByText("0 Riesgo")).toHaveAttribute("data-tone", "neutral");
  });
});
