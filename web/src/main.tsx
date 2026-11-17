import "@fontsource-variable/inter";
import "./styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { startLocale } from "./i18n";
import { ThemeProvider } from "./theme";

// Before the first render: every text and format reads the language of the page.
startLocale();

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
);
