import { Html, Head, Main, NextScript } from "next/document";

import { themeBootstrapScript } from "@/lib/theme";

export default function Document() {
  return (
    <Html lang="en" data-brand="A" suppressHydrationWarning>
      <Head>
        <link rel="icon" href="/favicon.ico" sizes="48x48" />
        <link rel="icon" href="/icon.svg" type="image/svg+xml" />
        <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
