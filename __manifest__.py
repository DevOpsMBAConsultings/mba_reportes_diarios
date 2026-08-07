{
    "name": "Panamá - Reportes Diarios Cierre de Caja (MBA Consultings)",
    "version": "18.0.1.3.8",
    "category": "Accounting/Localizations",
    "summary": "Reportes diarios agnósticos: Cierre de caja para facturación, cobros CxC, POS y matriz mensual MTD. | MBA Consultings",
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



