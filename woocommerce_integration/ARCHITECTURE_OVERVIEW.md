# WooCommerce Integration - Architecture Overview

## System Architecture

```
┌─────────────────┐    ┌──────────────────────┐    ┌─────────────────┐
│   Odoo 18       │    │  WooCommerce Product │    │  WooCommerce    │
│   Products      │◄──►│  Table (Local)       │◄──►│  Store (API)    │
└─────────────────┘    └──────────────────────┘    └─────────────────┘
```

## Data Flow Diagram

### 1. Import Flow
```
WooCommerce Store API
        ↓ (GET /products)
Import Wizard
        ↓ (Create records)
WooCommerce Product Table
        ↓ (Link)
Odoo Product Table
```

### 2. Bidirectional Sync Flow
```
Odoo Product Changes
        ↓ (Auto-sync enabled)
WooCommerce Product Table
        ↓ (Update)
WooCommerce Store API
        ↓ (PUT /products/{id})

WooCommerce Product Table Changes
        ↓ (Write method override)
WooCommerce Store API (PUT)
        ↓ (Update)
Odoo Product (if linked)
```

## Model Relationships

### WooCommerce Connection
```
woocommerce.connection
├── name (Char)
├── store_url (Char)
├── consumer_key (Char)
├── consumer_secret (Char)
├── status (Selection)
└── connection_test_result (Text)
```

### WooCommerce Product
```
woocommerce.product
├── wc_product_id (Integer) - WooCommerce ID
├── name (Char) - Product name
├── wc_sku (Char) - SKU
├── price (Float) - Current price
├── regular_price (Float) - Regular price
├── sale_price (Float) - Sale price
├── status (Selection) - draft/publish
├── sync_status (Selection) - pending/synced/error
├── connection_id (Many2one) → woocommerce.connection
├── odoo_product_id (Many2one) → product.template
└── wc_data (Text) - Raw JSON data
```

### Product Template Extension
```
product.template (Extended)
├── wc_connection_id (Many2one) → woocommerce.connection
├── wc_product_id (Integer) - WooCommerce product ID
├── wc_sync_enabled (Boolean) - Enable sync
├── wc_auto_sync (Boolean) - Auto-sync on changes
├── wc_sync_direction (Selection) - Sync direction
├── wc_image_sync_enabled (Boolean) - Include images
├── wc_sync_status (Selection) - Sync status
├── wc_last_sync (Datetime) - Last sync time
└── wc_last_error (Text) - Last error message
```

## View Structure

### Menu Hierarchy
```
WooCommerce (Main Menu)
├── Connections
│   ├── List View (woocommerce.connection)
│   └── Form View (Connection setup)
├── WooCommerce Products
│   ├── List View (woocommerce.product)
│   └── Form View (Product details + sync buttons)
└── Import Products
    └── Wizard Form (Import configuration)
```

### Product Template Integration
```
Product Template Form (Extended)
├── General Information (Existing)
├── Sales (Existing)
├── Inventory (Existing)
└── 🛒 WooCommerce (New Tab)
    ├── Connection Settings
    ├── Sync Configuration
    ├── Sync Status
    └── Manual Actions
```

## API Integration Points

### WooCommerce REST API Endpoints
```
Base URL: {store_url}/wp-json/wc/v3/

GET    /products              - Fetch products
POST   /products              - Create product
PUT    /products/{id}         - Update product
DELETE /products/{id}         - Delete product
```

### Authentication Flow
```
1. Consumer Key + Secret → HTTP Basic Auth
2. HTTPS Required
3. API Version: v3
4. Rate Limiting: WooCommerce default
```

## Sync Logic

### Price Mapping Logic
```
Odoo Sales Price (list_price)
        ↓
WooCommerce Sale Price (sale_price)
        ↓
WooCommerce Regular Price (regular_price) - Set separately
```

### Sync Triggers
```
Odoo Product Write:
├── wc_sync_enabled = True
├── wc_auto_sync = True
├── Field changed in sync_fields
└── → Trigger WooCommerce sync

WooCommerce Product Write:
├── Field changed in sync_fields
├── connection_id exists
├── wc_product_id exists
└── → Trigger bidirectional sync
```

### Sync Fields
```
Odoo → WooCommerce:
├── name
├── list_price
├── default_code
├── description
├── description_sale
├── sale_ok
└── image_1920 (if enabled)

WooCommerce → Odoo:
├── name
├── sale_price
├── regular_price
├── wc_sku
├── status
└── wc_data
```

## Error Handling

### Error Types
```
1. API Connection Errors
   ├── Authentication failed
   ├── Network timeout
   └── Invalid endpoint

2. Data Validation Errors
   ├── Invalid price format
   ├── Missing required fields
   └── Invalid product type

3. Sync Errors
   ├── Circular sync prevention
   ├── Transaction conflicts
   └── Field mapping errors
```

### Error Recovery
```
1. Log error details
2. Update sync_status = 'error'
3. Store error message
4. Show user notification
5. Allow manual retry
```

## Security Implementation

### Access Control
```
User Groups:
├── woocommerce_integration.group_user
│   ├── Read access to WooCommerce data
│   └── Basic sync operations
└── woocommerce_integration.group_manager
    ├── Full CRUD access
    ├── Connection management
    └── Advanced sync configuration
```

### Data Protection
```
1. API credentials encrypted in database
2. HTTPS required for API communication
3. Input validation on all fields
4. SQL injection prevention
5. XSS protection in views
```

## Performance Considerations

### Optimization Strategies
```
1. Batch Operations
   ├── Import multiple products at once
   ├── Bulk sync operations
   └── Efficient database queries

2. Caching
   ├── Connection status caching
   ├── API response caching
   └── Sync status caching

3. Background Processing
   ├── Cron jobs for automatic sync
   ├── Queue system for large operations
   └── Async API calls
```

## Deployment Checklist

### Pre-Installation
```
1. Odoo 18 compatibility
2. Python requests library
3. WooCommerce store with REST API enabled
4. Valid SSL certificate for store
5. API credentials generated
```

### Installation Steps
```
1. Add module path to odoo.conf
2. Install module from Apps
3. Configure WooCommerce connection
4. Test API connectivity
5. Import sample products
6. Configure sync settings
7. Test bidirectional sync
```

### Post-Installation
```
1. Set up cron jobs
2. Configure user permissions
3. Train users on sync operations
4. Monitor sync logs
5. Set up error notifications
```

## Maintenance

### Regular Tasks
```
1. Monitor sync status
2. Check error logs
3. Update API credentials if needed
4. Test connection periodically
5. Backup sync configurations
```

### Troubleshooting
```
1. Check Odoo logs
2. Verify API connectivity
3. Validate data formats
4. Test individual sync operations
5. Review error messages
```


