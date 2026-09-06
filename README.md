# FireWatch Colombia

Auditoría regional de la clasificación de fuentes térmicas en el producto
VIIRS 375 m de NASA FIRMS sobre el territorio colombiano.

---

## Problema

Los sistemas de detección satelital de incendios activos son la principal
fuente de información para el monitoreo de fuego en países sin infraestructura
terrestre de vigilancia densa. Sin embargo, los sensores infrarrojos no
detectan incendios: detectan anomalías térmicas. Cualquier fuente de calor
suficientemente intensa dentro del campo de visión instantáneo del sensor
produce una detección, con independencia de su origen.

El producto VIIRS de procesamiento estándar incorpora un campo `type` que
distingue cuatro categorías: incendio de vegetación presunto (0), volcán
activo (1), otra fuente terrestre estática (2) y detección marina (3). La
práctica establecida en la literatura consiste en conservar únicamente las
detecciones de tipo 0 para el análisis de incendios de vegetación.

Esa máscara se deriva de un tratamiento global, construido a partir de
inventarios de fuentes conocidas. Su desempeño sobre territorios específicos,
particularmente en regiones con infraestructura industrial dispersa y poco
documentada, no ha sido caracterizado de forma sistemática.

## Pregunta de investigación

> ¿Qué proporción de las detecciones VIIRS clasificadas como incendio de
> vegetación presunto sobre territorio colombiano corresponde en realidad a
> fuentes térmicas antrópicas persistentes, y es posible identificarlas a
> partir de su firma espaciotemporal sin recurrir a datos auxiliares de
> infraestructura?

### Hipótesis

**H₀.** La distribución de los descriptores de persistencia sobre las celdas
clasificadas como `type = 0` es unimodal, y no admite separación en
subpoblaciones.

**H₁.** Dicha distribución presenta al menos dos modos. El modo de alta
recurrencia corresponde a fuentes térmicas antrópicas persistentes no
incluidas en la máscara global de FIRMS.

### Relevancia

Si la proporción de detecciones contaminadas es significativa, las
estadísticas nacionales de área quemada derivadas de sensores satelitales
incorporan un sesgo sistemático, concentrado espacialmente en las regiones
con mayor densidad de infraestructura de hidrocarburos.

---

## Fundamento del método

Una fuente térmica antrópica fija y un incendio de vegetación difieren en
cuatro dimensiones observables sin información auxiliar:

| Dimensión | Fuente antrópica persistente | Incendio de vegetación |
|---|---|---|
| **Recurrencia** | Reaparece en la misma celda durante años | Episódico, no recurrente |
| **Estabilidad radiométrica** | FRP de baja dispersión relativa | FRP errático |
| **Estacionalidad** | Sin estructura anual | Concentrado en temporada seca |
| **Régimen horario** | Operación continua | Sesgo vespertino marcado |

El régimen bimodal de precipitación en Colombia concentra los incendios de
vegetación en dos temporadas secas, aproximadamente diciembre a marzo y julio
a agosto. Una fuente industrial no exhibe esa estructura. La concentración
circular sobre el día del año es, por tanto, un discriminante con motivación
física y no meramente estadística.

## Estrategia de validación

El estudio no requiere anotación manual. Las celdas etiquetadas por FIRMS como
volcán activo o fuente estática terrestre constituyen un **conjunto de
positivos verificados**. Las celdas de tipo 0 con recurrencia baja constituyen
negativos de alta certeza. Con ese conjunto de referencia se calibra el poder
discriminante de cada descriptor antes de aplicarlo a las celdas en duda.

Esta estrategia resuelve el problema central de la aproximación: se dispone de
verdad de campo parcial, provista y validada por el propio productor del dato.

---

## Datos

### Fuentes

| Producto | Sensor | Plataforma | Cobertura empleada |
|---|---|---|---|
| `VIIRS_SNPP_SP` | VIIRS 375 m | Suomi-NPP | 2022-01-01 a 2025-12-31 |
| `VIIRS_NOAA20_SP` | VIIRS 375 m | NOAA-20 | 2022-01-01 a 2025-12-31 |

