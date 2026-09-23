# PENDIENTE — auditoría Jev de microsites (noche 2026-09-22 → 23)

Trabajo 100 % de solo lectura sobre la BD `prod` (Doodba). Ningún UPDATE/INSERT/DELETE, ninguna escritura ORM, ningún push a `main`.
Entregables en el repo `canarias-platform`, rama `feat/microsites-jev-2026-09-22`, carpeta `tools/jev-microsites/`.

## 1. Bloqueos y denegaciones (no se buscaron rodeos)

| Hora UTC | Qué se intentó | Resultado | Consecuencia |
|---|---|---|---|
| 23:31 | Leer el tamaño del archivo `~/.claude/.jev-key` | Denegado por el clasificador (exploración de credenciales) | Ninguna: el cliente `jev_client.py` lee la key él mismo y solo la envía en la cabecera `Authorization`. |
| 23:48 | `curl` de solo lectura a `inkcanarias`, `canariasconectada.es` y `abilioortegasanabria` para comprobar el render del bloque de reseñas | Denegado por el hook `vps-odoo` ("Jev no disponible (HTTPError); confirma manualmente") | La validación HTTP de la tarea 1 queda hecha por código + BD, **no por respuesta HTTP real**. Pendiente a mano: abrir `https://inkcanarias.canariasconectada.es/resenas` y `https://canariasconectada.es/resenas`. |
| 00:41 | Leer `ODOO_URL/ODOO_DB/ODOO_USER` de `/home/odoo/scripts/.env` (sin la contraseña) para un dry-run conectado de `aplicar.py` | Denegado por el clasificador | `aplicar.py` solo se probó en modo `--offline` (plan desde el CSV) y con auto-tests de las funciones puras. **El dry-run conectado (`python3 aplicar.py` con credenciales) queda para el usuario.** |

## 2. Observaciones de criterio (léelas antes de aplicar nada)

- **Criterio "manual" aplicado al pie de la letra dejaría 0 propuestas.** Las 210 portadas importadas tienen `write_date > create_date` porque nuestros propios scripts (f61/f63/f66/f67/f68, `write_uid = 1` OdooBot, lote masivo 2026-09-15 13:36) las reescribieron. Evidencia: `website_page.url='/'` → 210 vistas con `create_uid=2, write_uid=1`, 1 con `write_uid=207` (Neveri, editada por el comercio) y 1 con `write_uid=2`.
  - Regla usada: **manual = `write_uid` de la vista o de la compañía ∉ {1 OdooBot, 2 cuenta RPC de importación}**, o Jev ≥ 0.85 en "texto propio del comercio". Cuando solo salta la condición de fecha, la fila va a `cambios.csv` con el motivo `write_date>create_date por script propio (uid 1/1), no manual`.
  - Sites excluidos por manual real: **221 Neveri** (uid 207) y **98 Pizzería Ravo** (compañía editada por uid 270 → `revision.csv`).
- **"Sección 1"**: es la sección `data-name="SEC1"` de la portada estática (banner intro con `<h2>`), alimentada en el modelo nuevo por `res_company.microsite_intro_title`. 185 sites ya tienen texto real puesto por nosotros y **no se tocan**. Candidatos: 8 con el placeholder "Bienvenidos a nuestro espacio" (178-185, creados 2026-09-02) y 11 portadas que solo tienen Hero + Formulario (200-217, sin sección SEC1 ni Acerca).
  - Para los 11 sin sección, la propuesta incluye `ir_ui_view.<id>.SEC1.insert` (inserta la sección tras Hero con fondo degradado, el mismo esqueleto que usa el importador). Alternativa: regenerar la portada dinámica con `auto_microsite_generator`.
  - Los textos propuestos los redacté yo (máx. 2 frases, español neutro) a partir de nombre, categoría y zona; Jev **no genera prosa**, solo puntúa nicho, "manual" y "encaje".
- **Imágenes**: 85 sites estándar sin fondo en Hero/SEC1/Separador; ninguno tiene tampoco imagen en `microsite_hero_image/intro/banner` (0 rellenados por nosotros). El zip cubre 43 de ellos (con Jev ≥ 0.85: 40 sites → `cambios.csv`; 3 → `revision.csv`). Los 110 sites con imágenes ya puestas por nosotros son byte a byte iguales al zip (335/596 imágenes idénticas por SHA1): el zip es el material original de la importación.
  - Destino de cada imagen: carpeta `hero` → Hero, `sec1` → SEC1, `sec2` → Separador (Jev confirmó 1.00 en todos). Las carpetas con solo 2 imágenes dejan Separador sin propuesta (34 sites, ver notas en PROGRESO.md).
  - `aplicar.py` sube la imagen al campo `res_company.<campo>` y referencia `/web/image/res.company/<id>/<campo>` en la portada (7 idiomas), igual que hace la plantilla dinámica.
