# WooCommerce Integration Module - Technical Documentation

## Overview
This module integrates Odoo 18 with WooCommerce, providing bidirectional synchronization of products between both systems. It allows users to manage WooCommerce products from Odoo and keep both systems in sync.

## Architecture

### 1. Models (Database Tables)

#### 1.1 WooCommerce Connection (`woocommerce.connection`)
**File:** `models/woocommerce_connection.py`
**Purpose:** Stores connection details to WooCommerce stores

**Key Fields:**
- `name`: Connection name
- `store_url`: WooCommerce store URL
- `consumer_key`: WooCommerce API consumer key
- `consumer_secret`: WooCommerce API consumer secret
- `status`: Connection status (active/inactive)

**Key Methods:**
- `test_connection()`: Tests API connectivity
- `get_products()`: Fetches products from WooCommerce
- `create_product()`: Creates product in WooCommerce
- `update_product()`: Updates product in WooCommerce
- `delete_product()`: Deletes product from WooCommerce

#### 1.2 WooCommerce Product (`woocommerce.product`)
**File:** `models/woocommerce_product.py`
**Purpose:** Stores WooCommerce product data locally in Odoo

**Key Fields:**
- `wc_product_id`: WooCommerce product ID
- `name`: Product name
- `wc_sku`: Product SKU
- `price`: Current price
- `regular_price`: Regular price (Tarif régulier)
- `sale_price`: Sale price (Tarif promo)
- `status`: Product status (draft/publish)
- `sync_status`: Sync status (pending/synced/error)
- `connection_id`: Link to WooCommerce connection
- `odoo_product_id`: Link to Odoo product

**Key Methods:**
- `write()`: Overridden to trigger bidirectional sync
- `_sync_to_woocommerce_store()`: Syncs changes to WooCommerce store
- `_sync_to_odoo_product()`: Syncs changes to linked Odoo product
- `action_sync_to_woocommerce()`: Manual sync to WooCommerce
- `action_sync_to_odoo()`: Manual sync to Odoo

#### 1.3 Product Template Extension (`product.template`)
**File:** `models/product_template.py`
**Purpose:** Extends Odoo's product template with WooCommerce fields

**Added Fields:**
- `wc_connection_id`: WooCommerce connection
- `wc_product_id`: WooCommerce product ID
- `wc_sync_enabled`: Enable WooCommerce sync
- `wc_auto_sync`: Auto-sync on changes
- `wc_sync_direction`: Sync direction (odoo_to_wc/wc_to_odoo)
- `wc_image_sync_enabled`: Include images in sync
- `wc_sync_status`: Sync status
- `wc_last_sync`: Last sync timestamp
- `wc_last_error`: Last sync error

**Key Methods:**
- `write()`: Overridden to trigger WooCommerce sync
- `_prepare_woocommerce_data()`: Prepares data for WooCommerce API
- `_update_woocommerce_product_table()`: Updates WooCommerce product table
- `action_sync_to_woocommerce()`: Manual sync action

#### 1.4 Import Wizard (`woocommerce.import.wizard`)
**File:** `models/woocommerce_import_wizard.py`
**Purpose:** Handles bulk import of products from WooCommerce

**Key Fields:**
- `connection_id`: WooCommerce connection
- `import_limit`: Number of products to import
- `import_images`: Import product images
- `overwrite_existing`: Overwrite existing products

**Key Methods:**
- `action_start_import()`: Starts import process
- `_import_products_simple()`: Simplified import logic

### 2. Views (User Interface)

#### 2.1 Menu Structure
**File:** `views/menu.xml`
**Structure:**
```
WooCommerce
├── Connections
├── WooCommerce Products
└── Import Products
```

#### 2.2 Connection Views
**File:** `views/woocommerce_connection_views.xml`
- **List View:** Shows all connections with status
- **Form View:** Connection setup form with test button

#### 2.3 Product Views
**File:** `views/woocommerce_product_views.xml`
- **List View:** Shows WooCommerce products with sync status
- **Form View:** Product details with sync buttons

#### 2.4 Product Template Extension Views
**File:** `views/product_template_views.xml`
- **WooCommerce Tab:** Added to existing product form
- **Sync Fields:** All WooCommerce-related fields
- **Sync Buttons:** Manual sync actions

#### 2.5 Import Wizard Views
**File:** `views/woocommerce_import_wizard_views.xml`
- **Form View:** Import configuration and progress

### 3. Controllers
**File:** `controllers/main.py`
**Purpose:** Basic controller for potential webhooks (currently minimal)

