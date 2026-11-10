# 0018 · Sin caché aparte (Redis) para la extracción

- **Estado:** Aceptada
- **Fecha:** 2026-11-03

## Contexto

La ingesta parecía lenta, y se propuso guardar las descargas en una caché para no repetirlas.

## Decisión

No añadir ninguna caché.

## Alternativas descartadas

- **Redis delante de los extractores.** Sería un servicio más y más RAM para ahorrar alrededor de 1 s por conector.

## Consecuencias

- **A favor.** Bronze ya hace de caché: guarda cada respuesta por ventana, y el catch-up solo pide los días que
  faltan. Medido por conector, extraer cuesta unos 1 s, mientras que arrancar Spark y leer Delta cuesta unos 45 s
  ([0004](0004-spark-local-en-la-tarea.md)).
- **En contra.** Ninguno medible. Relanzar una ventana vuelve a llamar a la fuente, y eso además recoge las
  revisiones que haya publicado.

## Cuándo revisarla

Si alguna fuente empieza a limitar las peticiones de forma estricta. Aun así, antes que Redis convendría leer de
bronze cuando la ventana ya está descargada.

En la v0.15.0 se fue un paso más allá ([0021](0021-solo-los-dias-que-faltan.md)): una ejecución no vuelve a pedir
los días que ya cargó una ejecución correcta, y se salta entera si no falta ninguno.

**La lección:** medir antes de optimizar. La solución a la lentitud es un servidor Spark Connect compartido.
