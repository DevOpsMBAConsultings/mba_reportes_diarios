/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class DailyPosReport extends Component {
    static template = "mba_reportes_diarios.DailyPosReportTemplate";

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");

        const today = new Date().toISOString().split("T")[0];

        this.state = useState({
            date_report: today,
            loading: true,
            data: {},
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "mba.daily.pos.wizard",
                "get_client_report_data",
                [this.state.date_report]
            );
            this.state.data = data;
        } catch (error) {
            console.error("Error loading POS report data:", error);
        } finally {
            this.state.loading = false;
        }
    }

    async onDateChange() {
        await this.loadData();
    }

    openOrder(orderId) {
        if (!orderId) return;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "pos.order",
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
            date_report: this.state.date_report,
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

registry.category("actions").add("mba_daily_pos_report", DailyPosReport);
