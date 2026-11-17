// English (British spelling, as the numbers and dates: en-GB).

import type { Messages } from "./es";

export const en: Messages = {
  app: {
    name: "Mallorca in data",
  },
  dashboards: {
    home: {
      label: "Home",
      title: "Mallorca in data",
      description:
        "Water, climate, tourism and energy on the island, compared with what is normal for each month. Fifteen " +
        "open sources, with their quality checked on every load.",
    },
    tourism: {
      label: "Tourism and resources",
      title: "Tourism and resources",
      description: "How many tourists arrive each month, and what happens to water and electricity at the same time.",
    },
    climate: {
      label: "Climate and water",
      title: "Climate and water",
      description: "Aquifer reserves, rainfall of the hydrological year and temperature against normal.",
    },
    mobility: {
      label: "Mobility",
      title: "Mobility",
      description:
        "Scheduled bus, train and metro service (EMT in Palma and CTM across the island) against the population of " +
        "each municipality.",
    },
    weather: {
      label: "Weather and environment",
      title: "Weather and environment",
      description: "Temperature, air quality, waves, weather episodes and earthquakes.",
    },
    explorer: {
      label: "Explorer",
      title: "Series explorer",
      description: "Any series of the platform, day by day: source, metric and station, with its quality and anomalies.",
    },
    operations: {
      label: "Operations",
      title: "Platform operations",
      description: "Status of each source, quality rules, detected anomalies and proposed corrections.",
    },
  },
  layout: {
    dashboards: "Dashboards",
    openMenu: "Open the menu",
    closeMenu: "Close the menu",
    darkMode: "Dark mode",
    lightMode: "Light mode",
    switchToDark: "Switch to dark mode",
    switchToLight: "Switch to light mode",
    language: "Language",
    catalogue: "Catalogue",
    footer:
      "Open data from AEMET, SOCIB, EEA, REData, IGN, INE, EMT, CTM, SEGITTUR, Govern de les Illes Balears and " +
      "Open-Meteo. Map © OpenStreetMap.",
  },
  data: {
    loadError: (error: string) => `The data could not be loaded: ${error}`,
    empty: "No data",
  },
  format: {
    lessThanAnHourAgo: "less than 1 h ago",
    thousands: "k",
    millions: "M",
  },
};
