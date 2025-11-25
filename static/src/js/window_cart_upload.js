/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.WindowCartUpload = publicWidget.Widget.extend({
    selector: '.oe_website_sale',
    events: {},

    /**
     * @override
     */
    start: function () {
        var self = this;
        // Inject upload block after page loads
        this._injectUploadBlock();
        return this._super.apply(this, arguments);
    },

    /**
     * Inject the upload block into the cart page
     */
    _injectUploadBlock: function () {
        var self = this;
        
        console.log('[Window Cart Upload] Starting injection process');
        console.log('[Window Cart Upload] Current URL:', window.location.pathname);
        
        // Check if we're on the cart page
        if (!window.location.pathname.includes('/shop/cart')) {
            console.log('[Window Cart Upload] Not on cart page, skipping injection');
            return;
        }

        console.log('[Window Cart Upload] On cart page, looking for injection target...');

        // Try to find a good location to inject - cart summary area
        var $cartLines = this.$('#cart_products, .js_cart_lines').first();
        var $oeStructure = this.$('#oe_structure_website_sale_cart_1').first();
        var $cartSummary = this.$('#o_cart_summary, .o_total_card, .o_wsale_cart_summary').first();
        var $checkoutButton = this.$('a[name="website_sale_main_button"]').first();
        
        console.log('[Window Cart Upload] Found elements:');
        console.log('  - Cart Lines:', $cartLines.length, $cartLines.length ? $cartLines[0] : 'not found');
        console.log('  - oe_structure:', $oeStructure.length, $oeStructure.length ? $oeStructure[0] : 'not found');
        console.log('  - Cart Summary:', $cartSummary.length, $cartSummary.length ? $cartSummary[0] : 'not found');
        console.log('  - Checkout Button:', $checkoutButton.length, $checkoutButton.length ? $checkoutButton[0] : 'not found');
        
        // Determine target location
        var $target = null;
        var position = 'before';
        
        if ($cartLines.length) {
            $target = $cartLines;
            position = 'after';
            console.log('[Window Cart Upload] Using cart lines as target (after)');
        } else if ($oeStructure.length) {
            $target = $oeStructure;
            position = 'inside';
            console.log('[Window Cart Upload] Using oe_structure as target (inside)');
        } else if ($cartSummary.length) {
            $target = $cartSummary;
            position = 'inside';
            console.log('[Window Cart Upload] Using cart summary as target (inside)');
        } else if ($checkoutButton.length) {
            $target = $checkoutButton;
            position = 'before';
            console.log('[Window Cart Upload] Using checkout button as target (before)');
        } else {
            // Fallback: try to find any container
            $target = this.$('.oe_cart, .container').first();
            position = 'inside';
            console.log('[Window Cart Upload] Using fallback container as target:', $target.length, $target.length ? $target[0] : 'not found');
        }

        if (!$target || !$target.length) {
            console.error('[Window Cart Upload] Could not find any target element for injection');
            console.log('[Window Cart Upload] Available elements in page:', this.$('*').length);
            return;
        }

        console.log('[Window Cart Upload] Target element found:', $target[0]);
        console.log('[Window Cart Upload] Injection position:', position);
        console.log('[Window Cart Upload] Fetching upload block from server...');

        // Fetch the upload block HTML from server using fetch API
        fetch('/shop/cart/get_upload_block')
            .then(function (response) {
                console.log('[Window Cart Upload] Server response status:', response.status, response.statusText);
                if (!response.ok) {
                    throw new Error('HTTP error! status: ' + response.status);
                }
                return response.text();
            })
            .then(function (html) {
                console.log('[Window Cart Upload] Received HTML, length:', html ? html.length : 0);
                if (html && html.trim()) {
                    console.log('[Window Cart Upload] HTML preview (first 200 chars):', html.substring(0, 200));
                    var $uploadBlock = $(html);
                    console.log('[Window Cart Upload] Parsed HTML into jQuery object, elements:', $uploadBlock.length);
                    
                    // Inject into target
                    if (position === 'inside') {
                        $target.append($uploadBlock);
                        console.log('[Window Cart Upload] Successfully injected upload block INSIDE target');
                    } else if (position === 'before') {
                        $target.before($uploadBlock);
                        console.log('[Window Cart Upload] Successfully injected upload block BEFORE target');
                    } else {
                        $target.after($uploadBlock);
                        console.log('[Window Cart Upload] Successfully injected upload block AFTER target');
                    }
                    console.log('[Window Cart Upload] Injection complete!');
                } else {
                    console.warn('[Window Cart Upload] Received empty HTML from server');
                }
            })
            .catch(function (error) {
                console.error('[Window Cart Upload] Error loading upload block:', error);
                console.error('[Window Cart Upload] Error stack:', error.stack);
            });
    },
});

