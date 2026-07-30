# Plan de refactor UI — mba_reportes_diarios

**Versión base:** 18.0.1.0.17
**Objetivo:** que los 5 reportes hablen el lenguaje visual nativo de Odoo 18 en vez de la estética de dashboard genérico, sin perder la identidad de MBA.
**Estado:** plan aprobado, pendiente de ejecución.

---

## 0. Corrección de dos diagnósticos previos

Antes de nada, dos cosas que se dijeron en la consultoría inicial y que el código desmiente:

1. **`o_bruto` / `o_neto` / `o_breakdown` no son clases muertas.** Eran falsos positivos de un grep sobre `o_[a-z_]*`; en realidad provienen de nombres de campos (`contado_breakdown`, `formatted_monto_neto`, `formatted_monto_bruto`). Las 21 clases definidas en el CSS se usan todas. No hay CSS muerto que borrar.

2. **`#017e84` sí pertenece a la paleta de Odoo.** Está en `addons/web/static/src/scss/primary_variables.scss:75` como `$o-enterprise-action-color`. La decisión de usarlo como acento no fue arbitraria y no hay que revertirla — hay que *nombrarla*.

El diagnóstico de fondo se sostiene, pero el problema real es más específico y más fácil de arreglar de lo que parecía.

---

## 1. El problema real

No es que los colores estén mal elegidos. Es que **están hardcodeados hexadecimales que ya existen como variables de Odoo**. Cada hex del CSS tiene su variable equivalente:

| Hex en el módulo | Ocurrencias | Variable Odoo 18 | Definida en |
|---|---|---|---|
| `#f8f9fa` | 3 | `$o-gray-100` | primary_variables.scss:51 |
| `#e9ecef` | 3 | `$o-gray-200` | primary_variables.scss:52 |
| `#dee2e6` | 1 | `$o-gray-300` | primary_variables.scss:53 |
| `#6c757d` | 2 | `$o-gray-600` | primary_variables.scss:56 |
| `#495057` | 1 | `$o-gray-700` | primary_variables.scss:57 |
| `#212529` | 3 | `$o-gray-900` | primary_variables.scss:59 |
| `#017e84` | 4 | `$o-enterprise-action-color` | primary_variables.scss:75 |
| `#714B67` | 2 | `$o-enterprise-color` | primary_variables.scss:74 |
| `#ffffff` | 5 | `$o-view-background-color` | primary_variables.scss:136 |
| `#f1f3f5` | 2 | — (sin equivalente; usar `$o-gray-100`) | |
| `#198754` | 1 | — (es Bootstrap 5, no Odoo; usar `$o-success` = `#28a745`) | |
| `#0dcaf0` | 1 | — (es Bootstrap 5, no Odoo; usar `$o-info` = `#17a2b8`) | |
| `#0056b3` | 1 | — (Bootstrap 4 legacy; eliminar) | |
| `#e6f4f1` | 1 | — (tinte manual del teal; derivar con `mix()`) | |

Consecuencias concretas de esto:

- **`#714B67` es el color Enterprise.** En Community, `$o-brand-primary` resuelve a `$o-community-color` = `#71639e`. Al hardcodear `#714B67` el módulo se pinta de Enterprise sobre una instancia Community — inconsistente con el resto de la UI del cliente.
- **`#198754` y `#0dcaf0` son de Bootstrap, no de Odoo.** Los KPI cards de éxito e info usan una paleta que no es la del webclient.
- **Nada responde al tema.** Si el cliente instala un tema que sobreescribe `$o-brand-primary`, o si se activa el esquema oscuro (`$o-webclient-color-scheme`), el módulo se queda fijo en sus hex.

### Precisión sobre el mecanismo

Las variables `$o-*` son **SCSS, no CSS custom properties**: Odoo las resuelve al compilar el bundle en el servidor, y el CSS que llega al navegador ya lleva el hex literal. No son dinámicas en tiempo de ejecución.

Lo que se gana no es dinamismo runtime, sino **resolución contra la instalación concreta**. El mecanismo es el flag `!default`: cada variable en `primary_variables.scss` lo lleva, lo que significa "asigna este valor solo si nadie lo asignó antes". Un módulo que se cargue antes en el bundle `web._assets_primary_variables` gana.