### 4. Security

#### 4.1 Access Rights
**File:** `security/ir.model.access.csv`
**Grants:**
- User access to read WooCommerce data
- Manager access to create/edit/delete
- System admin full access

#### 4.2 Groups
**File:** `security/groups.xml`
**Groups:**
- `woocommerce_integration.group_user`: Basic user access
- `woocommerce_integration.group_manager`: Manager access

### 5. Data Files

#### 5.1 Cron Job
**File:** `data/ir_cron_data.xml`
**Purpose:** Scheduled automatic synchronization
- **Frequency:** Daily
- **Model:** `woocommerce.product`
- **Method:** `_cron_sync_products`

## Data Flow

### 1. Product Import Flow
```
WooCommerce Store → Import Wizard → WooCommerce Product Table → Odoo Product Table
```

### 2. Bidirectional Sync Flow
```
Odoo Product ↔ WooCommerce Product Table ↔ WooCommerce Store
```

### 3. Price Mapping
- **Odoo Sales Price** (`list_price`) → **WooCommerce Sale Price** (`sale_price`)
- **WooCommerce Regular Price** (`regular_price`) → **Normal price** (set separately)

## Key Features

### 1. Bidirectional Synchronization
- Changes in Odoo products sync to WooCommerce
- Changes in WooCommerce product table sync to both WooCommerce store and Odoo
- Automatic sync on field changes
- Manual sync buttons for control

### 2. Price Management
- Correct mapping between Odoo and WooCommerce price fields
- Support for regular prices and promotional prices
- WooCommerce product table acts as intermediary for price data

### 3. Error Handling
- Comprehensive error logging
- User-friendly error messages
- Sync status tracking
- Automatic retry mechanisms

### 4. User Interface
- Integrated WooCommerce tab in product forms
- Sync status indicators
- Manual sync buttons
- Import wizard for bulk operations

## File Structure
```
woocommerce_integration/
├── __init__.py
├── __manifest__.py
├── controllers/
│   ├── __init__.py
│   └── main.py
├── models/
│   ├── __init__.py
│   ├── woocommerce_connection.py
│   ├── woocommerce_product.py
│   ├── product_template.py
│   ├── woocommerce_import_wizard.py
│   ├── woocommerce_conflict_resolution_wizard.py
│   └── res_config_settings.py
├── views/
│   ├── menu.xml
│   ├── woocommerce_connection_views.xml
│   ├── woocommerce_product_views.xml
│   ├── product_template_views.xml
│   ├── woocommerce_import_wizard_views.xml
│   ├── woocommerce_conflict_resolution_wizard_views.xml
│   └── res_config_settings.xml
├── security/
│   ├── ir.model.access.csv
│   └── groups.xml
├── data/
│   └── ir_cron_data.xml
├── static/
│   └── description/
│       └── logo.svg
└── TECHNICAL_DOCUMENTATION.md
```

## API Integration

### WooCommerce REST API Endpoints Used
- `GET /wp-json/wc/v3/products` - Fetch products
- `POST /wp-json/wc/v3/products` - Create product
- `PUT /wp-json/wc/v3/products/{id}` - Update product
- `DELETE /wp-json/wc/v3/products/{id}` - Delete product

### Authentication
- Uses WooCommerce REST API authentication
- Consumer Key and Consumer Secret
- HTTPS required for security

## Configuration

### 1. Module Installation
1. Add module path to `addons_path` in `odoo.conf`
2. Install module from Odoo Apps
3. Configure WooCommerce connection

### 2. WooCommerce Setup
1. Enable WooCommerce REST API
2. Generate Consumer Key and Secret
3. Set proper permissions for API access

### 3. Product Setup
1. Enable WooCommerce sync on products
2. Configure sync direction and options
3. Test synchronization

## Troubleshooting

### Common Issues
1. **400 Bad Request**: Check WooCommerce API data format
2. **Authentication Failed**: Verify Consumer Key/Secret
3. **Sync Errors**: Check connection status and logs
4. **Price Mapping**: Ensure correct field mapping

### Logs
- Check Odoo logs for detailed error information
- WooCommerce API responses logged for debugging
- Sync status tracked in database

## Future Enhancements
1. Image synchronization via WooCommerce media API
2. Category synchronization
3. Inventory synchronization
4. Order synchronization
5. Customer synchronization
6. Webhook support for real-time updates

## Dependencies
- Odoo 18
- Python requests library
- WooCommerce REST API v3
- HTTPS for secure API communication


