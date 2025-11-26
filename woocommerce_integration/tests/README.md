# WooCommerce Integration - Unit Tests

This directory contains unit tests for the WooCommerce Integration module.

## Test Structure

- `test_woocommerce_connection.py` - Tests for WooCommerce connection management
- `test_woocommerce_product.py` - Tests for WooCommerce product synchronization
- `test_woocommerce_webhook.py` - Tests for webhook handling
- `test_woocommerce_import_wizard.py` - Tests for import wizard functionality

## Running Tests

To run all tests:
```bash
python3 odoo/odoo-bin -c odoo.conf --test-enable --stop-after-init -d your_database -u woocommerce_integration
```

Or if odoo-bin is in your PATH:
```bash
./odoo/odoo-bin -c odoo.conf --test-enable --stop-after-init -d your_database -u woocommerce_integration
```

To run specific test file:
```bash
python3 odoo/odoo-bin -c odoo.conf --test-enable --stop-after-init -d your_database -u woocommerce_integration --test-tags=woocommerce_integration.test_woocommerce_connection
```

## Test Coverage

### Connection Tests
- Connection creation and validation
- API URL generation
- Authentication headers
- Connection testing (success/failure scenarios)
- Product fetching
- Category fetching
- Product creation and updates

### Product Tests
- Product creation from WooCommerce data
- Data formatting and computation
- Variable product detection
- Image count computation
- Sync operations

### Webhook Tests
- GET request handling
- POST request handling
- Inactive webhook handling
- Invalid JSON handling
- Signature verification

### Import Wizard Tests
- Wizard creation and configuration
- Batch size computation
- Progress tracking
- Import settings validation

## Notes

- Tests use mocking to avoid actual API calls
- All tests use TransactionCase for database transactions
- Webhook tests use HttpCase for HTTP request testing