```
web._assets_primary_variables    (web/__manifest__.py:378)
├── web/static/src/scss/primary_variables.scss     ← los !default
└── web/static/src/**/*.variables.scss
```

Otros módulos se inyectan en ese mismo bundle para sobreescribir; `account` lo hace con su propio `scss/variables.scss` (`account/__manifest__.py:97`). Ese es el punto de extensión, y es también cómo `web_enterprise` convierte `$o-brand-primary` de `#71639e` (Community) a `#714B67` (Enterprise).

Consecuencia práctica para este módulo: al usar `$o-brand-primary` en vez de `#714B67`, el reporte se pinta morado-community en una instancia CE y morado-enterprise en una EE, sin condicionales. Hoy fuerza el look Enterprise en ambas.

Si en el futuro se quisiera cambio de color en runtime (sin recompilar assets), habría que emitir CSS custom properties desde el SCSS. No es necesario aquí y añade una capa de indirección que Odoo no usa para esto.

Y dos redundancias puras:

- **`font-family` re-declarado** (`css/daily_cxc_report.css:9`): el stack `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, ...` es literalmente `$o-system-fonts` (primary_variables.scss:30), que Odoo ya aplica al body. Es una línea que no hace nada.
- **`font-family` monospace en `.text-amount`**: `SFMono-Regular, Menlo, Monaco, Consolas, ...` es exactamente `$o-font-family-monospace` (primary_variables.scss:115). Aparte de ser redundante, es una decisión de diseño discutible — ver §3.

---

## 2. El problema de namespace (el más urgente)

De las 21 clases del CSS, **6 no tienen prefijo alguno**:

| Clase | Usos en plantillas | Riesgo |
|---|---|---|
| `.text-amount` | 59 | Alto — nombre genérico, colisión probable con otros módulos |
| `.clickable-link` | 13 | Alto |
| `.total-row` | 10 | Alto |
| `.table-cxc` | 12 | Medio |
| `.tr-method-header` | 2 | Medio |
| `.tr-detail-row` | 2 | Medio |
| `.badge-method` | 2 | Medio — además pisa `.badge` de Bootstrap |
| `.caret-icon` | 4 | Medio |
| `.kpi_title` / `.kpi_value` / `.kpi_success` / `.kpi_info` | 56 | Medio |
| `.report_title` / `.report_subtitle` | 10 | Alto — `report` es un término muy usado |

Estas clases se inyectan en `web.assets_backend`, es decir en **toda** la UI de Odoo, no solo en tus vistas. Cualquier otro módulo que defina `.total-row` o `.text-amount` entra en conflicto, y el ganador depende del orden de carga de assets. Esto es un bug latente, no un tema estético.

Segundo problema de namespace: **los 5 reportes usan las clases `o_daily_cxc_*`**. El reporte de POS, comisiones, facturación e ingresos mensuales se visten con el CSS del reporte de CxC. Funciona, pero cualquier ajuste al CxC afecta a los otros cuatro sin que nada lo indique.

---

## 3. Cambios de diseño propuestos

Más allá de la limpieza técnica, estos son los cambios de lenguaje visual. Cada uno es independiente: se pueden aplicar por separado.

### 3.1 Eliminar el cromo de tarjeta

- Quitar `box-shadow: 0 1px 3px rgba(0,0,0,.08)` (3 ocurrencias). Odoo backend no usa sombras en contenido.
- Quitar `border-radius: 8px` (3 ocurrencias) o bajarlo a `$o-border-radius` (4px). El 8px no existe en la escala de Odoo (`4px` / `3px` / `6px`).
- Cambiar el fondo de página `#f8f9fa` por `$o-view-background-color` (blanco). El gris de fondo es `$o-webclient-background-color`, que Odoo ya aplica *fuera* de la vista — repetirlo dentro duplica el efecto.
- Reemplazar los contenedores `.o_cxc_card` por bandas separadas con `border-bottom: 1px solid $o-gray-300`.

### 3.2 Densidad

- Padding de celda: de `0.75rem 1rem` a `$o-table-cell-padding-y-sm $o-table-cell-padding-x-sm` (`.5rem .3rem`).

**Corrección de una cifra que dí antes.** Escribí que esto "aproximadamente duplica las filas visibles". Es un overclaim. Midiendo:

