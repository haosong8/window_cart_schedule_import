# -*- coding: utf-8 -*-

import json
import logging

from odoo import http, _
from odoo.exceptions import UserError
from odoo.http import request
from werkzeug.exceptions import Forbidden

_logger = logging.getLogger(__name__)


class WindowCartImportController(http.Controller):

    @http.route(
        "/shop/cart/upload_window_schedule",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def upload_window_schedule(self, **post):
        """Handle window schedule file upload and add items to cart."""
        # Must be logged in
        if request.env.user._is_public():
            return request.redirect("/web/login?redirect=/shop/cart")

        partner = request.env.user.partner_id.commercial_partner_id
        if not partner.allow_window_schedule_upload:
            raise Forbidden(_("You are not allowed to upload window schedules."))

        file = request.httprequest.files.get("schedule_file")
        if not file or not file.filename:
            request.session["window_schedule_upload_error"] = _("Please select a file.")
            return request.redirect("/shop/cart")

        # Check file size (limit to 10MB)
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        if file_size > 10 * 1024 * 1024:  # 10MB
            request.session["window_schedule_upload_error"] = _("File size exceeds 10MB limit.")
            return request.redirect("/shop/cart")

        Service = request.env["window.schedule.import.service"]
        
        try:
            rows = Service.load_file(file, file.filename)
            row_dicts = Service.rows_to_dicts(rows)
            resolved_rows = Service.resolve_rows(row_dicts)
        except UserError as e:
            _logger.warning("User error parsing schedule file: %s", str(e))
            request.session["window_schedule_upload_error"] = str(e)
            return request.redirect("/shop/cart")
        except Exception as e:
            _logger.exception("Error parsing schedule file")
            request.session["window_schedule_upload_error"] = _("An error occurred while parsing the file. Please check the file format and try again.")
            return request.redirect("/shop/cart")

        # Add to cart using same logic as configurator
        result_summary = self._add_rows_to_cart(resolved_rows)
        request.session["window_schedule_upload_summary"] = result_summary
        return request.redirect("/shop/cart")

    def _add_rows_to_cart(self, resolved_rows):
        """Add resolved rows to cart using window configurator logic."""
        PriceService = request.env["window.configurator.price.service"].sudo()
        website = request.website
        order = website.sale_get_order(force_create=True)
        
        successes = 0
        failures = []

        for row in resolved_rows:
            product = row["product"]
            attribute_value_ids = row["attribute_value_ids"]
            qty = row["qty"]
            width_in = row["width_in"]
            height_in = row["height_in"]
            window_label = row.get("label") or ""

            # Get pricelist and fiscal position
            pricelist = order.pricelist_id
            fiscal_position = order.fiscal_position_id
            if not pricelist:
                pricelist = website.pricelist_id if website else None
            if not fiscal_position and website:
                fiscal_position = website.fiscal_position_id

            try:
                # Compute price using the same service as window_configurator
                price_data = PriceService.compute_price(
                    product_tmpl=product.product_tmpl_id,
                    width_in=width_in,
                    height_in=height_in,
                    attribute_value_ids=attribute_value_ids,
                    qty=qty,
                    pricelist=pricelist,
                    fiscal_position=fiscal_position,
                    website=website,
                )
            except UserError as e:
                _logger.warning("User error computing price for row %s: %s", row["row_number"], str(e))
                failures.append(
                    _("Row %(row)s: %(err)s") %
                    {"row": row["row_number"], "err": str(e)}
                )
                continue
            except Exception as e:
                _logger.exception("Error computing price for row %s", row["row_number"])
                failures.append(
                    _("Row %(row)s: price computation failed: %(err)s") %
                    {"row": row["row_number"], "err": str(e)}
                )
                continue

            # Build config_json with attribute_value_ids
            config_dict = {
                "attribute_value_ids": attribute_value_ids,
            }
            config_json = json.dumps(config_dict)

            # Build custom_values as window_configurator/add_to_cart does
            custom_values = {
                "width_in": width_in,
                "height_in": height_in,
                "area_sqft": price_data.get("area_sqft", 0.0),
                "config_json": config_json,
                "window_label": window_label,
                "configured_retail_rate_per_sqft": price_data.get("retail_rate_per_sqft", 0.0),
                "configured_effective_rate_per_sqft": price_data.get("effective_rate_per_sqft", 0.0),
            }

            try:
                # Map attribute_value_ids to product.template.attribute.value IDs
                line_model = request.env["sale.order.line"]
                template_attribute_value_ids = line_model._map_configurator_attribute_value_ids(
                    product.product_tmpl_id, attribute_value_ids
                )

                # Use _cart_update with custom_values
                # This mirrors the logic in window_configurator controllers
                line_result = order._cart_update(
                    product_id=product.id,
                    add_qty=qty,
                    set_qty=None,
                    product_custom_attribute_values=None,
                    no_variant_attribute_values=template_attribute_value_ids if template_attribute_value_ids else None,
                )

                if line_result.get("warning"):
                    raise UserError(line_result.get("warning"))

                # Find the line that was created/updated
                line = None
                if line_result.get("line_id"):
                    line = request.env["sale.order.line"].browse(line_result["line_id"])
                
                if not line or not line.exists():
                    # Fallback: find the most recently created line for this product
                    line_candidates = order.order_line.filtered(
                        lambda l: l.product_id.id == product.id
                    ).sorted("create_date", reverse=True)
                    if line_candidates:
                        line = line_candidates[0]

                if not line:
                    raise UserError(_("Could not find cart line to update"))

                # Update the line with custom values
                line.write({
                    "width_in": width_in,
                    "height_in": height_in,
                    "price_unit": price_data["price_unit"],
                    "config_json": config_json,
                    "window_label": window_label,
                    "configured_retail_rate_per_sqft": price_data.get("retail_rate_per_sqft", 0.0),
                    "configured_effective_rate_per_sqft": price_data.get("effective_rate_per_sqft", 0.0),
                })
                
                # Update descriptions and recompute
                line._update_configurator_descriptions()
                line._compute_tax_id()
                line._compute_amount()
                line.invalidate_recordset(["price_total", "price_subtotal"])

                successes += 1
            except UserError as e:
                _logger.warning("User error adding row %s to cart: %s", row["row_number"], str(e))
                failures.append(
                    _("Row %(row)s: %(err)s") %
                    {"row": row["row_number"], "err": str(e)}
                )
            except Exception as e:
                _logger.exception("Error adding row %s to cart", row["row_number"])
                failures.append(
                    _("Row %(row)s: failed to add to cart: %(err)s") %
                    {"row": row["row_number"], "err": str(e)}
                )

        return {
            "success_count": successes,
            "failure_messages": failures,
        }

    @http.route(
        "/shop/cart/get_upload_block",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
    )
    def get_upload_block(self, **kw):
        """Return the upload block HTML for JavaScript injection."""
        _logger.info("Window Cart Upload: get_upload_block called")
        
        if request.env.user._is_public():
            _logger.info("Window Cart Upload: User is public, returning empty")
            return request.make_response("")
        
        _logger.info("Window Cart Upload: User is logged in: %s", request.env.user.login)
        
        partner = request.env.user.partner_id.commercial_partner_id
        is_company = partner.company_type == "company"
        allow_upload = is_company or partner.allow_window_schedule_upload

        _logger.info(
            "Window Cart Upload: Partner: %s (company_type=%s, allow_flag=%s, effective_access=%s)",
            partner.name,
            partner.company_type,
            partner.allow_window_schedule_upload,
            allow_upload,
        )
        
        if not allow_upload:
            _logger.info("Window Cart Upload: Partner does not have permission, returning empty")
            _logger.info(
                "Window Cart Upload: To enable, either set company_type='company' or allow_window_schedule_upload=True on partner: %s (ID: %s)",
                partner.name,
                partner.id,
            )
            return request.make_response("")
        elif is_company and not partner.allow_window_schedule_upload:
            _logger.info(
                "Window Cart Upload: Partner is a company, auto-enabling upload access even though flag is False"
            )
        
        # Render the template
        try:
            _logger.info("Window Cart Upload: Attempting to render template: window_cart_schedule_import.window_cart_upload_block")
            html = request.env["ir.ui.view"]._render_template(
                "window_cart_schedule_import.window_cart_upload_block",
                values={}
            )
            _logger.info("Window Cart Upload: Template rendered successfully, HTML length: %s", len(html) if html else 0)
            if html:
                _logger.info("Window Cart Upload: HTML preview (first 300 chars): %s", html[:300])
            return html
        except Exception as e:
            _logger.exception("Window Cart Upload: Error rendering template: %s", str(e))
            return request.make_response("")

    @http.route(
        "/shop/cart/window_schedule_template",
        type="http",
        auth="public",
        website=True,
    )
    def download_window_schedule_template(self, **kw):
        """Download CSV template for window schedule upload."""
        # Enforce login+B2B access
        if request.env.user._is_public():
            return request.redirect("/web/login?redirect=/shop/cart")
        
        partner = request.env.user.partner_id.commercial_partner_id
        allow_upload = (partner.company_type == "company") or partner.allow_window_schedule_upload
        if not allow_upload:
            raise Forbidden(_("You are not allowed to download window schedule templates."))

        template_content = (
            "Label,System,Product Code,Width,Height,Unit,Qty,Color,Glass,Hardware\n"
            "Kitchen Window,Series 100,WIN-100,36,48,in,1,White,Double Pane,Standard\n"
            "Living Room,Series 200,WIN-200,48,60,in,2,Black,Triple Pane,Premium\n"
        )

        headers = [
            ("Content-Type", "text/csv; charset=utf-8"),
            ("Content-Disposition", "attachment; filename=window_schedule_template.csv"),
        ]
        return request.make_response(template_content.encode("utf-8"), headers=headers)

