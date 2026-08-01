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

        const now = new Date();

        this.months = [
            { value: 1, label: "Enero" },
            { value: 2, label: "Febrero" },
            { value: 3, label: "Marzo" },
            { value: 4, label: "Abril" },
            { value: 5, label: "Mayo" },
            { value: 6, label: "Junio" },
            { value: 7, label: "Julio" },
            { value: 8, label: "Agosto" },
            { value: 9, label: "Septiembre" },
            { value: 10, label: "Octubre" },
            { value: 11, label: "Noviembre" },
            { value: 12, label: "Diciembre" },
        ];

        // Rango de anios ofrecido: 5 atras y el actual.
        const currentYear = now.getFullYear();
        this.years = [];
        for (let y = currentYear; y >= currentYear - 5; y--) {
            this.years.push(y);
        }

        this.state = useState({
            month: now.getMonth() + 1,
            year: currentYear,
            loading: true,
            data: {},
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    /**
     * El backend recibe una fecha cualquiera del mes mas period_type 'month',
     * y resuelve el rango completo en _get_date_bounds(). Se manda el dia 1
     * para no depender de meses de 28/30/31 dias.
     */
    get referenceDate() {
        const mm = String(this.state.month).padStart(2, "0");
        return `${this.state.year}-${mm}-01`;
    }

    get periodLabel() {
        const m = this.months.find((x) => x.value === Number(this.state.month));
        return `${m ? m.label : ""} ${this.state.year}`;
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "mba.daily.pos.wizard",
                "get_client_report_data",
                [this.referenceDate, null, "month"]
            );
            this.state.data = data;
        } catch (error) {
            console.error("Error loading monthly closing data:", error);
        } finally {
            this.state.loading = false;
        }
    }

    async onPeriodChange() {
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
            date_report: this.referenceDate,
            period_type: "month",
            month: String(this.state.month),
            year: this.state.year,
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
