import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "企业知识问答",
  description: "Enterprise QA system S1 shell",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
