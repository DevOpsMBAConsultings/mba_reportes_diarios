/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MonthlyIncomeReport extends Component {
    static template = "mba_reportes_diarios.MonthlyIncomeReportTemplate";

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
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "mba.monthly.income.wizard",
                "get_client_report_data",
                [this.state.date_from, this.state.date_to]
            );
            this.state.data = data;
        } catch (error) {
            console.error("Error loading monthly income report data:", error);
        } finally {
            this.state.loading = false;
        }
    }

    async onDateChange() {
        await this.loadData();
    }

    async printPdf() {
        const wizardId = await this.orm.create("mba.monthly.income.wizard", [{
            date_from: this.state.date_from,
            date_to: this.state.date_to,
            company_id: this.state.data.company_id,
        }]);

        const action = await this.orm.call(
            "mba.monthly.income.wizard",
            "action_print_report",
            [[wizardId]]
        );

        return this.actionService.doAction(action);
    }

    async exportXlsx() {
        const res = await this.orm.create("mba.monthly.income.wizard", [{
            date_from: this.state.date_from,
            date_to: this.state.date_to,
            company_id: this.state.data.company_id,
        }]);
        const id = Array.isArray(res) ? res[0] : res;

        const action = await this.orm.call(
            "mba.monthly.income.wizard",
            "action_export_xlsx",
            [[id]]
        );

        return this.actionService.doAction(action);
    }
}

registry.category("actions").add("mba_monthly_income_report", MonthlyIncomeReport);

