# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import datetime


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

    # ── Clasificación de facturas ───────────────────────────────────────────

    def _is_pos_invoice(self, inv):
        """
        Indica si la factura se originó en el Punto de Venta.

        El módulo point_of_sale añade el campo 'pos_order_ids' a account.move
        (One2many hacia pos.order). Se accede de forma defensiva porque este
        módulo solo depende de 'account' y POS puede no estar instalado.
        """
        if 'pos_order_ids' not in inv._fields:
            return False
        return bool(inv.pos_order_ids)

    def _is_invoice_credit(self, inv):
        """
        Determina si una factura es a crédito.

        Regla de negocio de Moto Lider: la caja (POS) es siempre transaccional
        y de contado. El crédito vive exclusivamente en el canal de ventas
        (sale.order -> account.move) para distribución.
        """
        # 1. POS es siempre contado, sin importar el término que traiga.
        if self._is_pos_invoice(inv):
            return False

        # 2. Campo DGI (mba_pa_edi) si está disponible.
        if 'dgi_payment_term_type' in inv._fields and inv.dgi_payment_term_type:
            return inv.dgi_payment_term_type == 'credito'

        # 3. Términos de pago estándar de Odoo.
        term = inv.invoice_payment_term_id
        if term:
            tname = (term.name or '').lower()
            if any(kw in tname for kw in ('contado', 'inmediato', 'immediate', '0 día', '0 dia')):
                return False
            if any(kw in tname for kw in ('crédito', 'credito', '30', '60', '90', '120', 'día', 'dia')):
                return True
            for line in term.line_ids:
                if getattr(line, 'nb_days', 0) > 0:
                    return True

        return False

    def _get_reconciled_invoices(self, payment):
        """
        Devuelve las facturas conciliadas contra un pago entrante.

        Se recorre la conciliación a través de las líneas por cobrar del
        asiento del pago (matched_debit_ids: el pago es el crédito y la
        factura el débito).
        """
        invoices = self.env['account.move']
        receivable_lines = payment.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type == 'asset_receivable'
        )
        for line in receivable_lines:
            for partial in line.matched_debit_ids:
                inv_move = partial.debit_move_id.move_id
                if inv_move and inv_move.is_invoice():
                    invoices |= inv_move
        return invoices

    def _classify_journal(self, journal):
        """Traduce el diario a una etiqueta de método de cobro."""
        CARD_KEYWORDS = (
            'tarjeta', 'card', 'visa', 'master', 'clave',
            'datafast', 'pos terminal', 'débito', 'debito',
        )
        if not journal:
            return _('Otros')

        jname = (journal.name or '').lower()
        if journal.type == 'cash':
            return _('Efectivo')
        if journal.type == 'bank':
            if any(kw in jname for kw in CARD_KEYWORDS):
                return _('Tarjeta de Crédito / Débito')
            return _('Transferencia / Depósito Banco')
        return journal.name or _('Otros')

    # ── Consultas base ──────────────────────────────────────────────────────

    def _get_credit_invoices(self):
        """
        Facturas a crédito emitidas en el día por el canal de ventas.

        Sección informativa: NO suma a los totales de cobros, porque emitir
        una factura a crédito no representa una entrada de dinero.
        """
        invoices = self.env['account.move'].search([
            ('invoice_date', '=', self.date_report),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ], order='name asc')
        return invoices.filtered(lambda i: self._is_invoice_credit(i))

    # ── Datos del reporte ───────────────────────────────────────────────────

    def _get_report_data(self):
        """
        Calcula los datos del reporte PDF de Cobros CxC.

        Alcance (regla de negocio de Moto Lider): este reporte cubre
        exclusivamente la cartera del canal de ventas (sale.order ->
        account.move) con término de pago a crédito. La caja del Punto de
        Venta NO entra aquí: tiene su propio reporte de cierre.
        """
        self.ensure_one()

        # 1. Pagos entrantes del día.
        #    Odoo 18: los estados de account.payment son
        #    draft | in_process | paid | canceled | rejected
        payments = self.env['account.payment'].search([
            ('date', '=', self.date_report),
            ('payment_type', '=', 'inbound'),
            ('state', 'in', ('in_process', 'paid')),
            ('company_id', '=', self.company_id.id),
        ], order='partner_id, name asc')

        payment_details = []
        method_totals = {}

        for p in payments:
            reconciled = self._get_reconciled_invoices(p)

            # Filtro de alcance: solo cartera de ventas a crédito.
            # Un pago sin factura conciliada es un anticipo o abono a saldo;
            # se conserva porque POS no genera account.payment, de modo que
            # todo anticipo proviene por definición del canal de ventas.
            if reconciled:
                relevant = reconciled.filtered(
                    lambda i: self._is_invoice_credit(i)
                )
                if not relevant:
                    continue
                invoice_str = ', '.join(relevant.mapped('name'))
            else:
                invoice_str = _('Abono a Saldo / Anticipo')

            method_name = self._classify_journal(p.journal_id)
            amount = p.amount or 0.0

            if method_name not in method_totals:
                method_totals[method_name] = {
                    'name': method_name,
                    'amount': 0.0,
                    'count': 0,
                }
            method_totals[method_name]['amount'] += amount
            method_totals[method_name]['count'] += 1

            partner_name = p.partner_id.name or _('Cliente General')
            partner_ref = p.partner_id.ref or p.partner_id.vat or ''
            partner_label = f"[{partner_ref}] {partner_name}" if partner_ref else partner_name

            payment_details.append({
                'payment_name': p.name or '',
                'partner': partner_label,
                'method_name': method_name,
                'journal_name': p.journal_id.name if p.journal_id else '',
                'reference': p.memo or '',
                'invoices': invoice_str,
                'amount': amount,
            })

        methods_list = sorted(
            method_totals.values(), key=lambda x: x['amount'], reverse=True
        )
        grand_total = sum(d['amount'] for d in payment_details)

        # 2. Sección informativa: facturas a crédito emitidas hoy.
        credit_details = []
        for inv in self._get_credit_invoices():
            partner_ref = inv.partner_id.ref or inv.partner_id.vat or ''
            partner_name = inv.partner_id.name or ''
            partner_label = f"[{partner_ref}] {partner_name}" if partner_ref else partner_name

            credit_details.append({
                'name': inv.name or '',
                'partner': partner_label,
                'payment_term': inv.invoice_payment_term_id.name or '',
                'date_due': inv.invoice_date_due,
                'amount_total': inv.amount_total or 0.0,
                'amount_residual': inv.amount_residual or 0.0,
            })

        credit_totals = {
            'amount_total': sum(c['amount_total'] for c in credit_details),
            'amount_residual': sum(c['amount_residual'] for c in credit_details),
            'count': len(credit_details),
        }

        return {
            'company': self.company_id,
            'date_report': self.date_report,
            'time_report': fields.Datetime.context_timestamp(
                self, datetime.now()
            ).strftime('%I:%M %p'),
            # Cobros efectivamente recibidos
            'methods': methods_list,
            'details': payment_details,
            'grand_total': grand_total,
            'total_count': len(payment_details),
            # Informativo: facturación a crédito del día (no suma a cobros)
            'credit_invoices': credit_details,
            'credit_totals': credit_totals,
        }
