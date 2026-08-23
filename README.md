# Panamá - Reportes Diarios Cierre de Caja (`mba_reportes_diarios`)

[![Odoo Version](https://img.shields.io/badge/Odoo-18.0-%23875A7B?logo=odoo)](https://www.odoo.com)
[![License](https://img.shields.io/badge/License-LGPL--3-blue.svg)](https://www.gnu.org/licenses/lgpl-3.0.html)
[![Author](https://img.shields.io/badge/Author-MBA%20Consultings-green)](https://www.mbaconsultings.com)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen)]()
[![Dependencies](https://img.shields.io/badge/Depends-account%20%7C%20point_of_sale%20(optional)%20%7C%20account_commission_oca%20(optional)-orange)]()

Cinco reportes de cierre de caja para Panamá, todos de **solo lectura**: ningún reporte modifica facturas, inventario ni pagos, solo los consulta y los presenta.

---

## 📋 Tabla de Contenidos

- [Resumen de Reportes](#-resumen-de-reportes)
- [Arquitectura y Diseño](#-arquitectura-y-diseño)
- [Instalación](#-instalación)
- [Configuración](#-configuración)
- [Uso](#-uso)
- [Reportes en Detalle](#-reportes-en-detalle)
- [API para Frontend OWL](#-api-para-frontend-owl)
- [Estructura del Módulo](#-estructura-del-módulo)
- [Seguridad y Permisos](#-seguridad-y-permisos)
- [Pruebas](#-pruebas)
- [Contribución](#-contribución)
- [Licencia](#-licencia)
- [Soporte](#-soporte)

---

## 📊 Resumen de Reportes

| # | Reporte | Tipo | Módulo Requerido | Descripción |
|---|---------|------|------------------|-------------|
| 1 | **Cierre Diario / Mensual (POS)** | Diario + Mensual | `point_of_sale` | Combina ventas de POS y facturas de Ventas (sin duplicar). Incluye totales, impuestos, recaudo por método de pago, costo de ventas, utilidad bruta y desglose por departamento. |
| 2 | **Cierre Diario (Facturación)** | Diario | `account` | Facturas originadas en POS para que el cajero cuadre su caja: contado vs. crédito, gravable vs. exento, cobros por método de pago de sesión POS. |
| 3 | **Cobros Cuentas por Cobrar (CxC)** | Diario + Mensual | `account` | Cartera del canal Ventas a crédito: pagos entrantes conciliados contra facturas saldadas + listado informativo de facturas a crédito emitidas (no suman al total). |
| 4 | **Comisiones de Ventas (Pre-Cierre)** | Rango de fechas | `account_commission_oca` (OCA) | Por vendedor y por factura: comisión devengada, pendiente de liquidar y ya liquidada. |
| 5 | **Resumen Mensual de Ingresos (MTD)** | Mensual (matriz día/día) | `account` + `point_of_sale` (opcional) | Matriz día por día del mes: efectivo, tarjetas, transferencias, cobros CxC y facturas a crédito (informativo), con totales acumulados. |

---

## 🏗️ Arquitectura y Diseño

### Modelo Catálogo Unificado
El módulo expone un modelo `mba.report.template` que lista los reportes disponibles (nombre, ícono, XML ID de la acción de su wizard) y arma el menú de reportes en la interfaz. Cada reporte se oculta automáticamente del menú si el módulo del que depende no está instalado.

### Wizards Independientes
Cada reporte tiene su propio wizard:
- `mba.daily.cxc.wizard`
- `mba.daily.invoice.wizard`
- `mba.daily.pos.wizard`
- `mba.monthly.income.wizard`
- `mba.sales.commission.wizard`

El usuario elige fecha y compañía, y el wizard consulta y clasifica facturas/pagos, calcula costos y genera un PDF con los totales.

### Trazabilidad de Costos (Cierre POS)
El costo de las facturas de Ventas se traza línea por línea hasta su entrega real en inventario:
```
Factura → Línea de Orden de Venta → Movimiento de Bodega → Capa de Valoración (stock.valuation.layer)
```
Así el costo siempre aparece en la **fecha de la factura**, sin importar qué día se validó la salida física en el sistema. Las ventas de POS usan el costo registrado el mismo día de la venta. Si un producto no tiene costo rastreable, se usa el **costo estándar** de su ficha.

### Diseño Agnóstico (Defensive Programming)
- El módulo **solo depende de `account`** (dependencia obligatoria).
- Si el cliente no tiene instalado **Inventario**, **Ventas** o **Punto de Venta**, cada sección que dependa de esos módulos se desactiva sola (o muestra un aviso) en vez de fallar.
- Un reporte queda **oculto automáticamente** del menú si el módulo del que depende no está instalado.
- Todo acceso a modelos opcionales (`pos.order`, `stock.valuation.layer`, `account.invoice.line.agent`) se hace vía `'model.name' in self.env`.

---

## 📦 Instalación

### Requisitos Previos
- Odoo 18.0
- Módulo base `account` (incluido en Odoo Enterprise/Community)
- Opcional: `point_of_sale` para reportes de POS
- Opcional: `account_commission_oca` (OCA) para reporte de Comisiones

### Instalación Estándar
```bash
# Clonar el repositorio en tu directorio de addons personalizados
git clone git@github.com:DevOpsMBAConsultings/mba_reportes_diarios.git

# Agregar la ruta a tu odoo.conf (addons_path) o instalar via interfaz de Odoo
# Actualizar lista de aplicaciones → Buscar "Panamá - Reportes Diarios" → Instalar
```

### Instalación OCA (Comisiones)
```bash
# Para el reporte de Comisiones de Ventas
git clone https://github.com/OCA/account-invoicing.git -b 18.0 --depth 1
# Activar módulo account_commission_oca
```

---

## ⚙️ Configuración

### 1. Catálogo de Reportes
Al instalar el módulo se crean 5 registros en `mba.report.template` (ver `data/report_template_data.xml`). Puedes:
- Activar/desactivar reportes individuales
- Cambiar el orden (`sequence`)
- Modificar íconos (`icon` - clases FontAwesome)
- Ver estado de disponibilidad (`module_installed`)

### 2. Diarios de Facturación (Cierre Facturación)
En el wizard "Cierre de Caja - Facturación" puedes filtrar por **Serie / Diarios de Venta** específicos. Dejar vacío para incluir todos los diarios tipo `sale`.

### 3. Métodos de Pago POS
Para que el desglose de cobros unifique nombres entre POS y Ventas:
1. Ve a **Contabilidad → Configuración → Diarios → [Tu Diario] → Pestaña "Pagos entrantes"**
2. Renombra las líneas de método de pago para que coincidan textualmente con los nombres de `pos.payment.method` del POS
   - Ej: `Tarjeta de Crédito`, `Tarjeta de Débito`, `Transf. Banesco`, `Transf. Banco General`

---

## 🚀 Uso

### Acceso desde Menú
**Contabilidad → Reportes → Reportes Diarios**

Desde ahí tienes acceso directo a cada reporte como **Vista Dinámica OWL (Client Action)** a pantalla completa, o al **Catálogo de Reportes** para gestión administrativa.

### Flujo Típico
1. Selecciona el reporte deseado
2. Elige la fecha (o rango de fechas para mensuales)
3. Selecciona la empresa (si tienes multi-company)
4. Clic en **Generar** → Se abre el dashboard interactivo
5. Opcional: **Imprimir PDF** desde el botón del wizard

---

## 📄 Reportes en Detalle

### 1. Cierre Diario / Mensual (Punto de Venta)
**Modelo:** `mba.daily.pos.wizard`  
**Acción PDF:** `action_report_daily_pos`  
**Client Action:** `action_daily_pos_client`

**Secciones del Reporte:**
- **Resumen de Sesiones POS** del día/rango
- **Totales Generales**: Ventas (POS + Ventas), Impuestos, Órdenes, Sin Impuesto
- **Desglose por Canal**: Ventas POS vs Ventas Facturación
- **Recaudo por Método de Pago**: POS + Pagos de facturas conciliados
- **Cobros Cuentas por Cobrar (CxC)** del período (excluye POS)
- **Detalle de Órdenes**: POS + Facturas fuera de caja (ordenadas por origen y nombre)
- **Productos Vendidos**: Agregados con cantidad, bruto, impuestos, neto
- **Costo de Ventas, Utilidad Bruta e Inventario**:
  - Costo trazado por factura (Ventas) + Heurístico día+producto (POS)
  - Inventario actual desglosado por categoría (stock.quant)
  - Compras recibidas hoy + en tránsito por categoría
  - Margen por categoría y total

**Modo Mensual:** Misma lógica, rango de fechas configurable (mes completo o rango personalizado).

---

### 2. Cierre Diario (Facturación)
**Modelo:** `mba.daily.invoice.wizard`  
**Acción PDF:** `action_report_daily_invoice`  
**Client Action:** `action_daily_invoice_client`

**Secciones:**
1. **Resumen**: Ventas brutas, ITBMS, Contado, Crédito, Transacciones, Gravable, Exento
2. **Desglose de Caja (POS)**: Efectivo, Tarjeta (vouchers), Transferencia — desde `pos.payment`
3. **Estadísticas CxC**: En cero por diseño (la cartera vive en reporte CxC)
4. **Tabla de Transacciones**: Documento, Cliente, Neto, Impuestos, Contado, Crédito
5. **Productos Vendidos**: Ítem, Descripción, Cantidad, Bruto, Impuestos, Neto

**Regla de Negocio:** Solo facturas **originadas en POS** (`pos_order_ids` presente). El canal de distribución (sale.order → account.move) NO entra aquí.

---

### 3. Cobros de Cuentas por Cobrar (CxC)
**Modelo:** `mba.daily.cxc.wizard`  
**Acción PDF:** `action_report_daily_cxc`  
**Client Action:** `action_daily_cxc_client`

**Secciones:**
- **Cobros Efectivamente Recibidos**: Pagos `account.payment` entrantes (in_process/paid) del período
  - Excluye: pagos de POS, clientes "Consumidor Final", "Cliente General"
  - Clasifica por diario: Efectivo, Tarjeta Crédito/Débito, Transferencia/Depósito
  - Conciliación: vincula cada pago a las facturas que salda (via `matched_debit_ids`)
- **Informativo - Facturas a Crédito Emitidas**: Del canal Ventas (no POS), no suman a cobros
  - Muestra: Factura, Cliente, Término Pago, Vencimiento, Total, Residual

**Regla de Negocio:** Cubre **exclusivamente cartera del canal Ventas** (sale.order → account.move) con término a crédito. La caja POS tiene su propio reporte.

---

### 4. Comisiones de Ventas (Pre-Cierre)
**Modelo:** `mba.sales.commission.wizard`  
**Acción PDF:** `action_report_sales_commission`  
**Client Action:** `action_sales_commission_client`  
**Requiere:** `account_commission_oca` (OCA)

**Filtros:**
- Rango de fechas (mes actual por defecto)
- Agente/Vendedor específico
- Estado liquidación: Todas / Pendientes / Liquidadas
- Estado cobro factura: Todas / Solo Pagadas / Publicadas

**Salida:**
- Por Agente: Ventas totales, Comisión total, Pendiente, Liquidada, # Facturas
- Detalle por Factura: Fecha, Cliente, Subtotal, Comisión, Pendiente, Liquidada, Estado (Pendiente/Parcial/Liquidada), Estado cobro

---

### 5. Resumen Mensual de Ingresos (MTD)
**Modelo:** `mba.monthly.income.wizard`  
**Acción PDF:** `action_report_monthly_income`  
**Client Action:** `action_monthly_income_client`

**Matriz Día × Concepto:**
| Concepto | Informativo? |
|----------|--------------|
| EFECTIVO | No |
| TARJETA CLAVE (DÉBITO) | No |
| VISA - MASTERCARD (CRÉDITO) | No |
| ACH / TRANSFERENCIAS DIRECTAS | No |
| COBROS CXC (RECIBOS / CHEQUES) | No |
| FACTURAS A CRÉDITO (EMITIDAS) | **Sí** |

**Fuentes de Datos:**
1. **Facturas** (`account.move`): Solo fila "Facturas a Crédito" (informativo)
2. **Pagos** (`account.payment`): Clasificación por diario + conciliación (si factura conciliada es de día anterior → CxC)
3. **POS** (`pos.order` + `pos.payment`): Alimenta efectivo/clave/visa/ach (POS no genera account.payment)

**Totales:**
- **Total MTD Ingresos**: Suma de filas NO informativas (dinero real recibido)
- **Total Facturas Crédito MTD**: Solo informativo (evita doble conteo con CxC)

---

## 🔌 API para Frontend OWL

Todos los wizards exponen un método `@api.model get_client_report_data(...)` que retorna un diccionario serializable a JSON para consumo asíncrono por el dashboard OWL (Client Actions a pantalla completa).

### Parámetros Comunes
```python
# Diarios (POS, Facturación, CxC)
get_client_report_data(
    date_report=fields.Date,      # Fecha única (modo diario)
    company_id=int,               # ID de empresa
    period_type='day'|'month',    # Tipo de período
    date_from=fields.Date,        # Rango personalizado
    date_to=fields.Date,
)

# Mensual (MTD)
get_client_report_data(
    date_from=fields.Date,
    date_to=fields.Date,
    company_id=int,
)

# Comisiones
get_client_report_data(
    date_from=fields.Date,
    date_to=fields.Date,
    agent_id=int,                 # Opcional
    settlement_state='all'|'pending'|'settled',
    payment_state='all'|'paid'|'posted',
    company_id=int,
)
```

### Respuesta Típica
```json
{
  "company_name": "Mi Empresa",
  "company_id": 1,
  "date_report": "2025-01-15",
  "time_report": "02:30 PM",
  "total_ventas": 12500.00,
  "formatted_total_ventas": "12,500.00",
  "payment_methods": [
    {"name": "Efectivo", "amount": 5000.00, "formatted_amount": "5,000.00", "count": 25},
    {"name": "Tarjeta", "amount": 7500.00, "formatted_amount": "7,500.00", "count": 18}
  ],
  "orders": [...],
  "products": [...],
  "cost_inventory": {...}
}
```

---

## 📁 Estructura del Módulo

```
mba_reportes_diarios/
├── __init__.py
├── __manifest__.py              # Definición del módulo (v18.0.1.3.19)
├── README.md                    # Este archivo
├── REFACTOR_UI.md               # Documentación del refactor UI (FASES A, B, C)
├── .gitignore
├── data/
│   └── report_template_data.xml # Registros iniciales mba.report.template
├── models/
│   ├── __init__.py
│   └── report_template.py       # Modelo catálogo + acción abrir wizard
├── wizard/
│   ├── __init__.py
│   ├── daily_invoice_wizard.py  # Cierre Facturación
│   ├── daily_pos_wizard.py      # Cierre POS (Diario + Mensual)
│   ├── daily_cxc_wizard.py      # Cobros CxC (Diario + Mensual)
│   ├── monthly_income_wizard.py # Resumen MTD
│   └── sales_commission_wizard.py # Comisiones (requiere OCA)
├── report/
│   ├── daily_invoice_report.xml
│   ├── daily_invoice_report_template.xml
│   ├── daily_cxc_report.xml
│   ├── daily_cxc_report_template.xml
│   ├── daily_pos_report.xml
│   ├── daily_pos_report_template.xml
│   ├── monthly_income_report.xml
│   ├── monthly_income_report_template.xml
│   ├── sales_commission_report.xml
│   └── sales_commission_report_template.xml
├── views/
│   ├── report_template_views.xml      # Tree/Form + Menús + Acciones Client
│   ├── daily_invoice_wizard_views.xml
│   ├── daily_cxc_wizard_views.xml
│   ├── daily_pos_wizard_views.xml
│   ├── monthly_income_wizard_views.xml
│   └── sales_commission_wizard_views.xml
├── security/
│   └── ir.model.access.csv            # Permisos por grupo account.user/manager
└── static/
    └── src/
        ├── scss/
        │   └── report_common.scss     # Estilos compartidos (fase C: look nativo Odoo)
        ├── xml/                       # Plantillas QWeb OWL (Client Actions)
        │   ├── daily_cxc_report.xml
        │   ├── daily_invoice_report.xml
        │   ├── daily_pos_report.xml
        │   ├── monthly_closing_report.xml
        │   ├── monthly_income_report.xml
        │   ├── sales_commission_report.xml
        │   └── closing_report_body.xml  # Cuerpo compartido POS/Mensual
        └── js/                        # Componentes OWL
            ├── daily_cxc_report.js
            ├── daily_invoice_report.js
            ├── daily_pos_report.js
            ├── monthly_closing_report.js
            ├── monthly_income_report.js
            └── sales_commission_report.js
```

---

## 🔐 Seguridad y Permisos

| Modelo | Usuario Contabilidad (`account.group_account_user`) | Manager Contabilidad (`account.group_account_manager`) |
|--------|---------------------------------------------------|------------------------------------------------------|
| `mba.report.template` | Lectura | Lectura, Escritura, Creación, Eliminación |
| `mba.daily.invoice.wizard` | Lectura, Escritura, Creación | Lectura, Escritura, Creación |
| `mba.daily.pos.wizard` | Lectura, Escritura, Creación | Lectura, Escritura, Creación |
| `mba.daily.cxc.wizard` | Lectura, Escritura, Creación | Lectura, Escritura, Creación |
| `mba.monthly.income.wizard` | Lectura, Escritura, Creación | Lectura, Escritura, Creación |
| `mba.sales.commission.wizard` | Lectura, Escritura, Creación | Lectura, Escritura, Creación |

> **Nota:** Ningún wizard tiene permiso `unlink` (eliminación) para usuarios, solo managers.

---

## 🧪 Pruebas

### Verificación Manual Rápida
1. Instala el módulo en una BD con datos de prueba (POS, Ventas, Facturas, Pagos)
2. Ve a **Contabilidad → Reportes → Reportes Diarios**
3. Abre cada reporte y verifica:
   - Carga sin errores
   - Datos coherentes con lo esperado
   - PDF se genera correctamente
   - Filtros de fecha/empresa funcionan

### Casos Edge a Validar
- [ ] BD **sin** `point_of_sale` instalado → Reportes POS ocultos, Cierre Facturación funciona
- [ ] BD **sin** `stock` / `stock_account` → Costo/Inventario muestra aviso "No disponible"
- [ ] BD **sin** `account_commission_oca` → Reporte Comisiones muestra aviso "Módulo OCA no instalado"
- [ ] Factura POS facturada después → No se duplica en Cierre POS (exclusión `pos_order_ids`)
- [ ] Entrega validada día posterior a factura → Costo aparece en fecha de factura (trazabilidad)
- [ ] Facturación parcial de una orden de venta → Costo unitario prorrateado (no duplicado)
- [ ] Multi-company → Filtro `company_id` respeta aislamiento de datos

---

## 🤝 Contribución

1. Fork del repositorio
2. Crea una rama: `git checkout -b feature/nueva-funcionalidad`
3. Commit tus cambios: `git commit -m 'feat: descripción clara'`
4. Push a la rama: `git push origin feature/nueva-funcionalidad`
5. Abre un Pull Request

### Estándares de Código
- Python: PEP 8, type hints donde aporte valor
- XML: Indentación 4 espacios, comentarios de sección `<!-- ═══ ... ═══ -->`
- SCSS: Variables `$o-*` de Odoo, prefijo `o_mba_*` para clases
- JS/OWL: Componentes funcionales, `useState`, `onMounted`, `orm` service

---

## 📄 Licencia

**LGPL-3.0** — Ver [LICENSE](LICENSE) o https://www.gnu.org/licenses/lgpl-3.0.html

---

## 📞 Soporte

| Canal | Contacto |
|-------|----------|
| 🌐 Web | https://www.mbaconsultings.com |
| 📧 Email | soporte@mbaconsultings.com |
| 🐛 Issues | https://github.com/DevOpsMBAConsultings/mba_reportes_diarios/issues |
| 📖 Wiki | https://github.com/DevOpsMBAConsultings/mba_reportes_diarios/wiki |

---

## 🏷️ Versionado

Este módulo sigue **SemVer** alineado con Odoo: `18.0.{major}.{minor}.{patch}`

| Versión | Fecha | Cambios Principales |
|---------|-------|---------------------|
| 18.0.1.3.19 | 2025-08 | Refactor UI completo (FASES A, B, C), Client Actions OWL, Catálogo unificado |
| 18.0.1.0.17 | 2025-07 | Fix scroll vertical, mejoras trazabilidad costo |
| 18.0.1.0.0  | 2025-06 | Migración a Odoo 18, arquitectura agnóstica |

Ver `REFACTOR_UI.md` para detalle técnico del rediseño de interfaz.

---

**Desarrollado por [MBA Consultings](https://www.mbaconsultings.com) — Brooks Gonzalez**  
*Panamá 🇵🇦*