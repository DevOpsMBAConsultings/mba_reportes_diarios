# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MbaReportTemplate(models.Model):
    _name = 'mba.report.template'
    _description = 'Plantilla de Reporte Diario'
    _order = 'sequence, id'

    name = fields.Char("Nombre del Reporte", required=True)
    description = fields.Text("Descripción")
    active = fields.Boolean("Activo", default=True)
    sequence = fields.Integer("Secuencia", default=10)
    icon = fields.Char(
        "Icono",
        default="fa-file-text-o",
        help="Clase CSS del ícono FontAwesome (ej: fa-print, fa-bar-chart).",
    )
    required_module = fields.Char(
        "Módulo Requerido",
        help=(
            "Nombre técnico del módulo de Odoo que debe estar instalado "
            "para usar este reporte (ej: point_of_sale). "
            "Dejar vacío si no requiere ningún módulo adicional."
        ),
    )
    module_installed = fields.Boolean(
        "Módulo Disponible",
        compute='_compute_module_installed',
        help="Indica si el módulo requerido está instalado en esta instancia de Odoo.",
    )
    wizard_action_xmlid = fields.Char(
        "Acción del Wizard (XML ID)",
        help=(
            "XML ID completo de la acción de ventana del wizard asociado "
            "(ej: mba_reportes_diarios.action_daily_invoice_wizard)."
        ),
    )

    # ── Computed ────────────────────────────────────────────────────────────

    @api.depends('required_module')
    def _compute_module_installed(self):
        IrModule = self.env['ir.module.module']
        for rec in self:
            if rec.required_module:
                module = IrModule.sudo().search([
                    ('name', '=', rec.required_module),
                    ('state', '=', 'installed'),
                ], limit=1)
                rec.module_installed = bool(module)
            else:
                # Sin dependencia externa → siempre disponible
                rec.module_installed = True

    # ── Acciones ────────────────────────────────────────────────────────────

    def action_open_wizard(self):
        """Abre el wizard del reporte seleccionado."""
        self.ensure_one()

        if self.required_module and not self.module_installed:
            raise UserError(_(
                "El módulo requerido '%s' no está instalado.\n\n"
                "Este reporte necesita que el módulo esté instalado "
                "y activado para poder funcionar."
            ) % self.required_module)

        if not self.wizard_action_xmlid:
            raise UserError(_(
                "Este reporte no tiene un wizard configurado.\n"
                "Contacte al administrador del sistema."
            ))

        try:
            action = self.env.ref(self.wizard_action_xmlid).sudo().read()[0]
        except (ValueError, Exception):
            raise UserError(_(
                "No se encontró la acción '%s'.\n"
                "Es posible que el módulo asociado no esté instalado correctamente."
            ) % self.wizard_action_xmlid)

        return action
