# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import datetime, time


class MbaDailyCxcWizard(models.TransientModel):
    _name = 'mba.daily.cxc.wizard'
    _description = 'Wizard - Cobros de Cuentas por Cobrar (CxC)'

    date_report = fields.Date(
        "Fecha del Reporte",
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        'res.company',
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
    )

    # ── Acción principal ────────────────────────────────────────────────────

    def action_print_report(self):
        """Genera el reporte PDF de cobros de CxC."""
        self.ensure_one()
        return self.env.ref(
            'mba_reportes_diarios.action_report_daily_cxc'
        ).report_action(self)

    # ── Helpers de formato ──────────────────────────────────────────────────

    def fmt(self, value):
        """Formatea un número con 2 decimales y separador de miles."""
        if value is None:
            value = 0.0
        return '{:,.2f}'.format(value)

    def fmt_int(self, value):
        """Formatea un número entero."""
        if value is None:
            value = 0
        return '{:,.0f}'.format(value)

    # ── Datos del reporte ───────────────────────────────────────────────────

    def _get_report_data(self):
        """
        Calcula todos los datos necesarios para el reporte PDF de Cobros CxC.
        """
        self.ensure_one()

        # 1. Pagos entrantes del día (account.payment)
        # Odoo 18: los estados de account.payment son
        # draft | in_process | paid | canceled | rejected
        # ('posted', 'reconciled') son estados de Odoo <= 16 y no coinciden
        # con ningún registro (Odoo no lanza error, solo devuelve vacío).
        payments = self.env['account.payment'].search([
            ('date', '=', self.date_report),
            ('payment_type', '=', 'inbound'),
            ('state', 'in', ('in_process', 'paid')),
            ('company_id', '=', self.company_id.id),
        ], order='partner_id, name asc')

        # 2. Clasificación y detalle por cliente/pago
        payment_details = []
        method_totals = {}

        CARD_KEYWORDS = (
            'tarjeta', 'card', 'visa', 'master', 'clave',
            'datafast', 'pos terminal', 'débito', 'debito',
        )

        for p in payments:
            journal = p.journal_id
            journal_type = journal.type if journal else ''
            jname = (journal.name or '').lower()

            if journal_type == 'cash':
                method_name = _('Efectivo')
            elif journal_type == 'bank':
                if any(kw in jname for kw in CARD_KEYWORDS):
                    method_name = _('Tarjeta de Crédito / Débito')
                else:
                    method_name = _('Transferencia / Depósito Banco')
            else:
                method_name = journal.name if journal else _('Otros')

            amount = p.amount or 0.0
            if method_name not in method_totals:
                method_totals[method_name] = {
                    'name': method_name,
                    'amount': 0.0,
                    'count': 0,
                }
            method_totals[method_name]['amount'] += amount
            method_totals[method_name]['count'] += 1

            # Factura(s) relacionada(s) si están reconciliadas
            invoices = []
            receivable_lines = p.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
            )
            for line in receivable_lines:
                for partial in line.matched_debit_ids:
                    inv_move = partial.debit_move_id.move_id
                    if inv_move.name and inv_move.name not in invoices:
                        invoices.append(inv_move.name)

            invoice_str = ', '.join(invoices) if invoices else _('Abono a Saldo / Anticipo')

            partner_name = p.partner_id.name or _('Cliente General')
            partner_ref = p.partner_id.ref or p.partner_id.vat or ''
            partner_label = f"[{partner_ref}] {partner_name}" if partner_ref else partner_name

            payment_details.append({
                'payment_name': p.name or '',
                'partner': partner_label,
                'method_name': method_name,
                'journal_name': journal.name if journal else '',
                'reference': p.ref or '',
                'invoices': invoice_str,
                'amount': amount,
            })

        # 3. Cobros / Órdenes a crédito POS (si POS está instalado)
        pos_credit_details = []
        if 'pos.order' in self.env:
            date_start = datetime.combine(self.date_report, time.min)
            date_end = datetime.combine(self.date_report, time.max)
            pos_orders = self.env['pos.order'].search([
                ('date_order', '>=', date_start),
                ('date_order', '<=', date_end),
                ('state', 'in', ('paid', 'done', 'invoiced')),
                ('company_id', '=', self.company_id.id),
            ])
            # Filtrar órdenes que tengan líneas de pago marcadas como crédito/cuenta cliente
            for order in pos_orders:
                for pp in order.payment_ids:
                    pm_name = (pp.payment_method_id.name or '').lower()
                    if 'cuenta' in pm_name or 'crédito' in pm_name or 'credito' in pm_name or 'cxc' in pm_name:
                        amount = pp.amount or 0.0
                        method_label = f"POS - {pp.payment_method_id.name}"
                        if method_label not in method_totals:
                            method_totals[method_label] = {
                                'name': method_label,
                                'amount': 0.0,
                                'count': 0,
                            }
                        method_totals[method_label]['amount'] += amount
                        method_totals[method_label]['count'] += 1

                        partner_name = order.partner_id.name or _('Cliente POS')
                        partner_ref = order.partner_id.ref or order.partner_id.vat or ''
                        partner_label = f"[{partner_ref}] {partner_name}" if partner_ref else partner_name

                        pos_credit_details.append({
                            'payment_name': order.name or '',
                            'partner': partner_label,
                            'method_name': method_label,
                            'journal_name': pp.payment_method_id.name or 'POS',
                            'reference': order.pos_reference or '',
                            'invoices': _('Orden POS a Crédito'),
                            'amount': amount,
                        })

        all_details = payment_details + pos_credit_details
        methods_list = sorted(method_totals.values(), key=lambda x: x['amount'], reverse=True)
        grand_total = sum(d['amount'] for d in all_details)

        return {
            'company': self.company_id,
            'date_report': self.date_report,
            'time_report': fields.Datetime.context_timestamp(
                self, datetime.now()
            ).strftime('%I:%M %p'),
            'methods': methods_list,
            'details': all_details,
            'grand_total': grand_total,
            'total_count': len(all_details),
        }
