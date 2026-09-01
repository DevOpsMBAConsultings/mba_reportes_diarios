# -*- coding: utf-8 -*-
import io
import base64
import xlsxwriter
from odoo import api, fields, models, _
from datetime import datetime, date, time, timedelta
from dateutil.relativedelta import relativedelta


class MbaMonthlyIncomeWizard(models.TransientModel):
    _name = 'mba.monthly.income.wizard'
    _description = 'Wizard - Resumen Mensual de Ingresos (MTD)'

    @api.model
    def _default_date_from(self):
        today = fields.Date.context_today(self)
        return today.replace(day=1)

    date_from = fields.Date(
        "Fecha Desde",
        required=True,
        default=_default_date_from,
    )
    date_to = fields.Date(
        "Fecha Hasta",
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
        """Genera el reporte PDF de Resumen Mensual MTD."""
        self.ensure_one()
        return self.env.ref(
            'mba_reportes_diarios.action_report_monthly_income'
        ).report_action(self)

    def action_export_xlsx(self):
        """Genera el reporte de Resumen Mensual MTD en formato Excel (.xlsx)."""
        if self._ids and isinstance(self._ids[0], (list, tuple)):
            self = self.browse(self._ids[0][0])
        self.ensure_one()
        raw_data = self._get_report_data()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # Formatos
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'font_color': '#1E3A8A'})
        subtitle_fmt = workbook.add_format({'font_size': 10, 'font_color': '#4B5563'})
        kpi_title_fmt = workbook.add_format({'bold': True, 'font_size': 9, 'font_color': '#6B7280'})
        kpi_value_fmt = workbook.add_format({'bold': True, 'font_size': 13, 'font_color': '#047857', 'num_format': '$#,##0.00'})
        kpi_info_value_fmt = workbook.add_format({'bold': True, 'font_size': 13, 'font_color': '#0284C7', 'num_format': '$#,##0.00'})

        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#F3F4F6', 'font_color': '#374151', 'border': 1, 'align': 'left'})
        day_header_fmt = workbook.add_format({'bold': True, 'bg_color': '#F3F4F6', 'font_color': '#374151', 'border': 1, 'align': 'center', 'text_wrap': True})
        total_header_fmt = workbook.add_format({'bold': True, 'bg_color': '#E5E7EB', 'font_color': '#111827', 'border': 1, 'align': 'right'})

        concept_fmt = workbook.add_format({'bold': True, 'border': 1, 'font_size': 9, 'font_color': '#1F2937'})
        concept_info_fmt = workbook.add_format({'bold': True, 'border': 1, 'font_size': 9, 'font_color': '#4B5563'})

        num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'align': 'right'})
        num_zero_fmt = workbook.add_format({'border': 1, 'align': 'center', 'font_color': '#9CA3AF'})
        total_num_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'border': 1, 'bg_color': '#F9FAFB', 'align': 'right'})

        grand_total_label_fmt = workbook.add_format({'bold': True, 'bg_color': '#EEF2FF', 'font_color': '#1E40AF', 'border': 1, 'align': 'left'})
        grand_total_num_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'border': 1, 'bg_color': '#EEF2FF', 'font_color': '#1E40AF', 'align': 'right'})

        ws = workbook.add_worksheet("Resumen MTD")

        # Título y metadatos
        ws.write(0, 0, f"Resumen Mensual de Ingresos (MTD) - {raw_data['company'].name}", title_fmt)
        ws.write(1, 0, f"Rango: {raw_data['date_from']} al {raw_data['date_to']} | Generado: {raw_data['time_report']}", subtitle_fmt)

        # KPIs superiores
        ws.write(3, 0, "Total Ingresos Acumulado (MTD)", kpi_title_fmt)
        ws.write(4, 0, raw_data['grand_total_mtd'], kpi_value_fmt)

        ws.write(3, 3, "Facturación a Crédito Emitida (Informativo)", kpi_title_fmt)
        ws.write(4, 3, raw_data['credit_total_mtd'], kpi_info_value_fmt)

        # Encabezados de la tabla
        row = 6
        ws.write(row, 0, "Concepto de Ingreso", header_fmt)
        col = 1
        for h in raw_data['day_headers']:
            ws.write(row, col, f"{h['label']}\n{h['day_name']}", day_header_fmt)
            col += 1
        ws.write(row, col, "TOTAL MTD", total_header_fmt)
        total_col = col

        # Filas de conceptos
        row += 1
        for cr in raw_data['concept_rows']:
            is_info = cr.get('informative', False)
            ws.write(row, 0, cr['name'] + (" (Informativo)" if is_info else ""), concept_info_fmt if is_info else concept_fmt)
            
            for i, val in enumerate(cr['values']):
                c_idx = i + 1
                if val == 0.0 or val is None:
                    ws.write(row, c_idx, "-", num_zero_fmt)
                else:
                    ws.write(row, c_idx, val, num_fmt)
            
            ws.write(row, total_col, cr['total'], total_num_fmt)
            row += 1

        # Fila de Total Ingresos Día
        ws.write(row, 0, "TOTAL INGRESOS DÍA:", grand_total_label_fmt)
        for i, val in enumerate(raw_data['daily_totals']):
            c_idx = i + 1
            ws.write(row, c_idx, val, grand_total_num_fmt)
        ws.write(row, total_col, raw_data['grand_total_mtd'], grand_total_num_fmt)

        # Ajuste de anchos de columna
        ws.set_column(0, 0, 38)
        ws.set_column(1, total_col - 1, 10)
        ws.set_column(total_col, total_col, 15)

        workbook.close()
        output.seek(0)

        filename = f"Resumen_Mensual_Ingresos_{raw_data['date_from']}_{raw_data['date_to']}.xlsx"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    # ── Helpers de formato ──────────────────────────────────────────────────

    def fmt(self, value):
        """Formatea un número con 2 decimales y separador de miles."""
        if value is None or value == 0:
            return '-'
        return '{:,.2f}'.format(value)

    def fmt_total(self, value):
        """Formatea totales."""
        if value is None:
            value = 0.0
        return '{:,.2f}'.format(value)

    # ── Auxiliar para detectar facturas a crédito ───────────────────────────

    def _is_pos_invoice(self, inv):
        """
        Indica si la factura se originó en el Punto de Venta.

        El módulo point_of_sale añade 'pos_order_ids' a account.move. Acceso
        defensivo: este módulo solo depende de 'account'.
        """
        if 'pos_order_ids' not in inv._fields:
            return False
        return bool(inv.pos_order_ids)

    def _is_invoice_credit(self, inv):
        # Regla de negocio: la caja (POS) es siempre contado. El crédito vive
        # exclusivamente en el canal de ventas para distribución.
        if self._is_pos_invoice(inv):
            return False
        if 'dgi_payment_term_type' in inv._fields and inv.dgi_payment_term_type:
            return inv.dgi_payment_term_type == 'credito'
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

    # ── Datos del reporte ───────────────────────────────────────────────────

    def _get_report_data(self):
        """
        Genera la matriz de ingresos MTD (Día por Día).
        """
        self.ensure_one()

        if self.date_from > self.date_to:
            date_from, date_to = self.date_to, self.date_from
        else:
            date_from, date_to = self.date_from, self.date_to

        # Rango de fechas
        num_days = (date_to - date_from).days + 1
        days_list = [date_from + timedelta(days=i) for i in range(num_days)]

        # Encabezados de columnas (ej: "1/Jul", "2/Jul", ...)
        day_headers = []
        for d in days_list:
            day_headers.append({
                'date': d,
                'label': f"{d.day}/{d.strftime('%b')}",
                'day_name': d.strftime('%a'),
            })

        # Estructura de conceptos de ingreso
        # 'informative': la fila se muestra pero NO suma a los totales.
        # Emitir una factura a crédito no es dinero recibido, y esa misma
        # plata vuelve a contarse en COBROS CXC cuando efectivamente se cobra.
        # Sumarla producía un doble conteo en el total general.
        concepts = [
            {'code': 'efectivo', 'name': 'EFECTIVO', 'informative': False},
            {'code': 'clave', 'name': 'TARJETA CLAVE (DÉBITO)', 'informative': False},
            {'code': 'visa_masterd', 'name': 'VISA - MASTERCARD (CRÉDITO)', 'informative': False},
            {'code': 'ach_directo', 'name': 'ACH / TRANSFERENCIAS DIRECTAS', 'informative': False},
            {'code': 'cobros_cxc', 'name': 'COBROS CXC (RECIBOS / CHEQUES)', 'informative': False},
            {'code': 'facturas_credito', 'name': 'FACTURAS A CRÉDITO (EMITIDAS)', 'informative': True},
        ]

        # Matriz de datos: {concept_code: {date: amount}}
        matrix = {c['code']: {d: 0.0 for d in days_list} for c in concepts}
        daily_totals = {d: 0.0 for d in days_list}

        # 1. Obtener todas las facturas del rango
        invoices = self.env['account.move'].search([
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
        ])

        for inv in invoices:
            sign = 1 if inv.move_type == 'out_invoice' else -1
            amount = (inv.amount_total or 0.0) * sign
            d = inv.invoice_date
            if d in matrix['facturas_credito'] and self._is_invoice_credit(inv):
                matrix['facturas_credito'][d] += amount

        # 2. Obtener todos los pagos del rango
        # Odoo 18: los estados de account.payment son
        # draft | in_process | paid | canceled | rejected
        payments = self.env['account.payment'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('payment_type', '=', 'inbound'),
            ('state', 'in', ('in_process', 'paid')),
            ('company_id', '=', self.company_id.id),
        ])

        CARD_CLAVE = ('clave', 'débito', 'debito')
        CARD_CREDIT = ('visa', 'master', 'card', 'tarjeta', 'datafast')

        for p in payments:
            d = p.date
            if d not in days_list:
                continue

            amount = p.amount or 0.0
            journal = p.journal_id
            jtype = journal.type if journal else ''
            jname = (journal.name or '').lower()

            # Clasificar si es cobro de factura previa (CxC)
            is_cxc = False
            receivable_lines = p.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
            )
            for line in receivable_lines:
                for partial in line.matched_debit_ids:
                    inv_move = partial.debit_move_id.move_id
                    if inv_move.is_invoice() and inv_move.invoice_date < d:
                        is_cxc = True
                        break
                if is_cxc:
                    break

            if is_cxc:
                matrix['cobros_cxc'][d] += amount
            else:
                if jtype == 'cash':
                    matrix['efectivo'][d] += amount
                elif jtype == 'bank':
                    if any(kw in jname for kw in CARD_CLAVE):
                        matrix['clave'][d] += amount
                    elif any(kw in jname for kw in CARD_CREDIT):
                        matrix['visa_masterd'][d] += amount
                    else:
                        matrix['ach_directo'][d] += amount

        # 3. Caja del Punto de Venta (POS).
        #
        # Regla de negocio de Moto Lider: "caja es POS". El bloque anterior
        # (account.payment) solo cubre el canal de ventas/distribución; POS
        # no genera account.payment (pos.payment crea asientos directamente,
        # ver _create_payment_moves en point_of_sale). Sin este bloque, el
        # resumen mensual subestimaba el ingreso real: toda la venta de
        # mostrador quedaba fuera.
        #
        # POS es siempre contado (regla ya aplicada en _is_invoice_credit),
        # así que solo alimenta efectivo/clave/visa_masterd/ach_directo.
        # Nunca toca cobros_cxc ni facturas_credito.
        if 'pos.order' in self.env:
            pos_date_start = datetime.combine(date_from, time.min)
            pos_date_end = datetime.combine(date_to, time.max)
            pos_orders = self.env['pos.order'].search([
                ('date_order', '>=', pos_date_start),
                ('date_order', '<=', pos_date_end),
                ('state', 'in', ('paid', 'done', 'invoiced')),
                ('company_id', '=', self.company_id.id),
            ])

            for order in pos_orders:
                # Conversión a la fecha local (context) del asiento POS:
                # date_order se guarda en UTC: usar la fecha naive tal cual
                # puede correr el día de una venta hecha en horas de la
                # noche a la fecha siguiente.
                d = fields.Datetime.context_timestamp(
                    self, order.date_order
                ).date()
                if d not in days_list:
                    continue

                for pp in order.payment_ids:
                    amount = pp.amount or 0.0
                    method = pp.payment_method_id
                    mtype = method.type
                    mname = (method.name or '').lower()

                    if mtype == 'cash':
                        matrix['efectivo'][d] += amount
                    elif mtype == 'bank':
                        if any(kw in mname for kw in CARD_CLAVE):
                            matrix['clave'][d] += amount
                        elif any(kw in mname for kw in CARD_CREDIT):
                            matrix['visa_masterd'][d] += amount
                        else:
                            matrix['ach_directo'][d] += amount
                    # 'pay_later' se ignora: no representa dinero recibido.
                    # Moto Lider no da de alta ese método en POS.

        # 4. Calcular totales acumulados MTD por concepto y por día
        concept_rows = []
        grand_total_mtd = 0.0
        credit_total_mtd = 0.0

        for c in concepts:
            row_code = c['code']
            informative = c.get('informative', False)
            daily_values = []
            row_total = 0.0

            for d in days_list:
                val = matrix[row_code][d]
                daily_values.append(val)
                row_total += val
                # Las filas informativas no alimentan los totales de ingresos.
                if not informative:
                    daily_totals[d] += val

            if informative:
                credit_total_mtd += row_total
            else:
                grand_total_mtd += row_total

            concept_rows.append({
                'name': c['name'],
                'values': daily_values,
                'total': row_total,
                'informative': informative,
            })

        daily_totals_list = [daily_totals[d] for d in days_list]

        return {
            'company': self.company_id,
            'date_from': date_from,
            'date_to': date_to,
            'time_report': fields.Datetime.context_timestamp(
                self, datetime.now()
            ).strftime('%I:%M %p'),
            'day_headers': day_headers,
            'concept_rows': concept_rows,
            'daily_totals': daily_totals_list,
            'grand_total_mtd': grand_total_mtd,
            # Informativo, fuera del total de ingresos
            'credit_total_mtd': credit_total_mtd,
        }

    # ── API para Cliente Dinámico (OWL Frontend) ────────────────────────────

    @api.model
    def get_client_report_data(self, date_from=None, date_to=None, company_id=None):
        """
        Retorna los datos formateados para el Dashboard OWL de Resumen Mensual (MTD).
        """
        if not date_from:
            date_from = fields.Date.context_today(self).replace(day=1)
        if not date_to:
            date_to = fields.Date.context_today(self)
        if not company_id:
            company_id = self.env.company.id

        wizard = self.create({
            'date_from': date_from,
            'date_to': date_to,
            'company_id': company_id,
        })
        raw_data = wizard._get_report_data()

        # Formatear encabezados de días
        headers = []
        for h in raw_data['day_headers']:
            headers.append({
                'date': str(h['date']),
                'label': h['label'],
                'day_name': h['day_name'],
            })

        # Formatear filas de conceptos
        rows = []
        for r in raw_data['concept_rows']:
            formatted_vals = [wizard.fmt(v) for v in r['values']]
            rows.append({
                'name': r['name'],
                'values': r['values'],
                'formatted_values': formatted_vals,
                'total': r['total'],
                'formatted_total': wizard.fmt_total(r['total']),
                'informative': r['informative'],
            })

        formatted_daily_totals = [wizard.fmt_total(v) for v in raw_data['daily_totals']]

        return {
            'company_name': raw_data['company'].name,
            'company_id': raw_data['company'].id,
            'date_from': str(raw_data['date_from']),
            'date_to': str(raw_data['date_to']),
            'time_report': raw_data['time_report'],
            'day_headers': headers,
            'concept_rows': rows,
            'daily_totals': raw_data['daily_totals'],
            'formatted_daily_totals': formatted_daily_totals,
            'grand_total_mtd': raw_data['grand_total_mtd'],
            'formatted_grand_total_mtd': wizard.fmt_total(raw_data['grand_total_mtd']),
            'credit_total_mtd': raw_data['credit_total_mtd'],
            'formatted_credit_total_mtd': wizard.fmt_total(raw_data['credit_total_mtd']),
        }