### Justificación del producto de procesamiento estándar

Se emplean exclusivamente productos con sufijo `_SP` y no sus equivalentes en
tiempo casi real. La razón es determinante y fue verificada empíricamente
contra la API: **los productos NRT no incluyen el campo `type`**. Sin ese
campo no existe conjunto de referencia y la validación propuesta resulta
imposible. Adicionalmente, los productos SP han superado el proceso de
validación de calidad, requisito para un análisis retrospectivo.

La contrapartida es un rezago de aproximadamente tres meses en la
disponibilidad, irrelevante para un estudio retrospectivo.

### Dominio espacial y sistema de referencia

El área de estudio corresponde al territorio continental colombiano, definido
por el rectángulo envolvente `-79.1, -4.3, -66.8, 13.5` en grados decimales.

Todo cálculo métrico se realiza en **EPSG:9377** (MAGNA-SIRGAS / Origen
Nacional), el sistema de referencia proyectado oficial adoptado por el
Instituto Geográfico Agustín Codazzi para el territorio continental. El uso
de un origen único nacional evita la distorsión asociada a los orígenes
zonales previos y garantiza que las distancias empleadas en el agrupamiento
y en la construcción de la rejilla sean métricamente consistentes en toda el
área de estudio.

### Restricciones de la API verificadas

- El parámetro `day_range` admite el intervalo `[1..5]`. Valores superiores
  producen `HTTP 400`.
- La cuota se limita a 5000 transacciones por intervalo de diez minutos.
- Varios errores se señalan con `HTTP 200` y cuerpo de texto plano, no como
  código de estado, lo que exige inspeccionar el contenido de la respuesta.

---

## Diseño metodológico

### 1. Arquitectura de datos

Se adopta una arquitectura por capas:

- **Bronze.** Respuestas crudas de la API, particionadas por sensor y bloque
  temporal. Caché idempotente: un bloque ya descargado no vuelve a
  solicitarse, lo que permite reanudar una ingesta interrumpida.
- **Silver.** Detecciones validadas, con marca temporal en hora local
  (UTC-5, sin horario de verano en Colombia), proyectadas a EPSG:9377 y
  deduplicadas entre sensores.
- **Gold.** Agregación a rejilla y descriptores de persistencia por celda.

### 2. Deduplicación multisensor

Suomi-NPP y NOAA-20 mantienen órbitas separadas por aproximadamente cincuenta
minutos, pero el solapamiento de barrido en los bordes produce observaciones
casi simultáneas del mismo foco. Dado que la recurrencia por celda es el
descriptor central del estudio, no deduplicar inflaría artificialmente la
variable de interés. Se consideran redundantes las detecciones separadas por
menos de 375 m, el tamaño nominal del píxel en nadir, y menos de quince
minutos.

### 3. Agregación a rejilla

Se emplea una rejilla regular de 500 m de lado sobre el CRS proyectado. La
elección excede la resolución nominal del sensor para absorber el error de
geolocalización, evitando que un mismo foco fijo se reparta entre celdas
adyacentes y subestime así la recurrencia medida.

### 4. Contraste de hipótesis

La unimodalidad se contrasta mediante el test de inmersión de Hartigan y
Hartigan, complementado con selección del número de componentes de una mezcla
gaussiana por criterio de información bayesiano. El primero evalúa la
unimodalidad; el segundo aporta evidencia sobre la existencia de
subpoblaciones diferenciadas.

### 5. Validación cruzada por bloques espaciales

Toda evaluación predictiva emplea partición por bloques espaciales contiguos y
no aleatoria. Un particionamiento aleatorio sobre datos con autocorrelación
espacial filtra información entre los conjuntos de ajuste y de prueba, y
produce estimaciones de desempeño optimistas. La partición por bloques es el
procedimiento estándar en la literatura geoespacial.

---

## Estructura del repositorio

