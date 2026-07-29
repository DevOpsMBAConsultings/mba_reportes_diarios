/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class SalesCommissionReport extends Component {
    static template = "mba_reportes_diarios.SalesCommissionReportTemplate";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split("T")[0];
        const lastDay = today.toISOString().split("T")[0];

        this.state = useState({
            date_from: firstDay,
            date_to: lastDay,
            settlement_state: "all",
            payment_state: "all",
            loading: true,
            data: {},
            expanded: {},
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "mba.sales.commission.wizard",
                "get_client_report_data",
                [
                    this.state.date_from,
                    this.state.date_to,
                    false, // agent_id
                    this.state.settlement_state,
                    this.state.payment_state,
                ]
            );
            this.state.data = data;

            // Expand all agents by default
            const expanded = {};
            if (data.agents) {
                for (const ag of data.agents) {
                    expanded[ag.agent_id] = true;
                }
            }
            this.state.expanded = expanded;
        } catch (error) {
            console.error("Error loading sales commission data:", error);
        } finally {
            this.state.loading = false;
        }
    }

    async onFilterChange() {
        await this.loadData();
    }

    toggleAgent(agentId) {
        this.state.expanded[agentId] = !this.state.expanded[agentId];
    }

    openInvoice(invoiceId) {
        if (!invoiceId) return;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "account.move",
            res_id: invoiceId,
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
        const wizardId = await this.orm.create("mba.sales.commission.wizard", [{
            date_from: this.state.date_from,
            date_to: this.state.date_to,
            settlement_state: this.state.settlement_state,
            payment_state: this.state.payment_state,
            company_id: this.state.data.company_id,
        }]);

        const action = await this.orm.call(
            "mba.sales.commission.wizard",
            "action_print_report",
            [[wizardId]]
        );

        return this.actionService.doAction(action);
    }

    async exportXlsx() {
        return this.printPdf();
    }
}

registry.category("actions").add("mba_sales_commission_report", SalesCommissionReport);
