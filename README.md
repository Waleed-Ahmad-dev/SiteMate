# Entrpryz Construction BOQ Module

## 1. Overview

The **Entrpryz Construction BOQ** (Bill of Quantities) module is a robust Odoo 18 application designed to streamline the financial management of construction projects. It enables construction companies, contractors, and project managers to create detailed budget estimations, track revisions through a rigorous approval workflow, and monitor actual consumption against planned budgets in real-time.

By bridging the gap between Project Management (`project`) and Accounting (`stock_account`, `account`), this module ensures that every material cost, labor hour, and overhead expense is accounted for and linked to specific analytic accounts.

---

## 2. Key Features

### 🏗️ Project-Centric Design

- **Direct Integration**: Every BOQ is strictly linked to an Odoo `Project` and an `Analytic Account`, ensuring financial integrity.
- **One Active BOQ Policy**: To prevent conflicting budgets, the system enforces a strict rule where only _one_ BOQ can be in an "Approved" or "Locked" state per project.
- **Task Linkage**: BOQ lines can be mapped to specific Project Tasks, allowing granular tracking of costs per activity using `activity_code`.

### 🔄 Advanced Versioning & History (Copy-on-Write)

- **Automatic Snapshots**: The module utilizes a "Copy-on-Write" mechanism. If a locked or submitted BOQ needs modification, the system automatically:
  1. Archives the current version as a snapshot.
  2. Increments the version number (e.g., v1 → v2).
  3. Creates an audit trail linking the revisions.
- **Manual Revisions**: Users can explicitly trigger a "Revise Manually" action to create a new version snapshot on demand.
- **Revision History**: Users can view the full history of a BOQ, comparing previous snapshots with the current active version to see exactly what changed and why.

### 💰 Comprehensive Budgeting & Reporting

- **Hierarchical BOQ**: Organize costs using **Sections** (e.g., "Substructure", "Superstructure") and **Notes** for better readability.
- **Multi-Cost Types**: Categorize expenses into:
  - `Material`: Tangible goods.
  - `Labor`: Manpower costs.
  - `Subcontract`: Outsourced work.
  - `Service`: Professional services.
  - `Overhead`: Indirect costs.
- **Currency Support**: Full multi-currency support inherited from the parent Company settings.

### 📊 Consumption & Variance Tracking

- **Planned vs. Actual**: Each line item tracks:
  - **Budget Amount**: Quantity × Estimated Rate.
  - **Consumed Amount**: Actuals tracked via integration (e.g., Purchase Orders).
  - **Remaining Amount**: Visual indicators turn red when over budget.
- **Visual Progress**: Integrated progress bars (`consumption_percentage`) show real-time burn rate for each line item.
- **Over-Consumption Control**: Optional strict enforcement to prevent exceeding budgeted quantities without explicit manager approval.

### 🛡️ Security & Access Control

- **Multi-Company**: Fully supports multi-company environments with record rules ensuring users only see BOQs for their allowed companies.
- **Role-Based Access**:
  - `User`: Can create and view BOQs.
  - `Manager`: Can approve, lock, and unlock BOQs.
  - `Finance Head`: Can authorize over-consumption.

---

## 3. Technical Architecture

### 3.1. File Structure

```bash
entrpryz_construction_boq/
├── models/
│   ├── boq.py              # Core logic: Header, Line, Section, Consumption
│   ├── boq_revision.py     # Audit mechanism for version history
│   ├── boq_report.py       # Reporting engines
│   └── ...                 # Extended standard models
├── views/
│   ├── boq_views.xml       # Form, Tree, and Search views for BOQ & Sections
│   ├── boq_report_views.xml # Pivot and Graph views
│   └── ...
├── security/
│   ├── construction_security.xml # Record rules and access groups
│   └── ir.model.access.csv       # ACL definitions
├── __manifest__.py         # Module metadata and dependencies
└── README.md
```

### 3.2. Data Models

| Model                          | Description      | Key Capabilities                                                 |
| :----------------------------- | :--------------- | :--------------------------------------------------------------- |
| `construction.boq`             | The BOQ Header.  | Versioning engine, Workflow state machine.                       |
| `construction.boq.line`        | Detail lines.    | Budget calculation, UI Progress Bars (`consumption_percentage`). |
| `construction.boq.section`     | Sections.        | Organization of lines, Company-specific.                         |
| `construction.boq.consumption` | Ledger.          | Stores actual consumption logs (date, user, qty, amount).        |
| `construction.boq.revision`    | Cross-reference. | Links an "Original" (archived) BOQ to a "New" (active) BOQ.      |

