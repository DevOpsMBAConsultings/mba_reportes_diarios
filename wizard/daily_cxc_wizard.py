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
    company_id = fields.Many2one(
        'res.company',
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
    )

    # ── Rango de fechas ─────────────────────────────────────────────────────

    def _get_date_bounds(self):
        """Devuelve (desde, hasta) como objetos date."""
        self.ensure_one()
        if self.date_from and self.date_to:
            if self.date_from > self.date_to:
                return self.date_to, self.date_from
            return self.date_from, self.date_to
        return self.date_report, self.date_report

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

    # ── Clasificación de facturas y pagos ───────────────────────────────────

    def _is_pos_payment(self, payment):
        """
        Determina si un pago (account.payment) proviene del Punto de Venta (POS).

        El POS de Odoo crea registros en account.payment al cerrar sesiones o procesar
        métodos bancarios/transferencia (ej. 'Combine los pagos con...'). Estos cobros
        pertenecen a caja transaccional y NO deben aparecer en Cobros de Cuentas por Cobrar (CxC).
        """
        # 1. Campos específicos de POS en account.payment
        for field_name in ('pos_payment_method_id', 'pos_session_id', 'pos_order_id'):
            if field_name in payment._fields and payment[field_name]:
                return True

        # 2. Relación desde el asiento contable (account.move) hacia pos.order
        if 'pos_order_ids' in payment.move_id._fields and payment.move_id.pos_order_ids:
            return True

        # 3. Inspección por palabras clave en memo o referencia (típicas del POS en Odoo)
        memo = (payment.memo or '').lower()
        move_ref = (payment.move_id.ref or '').lower() if payment.move_id else ''
        pos_keywords = (
            'punto de venta',
            'point of sale',
            'pos/',
            'combine los pagos',
            'combine payments',
            'combinar los pagos',
            'cierre de pdv',
        )
        if any(kw in memo for kw in pos_keywords) or any(kw in move_ref for kw in pos_keywords):
            return True

        # 4. Si el pago pertenece a clientes genéricos de mostrador/POS ("Consumidor Final",
        # "Cliente General") y no es de un cliente de crédito registrado.
        partner_name = (payment.partner_id.name or '').lower()
        if any(kw in partner_name for kw in ('consumidor final', 'cliente general', 'publico en general')):
            return True

        return False

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
        Facturas a crédito emitidas en el período por el canal de ventas.

        Sección informativa: NO suma a los totales de cobros, porque emitir
        una factura a crédito no representa una entrada de dinero.
        """
        date_from, date_to = self._get_date_bounds()
        invoices = self.env['account.move'].search([
            ('invoice_date', '>=', date_from),
            ('invoice_date', '<=', date_to),
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
        date_from, date_to = self._get_date_bounds()

        # 1. Pagos entrantes del período.
        #    Odoo 18: los estados de account.payment son
        #    draft | in_process | paid | canceled | rejected
        payments = self.env['account.payment'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('payment_type', '=', 'inbound'),
            ('state', 'in', ('in_process', 'paid')),
            ('company_id', '=', self.company_id.id),
        ], order='partner_id, name asc')

        payment_details = []
        method_totals = {}

        for p in payments:
            # Excluir cualquier pago originado en el Punto de Venta o de clientes de mostrador
            if self._is_pos_payment(p):
                continue

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
                'payment_id': p.id,
                'payment_name': p.name or '',
                'partner_id': p.partner_id.id if p.partner_id else False,
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

        # 2. Sección informativa: facturas a crédito emitidas en el período.
        credit_details = []
        for inv in self._get_credit_invoices():
            partner_ref = inv.partner_id.ref or inv.partner_id.vat or ''
            partner_name = inv.partner_id.name or ''
            partner_label = f"[{partner_ref}] {partner_name}" if partner_ref else partner_name

            credit_details.append({
                'invoice_id': inv.id,
                'name': inv.name or '',
                'partner_id': inv.partner_id.id if inv.partner_id else False,
                'partner': partner_label,
                'payment_term': inv.invoice_payment_term_id.name or '',
                'date_due': str(inv.invoice_date_due) if inv.invoice_date_due else '',
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
            'date_from': date_from,
            'date_to': date_to,
            'is_range': date_from != date_to,
            'time_report': fields.Datetime.context_timestamp(
                self, datetime.now()
            ).strftime('%I:%M %p'),
            # Cobros efectivamente recibidos
            'methods': methods_list,
            'details': payment_details,
            'grand_total': grand_total,
            'total_count': len(payment_details),
            # Informativo: facturación a crédito (no suma a cobros)
            'credit_invoices': credit_details,
            'credit_totals': credit_totals,
        }

    # ── API para Cliente Dinámico (OWL Frontend) ────────────────────────────

    @api.model
    def get_client_report_data(self, date_report=None, company_id=None,
                               period_type='day', date_from=None, date_to=None):
        """
        Retorna la información del reporte de cobros CxC en un diccionario
        serializable a JSON para ser consumido asíncronamente por el dashboard OWL.
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

        wizard = self.create(vals)
        raw_data = wizard._get_report_data()

        # Formatear números para pantalla
        for m in raw_data['methods']:
            m['formatted_amount'] = wizard.fmt(m['amount'])

        for d in raw_data['details']:
            d['formatted_amount'] = wizard.fmt(d['amount'])

        for c in raw_data['credit_invoices']:
            c['formatted_amount_total'] = wizard.fmt(c['amount_total'])
            c['formatted_amount_residual'] = wizard.fmt(c['amount_residual'])

        raw_data['credit_totals']['formatted_amount_total'] = wizard.fmt(raw_data['credit_totals']['amount_total'])
        raw_data['credit_totals']['formatted_amount_residual'] = wizard.fmt(raw_data['credit_totals']['amount_residual'])

        return {
            'company_name': raw_data['company'].name,
            'company_id': raw_data['company'].id,
            'date_report': str(raw_data['date_report']),
            'date_from': str(raw_data['date_from']),
            'date_to': str(raw_data['date_to']),
            'is_range': raw_data['is_range'],
            'time_report': raw_data['time_report'],
            'methods': raw_data['methods'],
            'details': raw_data['details'],
            'grand_total': raw_data['grand_total'],
            'formatted_grand_total': wizard.fmt(raw_data['grand_total']),
            'total_count': raw_data['total_count'],
            'credit_invoices': raw_data['credit_invoices'],
            'credit_totals': raw_data['credit_totals'],
        }

