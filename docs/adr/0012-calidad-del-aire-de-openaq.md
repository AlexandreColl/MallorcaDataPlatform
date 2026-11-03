# 0012 · Calidad del aire desde OpenAQ

- **Estado:** Rechazada. En su lugar, [0013](0013-calidad-del-aire-de-la-eea.md)
- **Fecha:** 2026-10-29

## Contexto

El plan inicial usaba OpenAQ para la calidad del aire medida en estación. Es un agregador mundial con una API única,
y a Open-Meteo le faltaban mediciones reales, porque sus datos salen del modelo CAMS.

## Decisión que se estudió

Integrar OpenAQ v3, con clave, para las estaciones de Mallorca.

## Por qué se rechazó

La prueba real con clave encontró tres problemas:

- **No aporta estaciones nuevas.** Las 8 estaciones activas de Mallorca son las de la red oficial que publica la EEA.
- **Faltan horas.** Solo trae un 30 % de las horas que publica la EEA.
- **Hay duplicados.** Foners y Bellver aparecen dos veces.

También se probó aqicn. Republica las mismas estaciones, solo da la última hora y la da como subíndices AQI de
EE. UU., no como concentraciones.

## Consecuencias

- La calidad del aire se lee directamente de la fuente oficial ([0013](0013-calidad-del-aire-de-la-eea.md)).
- Las coordenadas de las estaciones sí salen de OpenAQ, porque los metadatos de la EEA no las traen para España.
- **La lección:** ir a la fuente primaria. Un agregador añade un intermediario, pierde datos y no añade estaciones.
