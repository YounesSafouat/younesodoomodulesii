# BlackswanTechnology - Odoo Custom Modules

This repository contains custom Odoo modules for BlackswanTechnology business operations.

## Modules

- **woocommerce_integration** - WooCommerce bidirectional sync integration
- **stripe_integration** - Integration with Stripe payment gateway
- **yousign_integration** - YouSign electronic signature integration

---

## WooCommerce & WordPress Credentials

### WordPress Media Upload Authentication

**Store URL**: `https://wizardly-bhaskara.212-227-28-148.plesk.page`

**WordPress Username**: `contact_di6f68ul` (or your WordPress admin username)

**WordPress Application Password**: `pu4d vejb i7eI 0ABY U1YK 7PE7`

> **Note**: WordPress Application Passwords are used for REST API authentication to upload images to the WordPress media library.

### WooCommerce API Credentials

**Consumer Key**: `ck_4c5afbb20a70c2ced69e7e98882a5d8e079b9f06`

**Consumer Secret**: `cs_34150c97ca6052a2c6433cb544661a6aeec6a8ad`

**API Version**: `v3`

> **Note**: To get WooCommerce API credentials:
> 1. Go to WooCommerce > Settings > Advanced > REST API
> 2. Click "Add key"
> 3. Set permissions to "Read/Write"
> 4. Copy the Consumer Key and Consumer Secret

---

## Setup Instructions

### 1. WooCommerce Integration Setup

1. **Configure Connection**:
   - Go to Odoo > WooCommerce > Connections
   - Create a new connection
   - Fill in the store URL and WooCommerce API credentials
   - Fill in WordPress username and application password (for image upload)
   - Click "Test Connection"

2. **Import Products**:
   - Go to Connections
   - Click "Import Products"
   - Configure import settings
   - Click "Import"

3. **Sync Products**:
   - Products can be synced bidirectionally (Odoo ↔ WooCommerce)
   - Updates in Odoo will sync to WooCommerce
   - Updates in WooCommerce can be imported to Odoo

### 2. Image Management

#### Product Images Features

- **Multiple Images**: Each product supports multiple images with custom sequencing
- **Image Sources**: 
  - Import from WooCommerce (URLs stored, can be downloaded on demand)
  - Upload directly in Odoo
  - Sync from Odoo to WooCommerce

#### Image Import Process

During product import from WooCommerce:
- **Automatic Download**: Images are automatically downloaded from WooCommerce
- **Smart Naming**: Images are named using:
  - Alt text from WooCommerce (if available)
  - Or image name from WooCommerce
  - Or auto-generated name: "Product Name - Image 1"
- **Sequence Preserved**: Image order from WooCommerce is automatically maintained
  - First image: sequence 10
  - Second image: sequence 20
  - And so on...
- **Robust Download**:
  - 60-second timeout per image
  - Automatic retry (up to 3 attempts) on timeout or network errors
  - Size limit: 10 MB maximum per image
  - If download fails after retries, it's marked as 'error' without stopping the import

#### Image Upload to WooCommerce

To sync images TO WooCommerce:
1. Ensure WordPress credentials are configured in the connection
2. Open a WooCommerce product in Odoo
3. Go to the "Images" tab
4. For each image, click "Sync to WooCommerce"
   - This uploads the image to WordPress Media Library
   - Then associates it with the WooCommerce product

**Requirements**:
- WordPress Application Password is required for image upload
- Images are uploaded via WordPress REST API (`/wp-json/wp/v2/media`)

**✅ FIXED (Oct 16, 2025)**: Images now correctly attach to WooCommerce products! See `IMAGE_UPLOAD_FIX.md` for details.

**Two Upload Methods Available:**
1. **WordPress Media Library** (Recommended) - More reliable, requires WP credentials
2. **WooCommerce Base64** (Simpler) - No WP auth needed, direct upload via WooCommerce API

#### Image Sync Status

Each image has a sync status:
- **Pending**: Image URL stored, not yet uploaded to WooCommerce
- **Synced**: Image successfully synced with WooCommerce
- **Error**: Sync failed (check error message)

#### Managing Images

1. **View Images**: Open WooCommerce Product > Images tab
2. **Change Image Order**: Edit the sequence number (lower numbers appear first)
   - Sequence 10 = First image
   - Sequence 20 = Second image
   - Use increments of 10 to allow easy reordering
3. **Manual Download** (if needed): Click "Download from WooCommerce" button for images that failed during import
4. **Upload to WooCommerce**: Click "Sync to WooCommerce" button to upload Odoo images to WooCommerce
5. **Bulk Sync**: Use "Sync Product and Images" to sync all product images at once
6. **Edit Image Names**: You can rename images after import for better organization

---

## Troubleshooting

### Image Import Issues

If images fail to download during import:

1. **Check Image Sync Status**: Open WooCommerce Product > Images tab
   - **Pending**: Image needs to be downloaded manually
   - **Error**: Check the error message field for details

2. **Common Issues**:
   - **Timeout errors**: Large images or slow connection
     - Solution: Use "Download from WooCommerce" button to retry manually
   - **Image too large**: Files over 10 MB
     - Solution: Reduce image size in WooCommerce first
   - **Network errors**: Connection interrupted
     - Solution: Check internet connection and retry import

3. **Manual Download**: 
   - Open product > Images tab
   - Click "Download from WooCommerce" for failed images
   - Each image will retry with the same robust logic (3 attempts, 60s timeout)

### WordPress Authentication Issues

If you get "401 Unauthorized" errors when uploading images:

1. **Check WordPress Application Password**:
   - Go to WordPress Admin > Users > Your Profile
   - Scroll to "Application Passwords" section
   - Create a new application password
   - Copy the password (format: `xxxx xxxx xxxx xxxx xxxx xxxx`)
   - Paste it in Odoo WooCommerce connection settings

2. **Verify User Permissions**:
   - WordPress user must have "Editor" or "Administrator" role
   - User must have permission to upload media

3. **Test WordPress Authentication**:
   - In Odoo, go to WooCommerce > Connections
   - Open your connection
   - Click "Test WordPress Auth" button
   - This will verify if authentication is working

4. **Common Issues**:
   - **Wrong username**: Use WordPress username, not email
   - **Expired password**: Application passwords can expire
   - **Wrong format**: Must include spaces (xxxx xxxx xxxx xxxx xxxx xxxx)
   - **Insufficient permissions**: User needs media upload rights

### Connection Timeouts

If you experience frequent timeouts:
- Increase timeout in code (currently 60 seconds)
- Check server internet connection speed
- Consider importing products in smaller batches (set import limit)
- Review WooCommerce server response time

---

## Security Notes

⚠️ **IMPORTANT**: This file contains sensitive credentials. 

- **DO NOT** commit this file to public repositories
- **DO NOT** share these credentials publicly
- **ROTATE** credentials regularly
- Add `README.md` to `.gitignore` if it contains credentials

---

## Support

For issues or questions about these modules, contact the development team.
