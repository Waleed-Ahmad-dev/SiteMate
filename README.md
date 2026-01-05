# Entrpryz Construction BOQ

**Construction Bill of Quantities Management for Odoo**

This module provides a comprehensive solution for managing Bill of Quantities (BOQ) in construction projects within Odoo. It is designed to help construction companies estimate costs, track budgets, and manage the complete approval lifecycle of their project's BOQs with precision and ease.

## 🌟 Key Features

- **Seamless Project Integration**: Directly link your BOQs to existing Odoo Projects, ensuring all data is centralized.
- **Automatic Analytic Accounting**: The module automatically associates BOQs with the project's analytic account, enabling precise financial tracking and reporting.
- **Structured & Flexible BOQs**:
  - **Sections**: Organize your BOQ into logical groups (e.g., "Foundation", "Framing", "Electrical") using sections.
  - **Notes**: Add explanatory notes directly within the line items for better clarity.
- **Detailed Cost Categorization**: Classify every line item into specific cost types:
  - Material
  - Labor
  - Subcontract
  - Service
  - Overhead
- **Robust Approval Workflow**: Manage the lifecycle of your BOQ with a strict state machine:
  - **Draft**: Initial creation and editing phase.
  - **Submitted**: Sent to management for review.
  - **Approved**: Validated by authorized personnel (locks the BOQ against major changes).
  - **Locked**: Finalized state for execution and consumption.
  - **Closed**: Archived or completed BOQs.
- **Versioning Support**: Maintain multiple versions of a BOQ for the same project to track revisions and history.
- **Smart Budget Calculation**: Automatically computes total budgets based on quantities and estimated rates.
- **Audit Trail**: Built-in tracking of who created, approved, and modified the documents.

## 📦 Dependencies

This module relies on the following standard Odoo modules:

- `base`
- `project`
- `analytic`
- `purchase`
- `stock`
- `account`

## 🚀 Installation

1.  **Clone the Repository**:
    Download or clone this repository into your Odoo custom addons directory.

    ```bash
    git clone <repository-url> entrpryz_construction_boq
    ```

2.  **Update Configuration**:
    Ensure your `odoo.conf` file includes the path to your custom addons directory in the `addons_path` parameter.

3.  **Update App List**:

    - Enable **Developer Mode** in Odoo.
    - Go to **Apps** > **Update Apps List**.
    - Click **Update**.

4.  **Install the Module**:
    - Search for "Entrpryz Construction BOQ".
    - Click **Activate** (or Install).

## 📖 Usage Guide

### 1. Accessing the Module

Navigate to the new **Construction** app in your Odoo dashboard and select **BOQs**.

### 2. Creating a New BOQ

1.  Click the **New** button.
2.  **Reference**: A unique reference (e.g., New) is assigned automatically, but you can modify it if needed.
3.  **Project**: Select the Project this BOQ belongs to. The **Analytic Account** will be auto-filled based on the project settings.
4.  **Version**: Assign a version number (default is 1).

### 3. Adding Line Items

1.  Go to the **BOQ Lines** tab.
2.  Click **Add a section** to start a new category (e.g., "Phase 1").
3.  Click **Add a line** to add a cost item.
    - **Product**: Select a product (optional) to auto-fill description and price.
    - **Description**: Enter a detailed description of the work or material.
    - **Cost Type**: Categorize as Material, Labor, etc.
    - **Quantity**: Enter the required amount.
    - **Rate**: Enter the estimated unit cost.
    - **Expense Account**: Select the relevant financial account.

### 4. Approval Process

1.  **Submit**: Once the BOQ draft is complete, click **Submit**. The status changes to _Submitted_.
2.  **Approve**: A manager checks the details and clicks **Approve**. This records the **Approval Date** and **Approved By** user.
3.  **Lock**: To finalize the BOQ and prevent further edits, click **Lock**.

## 🛠 Project Structure

- `models/`: Contains the database logic (`boq.py`).
- `views/`: Contains the XML user interface definitions (`boq_views.xml`).
- `security/`: Contains access rights and permissions.
- `__manifest__.py`: Module metadata and configuration.

## 📄 License

This project is licensed under the **LGPL-3** (GNU Lesser General Public License v3.0).
See the [LICENSE](LICENSE) file for the full text.

## ✍️ Author

**ELB Marketing**
[https://www.entrpryz.com](https://entrpryz.com)
