# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import datetime, date


class MbaSalesCommissionWizard(models.TransientModel):
    _name = 'mba.sales.commission.wizard'
    _description = 'Wizard - Comisiones de Ventas (Pre-Cierre)'

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
    agent_id = fields.Many2one(
        'res.partner',
        string="Agente / Vendedor",
        help="Filtrar por un vendedor o agente específico.",
    )
    settlement_state = fields.Selection([
        ('all', 'Todas'),
        ('pending', 'Pendientes de Liquidar'),
        ('settled', 'Ya Liquidadas'),
    ], string="Estado de Liquidación", default='all', required=True)

    payment_state = fields.Selection([
        ('all', 'Todas'),
        ('paid', 'Solo Facturas Pagadas / Cobradas'),
        ('posted', 'Facturas Publicadas'),
    ], string="Estado de Cobro Factura", default='all', required=True)

    company_id = fields.Many2one(
        'res.company',
        string="Empresa",
        required=True,
        default=lambda self: self.env.company,
    )

    def action_print_report(self):
        """Genera el reporte PDF de Comisiones de Ventas."""
        self.ensure_one()
        return self.env.ref(
            'mba_reportes_diarios.action_report_sales_commission'
        ).report_action(self)

    def fmt(self, value):
        if value is None:
            value = 0.0
        return '{:,.2f}'.format(value)

    def _get_report_data(self):
        self.ensure_one()

        if 'account.invoice.line.agent' not in self.env:
            return {
                'oca_installed': False,
                'company': self.company_id,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'agents': [],
                'total_sales': 0.0,
                'total_commission': 0.0,
                'total_pending': 0.0,
                'total_settled': 0.0,
            }

        domain = [
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('company_id', '=', self.company_id.id),
            ('invoice_id.state', '=', 'posted'),
        ]
        if self.agent_id:
            domain.append(('agent_id', '=', self.agent_id.id))

        if self.settlement_state == 'pending':
            domain.append(('settled', '=', False))
        elif self.settlement_state == 'settled':
            domain.append(('settled', '=', True))

        if self.payment_state == 'paid':
            domain.append(('invoice_id.payment_state', 'in', ('in_payment', 'paid')))

        agent_lines = self.env['account.invoice.line.agent'].search(
            domain, order='agent_id, invoice_date asc, invoice_id asc'
        )

        agents_map = {}
        total_sales_gen = 0.0
        total_comm_gen = 0.0
        total_pending_gen = 0.0
        total_settled_gen = 0.0

        for line in agent_lines:
            agent = line.agent_id
            if not agent:
                continue

            agent_key = agent.id
            if agent_key not in agents_map:
                agents_map[agent_key] = {
                    'agent_id': agent.id,
                    'agent_name': agent.name or _('Agente Sin Nombre'),
                    'sales_total': 0.0,
                    'commission_total': 0.0,
                    'pending_total': 0.0,
                    'settled_total': 0.0,
                    'count': 0,
                    'lines': [],
                }

            inv_line = line.object_id
            inv = line.invoice_id
            sale_subtotal = inv_line.price_subtotal if inv_line else 0.0
            sign = -1 if inv and inv.move_type and 'refund' in inv.move_type else 1
            amount = (line.amount or 0.0)

            agents_map[agent_key]['sales_total'] += sale_subtotal * sign
            agents_map[agent_key]['commission_total'] += amount
            agents_map[agent_key]['count'] += 1

            if line.settled:
                agents_map[agent_key]['settled_total'] += amount
                total_settled_gen += amount
            else:
                agents_map[agent_key]['pending_total'] += amount
                total_pending_gen += amount

            total_sales_gen += sale_subtotal * sign
            total_comm_gen += amount

            pay_state_label = dict(
                inv._fields['payment_state'].selection
            ).get(inv.payment_state, inv.payment_state) if inv else ''

            agents_map[agent_key]['lines'].append({
                'agent_line_id': line.id,
                'invoice_id': inv.id if inv else False,
                'invoice_name': inv.name if inv else '',
                'invoice_date': str(line.invoice_date) if line.invoice_date else '',
                'partner_id': inv.partner_id.id if inv and inv.partner_id else False,
                'partner_name': inv.partner_id.name if inv and inv.partner_id else '',
                'product_id': inv_line.product_id.id if inv_line and inv_line.product_id else False,
                'product_name': inv_line.product_id.name if inv_line and inv_line.product_id else '',
                'price_subtotal': sale_subtotal * sign,
                'commission_name': line.commission_id.name if line.commission_id else '',
                'amount': amount,
                'payment_state': pay_state_label,
                'settled': line.settled,
                'settled_label': _('Liquidada') if line.settled else _('Pendiente'),
            })

        agents_list = sorted(agents_map.values(), key=lambda a: a['commission_total'], reverse=True)

        return {
            'oca_installed': True,
            'company': self.company_id,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'time_report': fields.Datetime.context_timestamp(
                self, datetime.now()
            ).strftime('%I:%M %p'),
            'agents': agents_list,
            'total_sales': total_sales_gen,
            'total_commission': total_comm_gen,
            'total_pending': total_pending_gen,
            'total_settled': total_settled_gen,
        }

    @api.model
    def get_client_report_data(self, date_from=None, date_to=None, agent_id=None, settlement_state='all', payment_state='all', company_id=None):
        if not date_from:
            date_from = fields.Date.context_today(self).replace(day=1)
        if not date_to:
            date_to = fields.Date.context_today(self)
        if not company_id:
            company_id = self.env.company.id

        vals = {
            'date_from': date_from,
            'date_to': date_to,
            'settlement_state': settlement_state or 'all',
            'payment_state': payment_state or 'all',
            'company_id': company_id,
        }
        if agent_id:
            vals['agent_id'] = agent_id

        wizard = self.create(vals)
        raw_data = wizard._get_report_data()

        if not raw_data.get('oca_installed'):
            return {
                'oca_installed': False,
                'company_name': wizard.company_id.name,
                'date_from': str(date_from),
                'date_to': str(date_to),
            }

        # Formatear números
        for agent in raw_data['agents']:
            agent['formatted_sales_total'] = wizard.fmt(agent['sales_total'])
            agent['formatted_commission_total'] = wizard.fmt(agent['commission_total'])
            agent['formatted_pending_total'] = wizard.fmt(agent['pending_total'])
            agent['formatted_settled_total'] = wizard.fmt(agent['settled_total'])

            for l in agent['lines']:
                l['formatted_price_subtotal'] = wizard.fmt(l['price_subtotal'])
                l['formatted_amount'] = wizard.fmt(l['amount'])

        return {
            'oca_installed': True,
            'company_name': raw_data['company'].name,
            'company_id': raw_data['company'].id,
            'date_from': str(raw_data['date_from']),
            'date_to': str(raw_data['date_to']),
            'time_report': raw_data['time_report'],
            'agents': raw_data['agents'],
            'total_sales': raw_data['total_sales'],
            'formatted_total_sales': wizard.fmt(raw_data['total_sales']),
            'total_commission': raw_data['total_commission'],
            'formatted_total_commission': wizard.fmt(raw_data['total_commission']),
            'total_pending': raw_data['total_pending'],
            'formatted_total_pending': wizard.fmt(raw_data['total_pending']),
            'total_settled': raw_data['total_settled'],
            'formatted_total_settled': wizard.fmt(raw_data['total_settled']),
        }