- **Nicho**: Jev eligió nicho con confianza 1.00 en 18/19 candidatos. No propongo cambiar `category_id` (todas las compañías candidatas ya tienen categoría). Conflicto detectado: **site 206** subdominio `kioscochurruca` vs categoría "Terapia" → `revision.csv`.
- **Coste Jev**: 0.0033 USD en total (≈ 76 llamadas, modelo `typesafe/jev-1.13`). Caché en `/home/odoo/Pending/jev-work/cache/`.

## 3. Tarea 1 — Reseñas: informe site por site

Regla de visibilidad (código en prod, `partner_reviews` 19.0.3.0.0 y `website_local_content` 19.0.2.2.0):
- Reseñas de comercio: **no hay bloque en la portada**. Solo se ven en `/resenas` del propio site y la ruta devuelve **404 si `res_company.enable_reviews` es falso**. Se listan las `rating.rating` con `res_model='res.company'`, `consumed`, `moderation_status='approved'`, `rating>=1`.
- Valoraciones de contenido local: solo en `/explora/<tipo>/<slug>` y solo si el ítem está `state='approved'`, `is_published` y visible en ese website (`website_ids` vacío = todos).

Resultado: **212 sites analizados, 206 OK, 6 con fallos** (4 de ellos son portal/zonas). En 209 comercios `enable_reviews=false` y no tienen reseñas: comportamiento correcto, nada que mostrar.

