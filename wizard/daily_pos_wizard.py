# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime, time, timedelta


class MbaDailyPosWizard(models.TransientModel):
    _name = 'mba.daily.pos.wizard'
    _description = 'Wizard - Cierre de Caja Diario (POS)'

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

    # ── Validación de módulo ────────────────────────────────────────────────

    def _check_pos_installed(self):
        """Verifica que el módulo POS esté instalado."""
        if 'pos.order' not in self.env:
            raise UserError(_(
                "El módulo Punto de Venta (POS) no está instalado.\n\n"
                "Instale el módulo 'point_of_sale' para poder utilizar "
                "este reporte."
            ))

    # ── Acción principal ────────────────────────────────────────────────────

    def action_print_report(self):
        """Genera el reporte PDF de cierre de caja POS."""
        self.ensure_one()
        self._check_pos_installed()
        return self.env.ref(
            'mba_reportes_diarios.action_report_daily_pos'
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
        Calcula todos los datos necesarios para el reporte PDF de POS.
        Accede a modelos POS de forma dinámica (sin dependencia dura).
        """
        self.ensure_one()
        self._check_pos_installed()

        PosOrder = self.env['pos.order']
        PosSession = self.env['pos.session']

        # ── Rango de fecha ──────────────────────────────────────────────
        date_start = datetime.combine(self.date_report, time.min)
        date_end = datetime.combine(self.date_report, time.max)

        # ── Órdenes POS del día ─────────────────────────────────────────
        orders = PosOrder.search([
            ('date_order', '>=', date_start),
            ('date_order', '<=', date_end),
            ('state', 'in', ('paid', 'done', 'invoiced')),
            ('company_id', '=', self.company_id.id),
        ], order='name asc')

        # ── Sesiones involucradas ───────────────────────────────────────
        session_ids = orders.mapped('session_id')
        sessions_info = []
        for session in session_ids:
            sessions_info.append({
                'name': session.name or '',
                'config_name': session.config_id.name or '',
                'user': session.user_id.name or '',
                'state': dict(session._fields['state'].selection).get(
                    session.state, session.state
                ),
                'start': session.start_at,
                'stop': session.stop_at,
            })

        # ── Totales generales ───────────────────────────────────────────
        total_ventas = sum(orders.mapped('amount_total'))
        total_impuestos = sum(orders.mapped('amount_tax'))
        total_sin_impuesto = total_ventas - total_impuestos
        total_ordenes = len(orders)

        # ── Desglose por método de pago POS ─────────────────────────────
        payment_breakdown = {}
        if 'pos.payment' in self.env:
            PosPayment = self.env['pos.payment']
            pos_payments = PosPayment.search([
                ('pos_order_id', 'in', orders.ids),
            ])
            for pp in pos_payments:
                method_name = pp.payment_method_id.name or _('Otros')
                if method_name not in payment_breakdown:
                    payment_breakdown[method_name] = {
                        'name': method_name,
                        'amount': 0.0,
                        'count': 0,
                    }
                payment_breakdown[method_name]['amount'] += pp.amount or 0.0
                payment_breakdown[method_name]['count'] += 1

        payment_methods = sorted(
            payment_breakdown.values(),
            key=lambda x: x['amount'],
            reverse=True,
        )
        total_pagos = sum(m['amount'] for m in payment_methods)

        # ── Detalle de órdenes ──────────────────────────────────────────
        order_details = []
        for order in orders:
            # Método de pago de la orden
            pay_methods = []
            if 'pos.payment' in self.env:
                for pp in order.payment_ids:
                    pay_methods.append(pp.payment_method_id.name or '')
            pay_method_str = ', '.join(pay_methods) if pay_methods else ''

            order_details.append({
                'order_id': order.id,
                'name': order.name or '',
                'partner_id': order.partner_id.id if order.partner_id else False,
                'partner': order.partner_id.name or _('Cliente Genérico'),
                'date': fields.Datetime.context_timestamp(self, order.date_order).strftime('%I:%M %p') if order.date_order else '',
                'amount_untaxed': (order.amount_total or 0.0) - (order.amount_tax or 0.0),
                'amount_tax': order.amount_tax or 0.0,
                'amount_total': order.amount_total or 0.0,
                'payment_method': pay_method_str,
            })

        order_totals = {
            'amount_untaxed': sum(o['amount_untaxed'] for o in order_details),
            'amount_tax': sum(o['amount_tax'] for o in order_details),
            'amount_total': sum(o['amount_total'] for o in order_details),
        }

        # ── Productos vendidos ──────────────────────────────────────────
        product_data = {}
        for order in orders:
            for line in order.lines:
                if not line.product_id:
                    continue
                key = line.product_id.id
                if key not in product_data:
                    product_data[key] = {
                        'product_id': line.product_id.id,
                        'item': line.product_id.default_code or '',
                        'descripcion': line.product_id.name or '',
                        'cantidad': 0.0,
                        'monto_bruto': 0.0,
                        'impuestos': 0.0,
                        'monto_neto': 0.0,
                    }
                product_data[key]['cantidad'] += line.qty or 0.0
                subtotal = line.price_subtotal or 0.0
                total = line.price_subtotal_incl or 0.0
                product_data[key]['monto_bruto'] += subtotal
                product_data[key]['impuestos'] += (total - subtotal)
                product_data[key]['monto_neto'] += total

        products = sorted(product_data.values(), key=lambda p: p['descripcion'])
        prod_totals = {
            'cantidad': sum(p['cantidad'] for p in products),
            'monto_bruto': sum(p['monto_bruto'] for p in products),
            'impuestos': sum(p['impuestos'] for p in products),
            'monto_neto': sum(p['monto_neto'] for p in products),
        }

        return {
            'company': self.company_id,
            'date_report': self.date_report,
            'time_report': fields.Datetime.context_timestamp(
                self, datetime.now()
            ).strftime('%I:%M %p'),
            # Resumen
            'sessions': sessions_info,
            'total_ventas': total_ventas,
            'total_impuestos': total_impuestos,
            'total_sin_impuesto': total_sin_impuesto,
            'total_ordenes': total_ordenes,
            # Pagos
            'payment_methods': payment_methods,
            'total_pagos': total_pagos,
            # Detalle de órdenes
            'orders': order_details,
            'order_totals': order_totals,
            # Productos
            'products': products,
            'prod_totals': prod_totals,
        }

    # ── API para Cliente Dinámico (OWL Frontend) ────────────────────────────

    @api.model
    def get_client_report_data(self, date_report=None, company_id=None):
        """
        Retorna los datos formateados para el Dashboard OWL de Cierre POS.
        """
        if not date_report:
            date_report = fields.Date.context_today(self)
        if not company_id:
            company_id = self.env.company.id

        wizard = self.create({
            'date_report': date_report,
            'company_id': company_id,
        })
        raw_data = wizard._get_report_data()

        # Formatear números
        for m in raw_data['payment_methods']:
            m['formatted_amount'] = wizard.fmt(m['amount'])

        for o in raw_data['orders']:
            o['formatted_amount_untaxed'] = wizard.fmt(o['amount_untaxed'])
            o['formatted_amount_tax'] = wizard.fmt(o['amount_tax'])
            o['formatted_amount_total'] = wizard.fmt(o['amount_total'])

        ot = raw_data['order_totals']
        ot['formatted_amount_untaxed'] = wizard.fmt(ot['amount_untaxed'])
        ot['formatted_amount_tax'] = wizard.fmt(ot['amount_tax'])
        ot['formatted_amount_total'] = wizard.fmt(ot['amount_total'])

        for p in raw_data['products']:
            p['formatted_cantidad'] = wizard.fmt_int(p['cantidad'])
            p['formatted_monto_bruto'] = wizard.fmt(p['monto_bruto'])
            p['formatted_impuestos'] = wizard.fmt(p['impuestos'])
            p['formatted_monto_neto'] = wizard.fmt(p['monto_neto'])

        pt = raw_data['prod_totals']
        pt['formatted_cantidad'] = wizard.fmt_int(pt['cantidad'])
        pt['formatted_monto_bruto'] = wizard.fmt(pt['monto_bruto'])
        pt['formatted_impuestos'] = wizard.fmt(pt['impuestos'])
        pt['formatted_monto_neto'] = wizard.fmt(pt['monto_neto'])

        return {
            'company_name': raw_data['company'].name,
            'company_id': raw_data['company'].id,
            'date_report': str(raw_data['date_report']),
            'time_report': raw_data['time_report'],
            'sessions': raw_data['sessions'],
            'total_ventas': raw_data['total_ventas'],
            'formatted_total_ventas': wizard.fmt(raw_data['total_ventas']),
            'total_impuestos': raw_data['total_impuestos'],
            'formatted_total_impuestos': wizard.fmt(raw_data['total_impuestos']),
            'total_sin_impuesto': raw_data['total_sin_impuesto'],
            'formatted_total_sin_impuesto': wizard.fmt(raw_data['total_sin_impuesto']),
            'total_ordenes': raw_data['total_ordenes'],
            'payment_methods': raw_data['payment_methods'],
            'total_pagos': raw_data['total_pagos'],
            'formatted_total_pagos': wizard.fmt(raw_data['total_pagos']),
            'orders': raw_data['orders'],
            'order_totals': ot,
            'products': raw_data['products'],
            'prod_totals': pt,
        }