```
firewatch-colombia/
├── src/firewatch/
│   ├── config.py              # parámetros del estudio, inmutables
│   ├── ingest/firms.py        # cliente de la API con caché idempotente
│   ├── layers/silver.py       # validación, deduplicación, proyección
│   ├── features/persistence.py# descriptores por celda
│   ├── analysis/              # contraste de hipótesis y validación
│   └── viz/style.py           # estilo de figuras
├── scripts/                   # ejecución por etapas
├── notebooks/                 # resultados y figuras
├── docs/figures/
└── tests/
```

## Reproducción

Requiere `uv` y una `MAP_KEY` de FIRMS, gratuita, solicitable en
https://firms.modaps.eosdis.nasa.gov/api/map_key/

```bash
git clone https://github.com/<usuario>/firewatch-colombia.git
cd firewatch-colombia
uv sync                      # reconstruye el entorno desde uv.lock

cp .env.example .env         # y edite FIRMS_MAP_KEY

uv run python scripts/01_ingest.py
uv run python scripts/02_silver.py
uv run python scripts/03_features.py
uv run python scripts/04_analysis.py
```

El archivo `uv.lock` fija las versiones exactas y sus hashes criptográficos,
de modo que el entorno de ejecución es reconstruible de forma verificable en
cualquier plataforma.

---

## Estado y alcance

Este repositorio contiene un estudio en curso. El alcance actual comprende la
ingesta, la construcción de descriptores de persistencia y el contraste de
unimodalidad sobre el conjunto de referencia.

**Trabajo declarado y no ejecutado a la fecha:**

- Incorporación del ciclo diurno derivado del producto de detección de fuego
  de GOES-19. Su cadencia de cinco a diez minutos permite reconstruir la
  variación intradiaria del FRP, que las dos a cuatro pasadas diarias de VIIRS
  no resuelven. Se espera que una fuente industrial exhiba potencia
  aproximadamente constante y un incendio de vegetación un máximo vespertino
  pronunciado.
- Agrupamiento espaciotemporal para la reconstrucción de eventos de incendio
  como objetos con extensión y duración, en lugar de detecciones puntuales.
- Clasificador supervisado sobre el conjunto de referencia, con evaluación
  por bloques espaciales e interpretación de contribuciones por descriptor.

## Limitaciones

- El producto VIIRS no detecta la totalidad de los incendios. Focos de
  pequeña extensión, de baja temperatura, o cuya ocurrencia se sitúa entre
  pasadas orbitales, quedan fuera del registro.
- Las plumas de humo sobrecalentadas pueden generar artefactos en detecciones
  nocturnas.
- El conjunto de referencia hereda los errores de la máscara `type` de FIRMS.
  Una fuente estática no incluida en dicha máscara aparece como negativo, lo
  que introduce un sesgo conservador en la calibración: el desempeño estimado
  constituye una cota inferior.
- La ausencia de un inventario público y consolidado de infraestructura
  térmica en Colombia impide la validación externa directa de los positivos
  identificados.

---

## Atribución de datos

Se reconoce el uso de datos e imágenes del Fire Information for Resource
Management System (FIRMS), operado por la NASA como parte del Earth Observing
System Data and Information System (EOSDIS).
https://earthdata.nasa.gov/firms

Las imágenes geoestacionarias corresponden al sensor ABI de GOES-19, operativo
como GOES-East desde abril de 2025, distribuidas por la NOAA a través del
Registry of Open Data on AWS.

## Licencia

Código bajo licencia MIT. Documentación y figuras bajo CC BY 4.0.
Los datos satelitales se rigen por las políticas de sus respectivos
proveedores.

## Cita

Si emplea este trabajo, cítelo mediante el archivo `CITATION.cff` incluido en
el repositorio.

## Autor

Néstor Oswaldo Vásquez Castro
Candidato a Magíster en Analítica de Datos, Universidad Central, Bogotá
ORCID: https://orcid.org/0009-0003-6483-790X
