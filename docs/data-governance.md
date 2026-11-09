# Gobierno del dato

Cada fuente tiene una ficha en el catálogo de fuentes (`dbt/seeds/dim_sources.csv`). La ficha dice:

- de quién es el dato;
- con qué licencia se usa y cómo se accede;
- si tiene datos personales y quién puede verlo;
- si se sigue publicando;
- qué servicio se ha acordado para ella (SLA).

El catálogo vive en git: cambiar un dueño, una licencia o un SLA es un PR que se revisa, como cualquier otro
cambio. La decisión está en el [ADR 0020](adr/0020-gobierno-del-dato-en-el-catalogo-de-fuentes.md).

## La ficha de una fuente

| Campo | Qué dice | Valores |
|---|---|---|
| `domain` | Área temática: la unidad de la que respondería un dueño del dato | `weather`, `air`, `sea`, `energy`, `seismic`, `mobility`, `tourism`, `water`, `population` |
| `owner` | El organismo que publica el dato y responde de su contenido. La plataforma solo lo copia, lo valida y lo transforma | Texto |
| `license` | La licencia o las condiciones de reutilización, tal como las publica el dueño | Texto |
| `terms_url` | La página del dueño con esas condiciones | URL |
| `access` | Cómo se lee | `open` (anónimo) o `api_key` (una clave gratuita, guardada en un `.env` fuera del repositorio) |
| `personal_data` | Si contiene datos de personas identificables (RGPD) | `true` / `false` |
| `classification` | Quién puede verlo | `public`, `internal`, `restricted` |
| `lifecycle` | Si se sigue publicando | `active` o `history` (una serie cerrada) |
| `sla_data_age_hours` | Antigüedad máxima del dato más reciente, en horas | Número, o vacío si la antigüedad no dice nada |
| `sla_success_rate` | Parte mínima de cargas correctas en los últimos 7 días | 0 a 1 |

Los tests de dbt exigen que cada fuente tenga su ficha completa:

- Ningún campo puede quedar vacío, salvo `sla_data_age_hours`.
- Los campos con una lista cerrada solo admiten esos valores.
- Toda fuente que llega a silver necesita una fila en el catálogo.

## Las fuentes hoy

| Fuente | Dueño | Licencia | Acceso | SLA de antigüedad | Cargas correctas |
|---|---|---|---|---|---|
| Open-Meteo, Open-Meteo Marine | Open-Meteo | CC BY 4.0 | Abierto | 48 h | 90 % |
| SOCIB | SOCIB | Acceso abierto con cita obligatoria | Abierto | 48 h | 80 % |
| EEA | Agencia Europea de Medio Ambiente (datos del Govern) | CC BY 4.0 | Abierto | 48 h | 90 % |
| REData | Red Eléctrica | Reutilización con cita | Abierto | 48 h | 80 % |
| AEMET (estaciones) | AEMET | Reutilización con cita (nota legal) | Clave | 5 días | 90 % |
| AEMET (avisos) | AEMET | Reutilización con cita (nota legal) | Clave | 48 h | 90 % |
| EMT Palma | EMT Palma | Sin licencia publicada en el repositorio | Abierto | 48 h | 90 % |
| CTM | Consorci de Transports de Mallorca | CC BY 4.0 | Abierto | 48 h | 90 % |
| Dataestur | Segittur | Reutilización con cita | Abierto | 100 días | 90 % |
| Reservas hídricas | Govern de les Illes Balears | CC BY (política de datos abiertos del Govern) | Abierto | 100 días | 90 % |
| Ibestat (presión humana) | Ibestat | Reutilización con cita | Abierto | 120 días | 90 % |
| INE (padrón) | INE | CC BY 4.0 | Abierto | 2 años | 90 % |
| IGN (sismos) | Instituto Geográfico Nacional | CC BY 4.0 | Abierto | Sin SLA: solo hay datos cuando hay sismos | 90 % |
| GOIB (histórico) | Govern de les Illes Balears | CC BY (política de datos abiertos del Govern) | Abierto | Histórico cerrado en 2021 | 90 % |

