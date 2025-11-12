# -*- coding: utf-8 -*-

import base64
import io
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Import QR code detection library (pyzbar)
try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    from PIL import Image
    PYZBAR_AVAILABLE = True
except ImportError:
    PYZBAR_AVAILABLE = False
    _logger.warning("pyzbar library not available. QR code extraction will not work.")

# Import PDF to image conversion library (pdf2image)
try:
    from pdf2image import convert_from_bytes
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    _logger.warning("pdf2image library not available. PDF QR code extraction will not work.")


class Document(models.Model):
    """
    Extends documents.document model to add QR code extraction functionality.
    
    This model adds:
    - x_archive_location field to store extracted QR code text
    - Automatic QR code extraction on document create/write
    - Manual QR code extraction via action_extract_qr_code method
    """
    _inherit = 'documents.document'

    x_archive_location = fields.Char(
        string="Archive Placement",
        help="Archive location extracted from QR code at the bottom of the document"
    )
    
    def action_extract_qr_code(self):
        """
        Manually extract QR code from document.
        
        This method can be called from:
        - Form view button
        - Document details panel button
        
        Returns:
            bool: True if QR code was found and extracted, False otherwise
            
        Raises:
            UserError: If no file data is available or extraction fails
        """
        for document in self:
            if not document.raw and not (document.attachment_id and document.attachment_id.raw):
                raise UserError(_("No file data available for this document."))
            
            try:
                qr_text = document._extract_qr_code_from_document()
                if qr_text:
                    document.with_context(skip_qr_extraction=True).write({'x_archive_location': qr_text})
                    _logger.info("QR code extracted successfully for document %s: %s", document.id, qr_text)
                    return True
                else:
                    _logger.info("No QR code found in document %s", document.id)
                    return False
            except Exception as e:
                _logger.error("Error extracting QR code for document %s: %s", document.id, str(e))
                raise UserError(_("Error extracting QR code: %s") % str(e))

    def _extract_qr_code_from_image(self, image_data):
        """
        Extract QR code text from image binary data.
        
        Args:
            image_data (bytes): Binary image data
            
        Returns:
            str|False: QR code text if found, False otherwise
        """
        if not PYZBAR_AVAILABLE:
            _logger.warning("pyzbar not available, cannot extract QR code")
            return False
        
        try:
            image = Image.open(io.BytesIO(image_data))
            
            # pyzbar requires RGB format
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            decoded_objects = pyzbar_decode(image)
            
            if decoded_objects:
                for obj in decoded_objects:
                    if obj.type == 'QRCODE':
                        qr_text = obj.data.decode('utf-8')
                        _logger.info("QR code extracted successfully: %s", qr_text)
                        return qr_text
                _logger.debug("Found barcodes but no QR code in image")
                return False
            else:
                _logger.debug("No QR code found in image")
                return False
                
        except Exception as e:
            _logger.error("Error extracting QR code from image: %s", str(e))
            return False

    def _extract_qr_code_from_pdf(self, pdf_data):
        """
        Extract QR code text from PDF binary data.
        
        Processes all pages of the PDF, checking from last page first since QR codes
        are typically located at the bottom of documents. Uses progressive DPI reduction
        for error handling.
        
        Args:
            pdf_data (bytes): Binary PDF data
            
        Returns:
            str|False: QR code text if found, False otherwise
        """
        if not PDF2IMAGE_AVAILABLE:
            _logger.warning("pdf2image not available, cannot extract QR code from PDF")
            return False
        
        try:
            if not pdf_data or len(pdf_data) < 4:
                _logger.warning("Invalid PDF data: too short or empty")
                return False
            
            if not pdf_data.startswith(b'%PDF'):
                _logger.debug("File does not appear to start with %PDF header, but trying to process anyway")
            
            # Convert PDF pages to images with progressive DPI reduction for error handling
            images = None
            try:
                images = convert_from_bytes(pdf_data, dpi=200, strict=False)
            except Exception as convert_error:
                _logger.warning("Error converting PDF to image: %s. Trying with lower DPI.", str(convert_error))
                try:
                    images = convert_from_bytes(pdf_data, dpi=150, strict=False)
                except Exception as convert_error2:
                    _logger.warning("Error converting PDF with low DPI: %s. Trying page by page.", str(convert_error2))
                    try:
                        images = convert_from_bytes(pdf_data, first_page=2, last_page=2, dpi=200, strict=False)
                    except Exception:
                        _logger.error("Could not convert PDF to image: %s", str(convert_error))
                        return False
            
            if not images:
                _logger.warning("Could not convert PDF to image - no images returned")
                return False
            
            # Process pages in reverse order (last page first) for efficiency
            for i in range(len(images) - 1, -1, -1):
                image = images[i]
                _logger.debug("Checking page %d of %d for QR code", i + 1, len(images))
                
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)
                
                qr_text = self._extract_qr_code_from_image(img_byte_arr.getvalue())
                if qr_text:
                    _logger.info("QR code found on page %d of %d", i + 1, len(images))
                    return qr_text
            
            _logger.debug("No QR code found in any page of PDF")
            return False
            
        except Exception as e:
            _logger.error("Error extracting QR code from PDF: %s", str(e))
            return False

    def _extract_qr_code_from_document(self):
        """
        Extract QR code from document's raw binary data.
        
        Handles both image and PDF files by:
        1. Retrieving raw data from attachment or document
        2. Processing binary data (handles bytes and base64 strings)
        3. Determining file type from MIME type or extension
        4. Delegating to appropriate extraction method
        
        Returns:
            str|False: QR code text if found, False otherwise
        """
        # Prefer attachment raw data if available
        if self.attachment_id:
            try:
                raw_data = self.attachment_id.raw
                if not raw_data:
                    _logger.debug("No raw data in attachment for document %s", self.id)
                    return False
            except Exception as e:
                _logger.debug("Error reading from attachment_id: %s, trying self.raw", str(e))
                raw_data = self.raw
        else:
            raw_data = self.raw
        
        if not raw_data:
            _logger.debug("No raw data available for document %s", self.id)
            return False
        
        try:
            # Odoo Binary field returns bytes via ORM, handle both bytes and base64 strings
            if isinstance(raw_data, bytes):
                document_data = raw_data
                _logger.debug("Using raw data directly as bytes for document %s", self.id)
            else:
                # Handle base64-encoded strings (e.g., from web API)
                try:
                    document_data = base64.b64decode(raw_data, validate=True)
                    _logger.debug("Decoded base64 string to bytes for document %s", self.id)
                except Exception as decode_error:
                    # Attempt to fix base64 padding issues
                    _logger.debug("Base64 decode error, trying to fix padding: %s", str(decode_error))
                    try:
                        missing_padding = len(raw_data) % 4
                        if missing_padding:
                            raw_data_fixed = raw_data + '=' * (4 - missing_padding)
                        else:
                            raw_data_fixed = raw_data
                        document_data = base64.b64decode(raw_data_fixed, validate=False)
                        _logger.debug("Decoded base64 string (with padding fix) to bytes for document %s", self.id)
                    except Exception as padding_error:
                        _logger.error("Error decoding base64 data for document %s: %s (padding fix also failed: %s)", 
                                    self.id, str(decode_error), str(padding_error))
                        return False
            
            mimetype = self.mimetype or ''
            
            # Route to appropriate extraction method based on file type
            if 'pdf' in mimetype.lower() or (self.file_extension and 'pdf' in self.file_extension.lower()):
                _logger.debug("Processing PDF file for QR code extraction")
                return self._extract_qr_code_from_pdf(document_data)
            
            elif any(img_type in mimetype.lower() for img_type in ['image', 'jpeg', 'jpg', 'png', 'gif', 'bmp']):
                _logger.debug("Processing image file for QR code extraction")
                return self._extract_qr_code_from_image(document_data)
            
            # Fallback to file extension detection if MIME type unavailable
            elif self.file_extension:
                ext = self.file_extension.lower()
                if ext == 'pdf':
                    return self._extract_qr_code_from_pdf(document_data)
                elif ext in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'tif']:
                    return self._extract_qr_code_from_image(document_data)
            
            _logger.debug("Unsupported file type for QR code extraction: %s", mimetype)
            return False
            
        except Exception as e:
            _logger.error("Error processing document for QR code extraction: %s", str(e))
            return False

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create to automatically extract QR code after document creation.
        
        Extracts QR code for documents with raw data, but does not block creation
        if extraction fails. Only extracts if x_archive_location is not already set.
        """
        documents = super().create(vals_list)
        
        for document in documents:
            if document.raw and not document.x_archive_location:
                try:
                    qr_text = document._extract_qr_code_from_document()
                    if qr_text:
                        document.write({'x_archive_location': qr_text})
                except Exception as e:
                    _logger.error("Error extracting QR code during create: %s", str(e))
                    continue
        
        return documents

    def write(self, vals):
        """
        Override write to automatically extract QR code when document file is updated.
        
        Extracts QR code only when:
        - File data is being updated (raw, datas, or attachment_id changed)
        - User has not explicitly set x_archive_location
        - Document has raw data and no existing location
        
        Uses context flag to prevent infinite recursion when updating x_archive_location.
        """
        # Prevent recursion when updating x_archive_location
        if self.env.context.get('skip_qr_extraction'):
            return super().write(vals)
        
        file_updated = 'raw' in vals or 'datas' in vals or 'attachment_id' in vals
        user_set_location = 'x_archive_location' in vals
        
        result = super().write(vals)
        
        if file_updated and not user_set_location:
            for document in self:
                if document.raw and not document.x_archive_location:
                    try:
                        qr_text = document._extract_qr_code_from_document()
                        if qr_text:
                            document.with_context(skip_qr_extraction=True).write({'x_archive_location': qr_text})
                            _logger.info("QR code extracted and saved for document %s: %s", document.id, qr_text)
                    except Exception as e:
                        _logger.error("Error extracting QR code during write: %s", str(e))
                        continue
        
        return result

