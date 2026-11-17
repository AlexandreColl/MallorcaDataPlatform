// Spanish: the reference. Its shape is the type of the other languages, so a text missing in one fails `tsc`.

export const es = {
  app: {
    name: "Mallorca en datos",
  },
  dashboards: {
    home: {
      label: "Inicio",
      title: "Mallorca en datos",
      description:
        "Agua, clima, turismo y energía de la isla, comparados con lo normal para cada mes. Quince fuentes abiertas, " +
        "con la calidad comprobada en cada carga.",
    },
    tourism: {
      label: "Turismo y recursos",
      title: "Turismo y recursos",
      description: "Cuántos turistas llegan cada mes y qué pasa a la vez con el agua y la electricidad.",
    },
    climate: {
      label: "Clima y agua",
      title: "Clima y agua",
      description: "Reservas de los acuíferos, lluvia del año hidrológico y temperatura frente a lo normal.",
    },
    mobility: {
      label: "Movilidad",
      title: "Movilidad",
      description:
        "Servicio programado de autobuses, tren y metro (EMT en Palma y CTM en toda la isla) frente a la población " +
        "de cada municipio.",
    },
    weather: {
      label: "Tiempo y entorno",
      title: "Tiempo y entorno",
      description: "Temperatura, calidad del aire, oleaje, episodios meteorológicos y sismos.",
    },
    explorer: {
      label: "Explorador",
      title: "Explorador de series",
      description:
        "Cualquier serie de la plataforma día a día: fuente, métrica y estación, con su calidad y sus anomalías.",
    },
    operations: {
      label: "Operación",
      title: "Operación de la plataforma",
      description: "Estado de cada fuente, reglas de calidad, anomalías detectadas y correcciones propuestas.",
    },
  },
  layout: {
    dashboards: "Dashboards",
    openMenu: "Abrir el menú",
    closeMenu: "Cerrar el menú",
    darkMode: "Modo oscuro",
    lightMode: "Modo claro",
    switchToDark: "Cambiar a modo oscuro",
    switchToLight: "Cambiar a modo claro",
    language: "Idioma",
    catalogue: "Catálogo",
    footer:
      "Datos abiertos de AEMET, SOCIB, EEA, REData, IGN, INE, EMT, CTM, SEGITTUR, Govern de les Illes Balears y " +
      "Open-Meteo. Mapa © OpenStreetMap.",
  },
  data: {
    loadError: (error: string) => `No se pudieron cargar los datos: ${error}`,
    empty: "Sin datos",
  },
  format: {
    lessThanAnHourAgo: "hace menos de 1 h",
    thousands: "mil",
    millions: "M",
  },
};

export type Messages = typeof es;
