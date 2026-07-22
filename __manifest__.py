{
    "name": "Panamá - Reportes Diarios Cierre de Caja (MBA Consultings)",
    "version": "18.0.1.0.2",
    "category": "Accounting/Localizations",
    "summary": "Reportes diarios agnósticos: Cierre de caja para facturación, cobros CxC y POS. | MBA Consultings",
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
        "views/daily_invoice_wizard_views.xml",
        "views/daily_cxc_wizard_views.xml",
        "views/daily_pos_wizard_views.xml",
        "views/report_template_views.xml",
        "data/report_template_data.xml"
    ],
    "installable": True,
    "application": False,
}