---

## 4. Installation & Configuration

### 4.1. Prerequisites

Ensure the following Odoo Community/Enterprise modules are installed:

- `project`
- `stock_account`
- `purchase`

### 4.2. Installation Steps

1. Clone this repository into your Odoo `addons` path.
2. Restart the Odoo service.
3. Log in as Administrator.
4. Go to **Apps**, search for `Entrpryz Construction BOQ`, and click **Activate**.

### 4.3. Post-Installation Configuration

1. **User Groups**: Go to _Settings > Users & Companies > Users_. Assign the "Construction / Manager" group to users who need approval rights.
2. **Analytic Accounts**: Ensure your Projects have valid Analytic Accounts configured, as the BOQ relies on them for cost allocation.
3. **BOQ Sections**: Go to _Construction > Configuration > BOQ Sections_ to pre-define common sections (e.g., "Civil", "MEP", "Finishing") for standardization across projects.

---

## 5. User Guide

### 5.1. Creating a Bill of Quantities

1. Navigate to **Construction > BOQs**.
2. Click **New**.
3. **Project Scope**:
    - Select the **Project**.
    - The **Analytic Account** will auto-fill from the project.
4. **Control & Versioning**:
    - **Version**: Automatically tracked (starts at 1).
    - **Previous Version**: Link to the predecessor if applicable.
5. Save to create a Draft.

### 5.2. Defining the Budget (Lines)

1. **Add Sections**: Break down the project (e.g., "Phase 1: Civil Works").
2. **Add Lines**:
    - **Product**: Select a product to auto-fill UoM and Cost.
    - **Description**: Enter a clear description (e.g. "Concrete M25 Grade").
    - **Cost Type**: Crucial for reporting (Material/Labor/etc.).
    - **Estimation**: Enter Quantity and Rate.
    - **Budget Amount**: Calculated automatically.
3. **Detailed View**: Click the line to open the detailed form view, which shows:
    - **Efficiency**: Visual progress bar.
    - **Consumption Logs**: Detailed history of actual spending.
4. **Expense Account**: Ensure the correct GL account is set.

### 5.3. Approval Workflow

1. **Submit**: When ready, click **Submit for Approval**. The status changes to `Submitted`.
2. **Approve**: A manager reviews the budget.
    - If valid, they click `Approve`.
    - _Constraint_: You cannot approve if another BOQ for this project is already active.
    - _Locking_: Once approved, the BOQ lines become read-only to preserve the budget baseline.
3. **Lock**: Finalizes the budget, making it read-only.
4. **Revise**:
    - **Auto-Revision**: Edit a locked BOQ and save. The system prompts a version upgrade.
    - **Manual Revision**: Click **Revise Manually** to force a new version snapshot immediately.

### 5.4. Tracking Consumption

Consumption is typically recorded automatically via Purchase Orders or Stock Picking if configured.

- **Visual Indicators**:
  - **Progress Bars**: Show % of budget consumed per line.
  - **Red Text**: Indicates "Remaining Amount" is negative (over budget).
  - **Amber Text**: Warns when "Remaining Amount" is low (<10% budget left).
- **Manual Entry**: You can manually add entries to the `consumption_ids` table in the form view if needed.

---

## 6. Troubleshooting

- **Error: "BOQ Line analytic account must match..."**
  - _Fix_: Ensure the Project's analytic account matches the one set on the BOQ lines. If you changed the Project, re-save to update lines.
- **Error: "An active BOQ with this version already exists..."**
  - _Fix_: You might have manually duplicated a BOQ without archiving the old one. Archive the old version first.
- **Cannot Delete Line**:
  - _Reason_: If the BOQ is linked to actual consumption records, Odoo prevents deletion to maintain audit integrity. Archive the line instead or reverse consumption.

## 7. Support

**Author**: Waleed Ahmad (Shadow Scripter)
**Website**: [Check out my portfolio](https://www.shadowscripter.online)
**License**: LGPL-3

---

## 8. License

This module is distributed under the [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.en.html) license.
