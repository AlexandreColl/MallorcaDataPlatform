# BiciPalma (bici pública de Palma)

- **Fuente**: el feed **GBFS 2.3** del sistema `nextbike_ea`, que Nextbike publica para BiciPalma:
  `https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_ea/es/`.
  - `station_status.json`: por estación, las bicis libres por tipo de vehículo, los anclajes libres y si está
    instalada, alquila y admite devoluciones. `ttl` de 60 s.
  - `station_information.json`: nombre, posición, número público y capacidad de cada estación.
- **Dueño**: SMAP (Societat Municipal d'Aparcaments i Projectes, del Ajuntament de Palma). Nextbike opera el sistema y
  publica el feed.
- **Licencia**: **CC0 1.0**, declarada en `system_information.json` (`license_id`).
- **Autenticación**: ninguna.
- **Datos**: solo el estado actual. No hay histórico que pedir, así que es una **fuente en vivo**
  ([ADR 0026](../../docs/adr/0026-fuentes-en-vivo-sin-historico.md)).

## Cómo se construye la serie

1. **El DAG `live_poll`** corre cada 5 minutos sin Spark (`core/live.py`). Guarda en bronze la respuesta de
   `station_status` y, una vez por hora, la de `station_information`, sin tocarlas:
   `bicipalma/snapshots/<dataset>/day=<día UTC>/<last_updated>.json`. La clave lleva el `last_updated` del feed, no la
   hora de la petición, así que pedir dos veces la misma respuesta deja una sola instantánea.
2. **El conector diario** no llama a la API. Lista las instantáneas de los días de su ventana, las lee de bronze y
   escribe un valor por estación, métrica y hora UTC.

| Métrica | Qué es | Unidad |
|---|---|---|
| `bikes_available`, `bikes_available_min`, `bikes_available_max` | Media, mínimo y máximo de las bicis libres de las instantáneas de la hora | `bikes` |
| `ebikes_available` | Media de las bicis libres con asistencia eléctrica (tipo `143`, e-SMARTbike) | `bikes` |
| `docks_available`, `docks_available_min`, `docks_available_max` | Lo mismo con los anclajes libres | `docks` |
| `occupancy` | Media de bicis / (bicis + anclajes libres), en % | `%` |

- **La `entity`** es el `station_id` de GBFS (el *uid* de la estación en Nextbike): `station_91733840`. El nombre, con su
  número público (`01 PARC DE SES VELES`), va a `silver.entities`, y `lat`/`lon` salen de `station_information`.
- **La ocupación** divide entre bicis más anclajes libres, no entre la capacidad publicada. Un anclaje roto no está
  ni libre ni ocupado, y contarlo como hueco haría parecer vacía una estación que no admite más bicis.
- **Una estación sin instalar** (`is_installed: false`) no da valores en esa instantánea. Una que no alquila
  (`is_renting: false`) sí: sus bicis siguen ahí.
- **`frequency: 1h`**. La regla de huecos espera una hora por estación desde la primera instantánea, y no antes: el
  núcleo lo sabe por `first_day()` y `observed_span()`. Las horas con el portátil apagado sí cuentan como huecos.
- **`recover_days: 31`**: bronze guarda todas las instantáneas, así que un día que el DAG diario no cargó se recupera
  en la siguiente ejecución.

## Lo que enseñaron las pruebas reales (2026-11-26)

- **El GBFS existe, aunque no está enlazado en ninguna parte.** `gbfs.nextbike.net/maps/gbfs/v2/gbfs.json` da 404. El
  código del sistema (`ea`) sale de la lista de ciudades de la API en vivo de Nextbike
  (`maps.nextbike.net/maps/nextbike-live.json?list_cities=1`), y con él `.../v2/nextbike_ea/gbfs.json` responde con los
  feeds en castellano, catalán e inglés. No hay GBFS 3.
- **CityBikes no es una segunda fuente.** `api.citybik.es/v2/networks/bicipalma` devuelve los mismos números con los
  mismos identificadores (su `extra.uid` es el `station_id` de GBFS), porque lee el feed de Nextbike. No declara
  licencia y sus términos dicen que no es exactamente open data. Por eso no hay respaldo: caería a la vez que el GBFS.
- **`last_reported` no dice nada de cada estación.** Las 106 llevan el mismo valor, que es el `last_updated` del feed:
  Nextbike sella todo el feed cuando lo genera, cada minuto. Por eso la instantánea se fecha con `last_updated`.
- **106 estaciones**, una de ellas virtual (`86 ESTADI MALLORCA NORD`, que además no alquilaba). Las capacidades van
  de 9 a 30 anclajes, con 1.796 en total.
- **Bicis más anclajes libres no suman la capacidad en 22 estaciones.** En 21 suman menos, por los anclajes rotos, y en
  una (`18 JOSEP DARDER METGE`) suman más: 16 en una estación de 15, con una bici fuera de anclaje. De ahí que la
  ocupación use la suma y no la capacidad.
- **Había 581 bicis libres a las 16:50 hora local, un 23 % eléctricas.** Hay dos tipos de vehículo: `150` SMARTbike y
  `143` e-SMARTbike. El tipo eléctrico se lee de `vehicle_types.json` y se fija en el YAML (`ebike_types`), porque solo
  cambia si llega un modelo nuevo.
- **El sondeo pesa poco.** Cada instantánea de estado ocupa unos 27 KB en bronze y la de estaciones unos 38 KB: unos 8
  MB al día. Un sondeo es un proceso de Python de unos 2 segundos y 75 MB de memoria, sin Spark ni JVM.
- **Spark rechaza enteros en `value`.** El mínimo y el máximo de bicis son enteros, y `createDataFrame` exige `double`:
  el conector convierte cada valor a `float`.
- **La primera carga real** leyó las instantáneas de las 15:50 a las 17:00 UTC: 2.544 valores, 106 estaciones × 3
  horas × 8 métricas. La hora de 16:00 a 17:00 tuvo sus 12 instantáneas. La regla de huecos esperó 318 horas por
  métrica (3 por estación), no 2.544 (24 por estación), y no encontró ningún hueco. En la hora de las 17:00 locales,
  19 estaciones se quedaron sin bicis en algún momento, aunque la red tenía 584 de media.

## Tests

`tests/test_bicipalma.py` reproduce:

- **El sondeo grabado** con `make record-fixtures CONNECTOR=bicipalma`: un `station_status` y un
  `station_information` reales de las 106 estaciones. En un conector en vivo, la grabación registra un sondeo de cada
  dataset en lugar del `extract`.
- **Instantáneas reales del poller** de una hora completa, en `tests/fixtures/snapshots/` con sus claves de bronze,
  recortadas a cinco estaciones y con los valores tal cual.
