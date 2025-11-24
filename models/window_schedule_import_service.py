# -*- coding: utf-8 -*-

import csv
import io
import logging

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import openpyxl
except ImportError:
    openpyxl = None


class WindowScheduleImportService(models.AbstractModel):
    _name = "window.schedule.import.service"
    _description = "Window Schedule Import Service"

    def load_file(self, file_stream, filename):
        """Decode file & detect type."""
        data = file_stream.read()
        ext = (filename or "").lower()
        
        if ext.endswith(".csv"):
            return self._parse_csv(data)
        elif ext.endswith(".xlsx"):
            return self._parse_xlsx(data)
        else:
            raise UserError(_("Unsupported file type: %s. Please upload a CSV or XLSX file.") % filename)

    def _parse_csv(self, data: bytes):
        """Parse CSV file."""
        text = data.decode("utf-8-sig")
        f = io.StringIO(text)
        reader = csv.reader(f)
        return list(reader)

    def _parse_xlsx(self, data: bytes):
        """Parse XLSX file."""
        if not openpyxl:
            raise UserError(_("openpyxl Python package is required for XLSX parsing. Please install it: pip install openpyxl"))
        
        f = io.BytesIO(data)
        wb = openpyxl.load_workbook(f, data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append([cell if cell is not None else "" for cell in row])
        return rows

    def rows_to_dicts(self, rows):
        """Build header map & convert to row dicts."""
        if not rows:
            raise UserError(_("The file is empty."))
        
        if len(rows) < 2:
            raise UserError(_("The file must contain at least a header row and one data row."))
        
        # Limit to 500 rows to prevent abuse
        if len(rows) > 501:  # 1 header + 500 data rows
            raise UserError(_("The file contains too many rows. Maximum 500 data rows allowed."))
        
        header = [str(h or "").strip().lower() for h in rows[0]]
        data_rows = rows[1:]

        def idx(candidates):
            for name in candidates:
                if name in header:
                    return header.index(name)
            return None

        col_map = {
            "label": idx(["label", "window label", "tag"]),
            "system": idx(["system", "series"]),
            "product_code": idx(["product code", "sku", "internal ref", "default_code"]),
            "width": idx(["width", "w"]),
            "height": idx(["height", "h"]),
            "unit": idx(["unit", "uom"]),
            "qty": idx(["qty", "quantity"]),
            "color": idx(["color", "frame color"]),
            "glass": idx(["glass", "glazing"]),
            "hardware": idx(["hardware"]),
        }

        for required in ("width", "height", "qty"):
            if col_map[required] is None:
                raise UserError(_("Missing required column: %s") % required)

        row_dicts = []
        row_number = 2  # for error messages (row 1 is header)
        
        for row in data_rows:
            if not any(row):
                row_number += 1
                continue

            def get(key, default=""):
                i = col_map.get(key)
                return (row[i] if i is not None and i < len(row) else default) or default

            row_dicts.append({
                "row_number": row_number,
                "label": str(get("label")).strip(),
                "system": str(get("system")).strip(),
                "product_code": str(get("product_code")).strip(),
                "width": get("width"),
                "height": get("height"),
                "unit": str(get("unit") or "in").lower(),
                "qty": get("qty") or 1,
                "color": str(get("color")).strip(),
                "glass": str(get("glass")).strip(),
                "hardware": str(get("hardware")).strip(),
            })
            row_number += 1

        return row_dicts

    def resolve_rows(self, row_dicts):
        """Resolve product, attributes, normalize dimensions."""
        Product = self.env["product.product"].sudo()
        Ptav = self.env["product.template.attribute.value"].sudo()
        resolved = []

        for row in row_dicts:
            try:
                qty = float(row["qty"]) or 1.0
                width = float(row["width"])
                height = float(row["height"])
            except (ValueError, TypeError):
                raise UserError(_("Row %s: invalid numeric values for width, height, or qty.") % row["row_number"])

            product = self._resolve_product(Product, row["system"], row["product_code"])
            if not product:
                raise UserError(
                    _("Row %s: no matching product for system '%s', code '%s'.")
                    % (row["row_number"], row["system"], row["product_code"])
                )

            attribute_value_ids = self._resolve_attributes(
                Ptav, product.product_tmpl_id, row
            )

            width_in, height_in = self._convert_to_inches(width, height, row["unit"])

            resolved.append({
                **row,
                "product": product,
                "qty": qty,
                "width_in": width_in,
                "height_in": height_in,
                "attribute_value_ids": attribute_value_ids,
            })

        return resolved

    def _convert_to_inches(self, width, height, unit):
        """Convert dimensions to inches."""
        if unit in ("in", "inch", "inches", ""):
            return width, height
        if unit in ("mm", "millimeter", "millimeters"):
            return width / 25.4, height / 25.4
        if unit in ("cm", "centimeter", "centimeters"):
            return width / 2.54, height / 2.54
        # fallback: assume inches
        return width, height

    def _resolve_product(self, Product, system, product_code):
        """Resolve product by system code or product code."""
        domain = [("is_window_door_product", "=", True), ("active", "=", True)]
        
        # First try by product code (default_code)
        if product_code:
            prod = Product.search(domain + [("default_code", "=", product_code)], limit=1)
            if prod:
                return prod

        # Then try by system name (fuzzy search on product name)
        if system:
            # Search for products with system in name
            prod = Product.search(domain + [("name", "ilike", system)], limit=1)
            if prod:
                return prod
            
            # Try template search
            tmpl = self.env["product.template"].sudo().search(
                [("name", "ilike", system), ("is_window_door_product", "=", True), ("active", "=", True)],
                limit=1,
            )
            if tmpl and tmpl.product_variant_id:
                return tmpl.product_variant_id

        return False

    def _resolve_attributes(self, Ptav, product_tmpl, row):
        """Resolve attribute values by name (case-insensitive)."""
        result_ids = []
        for key in ("color", "glass", "hardware"):
            val = row.get(key)
            if not val or not val.strip():
                continue
            
            val_clean = val.strip()
            
            # Search for attribute value by name within this product template (case-insensitive)
            # First try exact match
            rec = Ptav.search([
                ("product_tmpl_id", "=", product_tmpl.id),
                ("product_attribute_value_id.name", "=", val_clean),
            ], limit=1)
            
            # If not found, try case-insensitive match
            if not rec:
                rec = Ptav.search([
                    ("product_tmpl_id", "=", product_tmpl.id),
                    ("product_attribute_value_id.name", "ilike", val_clean),
                ], limit=1)
            
            if rec:
                result_ids.append(rec.product_attribute_value_id.id)
            else:
                # Log warning but don't fail - attributes are optional
                _logger = logging.getLogger(__name__)
                _logger.warning(
                    "Could not resolve attribute '%s'='%s' for product %s",
                    key, val_clean, product_tmpl.name
                )
        
        return result_ids

