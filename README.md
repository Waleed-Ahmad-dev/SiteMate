# Entrpryz Construction BOQ Module Documentation

## 1. Overview
The **Entrpryz Construction BOQ** (Bill of Quantities) module is designed for Odoo 18 to manage construction project budgets and bills of quantities effectively. It allows construction companies to estimate costs, track budgets against projects, and monitor material and labor consumption.

This module integrates with Odoo's Project, Accounting, and Product modules to provide a seamless experience for project managers and quantity surveyors.

## 2. Key Features
- **Project-Based BOQs:** Link every BOQ to a specific Project and Analytic Account.
- **Hierarchical Structure:** Organize BOQ lines with Sections and Notes for better readability.
- **Approval Workflow:** Strict lifecycle management (Draft → Submitted → Approved → Locked → Closed).
- **Budget Tracking:** Real-time calculation of total estimated budget.
- **Consumption Tracking:** Track consumed quantities and amounts against the estimated budget (planned vs. actual).
- **Cost Types:** Categorize costs into Material, Labor, Subcontract, Service, and Overhead.
- **Audit Trail:** Track creation, approvals, and changes via Odoo's chatter and audit fields.
- **Multi-Company Support:** Full support for multi-company environments.

## 3. Installation
1.  **Dependencies:** Ensure the following Odoo modules are available:
    *   `base`
    *   `project`
    *   `purchase`
    *   `stock`
    *   `account`
    *   `mail`
2.  **Install:**
    *   Place the `entrpryz_construction_boq` folder into your Odoo addons path.
    *   Update the App List in Odoo (Apps -> Update App List).
    *   Search for "Entrpryz Construction BOQ" and click **Activate**.

## 4. User Guide

### 4.1. Navigation
To access the module, go to the main Odoo dashboard and select **Construction**.
*   **Menu Path:** Construction > BOQs

### 4.2. Creating a New BOQ
1.  Click **New** (or Create) in the BOQ list view.
2.  **Reference:** Enter a reference name for the BOQ (e.g., "Villa Project BOQ Phase 1").
3.  **Project:** Select the Project this BOQ belongs to.
4.  **Analytic Account:** This will auto-populate based on the selected Project (if configured). It ensures costs are booked to the correct financial account.
5.  **Company:** Defaults to your current company.

### 4.3. Adding BOQ Lines
In the **BOQ Lines** tab, you can add line items, sections, and notes.

*   **Add a Section:** Click "Add a section" to create a header (e.g., "Foundation", "Electrical").
*   **Add a Line:** Click "Add a line" to insert a cost item.
    *   **Product:** Select a product (optional). If selected, description, UoM, and rate are auto-filled.
    *   **Description:** Detailed name of the item.
    *   **Cost Type:** Choose between Material, Labor, Subcontract, Service, or Overhead.
    *   **Quantity:** Estimated quantity.
    *   **Unit of Measure (UoM):** Unit for the quantity (e.g., m², kg, hours).
    *   **Rate:** Estimated unit cost.
    *   **Expense Account:** The GL account where expenses for this item will be recorded.
*   **Add a Note:** Click "Add a note" for additional comments or instructions.

**Totals:** The module automatically calculates the **Budget Amount** (Qty * Rate) for each line and updates the **Total Budget** at the bottom.

### 4.4. Workflow & Lifecycle
The BOQ moves through several stages to ensure control:

1.  **Draft:** The initial state. You can edit all fields and lines.
2.  **Submitted:** Click **Submit** when the estimation is complete. This indicates the BOQ is ready for review.
3.  **Approved:** A manager clicks **Approve**.
    *   *Validation:* You cannot approve an empty BOQ.
    *   *Constraint:* Only one active (Approved/Locked) BOQ is allowed per project to prevent conflicting budgets.
    *   *Locking:* Once approved, the BOQ lines become read-only to preserve the budget baseline.
4.  **Locked:** Click **Lock** to finalize the BOQ completely. This is functionally similar to Approved but indicates a frozen state.
5.  **Closed:** Click **Close** when the project or BOQ is finished.

### 4.5. Monitoring Consumption
The module tracks "Actuals" against the "Budget".
*   **Consumed Qty / Amount:** Shows how much has been used so far.
*   **Remaining Qty / Amount:** Shows the balance.
*   **Visual Indicators:** The "Remaining Amount" turns red if you are over budget (negative remaining).

*Note: Consumption data is populated via the `consumption_ids` relation, typically integrated with Purchase Orders or Stock Moves in custom implementations.*

## 5. Technical Documentation

### 5.1. Data Models
| Model Name | Description |
| :--- | :--- |
| `construction.boq` | The main header model for the Bill of Quantities. |
| `construction.boq.line` | Individual line items (materials, labor, etc.). |
| `construction.boq.section` | Sections for organizing lines (backend model, view uses `display_type`). |
| `construction.boq.consumption` | Ledger for tracking actual usage against BOQ lines. |

### 5.2. Access Rights & Security
*   **Group:** `base.group_user` (Internal User) has full access (Read, Write, Create, Delete) to all BOQ models by default.
*   **Record Rules:** Multi-company rules are applied. Users can only see BOQs belonging to their allowed companies.

### 5.3. Constraints
*   **Unique Project Version:** A project cannot have two BOQs with the same version number.
*   **One Active BOQ:** A project can only have one BOQ in 'Approved' or 'Locked' state at a time.
*   **Modification Lock:** BOQ lines cannot be edited once the BOQ is in 'Approved', 'Locked', or 'Closed' state.
*   **Analytic Integrity:** BOQ Line analytic accounts must match the parent BOQ's analytic account.

### 5.4. Integration Points
*   **Projects:** Links via `project_id`.
*   **Accounting:** Links via `analytic_account_id` and `expense_account_id`.
*   **Products:** Fetches default data from `product.product`.

## 6. Support
**Author:** ELB Marketing
**Website:** https://entrpryz.com
