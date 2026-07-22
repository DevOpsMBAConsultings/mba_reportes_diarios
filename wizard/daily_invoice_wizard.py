# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime


class MbaDailyInvoiceWizard(models.TransientModel):
    _name = 'mba.daily.invoice.wizard'
    _description = 'Wizard - Cierre de Caja Diario (Facturación)'

    date_report = fields.Date(
        "Fecha del Reporte",
        required=True,
        default=fields.Date.context_today,
    )
    journal_ids = fields.Many2many(
        'account.journal',
        string="Serie / Diarios de Venta",
        domain=[('type', '=', 'sale')],
        help="Filtrar por diarios de venta específicos. Dejar vacío para incluir todos.",
    )
    company_id = fields.Many2one(
        'res.company',
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
    )

    # ── Acción principal ────────────────────────────────────────────────────

    def action_print_report(self):
        """Genera el reporte PDF de cierre de caja (facturación)."""
        self.ensure_one()
        return self.env.ref(
            'mba_reportes_diarios.action_report_daily_invoice'
        ).report_action(self)

    # ── Helpers de formato ──────────────────────────────────────────────────

    def fmt(self, value):
        """Formatea un número con 2 decimales y separador de miles."""
        if value is None:
            value = 0.0
        return '{:,.2f}'.format(value)

    def fmt_int(self, value):
        """Formatea un número entero con separador de miles."""
        if value is None:
            value = 0
        return '{:,.0f}'.format(value)

    # ── Consultas base ──────────────────────────────────────────────────────

    def _get_invoices(self):
        """Obtiene las facturas publicadas del día."""
        domain = [
            ('invoice_date', '=', self.date_report),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ]
        if self.journal_ids:
            domain.append(('journal_id', 'in', self.journal_ids.ids))
        return self.env['account.move'].search(domain, order='name asc')

    def _get_payments(self):
        """Obtiene los pagos entrantes publicados del día."""
        domain = [
            ('date', '=', self.date_report),
            ('payment_type', '=', 'inbound'),
            ('state', 'in', ('posted', 'reconciled')),
            ('company_id', '=', self.company_id.id),
        ]
        return self.env['account.payment'].search(domain)

    # ── Clasificación de pagos ──────────────────────────────────────────────

    def _classify_payments(self, payments):
        """
        Clasifica los pagos del día en:
        - contado: reconciliados con facturas del mismo día
        - cxc: reconciliados con facturas de días anteriores (cobros de crédito)
        """
        contado = self.env['account.payment']
        cxc = self.env['account.payment']

        for payment in payments:
            is_contado = False
            # Rastrear reconciliación a través de las líneas del asiento
            receivable_lines = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
            )
            for line in receivable_lines:
                # matched_debit_ids: este pago (crédito) reconciliado contra débitos (facturas)
                for partial in line.matched_debit_ids:
                    invoice_move = partial.debit_move_id.move_id
                    if (invoice_move.is_invoice()
                            and invoice_move.invoice_date == self.date_report):
                        is_contado = True
                        break
                if is_contado:
                    break

            if is_contado:
                contado |= payment
            else:
                cxc |= payment

        return contado, cxc

    def _group_payments_by_type(self, payments):
        """
        Agrupa pagos por tipo de diario para el desglose:
        - cash → Efectivo
        - bank con nombre tipo tarjeta → Tarjeta de Crédito
        - bank otros → Transferencia
        """
        result = {
            'efectivo': 0.0,
            'tarjeta': 0.0,
            'transferencia': 0.0,
            'voucher_count': 0,
        }
        CARD_KEYWORDS = (
            'tarjeta', 'card', 'visa', 'master', 'clave',
            'datafast', 'pos terminal', 'débito', 'debito',
        )
        for p in payments:
            amount = p.amount or 0.0
            if p.journal_id.type == 'cash':
                result['efectivo'] += amount
            elif p.journal_id.type == 'bank':
                jname = (p.journal_id.name or '').lower()
                if any(kw in jname for kw in CARD_KEYWORDS):
                    result['tarjeta'] += amount
                    result['voucher_count'] += 1
                else:
                    result['transferencia'] += amount

        result['total'] = (
            result['efectivo'] + result['tarjeta'] + result['transferencia']
        )
        return result

    # ── Datos del reporte ───────────────────────────────────────────────────

    def _get_report_data(self):
        """
        Calcula todos los datos necesarios para el reporte PDF.
        Retorna un diccionario con las 4 secciones del reporte.
        """
        self.ensure_one()

        invoices = self._get_invoices()
        payments = self._get_payments()
        contado_payments, cxc_payments = self._classify_payments(payments)

        # ── Totales de facturas ─────────────────────────────────────────
        inv_regular = invoices.filtered(lambda i: i.move_type == 'out_invoice')
        inv_refund = invoices.filtered(lambda i: i.move_type == 'out_refund')

        total_ventas_brutas = (
            sum(inv_regular.mapped('amount_untaxed'))
            - sum(inv_refund.mapped('amount_untaxed'))
        )
        total_itbms = (
            sum(inv_regular.mapped('amount_tax'))
            - sum(inv_refund.mapped('amount_tax'))
        )

        # Contado vs Crédito (campo DGI si existe, sino todo como contado)
        has_dgi = 'dgi_payment_term_type' in self.env['account.move']._fields

        if has_dgi:
            inv_contado = invoices.filtered(
                lambda i: i.dgi_payment_term_type == 'contado'
            )
            inv_credito = invoices.filtered(
                lambda i: i.dgi_payment_term_type == 'credito'
            )
        else:
            # Sin campos DGI → todo es contado
            inv_contado = invoices
            inv_credito = self.env['account.move']

        def _sum_signed(records, field='amount_total'):
            """Suma con signo: positivo para facturas, negativo para notas de crédito."""
            total = 0.0
            for inv in records:
                sign = 1 if inv.move_type == 'out_invoice' else -1
                total += (getattr(inv, field) or 0.0) * sign
            return total

        total_contado = _sum_signed(inv_contado)
        total_credito = _sum_signed(inv_credito)

        # Gravable vs Exento (basado en si la línea tiene impuestos)
        total_gravable = 0.0
        total_exento = 0.0
        for inv in invoices:
            sign = 1 if inv.move_type == 'out_invoice' else -1
            for line in inv.invoice_line_ids:
                if line.display_type in ('line_section', 'line_note'):
                    continue
                subtotal = (line.price_subtotal or 0.0) * sign
                if line.tax_ids:
                    total_gravable += subtotal
                else:
                    total_exento += subtotal

        # ── Desglose de pagos ───────────────────────────────────────────
        contado_breakdown = self._group_payments_by_type(contado_payments)
        cxc_breakdown = self._group_payments_by_type(cxc_payments)

        # ── Estadísticas CxC ────────────────────────────────────────────
        num_facturas_credito = len(
            inv_credito.filtered(lambda i: i.move_type == 'out_invoice')
        )
        num_pagos_cxc = len(cxc_payments)
        monto_pagos_cxc = sum(cxc_payments.mapped('amount'))

        total_ingresos_general = contado_breakdown['total'] + cxc_breakdown['total']

        # ── Tabla de transacciones ──────────────────────────────────────
        transactions = []
        for inv in invoices:
            sign = 1 if inv.move_type == 'out_invoice' else -1
            monto_neto = (inv.amount_untaxed or 0.0) * sign
            impuestos = (inv.amount_tax or 0.0) * sign
            amount_total = (inv.amount_total or 0.0) * sign

            is_contado = (not has_dgi) or (inv.dgi_payment_term_type == 'contado')

            # Código del partner (ref o vat)
            partner_code = ''
            if inv.partner_id.ref:
                partner_code = inv.partner_id.ref
            elif inv.partner_id.vat:
                partner_code = inv.partner_id.vat

            descripcion = (
                '%s-%s' % (partner_code, inv.partner_id.name or '')
                if partner_code
                else (inv.partner_id.name or '')
            )

            transactions.append({
                'documento': inv.name or '',
                'descripcion': descripcion,
                'monto_neto': monto_neto,
                'impuestos': impuestos,
                'contado': amount_total if is_contado else 0.0,
                'credito': amount_total if not is_contado else 0.0,
            })

        tx_totals = {
            'monto_neto': sum(t['monto_neto'] for t in transactions),
            'impuestos': sum(t['impuestos'] for t in transactions),
            'contado': sum(t['contado'] for t in transactions),
            'credito': sum(t['credito'] for t in transactions),
        }

        # ── Tabla de productos vendidos ─────────────────────────────────
        product_data = {}
        for inv in invoices:
            sign = 1 if inv.move_type == 'out_invoice' else -1
            for line in inv.invoice_line_ids:
                if line.display_type in ('line_section', 'line_note'):
                    continue
                if not line.product_id:
                    continue

                key = line.product_id.id
                if key not in product_data:
                    product_data[key] = {
                        'item': line.product_id.default_code or '',
                        'descripcion': line.product_id.name or line.name or '',
                        'cantidad': 0.0,
                        'monto_bruto': 0.0,
                        'impuestos': 0.0,
                        'monto_neto': 0.0,
                    }
                product_data[key]['cantidad'] += (line.quantity or 0.0) * sign
                product_data[key]['monto_bruto'] += (line.price_subtotal or 0.0) * sign
                tax_amount = ((line.price_total or 0.0) - (line.price_subtotal or 0.0)) * sign
                product_data[key]['impuestos'] += tax_amount
                product_data[key]['monto_neto'] += (line.price_total or 0.0) * sign

        products = sorted(product_data.values(), key=lambda p: p['descripcion'])

        prod_totals = {
            'cantidad': sum(p['cantidad'] for p in products),
            'monto_bruto': sum(p['monto_bruto'] for p in products),
            'impuestos': sum(p['impuestos'] for p in products),
            'monto_neto': sum(p['monto_neto'] for p in products),
        }

        # Nombre de la serie/diario
        if self.journal_ids:
            series_name = ', '.join(self.journal_ids.mapped('name'))
        else:
            series_name = 'Todas'

        return {
            'company': self.company_id,
            'date_report': self.date_report,
            'time_report': fields.Datetime.context_timestamp(
                self, datetime.now()
            ).strftime('%I:%M %p'),
            'series_name': series_name,
            # Sección 1: Resumen
            'summary': {
                'total_ventas_brutas': total_ventas_brutas,
                'total_itbms': total_itbms,
                'total_contado': total_contado,
                'total_credito': total_credito,
                'total_transacciones': len(invoices),
                'total_gravable': total_gravable,
                'total_exento': total_exento,
            },
            'contado_breakdown': contado_breakdown,
            # Sección 2: CxC
            'cxc': {
                'num_facturas': num_facturas_credito,
                'num_pagos': num_pagos_cxc,
                'monto_pagos': monto_pagos_cxc,
            },
            'cxc_breakdown': cxc_breakdown,
            'total_ingresos_general': total_ingresos_general,
            # Sección 3: Transacciones
            'transactions': transactions,
            'tx_totals': tx_totals,
            # Sección 4: Productos
            'products': products,
            'prod_totals': prod_totals,
        }
