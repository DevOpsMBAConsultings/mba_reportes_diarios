/** @odoo-module **/

/**
 * Cierre Mensual de Ventas.
 *
 * Espejo del Cierre Diario, con dos diferencias:
 *   - el filtro es Mes + Año en vez de una fecha
 *   - envia period_type: 'month' al backend
 *
 * El backend es EL MISMO wizard (mba.daily.pos.wizard), asi que la logica de
 * agregacion de ordenes, productos y metodos de pago no puede divergir entre
 * el diario y el mensual. Aqui solo cambia el rango y la presentacion.
 */

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MonthlyClosingReport extends Component {
    static template = "mba_reportes_diarios.MonthlyClosingReportTemplate";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split("T")[0];
        const lastDay = today.toISOString().split("T")[0];

        this.state = useState({
            date_from: firstDay,
            date_to: lastDay,
            loading: true,
            data: {},
            collapsed: {},
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    toggleSection(sectionKey) {
        this.state.collapsed[sectionKey] = !this.state.collapsed[sectionKey];
    }

    isCollapsed(sectionKey) {
        return !!this.state.collapsed[sectionKey];
    }

    get periodLabel() {
        return `${this.state.date_from} al ${this.state.date_to}`;
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "mba.daily.pos.wizard",
                "get_client_report_data",
                [null, null, "month", this.state.date_from, this.state.date_to]
            );
            this.state.data = data || {
                sessions: [],
                payment_methods: [],
                orders: [],
                products: [],
            };
        } catch (error) {
            console.error("Error loading monthly closing data:", error);
            this.state.data = {
                sessions: [],
                payment_methods: [],
                orders: [],
                products: [],
            };
        } finally {
            this.state.loading = false;
        }
    }

    async onFilterChange() {
        await this.loadData();
    }

    openOrder(orderId, resModel) {
        if (!orderId) return;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: resModel || "pos.order",
            res_id: orderId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openPartner(partnerId) {
        if (!partnerId) return;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: partnerId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openProduct(productId) {
        if (!productId) return;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "product.product",
            res_id: productId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    async printPdf() {
        const wizardId = await this.orm.create("mba.daily.pos.wizard", [{
            date_from: this.state.date_from,
            date_to: this.state.date_to,
            period_type: "month",
            company_id: this.state.data.company_id,
        }]);

        const action = await this.orm.call(
            "mba.daily.pos.wizard",
            "action_print_report",
            [[wizardId]]
        );

        return this.actionService.doAction(action);
    }

    async exportXlsx() {
        return this.printPdf();
    }
}

registry.category("actions").add("mba_monthly_closing_report", MonthlyClosingReport);
