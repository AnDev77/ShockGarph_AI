import type { Metadata } from "next";
import { Provider } from "@/components/provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShockGraph AI",
  description: "시장 내재확률과 과거 시나리오별 ETF 반응 분포를 살펴보는 거시경제 이벤트 기반 자산 리스크 분석 도구",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body><Provider>{children}</Provider></body>
    </html>
  );
}