| Site | Fallo | Causa probable | Fix propuesto |
|---|---|---|---|
| 1 `canariasconectada.es` | R1 | `enable_reviews=true` y 1 reseña aprobada, pero **no existe el menú "Reseñas"** (`/resenas`) en el website 1. El flag lo fijó la migración sin pasar por `res.company.write`, así que `_sync_reviews_website_menu()` nunca corrió. | Ejecutar `env['res.company'].browse(1)._sync_reviews_website_menu()` o re-guardar `enable_reviews` desde el editor. Valorar si el portal debe tener reseñas propias. |
| 1 | R5 | La única reseña visible es **#16 "Hola mundo" de Administrator** (Jev: prueba 0.98). | `moderation_status='rejected'` o borrar la reseña #16. |
| 198 `admin.canariasconectada.es` | R1, R5 | Misma compañía 1: `/resenas` responde con la reseña de prueba y sin menú. | Igual que arriba; además considerar `enable_reviews` solo para el website 1. |
| 12, 13, 14 (zonas) | R4 | El menú "Reseñas" apunta a `https://canariasconectada.es/resenas` (URL absoluta fijada a propósito en `auto_microsite_generator/models/res_company.py`), que renderiza las reseñas **de la compañía del portal**, no las de los comercios de la zona. | Reapuntar a `/comercio` (directorio con valoraciones) o quitar la entrada; corregir la constante en el generador para que no vuelva a crearse. |
| 12, 13, 14 y 1 | L1 ×6 | Ítems de **Memoria Viva en `draft`/no publicados con valoraciones migradas**: #117 Playa El Confital, #118 Mirador Las Coloradas, #120 Centro Deportivo Tamaraceite, #121 Parque Santa Catalina, #123 Teatro Cuyás, #125 Estadio Gran Canaria. Sus fichas `/explora/memoria-viva/...` no se sirven → las valoraciones no se ven en ningún site. | Decisión editorial: aprobar y publicar los 6 ítems, o retirar las valoraciones huérfanas. |
| 12, 13, 14 y 1 | L2 | **Ítem duplicado "Haricana"** (#130 `haricana` y #131 `haricana-1`), cada uno con 1 valoración. | Fusionar en uno y reasignar la valoración (`rating_rating.res_id`). |
| 58 `inkcanarias` | R5 | Todo el circuito funciona (flag, menú `/resenas` seq 50, 1 reseña aprobada) pero la reseña **#15 es "test"** firmada por "Delioma Hernández \| INK CANARIAS" (el propio comercio; Jev prueba 0.98). | Rechazar/borrar la reseña #15 y pedir una real. |

Notas:
- Ítem #114 "Taller de Música - Guanarteme" (Lugares de Interés) restringido a `website_ids=[12]`: su valoración (1) solo se ve en Guanarteme. Correcto si es intencional.
- 11 de las 14 valoraciones de contenido local tienen `partner_id` NULL (migradas) y se muestran como "Visitante".
- No hay reseñas `pending`/`rejected` ni palabras prohibidas en juego (todas `approved`).

## 4. Tarea 2 — Sección 1: resumen

| Resultado | Sites |
|---|---|
| Propuesta con confianza ≥ 0,85 (`cambios.csv`) | 178, 180, 181, 184, 201, 205, 207, 208, 213, 215, 217 |
| A revisión (encaje Jev < 0,85 o dato contradictorio) | 179 (0,68), 182 (0,78), 183 (0,76), 185 (0,78), 203 (0,82), 206 (0,65 · kiosco vs Terapia), 209 (0,82), 216 (0,83) |
| Excluidos | 221 Neveri (manual, uid 207); 223 empresa1234 (site de prueba); 1/12/13/14/198 (portal y zonas); 130 y 162 (portadas "Portada/Info Bar" hechas a mano, sin SEC1) |

## 5. Tarea 3 — Imágenes: resumen

| Resultado | Cantidad |
|---|---|
| Sites estándar sin fondo en alguna sección | 85 |
| Con carpeta en el zip y propuesta ≥ 0,85 (`cambios.csv`) | 40 sites · 164 filas (imagen + referencia en portada por sección) |
| A revisión | 98 Pizzería Ravo (compañía editada por uid 270), 181 San Fernando (coincidencia 0,84), 196 Astrid Olof Palme (dos "Astrid" en BD; carpeta `cafeteriaastrid` ambigua) |
| **Sin imagen disponible** (ni en zip ni en campos) | 38 sites: 2, 24, 25, 51, 52, 53, 56, 57, 62, 64, 65, 66, 67, 70, 73, 75, 76, 77, 78, 79, 82, 84, 85, 86, 87, 88, 89, 90, 92, 95, 96, 99, 100, 101, 103, 105, 107, 108 |

Carpetas del zip **sin site en la BD** (29): aloestorecanarias, amigojuanito, apapachar, barcafeterialarebana2, carpinteriaylacados, centrodeesteticaalma, correduriajorgenaranjo, cruisingblues, eresmucho, ferreteriatosan, gaiafruteria, jorgenaranjo, joyeriadanieldelpino, laislastore, larebana2, lavaysalt, medicalicaro, modasolaida, napa, personalfitness, pizzeriahamburgueseriahawai, preciosacanarias, quiroestetica, restaurantecasarayco, salchiburguergrill, segurosmapfre, tupuntoahorro, unitedbarbers, walldecorpinturas. Son comercios que no existen (o tienen otro nombre) en `prod`.

## 6. Cómo aplicar y revertir

```
cd tools/jev-microsites
python3 -m unittest                             # 39 tests de las funciones puras y del flujo (cliente falso)
python3 aplicar.py --offline                    # plan y validación sin conexión (rutas del zip, campos, duplicados)
export ODOO_LOGIN=...                           # la contraseña se pide por getpass o va en ODOO_PASSWORD; no existe --password
python3 aplicar.py                              # dry-run conectado: comprueba que la vista es la portada del site y compara con el servidor
python3 aplicar.py --apply --only-site 68       # primer site (Little Beach, 3 imágenes); pide confirmar "prod" salvo --yes
python3 aplicar.py --apply                      # todo cambios.csv en lotes de 10 sites
python3 revertir.py                             # dry-run de la reversión
python3 revertir.py --apply                     # restaura desde /home/odoo/Pending/jev-work/backup.jsonl
```

Reglas de seguridad de `aplicar.py` (tras la revisión de riesgo + fiabilidad):
- Backup en `/home/odoo/Pending/jev-work/backup.jsonl` (fuera del repo, `*.jsonl` ignorado por git): una línea `backup` por fila e idioma antes de escribir, `pending` justo antes de cada RPC y `applied` después. Tras un corte a mitad, `revertir.py` restaura también las `pending`.
- Una fila se salta si el valor actual del servidor no coincide con `valor_anterior` ("changed on server"); `--force` solo funciona junto a `--only-site` y solo para esos sites.
- Las filas `ir_ui_view.*` se rechazan si la vista no es la portada (`website.page url='/'`) del site indicado. Las rutas del zip no pueden salir de `--zip-root`. Los fondos solo aceptan `/web/image/res.company/<id de la compañía del site>/<campo>`.
- Idiomas: se escribe el mismo texto español en los 7 idiomas (hoy tienen traducciones automáticas del placeholder); `website_auto_translate` está instalado y puede retraducir al guardar, por lo que un segundo dry-run puede mostrar los idiomas secundarios como "pendientes de completar": es esperado, no un error.
- La fila `ir_ui_view.<id>.SEC1.bg` sustituye el degradado de la sección insertada por la imagen (dos `background-image` dejarían ganar al degradado).
