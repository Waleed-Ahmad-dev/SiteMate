# Entrpryz Construction BOQ

**Version**: 1.0  
**Author**: Waleed Ahmad (Shadow Scripter)  
**License**: LGPL-3  
**Category**: Construction  

## Overview

**Entrpryz Construction BOQ** is a comprehensive Odoo module designed to manage the Bill of Quantities (BOQ) for construction projects. It provides end-to-end control over project budgets, material estimation, and actual consumption through tight integration with Odoo's Project, Purchase, Inventory, and Accounting modules.

This module allows construction companies to:
- Create detailed Bill of Quantities with multi-level structures.
- Enforce strict budget controls during purchasing and inventory issuance.
- Track real-time consumption and "Budget vs. Actual" variances.
- Manage revisions and version history for BOQ evolutions.

## Key Features

### 🏗️ BOQ Management
-   **Structure**: Organize BOQs by Project and Analytic Account.
-   **Line Items**: Support for Sections, Notes, and Product Lines.
-   **Cost Types**: Classify costs as Material, Labor, Subcontract, Service, or Overhead.
-   **Workflow**: Robust state machine (Draft → Submitted → Approved → Locked → Closed).
-   **Approvals**: Role-based approval workflow with validation gates (e.g., cannot approve without lines).

### 🔄 Versioning & Revisions
-   **Snapshots**: Automatic creation of immutable snapshots (v1, v2, etc.) upon major revisions.
-   **Audit Trail**: Track who approved revisions, when, and why.
-   **History View**: dedicated view to browse past versions of a BOQ for a specific project.
-   **Comparison**: Active vs. Previous version tracking.

### 💰 Budget Control
-   **Estimation**: Define Budget Quantity and Budget Rate per line item.
-   **Validation**: Prevent submission/approval of incomplete BOQs.
-   **Total Budget**: Real-time computation of the total project budget based on active lines.

### 🛒 Purchase Integration
-   **BOQ Purchase Mode**: New "Purchase Mode" on Purchase Orders to differentiate project purchases from regular stock replenishment.
-   **Line Linking**: Direct linking of Purchase Order Lines to specific BOQ Items.
-   **Budget enforcement**: Automatic validation to ensure PO quantities do not exceed BOQ remaining quantities.
-   **Project Alignment**: strict validation to ensure PO Project matches the BOQ Project.

### 📦 Inventory & Consumption
-   **Stock Moves**: Link Stock Moves (Delivery/Production outcomes) to BOQ Lines.
-   **Valuation Override**: Automatically route stock valuation to the BOQ Line's configured Expense Account instead of default category accounts.
-   **Consumption Ledger**: Comprehensive ledger (`construction.boq.consumption`) tracking every material consumption event.
-   **Over-Consumption Protection**: Optional strict blocking of stock moves that exceed budget limits.

### 📊 Project Integration
-   **Activity Codes**: Map BOQ lines to Project Tasks via unique Activity Codes.
-   **Analytic Distribution**: Automated propagation of Analytic Accounts to Journal Entries and Stock Moves.

## Installation

### Dependencies
This module requires the following Odoo Community/Enterprise modules:
-   `base`
-   `project`
-   `purchase`
-   `stock`
-   `stock_account`
-   `account`
-   `mail`
-   `analytic`

### Configuration
1.  **Analytic Accounts**: Ensure your Projects have Analytic Accounts configured, as the BOQ relies on them for cost tracking.
2.  **Product Setup**: Products used in BOQ lines **must** have:
    -   A valid Unit of Measure.
    -   A Standard Price (for budget estimation defaults).
    -   An Expense Account (or Category Expense Account).
3.  **User Access**: Ensure relevant users have access to Construction/Project, Purchase, and Inventory apps.

## Usage Workflow

### 1. Create a BOQ
1.  Navigate to **Construction > BOQs**.
2.  Click **New**.
3.  Select a **Project** (Analytic Account auto-fills).
4.  Add **BOQ Lines**:
    -   Use "Add Section" to organize items (e.g., "Foundation", "Electrical").
    -   Add Products, set **Budget Qty** and **Budget Rate**.
5.  **Submit** the BOQ for review.
6.  **Approve** the BOQ to make it active.

### 2. Purchasing Materials
1.  Create a **Purchase Order**.
2.  Set **Purchase Mode** to "BOQ Purchase".
3.  Select the **Project** and the active **BOQ**.
4.  Add Products. In the order line, select the specific **BOQ Item**.
    -   *Note: Only BOQ lines matching the product will appear.*
5.  Confirm Order. Odoo checks if the requested quantity allows for the remaining budget.

### 3. Consuming Materials (Stock)
1.  Process the **Delivery/Receipt** associated with the User/Project.
2.  On the Stock Move, ensure the **BOQ Line** is linked (auto-linked from PO).
3.  **Validate** the transfer.
    -   The system validates if `Consumed Qty + New Qty <= Budget Qty`.
    -   If valid, a **Consumption Record** is created.
    -   Accounting entries are generated with the correct Analytic Distribution and Expense Account.

### 4. Revising a BOQ
1.  Open an **Approved** or **Locked** BOQ.
2.  Click **Revise**.
3.  The system archives the current version (e.g., v1) as a read-only snapshot.
4.  The current record becomes a **Draft** (v2) ready for editing.
5.  Modify lines/quantities and re-submit for approval.

## Technical Architecture

### Core Models
| Model | Description |
| :--- | :--- |
| `construction.boq` | Header model containing project link, versioning, and total budget. |
| `construction.boq.line` | Detail lines (products/sections). Holds the core logic for consumption and remaining budget. |
| `construction.boq.consumption` | A ledger table recording every instance of consumption (source: Stock Move). |
| `construction.boq.revision` | Junction table tracking the relationship between an Original BOQ and its New Version. |

### Inherited Models
-   **`purchase.order`**: Added `purchase_type` and `boq_id`.
-   **`purchase.order.line`**: Added `boq_line_id` and budget partial constraints.
-   **`stock.move`**: Added `boq_line_id` and logic overlaps for `_action_done` and `_get_dest_account`.
-   **`project.task`**: Added `activity_code` for mapping tasks to costs.

## Troubleshooting

-   **"Product Configuration Warning"**: The selected product is missing a price, UoM, or Expense Account. Fix the product master data.
-   **"BOQ Quantity Exceeded"**: You are trying to purchase or consume more than the budgeted amount. Either increase the budget (Revise BOQ) or check the "Allow Over Consumption" flag on the BOQ Line.
-   **"Expense Account is missing"**: The system cannot determine where to book the cost. Set an expense account on the Product or its Category.

---
*Built with ❤️ for Odoo.*
