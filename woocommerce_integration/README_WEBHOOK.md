# WooCommerce Order Webhook Integration

## Overview

This functionality allows WooCommerce to automatically send order data to Odoo when customers place orders, creating corresponding sale orders in Odoo with detailed product information, quantities, and customer data.

## Features

### 🚀 **Automatic Order Creation**
- **Real-time order processing**: Orders are created in Odoo immediately when placed in WooCommerce
- **Detailed product information**: Includes product names, quantities, prices, and SKUs
- **Customer management**: Automatically creates or updates customer records
- **Shipping and fees**: Handles shipping costs and additional fees
- **Tax handling**: Processes tax information from WooCommerce

### 🔧 **Webhook Configuration**
- **Multiple webhook topics**: Support for order.created, order.updated, order.paid, etc.
- **Security**: Webhook signature verification for secure data transmission
- **Logging**: Complete webhook activity logging for debugging and monitoring
- **Auto-configuration**: Easy webhook setup with automatic URL generation

### 📊 **Order Data Mapping**
- **Product synchronization**: Maps WooCommerce products to Odoo products by SKU, name, or WooCommerce ID
- **Customer data**: Maps billing information to Odoo customer records
- **Order details**: Preserves order numbers, payment methods, and shipping information
- **Custom attributes**: Handles custom product attributes and variations

## Setup Instructions

### 1. Create WooCommerce Connection
1. Go to **WooCommerce Integration > Connections**
2. Create a new connection with your WooCommerce store details
3. Test the connection to ensure it's working

### 2. Create Order Webhook
1. In your WooCommerce connection, click **"Create Order Webhook"**
2. The system will automatically generate a webhook URL
3. Configure webhook settings:
   - **Auto Create Odoo Order**: Enable to automatically create orders
   - **Auto Create Customer**: Enable to automatically create customers
   - **Order Prefix**: Set prefix for Odoo order names (default: WC-)

### 3. Configure WooCommerce Webhook
1. In your WooCommerce admin, go to **WooCommerce > Settings > Advanced > Webhooks**
2. Create a new webhook with these settings:
   - **Name**: Order to Odoo
   - **Status**: Active
   - **Topic**: Order created
   - **Delivery URL**: Copy the webhook URL from Odoo
   - **Secret**: Set a secret key for security (optional but recommended)

### 4. Test the Integration
1. Place a test order in your WooCommerce store
2. Check the webhook logs in Odoo to see if the order was processed
3. Verify that a sale order was created in Odoo with the correct details

## Webhook URL Format

The webhook URL follows this format:
```
https://your-odoo-instance.com/woocommerce/webhook/{webhook_id}
```

## Data Flow

1. **Customer places order** in WooCommerce
2. **WooCommerce sends webhook** to Odoo with order data
3. **Odoo receives webhook** and validates the data
4. **Customer is created/updated** in Odoo if needed
5. **Sale order is created** with all order details
6. **Order lines are added** with product information
7. **Shipping and fees are processed** as additional order lines
8. **Webhook log is created** for tracking and debugging

## Supported Order Data

### Customer Information
- First name and last name
- Email address
- Phone number
- Billing address (street, city, state, country, postal code)

### Product Information
- Product name and SKU
- Quantity ordered
- Unit price
- Product variations and attributes

### Order Details
- Order number and key
- Order date
- Payment method
- Shipping method
- Shipping costs
- Additional fees
- Tax information

## Troubleshooting

### Common Issues

1. **Webhook not receiving data**
   - Check if the webhook URL is correct
   - Verify that the webhook is active in WooCommerce
   - Check webhook logs in Odoo for error messages

2. **Products not found**
   - Ensure products are synchronized between WooCommerce and Odoo
   - Check if SKUs match between systems
   - Verify product names are identical

3. **Customer creation issues**
   - Check if auto-create customer is enabled
   - Verify billing information is complete
   - Check for duplicate email addresses

### Webhook Logs

All webhook activity is logged in **WooCommerce Integration > Webhook Logs**. This includes:
- Raw webhook data received
- Processing status (success/error)
- Error messages and details
- Created Odoo order references

## Security

- **Webhook signature verification**: Optional but recommended for secure data transmission
- **Public endpoint**: Webhook endpoint is public but protected by signature verification
- **Data validation**: All incoming data is validated before processing
- **Error handling**: Comprehensive error handling prevents system crashes

## Customization

The webhook system is designed to be extensible. You can:
- Add custom order processing logic
- Modify customer creation rules
- Customize product mapping logic
- Add additional order line types
- Implement custom validation rules

## Support

For issues or questions about the webhook integration:
1. Check the webhook logs for error messages
2. Verify WooCommerce webhook configuration
3. Test the connection between WooCommerce and Odoo
4. Review the order data mapping settings
