import type { Metadata } from "next";
import { ResearchDashboard } from "@/components/research-dashboard";

export const metadata: Metadata = { title: "연구 노트 | ShockGraph AI" };

export default function Methodology() {
  return <ResearchDashboard />;
}
