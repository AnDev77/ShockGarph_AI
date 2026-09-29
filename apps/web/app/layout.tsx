import type { Metadata } from "next";
import { Provider } from "@/components/provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShockGraph AI",
  description: "거시 이벤트 확률과 자산 반응을 분리해 읽는 금융 리서치",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body><Provider>{children}</Provider></body>
    </html>
  );
}
