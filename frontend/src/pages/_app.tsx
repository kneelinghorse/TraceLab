import type { AppProps } from "next/app";
import Head from "next/head";
import { Inter } from "next/font/google";

import "@oods/tokens/css";
import "@/styles/globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { RoleProvider } from "@/contexts/RoleContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { AppShell } from "@/components/AppShell";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export default function MissionProtocolApp({ Component, pageProps }: AppProps) {
  return (
    <>
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>TraceLab</title>
      </Head>
      <AuthProvider>
        <RoleProvider>
          <ThemeProvider>
            <div className={`${inter.variable} font-sans min-h-screen`}>
              <AppShell><Component {...pageProps} /></AppShell>
            </div>
          </ThemeProvider>
        </RoleProvider>
      </AuthProvider>
    </>
  );
}
