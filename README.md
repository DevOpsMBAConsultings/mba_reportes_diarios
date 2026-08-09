# Panamá - Reportes Diarios Cierre de Caja (`mba_reportes_diarios`)

Reportes diarios de cierre de caja para Panamá: facturación, cobros de cuentas por cobrar (CxC), ventas de Punto de Venta, y una matriz mensual "mes a la fecha" (MTD) de ingresos y comisiones de venta.

## Qué hace

- **Cierre de facturación diario**: totales de facturas emitidas por día.
- **Cierre de CxC**: cobros del día, distinguiendo pagos que vienen del Punto de Venta de los que no.
- **Cierre de POS**: totales de ventas de POS del día.
- **Matriz mensual MTD**: acumulado de ingresos del mes a la fecha.
- **Comisiones de venta**: reporte de comisiones por vendedor.

## Cómo funciona

El módulo agrega un modelo catálogo, `mba.report.template`, que lista los reportes disponibles (cada uno con nombre, ícono, y el XML ID de la acción de su wizard). Este catálogo es lo que arma el menú de reportes en la interfaz.

Cada reporte tiene su propio wizard (`mba.daily.cxc.wizard`, `mba.daily.invoice.wizard`, `mba.daily.pos.wizard`, `mba.monthly.income.wizard`, `mba.sales.commission.wizard`). El usuario abre el wizard, elige fecha y compañía, y el wizard:

1. Consulta y clasifica las facturas/pagos del día (incluyendo lógica para detectar si un pago viene del POS).
2. Formatea los montos (miles, decimales).
3. Genera un reporte PDF vía QWeb con los totales.

Un detalle importante: si un reporte depende de un módulo de Odoo que no está instalado (por ejemplo `point_of_sale` para el cierre de POS), el campo `module_installed` del catálogo lo detecta automáticamente y ese reporte se oculta del menú, en vez de fallar al abrirlo.

## Dependencias

- `account`

## Licencia

LGPL-3.
