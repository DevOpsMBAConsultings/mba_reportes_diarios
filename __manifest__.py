{
    "name": "Panamá - Reportes Diarios Cierre de Caja (MBA Consultings)",
    "version": "18.0.1.3.16",
    "category": "Accounting/Localizations",
    "summary": "Reportes diarios agnósticos: Cierre de caja para facturación, cobros CxC, POS y matriz mensual MTD. | MBA Consultings",
    "description": """
Reportes Diarios de Cierre de Caja
===================================

Este módulo agrupa 5 reportes independientes. Todos son de SOLO LECTURA:
ningún reporte modifica facturas, inventario ni pagos, solo los consulta y
los presenta.

1. Cierre Diario / Cierre Mensual (Punto de Venta)
---------------------------------------------------
Combina en un solo reporte las ventas de caja (POS) y las facturas de
Ventas emitidas fuera de caja, sin duplicar (una venta de POS facturada
solo se cuenta una vez). Incluye:

* Total de ventas, órdenes, impuestos y recaudo por método de pago.
* Costo de ventas y utilidad bruta. El costo de las facturas de Ventas se
  traza línea por línea hasta su entrega real en inventario (factura
  -> línea de la orden de venta -> movimiento de bodega -> capa de
  valoración), así que el costo siempre aparece en la fecha de la
  factura, sin importar qué día se validó la salida física en el sistema.
  Las ventas de caja (POS) usan el costo registrado el mismo día en que
  se hizo la venta. Si un producto no tiene información de costo
  rastreable, se usa el costo estándar definido en su ficha.
* Desglose por departamento (categoría de producto): ventas, costo y
  utilidad de cada departamento, más el valor de inventario actual.

El Cierre Mensual usa exactamente la misma lógica que el Diario, solo
que sumada sobre un rango de fechas en vez de un solo día.

2. Cierre Diario (Facturación)
--------------------------------
Cubre únicamente las facturas que se originaron en el Punto de Venta, para
que el cajero pueda cuadrar su caja del día: contado vs crédito, gravable
vs exento, y desglose de cobros por método de pago (leído directamente de
los pagos de la sesión de POS).

3. Cobros de Cuentas por Cobrar (CxC)
----------------------------------------
Cubre la cartera del canal de Ventas (fuera de caja) a crédito: pagos
entrantes del día, conciliados contra las facturas que efectivamente
saldan, más un listado informativo de las facturas a crédito emitidas ese
día (no suman al total de cobros, porque emitir una factura a crédito
todavía no es dinero recibido).

4. Comisiones de Ventas (Pre-Cierre)
---------------------------------------
Requiere el módulo OCA account_commission_oca. Muestra, por vendedor y por
factura, la comisión devengada, pendiente de liquidar y ya liquidada.

5. Resumen Mensual de Ingresos (MTD)
----------------------------------------
Matriz día por día del mes: efectivo, tarjetas, transferencias, cobros de
CxC y facturas a crédito emitidas (informativo, no suma al total), con
totales acumulados por día y por concepto.

Diseño agnóstico
-----------------
El módulo solo depende de "account". Si el cliente no tiene instalado
Inventario, Ventas o Punto de Venta, cada sección que dependa de esos
módulos se desactiva sola (o muestra un aviso) en vez de fallar.
    """,
    "author": "MBA Consultings, Brooks Gonzalez",
    "website": "https://www.mbaconsultings.com",
    "license": "LGPL-3",
    "depends": [
        "account"
    ],
    "data": [
        "security/ir.model.access.csv",
        "report/daily_invoice_report.xml",
        "report/daily_invoice_report_template.xml",
        "report/daily_cxc_report.xml",
        "report/daily_cxc_report_template.xml",
        "report/daily_pos_report.xml",
        "report/daily_pos_report_template.xml",
        "report/monthly_income_report.xml",
        "report/monthly_income_report_template.xml",
        "report/sales_commission_report.xml",
        "report/sales_commission_report_template.xml",
        "views/daily_invoice_wizard_views.xml",
        "views/daily_cxc_wizard_views.xml",
        "views/daily_pos_wizard_views.xml",
        "views/monthly_income_wizard_views.xml",
        "views/sales_commission_wizard_views.xml",
        "views/report_template_views.xml",
        "data/report_template_data.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "mba_reportes_diarios/static/src/scss/report_common.scss",
            "mba_reportes_diarios/static/src/xml/daily_cxc_report.xml",
            "mba_reportes_diarios/static/src/js/daily_cxc_report.js",
            "mba_reportes_diarios/static/src/xml/daily_invoice_report.xml",
            "mba_reportes_diarios/static/src/js/daily_invoice_report.js",
            # El cuerpo compartido va PRIMERO: las plantillas que lo llaman
            # con t-call tienen que encontrarlo ya registrado.
            "mba_reportes_diarios/static/src/xml/closing_report_body.xml",
            "mba_reportes_diarios/static/src/xml/daily_pos_report.xml",
            "mba_reportes_diarios/static/src/js/daily_pos_report.js",
            "mba_reportes_diarios/static/src/xml/monthly_closing_report.xml",
            "mba_reportes_diarios/static/src/js/monthly_closing_report.js",
            "mba_reportes_diarios/static/src/xml/monthly_income_report.xml",
            "mba_reportes_diarios/static/src/js/monthly_income_report.js",
            "mba_reportes_diarios/static/src/xml/sales_commission_report.xml",
            "mba_reportes_diarios/static/src/js/sales_commission_report.js"
        ]
    },
    "installable": True,
    "application": False,
}



