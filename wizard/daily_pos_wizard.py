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
    date_from = fields.Date(
        "Fecha Desde",
    )
    date_to = fields.Date(
        "Fecha Hasta",
    )
    period_type = fields.Selection(
        [
            ('day', 'Diario'),
            ('month', 'Mensual / Rango'),
        ],
        string="Tipo de Cierre",
        default='day',
        required=True,
        help="Diario cubre un solo día. Mensual / Rango cubre el período seleccionado.",
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
        Devuelve (desde, hasta) como objetos date segun period_type o date_from/date_to.

        Un solo wizard sirve para el cierre diario y el mensual. La logica de
        agregacion es EXACTAMENTE la misma en los dos casos: lo unico que
        cambia es el rango. Asi no pueden divergir — si se corrige un calculo,
        queda corregido en ambos.
        """
        self.ensure_one()
        if self.date_from and self.date_to:
            if self.date_from > self.date_to:
                return self.date_to, self.date_from
            return self.date_from, self.date_to
        if self.period_type == 'month':
            today = fields.Date.context_today(self)
            year = self.year or today.year
            month = int(self.month or today.month)
            first = date(year, month, 1)
            last = first + relativedelta(months=1, days=-1)
            return first, last
        return self.date_report, self.date_report

    # ── Detección de módulo POS ─────────────────────────────────────────────

    def _is_pos_installed(self):
        """Indica si el módulo POS está instalado en la base de datos."""
        return 'pos.order' in self.env

    # ── Acción principal ────────────────────────────────────────────────────

    def action_print_report(self):
        """Genera el reporte PDF de cierre de caja."""
        self.ensure_one()
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

    # ── Costo de ventas, utilidad e inventario ──────────────────────────────

    def _get_cost_and_inventory(self, date_start, date_end, total_ventas, products=None, ventas_invoices=None):
        """
        Costo de ventas del periodo, utilidad bruta e inventario actual,
        y desglose por categoría de producto (departamento).

        Fuente: stock.valuation.layer (modulo stock_account). Acceso defensivo
        porque este modulo solo depende de 'account': si no hay valuacion
        instalada o configurada, devuelve ceros y el reporte lo avisa en vez
        de fallar.

        Atribución de costo (dos fuentes que NUNCA se solapan):

        1. Ventas fuera de caja (facturas en `ventas_invoices`): por cada
           línea de factura se sigue la cadena factura -> sale.order.line ->
           stock.move -> stock.valuation.layer, y el costo hereda la fecha
           de la FACTURA sin importar cuándo se validó la entrega en el
           sistema. Esto es lo que corrige el defase (caso S00053: entrega
           validada un día después de la factura).

           Se usa un costo UNITARIO promedio (costo total de los
           movimientos de esa línea de venta / cantidad total entregada) en
           vez de "sumar todos los movimientos por cada línea de factura",
           porque una misma orden puede facturarse en partes (facturación
           parcial); sumar el costo completo del movimiento en cada factura
           parcial lo duplicaría. Multiplicar el costo unitario por la
           cantidad de ESA línea evita el doble conteo sin necesidad de
           llevar un registro de "qué ya se usó" entre facturas.

           Si la línea de factura no tiene exactamente una sale.order.line
           detrás (factura manual sin orden de venta, o el raro caso de
           varias líneas de venta consolidadas en una), se cae directo a
           standard_price: mejor un número conservador y predecible que
           inventar un prorrateo.

        2. Todo lo demás (POS + cualquier salida de stock sin línea de venta
           asociada): se mantiene el heurístico histórico (producto + día de
           creación de la capa de valoración), EXCLUYENDO los movimientos ya
           explicados en el punto 1 para no contar el mismo costo dos veces.
           Para POS esto es razonable porque la entrega normalmente se valida
           el mismo día que la orden.
        """
        vacio = {
            'available': False,
            'costo_ventas': 0.0,
            'formatted_costo_ventas': self.fmt(0.0),
            'utilidad_bruta': 0.0,
            'formatted_utilidad_bruta': self.fmt(0.0),
            'margen_pct': 0.0,
            'formatted_margen_pct': '0.00%',
            'inventario_total': 0.0,
            'formatted_inventario_total': self.fmt(0.0),
            'inventario_categorias': [],
            'totals': {
                'valor': 0.0,
                'formatted_valor': self.fmt(0.0),
                'porc': 0.0,
                'formatted_porc': '0.00%',
                'ventas': 0.0,
                'formatted_ventas': self.fmt(0.0),
                'costo': 0.0,
                'formatted_costo': self.fmt(0.0),
                'utilidad': 0.0,
                'formatted_utilidad': self.fmt(0.0),
                'margen_pct': 0.0,
                'formatted_margen_pct': '0.00%',
                'compras': 0.0,
                'formatted_compras': self.fmt(0.0),
            },
        }
        if 'stock.valuation.layer' not in self.env:
            return vacio

        SVL = self.env['stock.valuation.layer']
        StockMove = self.env['stock.move']
        move_has_sale_line = 'sale_line_id' in StockMove._fields

        # ── 1. Costo trazado por factura (Ventas fuera de caja) ─────────
        costo_ventas_trazado = {}

        if ventas_invoices and move_has_sale_line:
            for inv in ventas_invoices:
                sign = 1 if inv.move_type == 'out_invoice' else -1
                for line in inv.invoice_line_ids:
                    if not line.product_id:
                        continue
                    if line.display_type in ('line_section', 'line_note'):
                        continue

                    pid = line.product_id.id
                    sale_lines = (
                        line.sale_line_ids
                        if 'sale_line_ids' in line._fields
                        else self.env['sale.order.line']
                    )

                    p_cost = None
                    if len(sale_lines) == 1:
                        moves = sale_lines.move_ids.filtered(
                            lambda m: m.state == 'done'
                            and m.location_dest_id.usage == 'customer'
                        )
                        total_qty = sum(moves.mapped('quantity'))
                        total_move_cost = -sum(moves.stock_valuation_layer_ids.mapped('value'))
                        if total_qty > 0 and total_move_cost > 0:
                            unit_cost = total_move_cost / total_qty
                            p_cost = unit_cost * (line.quantity or 0.0) * sign

                    if p_cost is None:
                        # Sin sale.order.line única y trazable: fallback
                        # directo a standard_price (ver docstring).
                        p_cost = (line.quantity or 0.0) * sign * (line.product_id.standard_price or 0.0)

                    costo_ventas_trazado[pid] = costo_ventas_trazado.get(pid, 0.0) + p_cost

        # ── 2. Resto de salidas (POS + sin línea de venta asociada) ─────
        #
        # La exclusión de lo ya trazado en el punto 1 se hace por una
        # propiedad ESTRUCTURAL del movimiento (¿tiene sale_line_id o no?),
        # nunca por "¿se trazó en ESTA llamada?". Es una distinción crítica:
        # el Cierre Diario procesa un día a la vez, en llamadas separadas
        # sin memoria entre sí. Si la exclusión dependiera de qué se trazó
        # en la llamada actual (como en una versión anterior de este
        # código), un movimiento vinculado a una línea de venta -pero cuya
        # factura cae en OTRO día- no se excluiría aquí, y el reporte de
        # ESE otro día (el de la validación de bodega) lo volvería a contar
        # como huérfano, duplicando el costo entre los dos días.
        #
        # Con el filtro estructural, cualquier movimiento con sale_line_id
        # queda SIEMPRE fuera de este heurístico de día+producto, sin
        # importar si su factura fue procesada en esta llamada o no. Ese
        # costo únicamente puede salir por el punto 1, el día en que se
        # genere el reporte de SU factura. Si esa factura nunca se procesó
        # (queda fuera del rango consultado), el costo simplemente no
        # aparece en este reporte — correcto, porque el objetivo es que el
        # costo viva en la fecha de la factura, no en la de la entrega.
        svl_domain = [
            ('company_id', '=', self.company_id.id),
            ('create_date', '>=', date_start),
            ('create_date', '<=', date_end),
            ('stock_move_id.location_dest_id.usage', '=', 'customer'),
        ]
        if move_has_sale_line:
            svl_domain.append(('stock_move_id.sale_line_id', '=', False))

        svl_by_product = {}
        salidas = SVL.search(svl_domain)
        for s in salidas:
            pid = s.product_id.id
            svl_by_product[pid] = svl_by_product.get(pid, 0.0) - s.value

        # ── Valoración de inventario desglosada desde stock.quant ──
        StockQuant = self.env['stock.quant']
        quants_all = StockQuant.search([
            ('location_id.usage', '=', 'internal'),
        ])

        inventario_fisico_bruto = 0.0
        inventario_deficit_negativo = 0.0
        categ_quant_val = {}
        categ_compras_val = {}

        if quants_all:
            for q in quants_all:
                cid = q.product_id.categ_id.id if q.product_id and q.product_id.categ_id else 0
                cname = (
                    q.product_id.categ_id.complete_name or q.product_id.categ_id.name
                    if q.product_id and q.product_id.categ_id
                    else _('Sin categoría')
                )
                cost = q.product_id.standard_price or 0.0
                val = q.quantity * cost

                if q.quantity > 0:
                    inventario_fisico_bruto += val
                else:
                    inventario_deficit_negativo += abs(val)

                if cid not in categ_quant_val:
                    categ_quant_val[cid] = {'name': cname, 'valor': 0.0}
                categ_quant_val[cid]['valor'] += val

        # ── Compras recibidas hoy e inventario en tránsito por categoría ──
        in_transit_total = 0.0
        if 'purchase.order.line' in self.env:
            POLine = self.env['purchase.order.line']
            po_lines = POLine.search([
                ('order_id.state', 'in', ('purchase', 'done')),
                ('company_id', '=', self.company_id.id),
            ])
            for pol in po_lines:
                qty_pending = (pol.product_qty or 0.0) - (pol.qty_received or 0.0)
                if qty_pending > 0:
                    cid = pol.product_id.categ_id.id if pol.product_id and pol.product_id.categ_id else 0
                    val_transit = qty_pending * (pol.price_unit or 0.0)
                    in_transit_total += val_transit
                    categ_compras_val[cid] = categ_compras_val.get(cid, 0.0) + val_transit

        # También sumar las compras ingresadas (recepciones validadas en el período)
        if 'stock.picking' in self.env:
            StockPicking = self.env['stock.picking']
            pickings = StockPicking.search([
                ('picking_type_id.code', '=', 'incoming'),
                ('state', '=', 'done'),
                ('date_done', '>=', date_start),
                ('date_done', '<=', date_end),
                ('company_id', '=', self.company_id.id),
            ])
            for sp in pickings:
                for sm in sp.move_ids.filtered(lambda m: m.state == 'done'):
                    cid = sm.product_id.categ_id.id if sm.product_id and sm.product_id.categ_id else 0
                    val_rec = (sm.quantity or 0.0) * (sm.price_unit or sm.product_id.standard_price or 0.0)
                    categ_compras_val[cid] = categ_compras_val.get(cid, 0.0) + val_rec

        grupos_inv = SVL.read_group(
            [('company_id', '=', self.company_id.id)],
            ['remaining_value:sum'],
            ['categ_id'],
        )
        
        if categ_quant_val:
            inventario_total = sum(item['valor'] for item in categ_quant_val.values())
        else:
            inventario_total = sum(
                (g.get('remaining_value') or 0.0) for g in grupos_inv
            )

        # ── Costo de ventas: traza + SVL restante + fallback standard_price ──
        costo_ventas = 0.0
        used_pids = set()

        if products:
            for p in products:
                pid = p.get('product_id')
                qty = p.get('cantidad', 0.0)
                used_pids.add(pid)

                traced = costo_ventas_trazado.get(pid, 0.0)
                leftover = svl_by_product.get(pid, 0.0)
                leftover = leftover if leftover > 0 else 0.0

                if traced or leftover:
                    p_cost = traced + leftover
                else:
                    prod_obj = self.env['product.product'].browse(pid) if pid else False
                    p_cost = qty * (prod_obj.standard_price if prod_obj else 0.0)

                p['costo'] = p_cost
                costo_ventas += p_cost

        for pid, val in svl_by_product.items():
            if pid not in used_pids:
                costo_ventas += val
        for pid, val in costo_ventas_trazado.items():
            if pid not in used_pids:
                costo_ventas += val

        utilidad = total_ventas - costo_ventas
        margen = (utilidad / total_ventas * 100.0) if total_ventas else 0.0

        # ── Desglose por categoría de producto ─────────────────────────
        categ_map = {}
        if categ_quant_val:
            for cid, data in categ_quant_val.items():
                categ_map[cid] = {
                    'categ_id': cid,
                    'name': data['name'],
                    'valor': data['valor'],
                    'ventas': 0.0,
                    'costo': 0.0,
                    'utilidad': 0.0,
                    'margen_pct': 0.0,
                    'porc': 0.0,
                    'compras': categ_compras_val.get(cid, 0.0),
                }
        else:
            for g in grupos_inv:
                val = g.get('remaining_value') or 0.0
                cid = g['categ_id'][0] if g.get('categ_id') else 0
                cname = g['categ_id'][1] if g.get('categ_id') else _('Sin categoría')
                if cid not in categ_map:
                    categ_map[cid] = {
                        'categ_id': cid,
                        'name': cname,
                        'valor': 0.0,
                        'ventas': 0.0,
                        'costo': 0.0,
                        'utilidad': 0.0,
                        'margen_pct': 0.0,
                        'porc': 0.0,
                        'compras': categ_compras_val.get(cid, 0.0),
                    }
                categ_map[cid]['valor'] += val

        if products:
            for p in products:
                cid = p.get('categ_id', 0)
                cname = p.get('categ_name', _('Sin categoría'))
                if cid not in categ_map:
                    categ_map[cid] = {
                        'categ_id': cid,
                        'name': cname,
                        'valor': 0.0,
                        'ventas': 0.0,
                        'costo': 0.0,
                        'utilidad': 0.0,
                        'margen_pct': 0.0,
                        'porc': 0.0,
                        'compras': categ_compras_val.get(cid, 0.0),
                    }
                categ_map[cid]['ventas'] += p.get('monto_bruto', 0.0)
                categ_map[cid]['costo'] += p.get('costo', 0.0)

        # Si hay costo (trazado o SVL) de productos no presentes en `products`
        for pid, val in list(svl_by_product.items()) + list(costo_ventas_trazado.items()):
            if pid not in used_pids:
                prod = self.env['product.product'].browse(pid)
                cid = prod.categ_id.id if prod and prod.categ_id else 0
                cname = prod.categ_id.name if prod and prod.categ_id else _('Sin categoría')
                if cid not in categ_map:
                    categ_map[cid] = {
                        'categ_id': cid,
                        'name': cname,
                        'valor': 0.0,
                        'ventas': 0.0,
                        'costo': 0.0,
                        'utilidad': 0.0,
                        'margen_pct': 0.0,
                        'porc': 0.0,
                        'compras': categ_compras_val.get(cid, 0.0),
                    }
                categ_map[cid]['costo'] += val

        categorias = []
        for c in categ_map.values():
            if not (c['valor'] or c['ventas'] or c['costo'] or c['compras']):
                continue
            c['utilidad'] = c['ventas'] - c['costo']
            c['margen_pct'] = (
                (c['utilidad'] / c['ventas'] * 100.0) if c['ventas'] else 0.0
            )
            c['porc'] = (
                (c['valor'] / inventario_total * 100.0) if inventario_total else 0.0
            )

            c['formatted_valor'] = self.fmt(c['valor'])
            c['formatted_porc'] = '{:.2f}%'.format(c['porc'])
            c['formatted_ventas'] = self.fmt(c['ventas'])
            c['formatted_costo'] = self.fmt(c['costo'])
            c['formatted_utilidad'] = self.fmt(c['utilidad'])
            c['formatted_margen_pct'] = '{:.2f}%'.format(c['margen_pct'])
            c['formatted_compras'] = self.fmt(c['compras'])

            categorias.append(c)

        categorias.sort(key=lambda c: c['valor'], reverse=True)

        total_ventas_cat = sum(c['ventas'] for c in categorias)
        total_costo_cat = sum(c['costo'] for c in categorias)
        total_utilidad_cat = sum(c['utilidad'] for c in categorias)
        total_compras_cat = sum(c['compras'] for c in categorias)
        total_margen_cat = (
            (total_utilidad_cat / total_ventas_cat * 100.0)
            if total_ventas_cat else 0.0
        )

        inv_operativo = inventario_fisico_bruto + in_transit_total - inventario_deficit_negativo

        return {
            'available': True,
            'costo_ventas': costo_ventas,
            'formatted_costo_ventas': self.fmt(costo_ventas),
            'utilidad_bruta': utilidad,
            'formatted_utilidad_bruta': self.fmt(utilidad),
            'margen_pct': margen,
            'formatted_margen_pct': '{:.2f}%'.format(margen),
            'inventario_total': inventario_total,
            'formatted_inventario_total': self.fmt(inventario_total),
            'fisico_bruto': inventario_fisico_bruto,
            'formatted_fisico_bruto': self.fmt(inventario_fisico_bruto),
            'deficit_negativo': inventario_deficit_negativo,
            'formatted_deficit_negativo': self.fmt(inventario_deficit_negativo),
            'compras_transito': in_transit_total,
            'formatted_compras_transito': self.fmt(in_transit_total),
            'inventario_operativo': inv_operativo,
            'formatted_inventario_operativo': self.fmt(inv_operativo),
            'inventario_categorias': categorias,
            'totals': {
                'valor': inventario_total,
                'formatted_valor': self.fmt(inventario_total),
                'fisico_bruto': inventario_fisico_bruto,
                'formatted_fisico_bruto': self.fmt(inventario_fisico_bruto),
                'deficit_negativo': inventario_deficit_negativo,
                'formatted_deficit_negativo': self.fmt(inventario_deficit_negativo),
                'compras_transito': in_transit_total,
                'formatted_compras_transito': self.fmt(in_transit_total),
                'inventario_operativo': inv_operativo,
                'formatted_inventario_operativo': self.fmt(inv_operativo),
                'porc': 100.0 if inventario_total else 0.0,
                'formatted_porc': '100.00%' if inventario_total else '0.00%',
                'ventas': total_ventas_cat,
                'formatted_ventas': self.fmt(total_ventas_cat),
                'costo': total_costo_cat,
                'formatted_costo': self.fmt(total_costo_cat),
                'utilidad': total_utilidad_cat,
                'formatted_utilidad': self.fmt(total_utilidad_cat),
                'margen_pct': total_margen_cat,
                'formatted_margen_pct': '{:.2f}%'.format(total_margen_cat),
                'compras': total_compras_cat,
                'formatted_compras': self.fmt(total_compras_cat),
            },
        }

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

        # ── Rango de fecha ──────────────────────────────────────────────
        bound_from, bound_to = self._get_date_bounds()
        date_start = datetime.combine(bound_from, time.min)
        date_end = datetime.combine(bound_to, time.max)

        # ── Órdenes POS del periodo (si el módulo POS está instalado) ───
        if self._is_pos_installed():
            PosOrder = self.env['pos.order']
            orders = PosOrder.search([
                ('date_order', '>=', date_start),
                ('date_order', '<=', date_end),
                ('state', 'in', ('paid', 'done', 'invoiced')),
                ('company_id', '=', self.company_id.id),
            ], order='name asc')
            session_ids = orders.mapped('session_id')
            total_ventas_pos = sum(orders.mapped('amount_total'))
            total_impuestos_pos = sum(orders.mapped('amount_tax'))
        else:
            orders = self.env['account.move'].browse()
            session_ids = self.env['account.move'].browse()
            total_ventas_pos = 0.0
            total_impuestos_pos = 0.0

        # ── Sesiones involucradas ───────────────────────────────────────
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

        # ── Cobros / Abonos de CxC del período ──────────────────────────
        # Cartera recuperada: pagos en account.payment que no son de POS y
        # que abonan a facturas o anticipos de clientes.
        cxc_breakdown = {}
        cxc_total = 0.0
        cxc_payments = self.env['account.payment'].search([
            ('date', '>=', bound_from),
            ('date', '<=', bound_to),
            ('payment_type', '=', 'inbound'),
            ('state', 'in', ('in_process', 'paid')),
            ('company_id', '=', self.company_id.id),
        ], order='date, name asc')

        for p in cxc_payments:
            # Excluir pagos de POS
            if 'pos_payment_method_id' in p._fields and p.pos_payment_method_id:
                continue
            if 'pos_order_ids' in p.move_id._fields and p.move_id.pos_order_ids:
                continue
            memo = (p.memo or '').lower()
            move_ref = (p.move_id.ref or '').lower() if p.move_id else ''
            if any(kw in memo for kw in ('pos/', 'punto de venta', 'combine los pagos')) or any(kw in move_ref for kw in ('pos/', 'punto de venta')):
                continue

            mname = self._payment_method_label(p) or _('Otros')
            amt = p.amount or 0.0
            if mname not in cxc_breakdown:
                cxc_breakdown[mname] = {
                    'name': mname,
                    'amount': 0.0,
                    'count': 0,
                }
            cxc_breakdown[mname]['amount'] += amt
            cxc_breakdown[mname]['count'] += 1
            cxc_total += amt

        cxc_methods = sorted(
            cxc_breakdown.values(),
            key=lambda x: x['amount'],
            reverse=True,
        )

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
                        'categ_id': line.product_id.categ_id.id if line.product_id.categ_id else 0,
                        'categ_name': line.product_id.categ_id.name if line.product_id.categ_id else _('Sin categoría'),
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
                        'categ_id': line.product_id.categ_id.id if line.product_id.categ_id else 0,
                        'categ_name': line.product_id.categ_id.name if line.product_id.categ_id else _('Sin categoría'),
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

        cost_inventory = self._get_cost_and_inventory(
            date_start, date_end, total_sin_impuesto, products,
            ventas_invoices=invoices,
        )

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
            # Pagos de Ventas
            'payment_methods': payment_methods,
            'total_pagos': total_pagos,
            # Recaudo de Cuentas por Cobrar (Abonos)
            'cxc_methods': cxc_methods,
            'cxc_total': cxc_total,
            'formatted_cxc_total': self.fmt(cxc_total),
            'total_recaudo_general': total_pagos + cxc_total,
            'formatted_total_recaudo_general': self.fmt(total_pagos + cxc_total),
            # Detalle de órdenes
            'orders': order_details,
            'order_totals': order_totals,
            # Productos
            'products': products,
            'prod_totals': prod_totals,
            # Costo de ventas e inventario
            'cost_inventory': cost_inventory,
        }

    # ── API para Cliente Dinámico (OWL Frontend) ────────────────────────────

    @api.model
    def get_client_report_data(self, date_report=None, company_id=None,
                               period_type='day', date_from=None, date_to=None):
        """
        Retorna los datos formateados para el Dashboard OWL de Cierre.

        period_type acepta 'day' (por defecto, comportamiento histórico) o
        'month' / rango de fechas si se pasan date_from y date_to.
        """
        if not company_id:
            company_id = self.env.company.id

        vals = {
            'period_type': period_type or 'day',
            'company_id': company_id,
        }
        if date_from and date_to:
            vals['date_from'] = date_from
            vals['date_to'] = date_to
            vals['date_report'] = date_from
        else:
            if not date_report:
                date_report = fields.Date.context_today(self)
            vals['date_report'] = date_report
            if vals['period_type'] == 'month':
                ref = fields.Date.to_date(date_report)
                vals['month'] = str(ref.month)
                vals['year'] = ref.year

        wizard = self.create(vals)
        raw_data = wizard._get_report_data()

        # Formatear números
        for m in raw_data['payment_methods']:
            m['formatted_amount'] = wizard.fmt(m['amount'])

        for cm in raw_data['cxc_methods']:
            cm['formatted_amount'] = wizard.fmt(cm['amount'])

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
            'cxc_methods': raw_data['cxc_methods'],
            'cxc_total': raw_data['cxc_total'],
            'formatted_cxc_total': raw_data['formatted_cxc_total'],
            'total_recaudo_general': raw_data['total_recaudo_general'],
            'formatted_total_recaudo_general': raw_data['formatted_total_recaudo_general'],
            'orders': raw_data['orders'],
            'order_totals': ot,
            'products': raw_data['products'],
            'prod_totals': pt,
            'cost_inventory': raw_data['cost_inventory'],
        }

