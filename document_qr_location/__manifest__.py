# -*- coding: utf-8 -*-
{
    'name': "Document QR Location",
    
    'summary': "Automatically extract QR codes from documents for archive placement",
    
    'description': """
Document QR Location Module
===========================

Automatically extracts QR codes from uploaded documents (images or PDFs) and stores
the archive placement information in a dedicated field.

Key Features:
-------------
* Automatic QR code extraction on document upload
* Support for image files (PNG, JPG, JPEG, GIF, BMP, TIFF)
* Support for multi-page PDF files
* Manual QR code extraction via button
* Archive placement field in form view and details panel
* Non-blocking: document upload continues even if QR extraction fails

Requirements:
-------------
* pyzbar - QR code detection library
* pdf2image - PDF to image conversion
* Pillow - Image processing library
* libzbar0 - System library for barcode detection
* poppler-utils - System utilities for PDF processing

See README.md for detailed installation and usage instructions.
    """,
    
    'author': "Blackswantechnology",
    'website': "https://agence-blackswan.com/",
    
    'category': 'Documents',
    'version': '1.0.0',
    
    # Dependencies
    'depends': ['documents'],
    
    # Assets
    'assets': {
        'web.assets_backend': [
            'document_qr_location/static/src/components/*.xml',
            'document_qr_location/static/src/components/*.js',
        ],
    },
    
    # Data files
    'data': [
        'security/ir.model.access.csv',
        'views/document_view.xml',
    ],
    
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}

