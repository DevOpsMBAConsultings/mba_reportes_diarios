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

    def _is_pos_invoice(self, inv):
        """
        Indica si la factura se originó en el Punto de Venta.

        point_of_sale añade 'pos_order_ids' a account.move (One2many hacia
        pos.order). Acceso defensivo: este módulo solo depende de 'account'.
        """
        if 'pos_order_ids' not in inv._fields:
            return False
        return bool(inv.pos_order_ids)

    def _get_invoices(self):
        """
        Facturas publicadas del día originadas en el Punto de Venta.

        Regla de negocio de Moto Lider: el cierre de caja es POS
        (pos.order -> account.move). El canal de distribución
        (sale.order -> account.move) no es caja y no entra en este reporte;
        su cartera se cubre en el reporte de Cobros CxC.
        """
        domain = [
            ('invoice_date', '=', self.date_report),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ]
        if self.journal_ids:
            domain.append(('journal_id', 'in', self.journal_ids.ids))

        invoices = self.env['account.move'].search(domain, order='name asc')

        # Si POS no está instalado no hay nada que acotar.
        if 'pos_order_ids' not in self.env['account.move']._fields:
            return invoices
        return invoices.filtered(lambda i: self._is_pos_invoice(i))

    # ── Clasificación de pagos ──────────────────────────────────────────────

    def _empty_breakdown(self):
        """Desglose de cobros en cero."""
        return {
            'efectivo': 0.0,
            'tarjeta': 0.0,
            'transferencia': 0.0,
            'voucher_count': 0,
            'total': 0.0,
        }

    def _group_pos_payments(self, invoices):
        """
        Desglosa los cobros de caja a partir de los pagos del POS.

        El POS no genera registros account.payment: pos.payment crea asientos
        contables directamente (ver pos_payment._create_payment_moves en
        point_of_sale). Por eso el desglose de caja debe leerse desde
        pos.payment y no desde account.payment.

        Clasificación por pos.payment.method.type, que Odoo define como
        cash | bank | pay_later. Dentro de 'bank' se separa tarjeta de
        transferencia por nombre del método.
        """
        result = self._empty_breakdown()

        if 'pos_order_ids' not in self.env['account.move']._fields:
            return result

        CARD_KEYWORDS = (
            'tarjeta', 'card', 'visa', 'master', 'clave',
            'datafast', 'pos terminal', 'débito', 'debito',
        )

        for inv in invoices:
            sign = 1 if inv.move_type == 'out_invoice' else -1
            for order in inv.pos_order_ids:
                for pp in order.payment_ids:
                    amount = (pp.amount or 0.0) * sign
                    method = pp.payment_method_id
                    mtype = method.type
                    mname = (method.name or '').lower()

                    if mtype == 'cash':
                        result['efectivo'] += amount
                    elif mtype == 'bank':
                        if any(kw in mname for kw in CARD_KEYWORDS):
                            result['tarjeta'] += amount
                            result['voucher_count'] += 1
                        else:
                            result['transferencia'] += amount
                    # 'pay_later' (cuenta cliente) no se contabiliza como
                    # ingreso de caja: no entró dinero. Moto Lider no da de
                    # alta ese método, pero se ignora explícitamente por si
                    # alguien lo habilita.

        result['total'] = (
            result['efectivo'] + result['tarjeta'] + result['transferencia']
        )
        return result

    # ── Datos del reporte ───────────────────────────────────────────────────

    def _is_invoice_credit(self, inv):
        """Determina si una factura es a crédito o contado."""
        # 0. POS es siempre contado: la caja es venta transaccional, el
        #    cliente paga y se va. El crédito vive en el canal de ventas.
        if self._is_pos_invoice(inv):
            return False

        # 1. Si existe el campo DGI (mba_pa_edi)
        if 'dgi_payment_term_type' in inv._fields and inv.dgi_payment_term_type:
            return inv.dgi_payment_term_type == 'credito'

        # 2. Términos de Pago estándar de Odoo (invoice_payment_term_id)
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

    def _get_report_data(self):
        """
        Calcula todos los datos necesarios para el reporte PDF.
        Retorna un diccionario con las 4 secciones del reporte.
        """
        self.ensure_one()

        invoices = self._get_invoices()

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

        # Contado vs Crédito (DGI o Término de Pago Odoo)
        inv_credito = invoices.filtered(lambda i: self._is_invoice_credit(i))
        inv_contado = invoices - inv_credito

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

        # ── Desglose de cobros de caja (desde pos.payment) ───────────────
        contado_breakdown = self._group_pos_payments(invoices)

        # ── Estadísticas CxC ────────────────────────────────────────────
        # La caja no genera cartera: en POS el cliente paga y se va. Estas
        # cifras quedan en cero por diseño y la cartera del canal de ventas
        # se reporta en "Cobros de Cuentas por Cobrar (CxC)".
        cxc_breakdown = self._empty_breakdown()
        num_facturas_credito = len(
            inv_credito.filtered(lambda i: i.move_type == 'out_invoice')
        )
        num_pagos_cxc = 0
        monto_pagos_cxc = 0.0

        total_ingresos_general = contado_breakdown['total']

        # ── Tabla de transacciones ──────────────────────────────────────
        transactions = []
        for inv in invoices:
            sign = 1 if inv.move_type == 'out_invoice' else -1
            monto_neto = (inv.amount_untaxed or 0.0) * sign
            impuestos = (inv.amount_tax or 0.0) * sign
            amount_total = (inv.amount_total or 0.0) * sign

            is_contado = not self._is_invoice_credit(inv)

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
