# WooCommerce Integration - User Guide

## Quick Start

### 1. Setup WooCommerce Connection
1. Go to **WooCommerce > Connections**
2. Click **Create** to add new connection
3. Fill in connection details:
   - **Name**: Give your connection a name
   - **Store URL**: Your WooCommerce store URL (e.g., https://yourstore.com)
   - **Consumer Key**: WooCommerce API consumer key
   - **Consumer Secret**: WooCommerce API consumer secret
4. Click **Test Connection** to verify
5. Save the connection

### 2. Import Products from WooCommerce
1. Go to **WooCommerce > Import Products**
2. Select your **WooCommerce Connection**
3. Set **Import Limit** (start with 10 for testing)
4. Check **Import Images** if needed
5. Check **Overwrite Existing** to update existing products
6. Click **Start Import**
7. Monitor the progress and logs

### 3. Configure Product Sync
1. Open any **Odoo Product**
2. Go to **🛒 WooCommerce** tab
3. Enable **🔄 Enable WooCommerce Sync**
4. Select **WooCommerce Connection**
5. Choose **🔄 Sync Direction**:
   - **Odoo to WooCommerce**: Changes in Odoo sync to WooCommerce
   - **WooCommerce to Odoo**: Changes in WooCommerce sync to Odoo
6. Enable **⚡ Auto Sync on Changes** for automatic sync
7. Enable **📷 Include Images** if needed
8. Save the product

## Daily Operations

### Syncing Products
- **Automatic**: Changes sync automatically if auto-sync is enabled
- **Manual**: Use **Sync to WooCommerce** button in product form
- **Bulk**: Select multiple products and use batch actions

### Managing WooCommerce Products
1. Go to **WooCommerce > WooCommerce Products**
2. View all imported products with sync status
3. Edit products directly in the table
4. Use **Sync to WooCommerce** button to update the store
5. Monitor sync status and errors

### Price Management
- **Odoo Sales Price** = **WooCommerce Sale Price** (promotional price)
- **WooCommerce Regular Price** = Normal price (set separately)
- Update prices in either system and they sync automatically

## Troubleshooting

### Common Issues

#### Connection Problems
- **Error**: "Connection failed"
- **Solution**: Check store URL, consumer key, and secret
- **Check**: Ensure WooCommerce REST API is enabled

#### Sync Errors
- **Error**: "Sync failed"
- **Solution**: Check the error message in the product's WooCommerce tab
- **Check**: Verify product has required fields (name, price)

#### Price Not Syncing
- **Issue**: Prices not updating correctly
- **Solution**: Check price mapping in WooCommerce product table
- **Check**: Ensure regular_price and sale_price are set correctly

### Getting Help
1. Check **Sync Status** in product forms
2. Review **Last Error** messages
3. Check Odoo logs for detailed error information
4. Test individual sync operations

## Best Practices

### Setup
1. Start with a small import (10 products) to test
2. Verify sync works before importing all products
3. Set up connections with proper permissions
4. Enable auto-sync only after testing manual sync

### Maintenance
1. Monitor sync status regularly
2. Check error logs weekly
3. Update API credentials when needed
4. Test connections periodically

### Data Management
1. Keep product names consistent between systems
2. Use SKUs for better product identification
3. Set up proper price structures (regular vs sale prices)
4. Regular backup of sync configurations

## Features Overview

### Automatic Sync
- Changes in Odoo products sync to WooCommerce automatically
- Changes in WooCommerce product table sync to both systems
- Real-time synchronization with error handling

### Manual Controls
- Manual sync buttons for control
- Bulk sync operations
- Import wizard for initial setup

### Error Handling
- User-friendly error messages
- Sync status tracking
- Automatic retry mechanisms
- Detailed logging for troubleshooting

### Price Management
- Correct price mapping between systems
- Support for regular and promotional prices
- WooCommerce product table as price source of truth

## Advanced Features

### Batch Operations
- Import multiple products at once
- Bulk sync operations
- Mass update capabilities

### Status Monitoring
- Real-time sync status indicators
- Error tracking and reporting
- Last sync timestamps

### Flexible Configuration
- Per-product sync settings
- Directional sync control
- Image sync options
- Auto-sync toggles


