# Panamá - Reportes Diarios Cierre de Caja (`mba_reportes_diarios`)

Cinco reportes de cierre de caja para Panamá, todos de **solo lectura**: ningún reporte modifica facturas, inventario ni pagos, solo los consulta y los presenta.

## Qué hace

1. **Cierre Diario / Cierre Mensual (Punto de Venta)** — combina en un solo reporte las ventas de POS y las facturas de Ventas emitidas fuera de caja, sin duplicar (una venta de POS que luego se factura solo se cuenta una vez). Incluye total de ventas, órdenes, impuestos y recaudo por método de pago, costo de ventas y utilidad bruta, y desglose por departamento (categoría de producto). El Cierre Mensual es la misma lógica sumada sobre un rango de fechas en vez de un solo día.
2. **Cierre Diario (Facturación)** — cubre solo las facturas originadas en el Punto de Venta, para que el cajero cuadre su caja del día: contado vs. crédito, gravable vs. exento, y cobros por método de pago leídos de los pagos de la sesión de POS.
3. **Cobros de Cuentas por Cobrar (CxC)** — cartera del canal de Ventas a crédito: pagos entrantes del día conciliados contra las facturas que saldan, más un listado informativo de facturas a crédito emitidas ese día (no suman al total, porque emitir una factura a crédito todavía no es dinero recibido).
4. **Comisiones de Ventas (Pre-Cierre)** — por vendedor y por factura, comisión devengada, pendiente de liquidar y ya liquidada (requiere el módulo OCA `account_commission_oca`).
5. **Resumen Mensual de Ingresos (MTD)** — matriz día por día del mes: efectivo, tarjetas, transferencias, cobros de CxC y facturas a crédito (informativo), con totales acumulados por día y por concepto.

## Cómo funciona

El módulo agrega un modelo catálogo, `mba.report.template`, que lista los reportes disponibles (nombre, ícono, XML ID de la acción de su wizard) y arma el menú de reportes en la interfaz.

Cada reporte tiene su propio wizard (`mba.daily.cxc.wizard`, `mba.daily.invoice.wizard`, `mba.daily.pos.wizard`, `mba.monthly.income.wizard`, `mba.sales.commission.wizard`). El usuario elige fecha y compañía, y el wizard consulta y clasifica facturas/pagos, calcula costos y genera un PDF con los totales.

El costo de las facturas de Ventas se traza línea por línea hasta su entrega real en inventario (factura → línea de la orden de venta → movimiento de bodega → capa de valoración), así que el costo siempre aparece en la fecha de la factura, sin importar qué día se validó la salida física en el sistema. Las ventas de POS usan el costo registrado el mismo día de la venta. Si un producto no tiene costo rastreable, se usa el costo estándar de su ficha.

**Diseño agnóstico**: el módulo solo depende de `account`. Si el cliente no tiene instalado Inventario, Ventas o Punto de Venta, cada sección que dependa de esos módulos se desactiva sola (o muestra un aviso) en vez de fallar. Un reporte queda oculto automáticamente del menú si el módulo del que depende no está instalado.

## Dependencias

- `account` (obligatoria)
- `account_commission_oca` (OCA, opcional — solo para el reporte de Comisiones de Ventas)

## Licencia

LGPL-3.