| | Antes | Después |
|---|---|---|
| Altura de fila | ~47px | ~36px (−22%) |
| Cromo vertical antes de la 1ª fila de datos | ~334px | ~187px (−44%) |
| Filas visibles en un viewport de 800px | ~10 | ~17 |

O sea +68%, no +100%. La ganancia grande **no viene del padding de celda** sino de eliminar el cromo de bloque: la tarjeta de cabecera, las tarjetas de KPI y los `margin-bottom: 1.5rem` de cada sección. Son estimaciones sobre line-height 1.5; el número real depende del zoom y del contenido.
- Gaps entre bloques: de `1.5rem` a `0` (los hairlines hacen la separación).
- Font size: de `0.9rem`/`0.85rem` a `$o-font-size-base-small` (13px) para tabla y `$o-font-size-base-smaller` (12px) para labels.

### 3.3 Jerarquía por peso, no por decoración

- Quitar `text-transform: uppercase` + `letter-spacing: 0.5px` de `.kpi_title` y `.table-cxc th`.
- Bajar los `font-weight: 700` a `$o-font-weight-medium` (500). Reservar 700 solo para la fila de total.
- Quitar el `border-left: 4px solid` de los KPI cards. Si se quiere diferenciar el KPI de éxito, hacerlo con el color del número, no con un borde decorativo.
- Fila de total: cambiar `background: #f1f3f5` + `border-top: 2px solid #017e84` por `border-top: 1px solid $o-gray-900` (convención contable) y `font-weight: $o-font-weight-bold`.

### 3.4 Régimen del acento teal

