# Window Cart Schedule Import

Odoo module that enables B2B customers to upload XLSX/CSV window schedules directly on the cart page (`/shop/cart`). The module automatically parses schedule rows, resolves products and attributes, computes prices, and adds configured windows/doors to the cart.

## Features

- **B2B-Only Access**: Controlled via partner flag `allow_window_schedule_upload`
- **File Format Support**: CSV and XLSX files
- **Automatic Product Resolution**: Finds products by system name or product code
- **Attribute Resolution**: Automatically matches color, glass, and hardware attributes
- **Unit Conversion**: Supports inches (in), millimeters (mm), and centimeters (cm)
- **Price Computation**: Uses the same pricing service as `window_configurator`
- **Cart Integration**: Uses the same cart update logic as `window_configurator` for consistency
- **Error Handling**: Per-row error reporting with detailed failure messages
- **Security**: File size limit (10MB) and row count limit (500 rows)

## Dependencies

- `website_sale` - Cart and checkout functionality
- `portal` - Logged-in user handling
- `window_configurator` - Pricing service and add_to_cart logic

## Installation

1. Copy the `window_cart_schedule_import` module to your Odoo addons directory
2. Update the apps list in Odoo
3. Install the module from Apps menu

## Configuration

### Enable B2B Access

1. Go to **Contacts** → Select a partner (or create a new B2B partner)
2. In the partner form, enable the checkbox **"Allow Window Schedule Upload (B2B)"**
3. Save the partner record

**Note**: The flag should be set on the **commercial partner** (parent company), not individual contacts.

## Usage

### For B2B Customers

1. **Login** to the website as a B2B customer with schedule upload enabled
2. Navigate to **Cart** (`/shop/cart`)
3. Scroll to the **"Upload Window Schedule"** section (visible only to authorized B2B partners)
4. **Download template** (optional) to see the expected format
5. **Upload** your XLSX or CSV schedule file
6. Click **"Upload and fill cart"**
7. Review the import summary showing:
   - Number of lines successfully added
   - Any errors or warnings for specific rows
8. Proceed with normal checkout

### File Format

The schedule file must contain the following columns:

#### Required Columns
- **Width** - Numeric value (width dimension)
- **Height** - Numeric value (height dimension)
- **Qty** - Quantity (numeric, defaults to 1 if empty)

#### Optional Columns
- **Label** - Window label/description (e.g., "Kitchen Window", "Master Bedroom")
- **System** - Window system/series name (used for product lookup)
- **Product Code** - Product SKU/default_code (used for product lookup)
- **Unit** - Unit of measurement: `in`, `mm`, or `cm` (defaults to `in`)
- **Color** - Frame color attribute value
- **Glass** - Glazing type attribute value
- **Hardware** - Hardware type attribute value

#### Column Name Variations

The module recognizes multiple column name variations:
- **Label**: `Label`, `Window Label`, `Tag`
- **System**: `System`, `Series`
- **Product Code**: `Product Code`, `SKU`, `Internal Ref`, `Default Code`
- **Width**: `Width`, `W`
- **Height**: `Height`, `H`
- **Unit**: `Unit`, `UOM`
- **Qty**: `Qty`, `Quantity`
- **Color**: `Color`, `Frame Color`
- **Glass**: `Glass`, `Glazing`
- **Hardware**: `Hardware`

#### Example CSV

```csv
Label,System,Product Code,Width,Height,Unit,Qty,Color,Glass,Hardware
Kitchen Window,Series 100,WIN-100,36,48,in,1,White,Double Pane,Standard
Living Room,Series 200,WIN-200,48,60,in,2,Black,Triple Pane,Premium
Master Bedroom,Series 100,WIN-100,42,60,in,1,White,Double Pane,Standard
```

### Product Resolution

The module resolves products in the following order:

1. **By Product Code**: If `Product Code` column is provided, searches for products with matching `default_code`
2. **By System Name**: If `System` column is provided, searches for products with matching name (case-insensitive)
3. **Fallback**: If neither matches, the row will fail with an error message

**Note**: Only products with `is_window_door_product = True` are considered.

### Attribute Resolution

Attributes (Color, Glass, Hardware) are resolved by matching the value name against `product.attribute.value` records associated with the product template. Matching is:
- Case-insensitive
- Exact match preferred, then partial match
- If an attribute cannot be resolved, a warning is logged but the row is still processed (attributes are optional)

## Technical Details

### Integration with window_configurator

The module integrates seamlessly with `window_configurator`:

- **Price Computation**: Uses `window.configurator.price.service.compute_price()` with the same parameters
- **Cart Updates**: Uses `sale.order._cart_update()` with custom values for dimensions, area, and configuration
- **Line Fields**: Sets the same fields on `sale.order.line`:
  - `width_in`, `height_in`, `area_sqft`
  - `config_json` (with attribute_value_ids)
  - `window_label`
  - `configured_retail_rate_per_sqft`, `configured_effective_rate_per_sqft`

### Service Model

The `window.schedule.import.service` abstract model provides reusable parsing and resolution logic:

- `load_file(file_stream, filename)` - Parses CSV or XLSX files
- `rows_to_dicts(rows)` - Converts raw rows to structured dictionaries
- `resolve_rows(row_dicts)` - Resolves products, attributes, and normalizes dimensions

### Security

- **Authentication**: All routes require login (public users redirected to login)
- **Authorization**: B2B access controlled via `partner.allow_window_schedule_upload`
- **File Size Limit**: 10MB maximum file size
- **Row Count Limit**: 500 data rows maximum
- **CSRF Protection**: Upload form includes CSRF token

### Error Handling

Errors are handled at multiple levels:

1. **File Parsing Errors**: Invalid file format, missing columns, etc.
2. **Product Resolution Errors**: Product not found for system/code
3. **Price Computation Errors**: Invalid dimensions, missing required fields
4. **Cart Update Errors**: Product unavailable, inventory issues, etc.

All errors are collected per-row and displayed in the import summary on the cart page.

## Troubleshooting

### "You are not allowed to upload window schedules"

- Ensure the partner has `allow_window_schedule_upload` enabled
- Check that the flag is set on the **commercial partner** (parent company)
- Verify the user is logged in (not a public user)

### "Missing required column: width/height/qty"

- Ensure your file has a header row with column names
- Check that column names match the expected variations (see File Format section)
- Column names are case-insensitive

### "Row X: no matching product for system '...', code '...'"

- Verify the product exists and has `is_window_door_product = True`
- Check that the product is active
- Ensure the system name or product code in the file matches exactly (case-insensitive for system name)

### "openpyxl Python package is required for XLSX parsing"

- Install openpyxl: `pip install openpyxl`
- Restart Odoo server after installation

### "File size exceeds 10MB limit"

- Split large files into smaller batches (max 500 rows per file)
- Or increase the limit in `controllers/window_cart_import.py` (line with `10 * 1024 * 1024`)

### Attributes not resolving

- Verify attribute values exist in Odoo for the product
- Check attribute value names match exactly (case-insensitive)
- Attributes are optional - rows will still be processed if attributes don't match

## File Structure

```
window_cart_schedule_import/
├── __init__.py
├── __manifest__.py
├── README.md
├── controllers/
│   ├── __init__.py
│   └── window_cart_import.py
├── models/
│   ├── __init__.py
│   ├── res_partner.py
│   └── window_schedule_import_service.py
├── security/
│   └── ir.model.access.csv
└── views/
    ├── res_partner_views.xml
    └── website_cart_import_templates.xml
```

## License

LGPL-3

## Author

Alumen

## Version

18.0.1.0.0

