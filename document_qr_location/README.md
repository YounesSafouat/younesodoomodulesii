# Document QR Location Module

## Overview

The Document QR Location module extends Odoo's Documents app to automatically extract QR codes from uploaded documents (images or PDFs) and store the archive placement information in a dedicated field. This module is designed to streamline document archival processes by automatically reading QR codes typically placed at the bottom of documents.

## Features

- **Automatic QR Code Extraction**: Automatically detects and extracts QR codes when documents are uploaded
- **Multi-Format Support**: Works with both image files (PNG, JPG, JPEG, GIF, BMP, TIFF) and PDF files
- **Multi-Page PDF Support**: Processes all pages of PDF documents, checking from the last page first (where QR codes are typically located)
- **Non-Blocking**: Document upload continues even if no QR code is found
- **Manual Extraction**: Provides a button to manually trigger QR code extraction
- **User-Friendly Interface**: Archive placement field is visible in both the form view and the document details panel
- **Error Handling**: Robust error handling ensures the module doesn't break document uploads

## Installation

### System Dependencies

1. **libzbar0** (for QR code detection):
   ```bash
   sudo apt-get update
   sudo apt-get install libzbar0
   ```

2. **poppler-utils** (for PDF to image conversion):
   ```bash
   sudo apt-get install poppler-utils
   ```

### Python Dependencies

Install the required Python packages in Odoo's Python environment:

```bash
pip3 install pyzbar pdf2image Pillow --break-system-packages
```

**Note**: The `--break-system-packages` flag may be required depending on your Python installation. If using a virtual environment, omit this flag.

### Module Installation

1. Copy the module to your Odoo addons path (e.g., `YounesModules/document_qr_location`)
2. Update the apps list in Odoo
3. Search for "Document QR Location" in the Apps menu
4. Click "Install"

## Module Structure

```
document_qr_location/
├── __init__.py
├── __manifest__.py
├── README.md
├── requirements.txt
├── models/
│   ├── __init__.py
│   └── document_qr.py          # Main model extending documents.document
├── views/
│   └── document_view.xml        # Form view extension
├── static/
│   └── src/
│       └── components/
│           ├── documents_details_panel.js    # JavaScript extension for sidebar
│           └── documents_details_panel.xml   # XML template for sidebar
└── security/
    └── ir.model.access.csv      # Access rights
```

## How It Works

### Architecture

The module extends Odoo's `documents.document` model to add QR code extraction functionality. It consists of three main components:

1. **Backend Model** (`models/document_qr.py`): Extends `documents.document` with QR code extraction logic
2. **Frontend View** (`views/document_view.xml`): Adds the Archive Placement field to the document form view
3. **Frontend Component** (`static/src/components/`): Extends the document details panel to show the Archive Placement field in the sidebar

### QR Code Extraction Process

#### Automatic Extraction

1. **Document Upload**: When a document is uploaded, the `create()` method is triggered
2. **File Type Detection**: The module checks the file's MIME type or extension to determine if it's a PDF or image
3. **Data Extraction**:
   - **For Images**: The raw image data is passed directly to the QR code decoder
   - **For PDFs**: The PDF is converted to images (one per page) using `pdf2image`, then each page is processed
4. **QR Code Detection**: The `pyzbar` library scans the image(s) for QR codes
5. **Text Extraction**: If a QR code is found, its text content is extracted
6. **Storage**: The extracted text is stored in the `x_archive_location` field

#### Manual Extraction

Users can manually trigger QR code extraction by:
1. Clicking the "Extract QR Code" button in the document form view header
2. Clicking the "Extract QR" button in the document details panel (right sidebar)

### Technical Details

#### Data Handling

- **Binary Field Access**: Odoo's `Binary` field returns bytes when accessed via ORM, not base64-encoded strings. The module handles both cases:
  - If `raw_data` is bytes: Uses it directly
  - If `raw_data` is a string: Decodes it as base64 (handles padding issues)

#### PDF Processing

- **Multi-Page Support**: Processes all pages of a PDF document
- **Reverse Order Processing**: Checks pages from last to first (more efficient since QR codes are typically on the last page)
- **DPI Optimization**: Uses 200 DPI for initial conversion, falls back to 150 DPI if needed
- **Error Handling**: Handles corrupted PDFs and conversion errors gracefully

#### Image Processing

- **Format Conversion**: Automatically converts images to RGB format (required by pyzbar)
- **Multiple Format Support**: Supports PNG, JPG, JPEG, GIF, BMP, TIFF
- **QR Code Filtering**: Only extracts QR codes (filters out other barcode types)

#### Recursion Prevention

- **Context Flag**: Uses `skip_qr_extraction` context flag to prevent infinite recursion when updating `x_archive_location`
- **Write Method Override**: Checks if `x_archive_location` is being set by the user to avoid overriding manual entries

### Field Behavior

- **Automatic Population**: Automatically populated when a QR code is detected
- **Manual Editing**: Users can manually edit the field if needed
- **Read-Only When Locked**: Field becomes read-only when the document is locked
- **Non-Blocking**: Document upload/update continues even if QR extraction fails

## Usage

### Automatic Extraction

1. Upload a document (image or PDF) with a QR code
2. The Archive Placement field will be automatically populated if a QR code is found
3. If no QR code is found, the field remains empty

### Manual Extraction

1. Open a document in the Documents app
2. In the form view, click the "Extract QR Code" button in the header
3. OR in the document details panel (right sidebar), click the "Extract QR" button
4. A notification will appear indicating success or failure
5. If successful, the Archive Placement field will be updated

### Viewing Archive Placement

The Archive Placement field is visible in:
- **Document Form View**: Below the Folder field
- **Document Details Panel**: In the right sidebar when viewing a document (below Tags)

## Configuration

No configuration is required. The module works out of the box after installation.

## Troubleshooting

### QR Code Not Detected

- **Check QR Code Quality**: Ensure the QR code is clear and not damaged
- **Check QR Code Size**: Very small QR codes may not be detected
- **Check PDF Quality**: Low-quality PDFs may not convert properly
- **Check Dependencies**: Ensure `pyzbar` and `pdf2image` are installed correctly

### PDF Conversion Errors

- **Check poppler-utils**: Ensure `poppler-utils` is installed
- **Check PDF Integrity**: The PDF may be corrupted
- **Check Logs**: Review Odoo logs for detailed error messages

### Module Not Working

- **Check Dependencies**: Verify all Python packages are installed
- **Check System Libraries**: Ensure `libzbar0` is installed
- **Restart Odoo**: Restart Odoo after installing dependencies
- **Upgrade Module**: Try upgrading the module in the Apps menu
- **Check Logs**: Review Odoo logs for error messages

## Dependencies

### Python Packages

- **pyzbar**: QR code and barcode detection library
- **pdf2image**: PDF to image conversion
- **Pillow**: Image processing library

### System Libraries

- **libzbar0**: ZBar library for barcode/QR code detection
- **poppler-utils**: PDF rendering utilities

### Odoo Modules

- **documents**: Odoo Documents app (base module)

## Compatibility

- **Odoo Version**: 18.0
- **Python Version**: 3.8+
- **Operating System**: Linux (Ubuntu/Debian recommended)

## License

LGPL-3

## Author

Blackswantechnology
Website: https://agence-blackswan.com/

## Support

For issues or questions, please contact the module author or check the Odoo logs for detailed error messages.

## Changelog

### Version 1.0.0
- Initial release
- Automatic QR code extraction on document upload
- Manual QR code extraction via button
- Support for images and PDFs
- Multi-page PDF support
- Archive Placement field in form view and details panel

