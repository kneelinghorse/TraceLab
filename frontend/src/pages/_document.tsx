import { Html, Head, Main, NextScript } from "next/document";

import { themeBootstrapScript } from "@/lib/theme";

export default function Document() {
  return (
    <Html lang="en" data-brand="A" data-theme="light" suppressHydrationWarning>
      <Head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </Head>
      <body>
        <Main />
        <NextScript />
      </body>
    </Html>
  );
}