`$o-enterprise-action-color` (#017e84) se queda, pero disciplinado:

- **Permitido:** links accionables (`.clickable-link`), iconos de caret, estados activos.
- **Prohibido:** títulos de sección (`.o_cxc_card_title` actualmente lo usa), fondos, bordes de total.
- `#714B67` hardcodeado → `$o-brand-primary` (resuelve a Community o Enterprise según la instalación). Así el morado deja de competir con el teal, porque el morado pasa a ser "el color de Odoo" y el teal "el color de la acción".
- `.clickable-link:hover` cambia a `#0056b3` (azul Bootstrap 4) — eliminar, mantener el mismo color y solo subrayar.

### 3.5 Monospace en montos — DECIDIDO: quitar

`.text-amount` pierde el `font-family` monospace. En su lugar:

```scss
.o_mba_amount {
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: $o-font-weight-medium;
}
```

`tabular-nums` da la alineación de dígitos que hacía útil el monospace, sin cambiar de familia tipográfica. Es lo que hace Odoo en sus propias vistas de lista para campos monetarios.

Contraargumento que se descarta: en un cierre de caja leído en columna el monospace ayuda a comparar magnitudes. Cierto, pero `tabular-nums` cubre ese caso — el ancho de dígito es igual — y no introduce una segunda familia tipográfica en la pantalla.

---

## 3.bis CSS que parece decorativo pero es funcional

**No tocar sin entender qué hacen.** Esto es lo que separa "más nativo" de "roto".

### El fix de scroll (v18.0.1.0.17, commit `cc7a683`, 29/07/2026)

Hace unas horas se añadió esto a `.o_daily_cxc_report`:

```css
height: 100%;
overflow-y: auto;
```

Es un fix, no decoración, y vive **exactamente en el selector que este refactor reescribe**. Si se reescribe la regla desde cero, se regresa el bug de scroll el mismo día que se arregló.

**Regla:** `o_mba_report` hereda `height: 100%`, `min-height: 100%` y `overflow-y: auto` textualmente. Se documenta con un comentario en el SCSS explicando por qué está ahí, para que el próximo que lo vea no lo borre por "limpieza".

### Otros casos

| Propiedad | Dónde | Función real | Acción |
|---|---|---|---|
| `overflow: hidden` | `.o_cxc_card` | Recorta la tabla al `border-radius` | Se puede quitar solo si también se quita el radius |
| `cursor: pointer` | `.tr-method-header` | Único indicio de que la fila es clicable | Conservar |
| `border-collapse: separate` + `border-spacing: 0` | `.table-cxc` | Permite el `border-bottom: 2px` del `th` | Conservar mientras exista ese borde |
| `.table-responsive` | plantillas (8 usos) | Scroll horizontal de Bootstrap | Conservar, es nativo |

---

## 3.ter Lo más nativo posible: el componente `Layout`

Existe un paso más nativo que todo lo anterior, y conviene nombrarlo aunque **no se ejecute ahora**.

Odoo 18 expone `Layout` en `@web/search/layout` (`web/static/src/search/layout.js`). Es el componente que envuelve todas las vistas nativas: renderiza el `ControlPanel` real — breadcrumbs, botones en su posición canónica — y un `<div class="o_content">` que ya trae el manejo de scroll resuelto.

```xml
<Layout display="{ controlPanel: {} }" className="'o_mba_report'">
    <t t-set-slot="layout-buttons">
        <button class="btn btn-secondary" t-on-click="printPdf">Imprimir</button>
    </t>
    ...contenido...
</Layout>
```

Adoptarlo daría, gratis:

- El control panel nativo en vez del header casero (`.o_daily_cxc_header` desaparece).
- Scroll gestionado por `.o_content` — el hack de `height: 100%` + `overflow-y: auto` deja de ser necesario.
- Botones en la posición donde el usuario de Odoo los busca.

**Por qué no ahora:** es un cambio estructural en los 5 JS y los 5 XML, no una sustitución de clases. Contradice el criterio de "sin dañar nada adicional" que rige este plan. Va como propuesta separada, después de que el refactor de CSS esté estable en producción.

---

## 4. Mapeo de clases

Prefijo nuevo: `o_mba_report_` para bloques, `o_mba_` para utilidades.

| Actual | Nueva | Ocurrencias a cambiar |
|---|---|---|
| `o_daily_cxc_report` | `o_mba_report` | 5 |
| `o_daily_cxc_header` | `o_mba_report_header` | 5 |
| `o_daily_cxc_kpis` | `o_mba_report_kpis` | 5 |
| `o_cxc_kpi_card` | `o_mba_report_kpi` | 17 |
| `kpi_title` | `o_mba_kpi_label` | 17 |
| `kpi_value` | `o_mba_kpi_value` | 17 |
| `kpi_success` | `o_mba_kpi_success` | 5 |
| `kpi_info` | `o_mba_kpi_info` | 5 |
| `o_cxc_card` | `o_mba_report_section` | 12 |
| `o_cxc_card_header` | `o_mba_report_section_header` | 12 |
| `o_cxc_card_title` | `o_mba_report_section_title` | 12 |
| `report_title` | `o_mba_report_title` | 5 |
| `report_subtitle` | `o_mba_report_subtitle` | 5 |
| `table-cxc` | `o_mba_report_table` | 12 |
| `tr-method-header` | `o_mba_group_row` | 2 |
| `tr-detail-row` | `o_mba_detail_row` | 2 |
| `total-row` | `o_mba_total_row` | 10 |
| `text-amount` | `o_mba_amount` | 59 |
| `clickable-link` | `o_mba_link` | 13 |
| `caret-icon` | `o_mba_caret` | 4 |
| `badge-method` | `o_mba_badge` | 2 |

Total: **226 sustituciones** en 5 archivos XML.

Mecánico, con una excepción: hay 4 atributos `t-att-class` con expresiones JS, de los cuales **2 contienen clases a renombrar** y un sed ciego los rompería:

```
daily_cxc_report.xml       state.expanded[method.name]   ? 'fa fa-caret-down caret-icon' : 'fa fa-caret-right caret-icon'
sales_commission_report.xml state.expanded[ag.agent_id]  ? 'fa fa-caret-down caret-icon' : 'fa fa-caret-right caret-icon'
```

Los otros 2 (`l.settled ? 'badge bg-success' : ...` y `row.informative ? 'bg-light text-muted' : ''`) usan solo clases de Bootstrap y no se tocan.

---

## 5. Archivos

**Borrar**
- `static/src/css/daily_cxc_report.css` (180 líneas)

**Crear**
- `static/src/scss/report_common.scss` — todo el estilo compartido, con variables Odoo

**Modificar**
- `__manifest__.py` — la entrada de assets pasa de `css/daily_cxc_report.css` a `scss/report_common.scss`. Mantener el orden actual (XML antes que JS por reporte); el SCSS va primero de todo.
- Las 5 plantillas en `static/src/xml/` — renombrado de clases.
- Bump de versión a `18.0.1.1.0` (cambio de UI, no un fix).

**Sin tocar**
- Los 5 `.js` (ninguno referencia clases CSS).
- Los wizards Python y las plantillas QWeb de `report/` (el PDF tiene su propio estilo y no comparte CSS).

---

## 6. Orden de ejecución, por nivel de riesgo

Criterio que rige el plan: **lo más cercano a Odoo nativo sin daño colateral.** Por eso el orden va de riesgo cero a riesgo visible, y cada fase es un punto de parada válido.

### Fase A — riesgo cero, cero cambio visual

Sustitución pura. Si algo se ve distinto al terminar la fase A, es un error.

1. `css/daily_cxc_report.css` → `scss/report_common.scss`, mismo contenido. Actualizar manifest. Verificar que compila.
2. Sustituir los 14 hex por variables `$o-*`. Excepciones deliberadas: `#714B67` → `$o-brand-primary` **sí cambia el píxel** en Community (a `#71639e`), y `#198754`/`#0dcaf0` → `$o-success`/`$o-info` también. Son las 3 correcciones intencionales; el resto debe ser idéntico.
3. Borrar el `font-family` redundante de `.o_mba_report` (es `$o-system-fonts`, que ya se aplica).
4. Añadir las clases nuevas como alias de las viejas. La UI sigue igual.

**Guardarraíl:** el bloque de `height` / `min-height` / `overflow-y` de §3.bis se copia textualmente. Verificar el scroll en los 5 reportes al cerrar la fase.

### Fase B — riesgo bajo, sin cambio visual

5. Renombrar clases en `daily_cxc_report.xml` (el más complejo, con el `t-att-class` del caret). Verificar en la instancia.
6. Renombrar en los otros 4, uno por commit. `sales_commission_report.xml` lleva el otro `t-att-class`.
7. Eliminar los alias viejos. Aquí termina el problema de namespace, que es la razón principal del refactor.

### Fase C — cambio visual, un commit por decisión

Cada punto es independiente y reversible por sí solo. Orden por impacto percibido:

8. Densidad (§3.2) — el de mayor efecto real para el usuario.
9. Quitar sombras y radius (§3.1).
10. Jerarquía por peso; quitar uppercase y letter-spacing (§3.3).
11. Régimen del acento (§3.4) y `tabular-nums` en montos (§3.5).

### Cierre

12. Bump a `18.0.1.1.0`, push al repo del módulo, `git subtree pull` en `motolider`.

Si el cliente rechaza el look de la fase C, las fases A y B **se quedan**: resuelven el bug de namespace y la corrección Community/Enterprise sin tocar el diseño. Ese es el punto de dividirlo así.

### Fuera de alcance por ahora

13. Adoptar `Layout` (§3.ter). Propuesta separada, después de que A–C estén estables.

---

## 7. Riesgos

- **231 sustituciones a mano.** Un sed global sobre `class="..."` no basta por los 4 `t-att-class`. Revisar esos 4 casos manualmente.
- **`.text-amount` con 59 usos** es el de mayor volumen; si se rompe, se nota en las 5 pantallas a la vez.
- **El subtree.** Todo esto se hace en `~/Work/Development/odoo-18/mba_reportes_diarios` (repo upstream), nunca en `motolider/mba_reportes_diarios` (copia de subtree). Editar la copia genera divergencia que el próximo `subtree pull` convierte en conflicto.
- **Percepción del cliente.** La versión densa se ve "más aburrida" en una demo. Si el reporte ya se presentó y se aprobó con el look actual, conviene validar el cambio antes de ejecutarlo.
- **No hay tests.** El módulo no tiene tour ni test JS, así que la verificación es manual: abrir los 5 reportes, expandir los acordeones, probar los drill-downs y el PDF.

---

## 8. Lo que este plan no toca

- La arquitectura OWL (correcta: `Component` + `useState` + `onWillStart` + registro en `actions`).
- La lógica de los wizards.
- Los reportes QWeb PDF.
- La duplicación de código entre los 5 componentes JS (cada uno reimplementa `loadData`, `onDateChange`, `printPdf`). Es un refactor legítimo — una clase base común — pero es otra conversación.