**Licencias.** Algunos dueños no publican una licencia concreta: EMT Palma, Dataestur, Ibestat, REData y SOCIB. En
esos casos la ficha lo dice en lugar de inventarla. Se aplican las condiciones por defecto de la reutilización de
información del sector público (Ley 37/2007): citar la fuente, no desnaturalizar el dato y no sugerir que el dueño
patrocina el uso. SOCIB exige además citar su repositorio. Antes de un uso comercial habría que confirmarlo con
cada dueño.

**Datos personales.** Ninguna fuente tiene datos personales:

- El padrón llega agregado por municipio y sexo.
- La presión humana del Ibestat es un total diario de la isla.
- Las paradas y las estaciones son lugares, no personas.

Por eso todas las fuentes se clasifican como `public`.

## Cómo se fija un SLA

El SLA es lo que se acuerda que la plataforma garantiza de cada fuente. No es lo que pasa hoy:

- **Antigüedad.** La suma del retraso con el que publica el dueño, su cadencia y un margen.
  - Una fuente horaria o diaria: 48 h. Dos días de margen cubren un fallo de un día y su reintento.
  - AEMET publica los valores diarios con 2 o 3 días de retraso: 5 días.
  - Las estadísticas mensuales salen uno o dos meses después del mes: unos 100 días. El IPH del Ibestat llega
    un poco más tarde: 120 días.
  - El padrón (1 de enero) se publica en diciembre del año siguiente: 2 años.
- **Cargas correctas.** El 90 % de las ejecuciones de 7 días. SOCIB y REData tienen cortes y errores 502 conocidos
  en sus servicios, así que se acuerda el 80 %. Sus reintentos ya cubren la mayoría.

`gold.source_health` compara cada fuente con su SLA:

- `sla_age_met`: si se cumple la antigüedad.
- `sla_success_met`: si se cumplen las cargas correctas.
- `sla_met`: el resultado conjunto. Es falso si falla una de las dos partes, verdadero si alguna se cumple y ninguna
  falla, y nulo si no hay nada que juzgar: una fuente sin SLA de antigüedad que no ha corrido.

## Dónde se ve

- **API:** `GET /v1/sources` y `GET /v1/sources/{source}` devuelven `governance` (la ficha) y `sla` (el objetivo y si
  se cumple).
- **Web, página Operación:**
  - el estado *Fuera de SLA* en la tabla de fuentes, con la parte que falla;
  - el panel *Gobierno del dato*, con el dueño, la licencia enlazada, el acceso y el SLA de cada fuente.
- **Grafana:**
  - la columna SLA del panel *Salud de las fuentes*;
  - la alerta *Fuente fuera de su SLA*, que calcula la antigüedad en vivo. La alerta *Fuente sin ejecución correcta*
    sigue cubriendo el caso de que no corran ni el DAG ni dbt.
- **dbt:** `dbt source freshness` da error en la fuente que pasa su SLA sin una carga nueva (`error_after` es el
  SLA, y un test lo mantiene igual que el catálogo).
- **Un histórico cerrado** (`lifecycle: history`) sale como *Histórico* en la web y no avisa. Antes se adivinaba
  por la antigüedad de su último dato, más de 800 días.

## Añadir una fuente

La fila del catálogo es parte del PR del conector ([adding-a-connector.md](adding-a-connector.md)):

1. Busca la licencia en la web del dueño. Si no publica ninguna, escríbelo así en la ficha.
2. Fija el SLA con la regla de arriba, a partir de la cadencia y del retraso de publicación, y pon el mismo valor
   como `error_after` de la fuente en `dbt/models/staging/_sources.yml` (el test lo comprueba).
3. Si la fuente tuviera datos personales, `personal_data: true` obliga a decidir antes de cargarla:
   - su clasificación;
   - quién puede leerla (un rol de Postgres aparte, fuera de la API pública);
   - cuánto tiempo se guarda.
