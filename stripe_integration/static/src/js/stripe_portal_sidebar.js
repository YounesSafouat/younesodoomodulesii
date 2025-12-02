/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.StripePortalSidebar = publicWidget.Widget.extend({
    selector: '.o_portal_sale_sidebar',
    
    /**
     * @override
     */
    start: function () {
        var def = this._super.apply(this, arguments);
        
        // Get the Stripe payment link URL from the main content div
        var quoteContent = this.$('#quote_content');
        var stripePaymentLinkUrl = quoteContent.data('stripe-payment-link-url');
        
        if (stripePaymentLinkUrl) {
            // Update sidebar Pay Now button
            var sidebarButton = this.$('#o_sale_portal_paynow');
            if (sidebarButton.length) {
                sidebarButton.attr('href', stripePaymentLinkUrl);
                sidebarButton.attr('target', '_blank');
                sidebarButton.removeAttr('data-bs-toggle');
                sidebarButton.removeAttr('data-bs-target');
                sidebarButton.off('click'); // Remove any click handlers
            }
            
            // Update bottom Pay Now button
            var bottomButton = this.$('div[name="sale_order_actions"] a[data-bs-target="#modalaccept"]');
            if (bottomButton.length && !bottomButton.closest('t[t-if="sale_order._has_to_be_signed()"]').length) {
                bottomButton.attr('href', stripePaymentLinkUrl);
                bottomButton.attr('target', '_blank');
                bottomButton.removeAttr('data-bs-toggle');
                bottomButton.removeAttr('data-bs-target');
                bottomButton.off('click'); // Remove any click handlers
            }
        }
        
        return def;
    },
});

