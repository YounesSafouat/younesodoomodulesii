/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { DocumentsDetailsPanel } from "@documents/components/documents_details_panel/documents_details_panel";
import { CharField } from "@web/views/fields/char/char_field";

/**
 * Extends DocumentsDetailsPanel to add Archive Placement field and manual QR extraction.
 * 
 * This patch adds:
 * - Archive Placement field display in the document details panel
 * - Manual QR code extraction button
 * - Integration with the backend action_extract_qr_code method
 */
patch(DocumentsDetailsPanel.prototype, {
    setup() {
        super.setup(...arguments);
        // Register CharField component for Archive Placement field display
        this.constructor.components = {
            ...this.constructor.components,
            CharField,
        };
    },
    
    /**
     * Manually trigger QR code extraction from the document details panel.
     * 
     * Calls the backend action_extract_qr_code method, reloads the record,
     * and displays appropriate notifications based on the result.
     */
    async onExtractQrCode() {
        if (!this.record || !this.record.data) {
            return;
        }
        
        const documentId = this.record.data.id;
        if (!documentId) {
            return;
        }
        
        try {
            const result = await this.orm.call(
                'documents.document',
                'action_extract_qr_code',
                [[documentId]],
            );
            
            await this.record.load();
            
            if (result === true) {
                this.env.services.notification.add(
                    "QR code extracted successfully! Check the Archive Placement field.",
                    { type: 'success' }
                );
            } else {
                this.env.services.notification.add(
                    "No QR code found in this document. Make sure the document contains a QR code.",
                    { type: 'warning' }
                );
            }
        } catch (error) {
            const errorMessage = error.message || error.data?.message || error.data?.debug || "Unknown error";
            this.env.services.notification.add(
                `Error extracting QR code: ${errorMessage}`,
                { type: 'danger' }
            );
        }
    },
});

