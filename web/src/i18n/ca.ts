// Catalan (standard, as the Govern de les Illes Balears writes it).

import type { Messages } from "./es";

export const ca: Messages = {
  app: {
    name: "Mallorca en dades",
  },
  dashboards: {
    home: {
      label: "Inici",
      title: "Mallorca en dades",
      description:
        "Aigua, clima, turisme i energia de l’illa, comparats amb el que és normal per a cada mes. Quinze fonts " +
        "obertes, amb la qualitat comprovada a cada càrrega.",
    },
    tourism: {
      label: "Turisme i recursos",
      title: "Turisme i recursos",
      description: "Quants turistes arriben cada mes i què passa alhora amb l’aigua i l’electricitat.",
    },
    climate: {
      label: "Clima i aigua",
      title: "Clima i aigua",
      description: "Reserves dels aqüífers, pluja de l’any hidrològic i temperatura respecte del que és normal.",
    },
    mobility: {
      label: "Mobilitat",
      title: "Mobilitat",
      description:
        "Servei programat d’autobusos, tren i metro (EMT a Palma i CTM a tota l’illa) respecte de la població de " +
        "cada municipi.",
    },
    weather: {
      label: "Temps i entorn",
      title: "Temps i entorn",
      description: "Temperatura, qualitat de l’aire, onatge, episodis meteorològics i sismes.",
    },
    explorer: {
      label: "Explorador",
      title: "Explorador de sèries",
      description:
        "Qualsevol sèrie de la plataforma dia a dia: font, mètrica i estació, amb la seva qualitat i les seves " +
        "anomalies.",
    },
    operations: {
      label: "Operació",
      title: "Operació de la plataforma",
      description: "Estat de cada font, regles de qualitat, anomalies detectades i correccions proposades.",
    },
  },
  layout: {
    dashboards: "Taulers",
    openMenu: "Obre el menú",
    closeMenu: "Tanca el menú",
    darkMode: "Mode fosc",
    lightMode: "Mode clar",
    switchToDark: "Canvia al mode fosc",
    switchToLight: "Canvia al mode clar",
    language: "Llengua",
    catalogue: "Catàleg",
    footer:
      "Dades obertes d’AEMET, SOCIB, EEA, REData, IGN, INE, EMT, CTM, SEGITTUR, Govern de les Illes Balears i " +
      "Open-Meteo. Mapa © OpenStreetMap.",
  },
  data: {
    loadError: (error: string) => `No s’han pogut carregar les dades: ${error}`,
    empty: "Sense dades",
  },
  format: {
    lessThanAnHourAgo: "fa menys d’1 h",
    thousands: "mil",
    millions: "M",
  },
};
