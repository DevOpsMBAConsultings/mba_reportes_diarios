# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import datetime, date, time, timedelta
from dateutil.relativedelta import relativedelta


class MbaDailyPosWizard(models.TransientModel):
    _name = 'mba.daily.pos.wizard'
    _description = 'Wizard - Cierre de Caja Diario (POS)'

    date_report = fields.Date(
        "Fecha del Reporte",
        required=True,
        default=fields.Date.context_today,
    )
    period_type = fields.Selection(
        [
            ('day', 'Diario'),
            ('month', 'Mensual'),
        ],
        string="Tipo de Cierre",
        default='day',
        required=True,
        help="Diario cubre un solo día. Mensual cubre el mes completo de la "
             "fecha seleccionada.",
    )
    # Para el cierre mensual: se elige mes y anio, no una fecha completa.
    month = fields.Selection(
        [
            ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'),
            ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
            ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'),
            ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre'),
        ],
        string="Mes",
        default=lambda self: str(fields.Date.context_today(self).month),
    )
    year = fields.Integer(
        string="Año",
        default=lambda self: fields.Date.context_today(self).year,
    )
    company_id = fields.Many2one(
        'res.company',
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
    )

    # ── Rango de fechas ─────────────────────────────────────────────────────

    def _get_date_bounds(self):
        """
        Devuelve (desde, hasta) como objetos date segun period_type.

        Un solo wizard sirve para el cierre diario y el mensual. La logica de
        agregacion es EXACTAMENTE la misma en los dos casos: lo unico que
        cambia es el rango. Asi no pueden divergir — si se corrige un calculo,
        queda corregido en ambos.

        En modo mensual se toma el mes de date_report completo, sin importar
        que dia del mes se haya elegido.
        """
        self.ensure_one()
        if self.period_type == 'month':
            today = fields.Date.context_today(self)
            year = self.year or today.year
            month = int(self.month or today.month)
            first = date(year, month, 1)
            last = first + relativedelta(months=1, days=-1)
            return first, last
        return self.date_report, self.date_report

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

    # ── Ventas fuera de caja (módulo de Ventas / facturación directa) ───────

    def _get_sale_invoices(self):
        """
        Facturas del día que NO se originaron en el Punto de Venta.

        Particion sin solape: el POS aporta pos.order y esto aporta las
        account.move que no tienen pos_order_ids. Una venta de caja facturada
        existe en los dos modelos, y si se sumaran ambos se contaria dos veces;
        por eso aqui se excluyen explicitamente.

        Acceso defensivo a pos_order_ids: el modulo solo depende de 'account'.
        """
        date_from, date_to = self._get_date_bounds()
        domain = [
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ]
        invoices = self.env['account.move'].search(domain, order='name asc')

        if 'pos_order_ids' not in self.env['account.move']._fields:
            return invoices
        return invoices.filtered(lambda i: not i.pos_order_ids)

    def _payment_method_label(self, payment):
        """
        Nombre del metodo de cobro de un account.payment.

        Fuente principal: payment_method_line_id.name, el campo "Nombre" que
        se configura en Contabilidad -> Diarios -> pestaña "Pagos entrantes".
        Es un campo NUCLEO de 'account' (no requiere point_of_sale) y es
        OBLIGATORIO en la pantalla "Registrar pago" de cualquier factura, asi
        que esta poblado para absolutamente todos los pagos del canal de
        Ventas.

        Moto Lider renombro manualmente esas lineas para que coincidan
        textualmente con los nombres de pos.payment.method del POS (Tarjeta
        de Crédito, Tarjeta de Débito, Transf. Banesco, Transf. Banco
        General), asi que este campo por si solo ya unifica el nombre entre
        POS y Ventas -> Registrar pago, sin depender de que point_of_sale
        este instalado ni de ninguna pantalla nueva.

        Se detecta si la linea fue efectivamente renombrada comparando
        contra el nombre generico de su account.payment.method (ej. "Pago
        manual"): si coincide, nadie la personalizo todavia y el nombre no
        aporta informacion util para "por donde entro el dinero", asi que se
        cae a pos.payment.method (por si el pago SI vino de una sesion POS,
        donde payment_method_line_id no es significativo) o al nombre del
        diario, en ese orden. Acceso 100% defensivo via _fields.
        """
        line = payment.payment_method_line_id
        if line and line.name and line.name != (line.payment_method_id.name or ''):
            return line.name

        journal = payment.journal_id
        if 'pos_payment_method_id' in payment._fields and payment.pos_payment_method_id:
            return payment.pos_payment_method_id.name
        if journal and 'pos_payment_method_ids' in journal._fields:
            methods = journal.pos_payment_method_ids
            if len(methods) == 1:
                return methods.name
        return journal.name or ''

    def _invoice_payment_label(self, invoice):
        """
        Metodo de cobro de una factura de ventas.

        Si esta conciliada con pagos, se usa el metodo de cobro unificado de
        esos pagos (ver _payment_method_label). Si no, es una venta a
        credito y no entro a caja hoy.
        """
        if 'matched_payment_ids' in invoice._fields and invoice.matched_payment_ids:
            names = []
            for pay in invoice.matched_payment_ids:
                name = self._payment_method_label(pay)
                if name and name not in names:
                    names.append(name)
            if names:
                return ', '.join(names)
        if invoice.payment_state in ('paid', 'in_payment'):
            return _('Cobrada')
        return _('Crédito')

    # ── Datos del reporte ───────────────────────────────────────────────────

    def _get_report_data(self):
        """
        Calcula todos los datos necesarios para el reporte PDF.

        Incluye las ventas de caja (pos.order) y las ventas facturadas fuera
        de caja (account.move sin pos_order_ids), en las tres secciones:
        detalle de ordenes, productos vendidos y desglose por metodo de pago.

        Accede a modelos POS de forma dinámica (sin dependencia dura).
        """
        self.ensure_one()
        self._check_pos_installed()

        PosOrder = self.env['pos.order']
        PosSession = self.env['pos.session']

        # ── Rango de fecha ──────────────────────────────────────────────
        bound_from, bound_to = self._get_date_bounds()
        date_start = datetime.combine(bound_from, time.min)
        date_end = datetime.combine(bound_to, time.max)

        # ── Órdenes POS del periodo ─────────────────────────────────────
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

        # ── Facturas de venta fuera de caja ─────────────────────────────
        invoices = self._get_sale_invoices()

        # ── Totales generales (caja + ventas) ───────────────────────────
        # Las notas de credito (out_refund) restan.
        inv_total = sum(
            (i.amount_total if i.move_type == 'out_invoice' else -i.amount_total)
            for i in invoices
        )
        inv_tax = sum(
            (i.amount_tax if i.move_type == 'out_invoice' else -i.amount_tax)
            for i in invoices
        )

        total_ventas_pos = sum(orders.mapped('amount_total'))
        total_impuestos_pos = sum(orders.mapped('amount_tax'))

        total_ventas = total_ventas_pos + inv_total
        total_impuestos = total_impuestos_pos + inv_tax
        total_sin_impuesto = total_ventas - total_impuestos
        total_ordenes = len(orders) + len(invoices)

        # Desglose por canal, para que el cajero pueda cuadrar su arqueo
        # aunque el reporte ahora incluya ventas que no pasaron por caja.
        total_ventas_ventas = inv_total
        total_ordenes_pos = len(orders)
        total_ordenes_ventas = len(invoices)

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

        # ── Desglose de las ventas fuera de caja ────────────────────────
        for inv in invoices:
            method_name = self._invoice_payment_label(inv)
            sign = 1 if inv.move_type == 'out_invoice' else -1
            if method_name not in payment_breakdown:
                payment_breakdown[method_name] = {
                    'name': method_name,
                    'amount': 0.0,
                    'count': 0,
                }
            payment_breakdown[method_name]['amount'] += sign * (inv.amount_total or 0.0)
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
                'res_model': 'pos.order',
                'origin': 'POS',
                'name': order.name or '',
                'partner_id': order.partner_id.id if order.partner_id else False,
                'partner': order.partner_id.name or _('Cliente Genérico'),
                'date': fields.Datetime.context_timestamp(self, order.date_order).strftime('%I:%M %p') if order.date_order else '',
                'amount_untaxed': (order.amount_total or 0.0) - (order.amount_tax or 0.0),
                'amount_tax': order.amount_tax or 0.0,
                'amount_total': order.amount_total or 0.0,
                'payment_method': pay_method_str,
            })

        # ── Detalle de las ventas fuera de caja ─────────────────────────
        for inv in invoices:
            sign = 1 if inv.move_type == 'out_invoice' else -1
            order_details.append({
                'order_id': inv.id,
                'res_model': 'account.move',
                'origin': 'Ventas',
                'name': inv.name or '',
                'partner_id': inv.partner_id.id if inv.partner_id else False,
                'partner': inv.partner_id.name or _('Sin cliente'),
                'date': fields.Datetime.context_timestamp(
                    self, inv.create_date
                ).strftime('%I:%M %p') if inv.create_date else '',
                'amount_untaxed': sign * (inv.amount_untaxed or 0.0),
                'amount_tax': sign * (inv.amount_tax or 0.0),
                'amount_total': sign * (inv.amount_total or 0.0),
                'payment_method': self._invoice_payment_label(inv),
            })

        order_details.sort(key=lambda o: (o['origin'], o['name']))

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

        # ── Productos de las ventas fuera de caja ───────────────────────
        for inv in invoices:
            sign = 1 if inv.move_type == 'out_invoice' else -1
            for line in inv.invoice_line_ids:
                # OJO: en Odoo 18 display_type de una linea normal vale
                # 'product', que es truthy (account_move_line.py:306-320).
                # Un `if line.display_type: continue` descarta TODAS las
                # lineas de producto. Hay que excluir solo secciones y notas.
                if not line.product_id:
                    continue
                if line.display_type in ('line_section', 'line_note'):
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
                subtotal = line.price_subtotal or 0.0
                total = line.price_total or 0.0
                product_data[key]['cantidad'] += sign * (line.quantity or 0.0)
                product_data[key]['monto_bruto'] += sign * subtotal
                product_data[key]['impuestos'] += sign * (total - subtotal)
                product_data[key]['monto_neto'] += sign * total

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
            'date_from': bound_from,
            'date_to': bound_to,
            'is_range': bound_from != bound_to,
            'time_report': fields.Datetime.context_timestamp(
                self, datetime.now()
            ).strftime('%I:%M %p'),
            # Resumen
            'sessions': sessions_info,
            'total_ventas': total_ventas,
            'total_impuestos': total_impuestos,
            'total_sin_impuesto': total_sin_impuesto,
            'total_ordenes': total_ordenes,
            # Desglose por canal
            'total_ventas_pos': total_ventas_pos,
            'total_ventas_ventas': total_ventas_ventas,
            'total_ordenes_pos': total_ordenes_pos,
            'total_ordenes_ventas': total_ordenes_ventas,
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
    def get_client_report_data(self, date_report=None, company_id=None,
                               period_type='day'):
        """
        Retorna los datos formateados para el Dashboard OWL de Cierre.

        period_type acepta 'day' (por defecto, comportamiento historico) o
        'month'. El componente OWL actual no lo envia, asi que sigue viendo
        el cierre del dia exactamente como antes; el parametro queda listo
        por si se agrega el selector en pantalla.
        """
        if not date_report:
            date_report = fields.Date.context_today(self)
        if not company_id:
            company_id = self.env.company.id

        vals = {
            'date_report': date_report,
            'period_type': period_type or 'day',
            'company_id': company_id,
        }
        # En modo mensual, _get_date_bounds() lee month/year. Si no se
        # rellenan aqui, caen en su default (el mes ACTUAL) y el reporte
        # ignora el mes que el usuario eligio en pantalla.
        if vals['period_type'] == 'month':
            ref = fields.Date.to_date(date_report)
            vals['month'] = str(ref.month)
            vals['year'] = ref.year

        wizard = self.create(vals)
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
            # Para que la pantalla OWL pueda titular "del Día" o "del Mes"
            'is_range': raw_data['is_range'],
            'date_from': str(raw_data['date_from']),
            'date_to': str(raw_data['date_to']),
            'total_ventas_pos': raw_data['total_ventas_pos'],
            'formatted_total_ventas_pos': wizard.fmt(raw_data['total_ventas_pos']),
            'total_ventas_ventas': raw_data['total_ventas_ventas'],
            'formatted_total_ventas_ventas': wizard.fmt(raw_data['total_ventas_ventas']),
            'total_ordenes_pos': raw_data['total_ordenes_pos'],
            'total_ordenes_ventas': raw_data['total_ordenes_ventas'],
            'payment_methods': raw_data['payment_methods'],
            'total_pagos': raw_data['total_pagos'],
            'formatted_total_pagos': wizard.fmt(raw_data['total_pagos']),
            'orders': raw_data['orders'],
            'order_totals': ot,
            'products': raw_data['products'],
            'prod_totals': pt,
        }

