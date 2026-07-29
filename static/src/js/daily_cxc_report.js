/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class DailyCxcReport extends Component {
    static template = "mba_reportes_diarios.DailyCxcReportTemplate";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        // Date in YYYY-MM-DD
        const today = new Date().toISOString().split("T")[0];

        this.state = useState({
            date_report: today,
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
                "mba.daily.cxc.wizard",
                "get_client_report_data",
                [this.state.date_report]
            );
            this.state.data = data;

            // Expand all method accordions by default
            const expanded = {};
            if (data.methods) {
                for (const m of data.methods) {
                    expanded[m.name] = true;
                }
            }
            this.state.expanded = expanded;
        } catch (error) {
            console.error("Error loading CxC report data:", error);
        } finally {
            this.state.loading = false;
        }
    }

    async onDateChange() {
        await this.loadData();
    }

    toggleMethod(methodName) {
        this.state.expanded[methodName] = !this.state.expanded[methodName];
    }

    getDetailsForMethod(methodName) {
        if (!this.state.data.details) return [];
        return this.state.data.details.filter(d => d.method_name === methodName);
    }

    // Drill-down actions
    openPayment(paymentId) {
        if (!paymentId) return;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "account.payment",
            res_id: paymentId,
            views: [[false, "form"]],
            target: "current",
        });
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

    async printPdf() {
        const wizardId = await this.orm.create("mba.daily.cxc.wizard", [{
            date_report: this.state.date_report,
            company_id: this.state.data.company_id,
        }]);

        const action = await this.orm.call(
            "mba.daily.cxc.wizard",
            "action_print_report",
            [[wizardId]]
        );

        return this.actionService.doAction(action);
    }

    async exportXlsx() {
        return this.printPdf();
    }
}

registry.category("actions").add("mba_daily_cxc_report", DailyCxcReport);
