import type { AppProps } from "next/app";
import Head from "next/head";
import { Inter } from "next/font/google";

import "@/styles/globals.css";
import { AuthProvider } from "@/contexts/AuthContext";
import { Navigation } from "@/components/Navigation";
import { useRouter } from "next/router";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export default function MissionProtocolApp({ Component, pageProps }: AppProps) {
  const router = useRouter();
  const showNav = !["/"].includes(router.pathname);

  return (
    <>
      <Head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>TraceLab</title>
      </Head>
      <AuthProvider>
        <div className={`${inter.variable} font-sans bg-[hsl(var(--background))] min-h-screen`}>
          {showNav && <Navigation />}
          <Component {...pageProps} />
        </div>
      </AuthProvider>
    </>
  );
}
