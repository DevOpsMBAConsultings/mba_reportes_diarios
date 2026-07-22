{
    'name': 'Reportes Diarios - Cierre de Caja',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Reports',
    'summary': 'Módulo agnóstico de reportes diarios: cierre de caja facturación, POS y más.',
    'description': """
Reportes Diarios — Cierre de Caja (Agnóstico)
==============================================

Módulo de reportería diaria configurable para Odoo 18 CE.

Características:
* Catálogo configurable de reportes (activar / desactivar)
* Detección automática de módulos instalados (POS, etc.)
* Reportes PDF vía QWeb con diseño profesional
* Cierre de caja diario — Facturación (account.move + account.payment)
* Cierre de caja diario — POS (pos.order + pos.payment, si está instalado)

El módulo NO depende de point_of_sale. Si POS está instalado,
el reporte POS se habilita automáticamente.
""",
    'author': 'MBA Consultings, Brooks Gonzalez',
    'website': 'https://www.mbaconsultings.com',
    'license': 'LGPL-3',
    'depends': [
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'report/daily_invoice_report.xml',
        'report/daily_invoice_report_template.xml',
        'report/daily_pos_report.xml',
        'report/daily_pos_report_template.xml',
        'views/daily_invoice_wizard_views.xml',
        'views/daily_pos_wizard_views.xml',
        'views/report_template_views.xml',
        'data/report_template_data.xml',
    ],
    'installable': True,
    'application': True,
}
