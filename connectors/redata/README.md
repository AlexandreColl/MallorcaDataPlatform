# REData (Red Eléctrica)

- **API**: <https://www.ree.es/es/datos/apidatos> (`https://apidatos.ree.es/en/datos/...`)
- **Autenticación**: ninguna.
- **Cobertura**: sistema eléctrico balear completo (`geo_limit=baleares`, `geo_ids=8743`). REData no separa
  Mallorca; la isla supone ~80 % de la demanda balear. Entidad en silver: `baleares` (sin coordenadas).
- **Zona horaria**: REData agrega por días locales (Europe/Madrid). Las peticiones usan días locales y los
  timestamps se convierten a UTC (la medianoche local de verano es las 22:00 UTC del día anterior).

| Dataset | Widget | Granularidad | Límite por petición | Métricas |
|---|---|---|---|---|
| `demand` | `demanda/evolucion` | horaria | 31 días (troceado automático) | `electricity_demand` (MWh) |
| `generation` | `generacion/estructura-generacion` | diaria | 366 días | `generation_<tecnología>` y `generation_total` (MWh) |
| `emissions` | `generacion/no-renovables-detalle-emisiones-CO2` | diaria | 366 días | `co2_emissions` (tCO2eq), `co2_intensity` (tCO2eq/MWh) |

Las series de la API se mapean a métricas en `connector.yaml` (`series`). Las que se descartan a propósito
van en `ignore`; cualquier otra genera un aviso en el log, para enterarse si aparece una tecnología nueva.

**Limitaciones**

- La generación y las emisiones solo existen en granularidad diaria para Baleares (la horaria devuelve 400).
- El widget `demanda-tiempo-real` no está disponible para Baleares; `demanda/evolucion` con `time_trunc=hour` sí.
- Los días de cambio de hora tienen 23 o 25 horas locales: el día de marzo aparece como 1 hueco en la regla `gaps`.
- La API devuelve a veces `502` transitorios; el cliente HTTP reintenta con backoff.

Prueba real (2026-10-24): 22-23 de octubre, 48 valores horarios de demanda, 9 series de generación y
2 de emisiones por día. Fixtures en `tests/fixtures/`.
