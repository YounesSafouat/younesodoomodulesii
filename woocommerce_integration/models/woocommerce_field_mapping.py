from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class WooCommerceFieldMapping(models.Model):
    _name = 'woocommerce.field.mapping'
    _description = 'WooCommerce Field Mapping'
    _order = 'connection_id, sequence'

    name = fields.Char(
        string='Mapping Name',
        required=True,
        help='Descriptive name for this field mapping'
    )
    
    connection_id = fields.Many2one(
        'woocommerce.connection',
        string='WooCommerce Connection',
        required=True,
        ondelete='cascade'
    )
    
    mapping_direction = fields.Selection([
        ('wc_to_odoo', 'WooCommerce → Odoo'),
        ('odoo_to_wc', 'Odoo → WooCommerce'),
        ('bidirectional', 'Bidirectional'),
    ], string='Mapping Direction', required=True, default='bidirectional')
    
    wc_field_name = fields.Selection(
        string='WooCommerce Field',
        selection='_get_wc_field_selection',
        required=True,
        help='Field name in WooCommerce'
    )
    
    wc_field_label = fields.Char(
        string='WooCommerce Field Label',
        help='Human readable label for the WooCommerce field'
    )
    
    odoo_field_name = fields.Selection(
        string='Odoo Field',
        selection='_get_odoo_field_selection',
        required=True,
        help='Field name in Odoo'
    )
    
    odoo_field_label = fields.Char(
        string='Odoo Field Label',
        help='Human readable label for the Odoo field'
    )
    
    field_type = fields.Selection([
        ('string', 'Text'),
        ('integer', 'Integer'),
        ('float', 'Float'),
        ('boolean', 'Boolean'),
        ('date', 'Date'),
        ('datetime', 'DateTime'),
        ('selection', 'Selection'),
        ('many2one', 'Many2one'),
        ('many2many', 'Many2many'),
        ('one2many', 'One2many'),
    ], string='Field Type', required=True, default='string')
    
    transform_function = fields.Selection([
        ('none', 'No Transformation'),
        ('uppercase', 'Convert to Uppercase'),
        ('lowercase', 'Convert to Lowercase'),
        ('title', 'Convert to Title Case'),
        ('trim', 'Trim Whitespace'),
        ('normalize_choice', 'Normalize Choice (remove accents)'),
        ('multiply', 'Multiply by Factor'),
        ('divide', 'Divide by Factor'),
        ('round', 'Round to Decimals'),
        ('custom', 'Custom Python Function'),
    ], string='Data Transformation', default='none')
    
    transform_value = fields.Char(
        string='Transform Value',
        help='Value for transformation (e.g., factor for multiply/divide, decimals for round)'
    )
    
    custom_function = fields.Text(
        string='Custom Function',
        help='Custom Python function for transformation. Use "value" as the input variable.'
    )
    
    is_required = fields.Boolean(
        string='Required',
        default=False,
        help='Whether this field is required for the mapping'
    )
    
    is_active = fields.Boolean(
        string='Active',
        default=True,
        help='Whether this mapping is active'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order of processing this mapping'
    )
    
    default_value = fields.Char(
        string='Default Value',
        help='Default value if source field is empty'
    )
    
    condition_domain = fields.Char(
        string='Condition',
        help='Domain condition for when to apply this mapping (e.g., [("status", "=", "publish")])'
    )
    
    notes = fields.Text(
        string='Notes',
        help='Additional notes about this mapping'
    )

    _sql_constraints = [
        ('wc_odoo_field_unique', 'unique(connection_id, wc_field_name, odoo_field_name)', 
         'Field mapping must be unique per connection!'),
    ]
    
    @api.onchange('wc_field_name')
    def _onchange_wc_field_name(self):
        """Auto-fill WooCommerce field label when field is selected"""
        if self.wc_field_name:

            for field_code, field_label in self._get_wc_field_selection():
                if field_code == self.wc_field_name:
                    self.wc_field_label = field_label
                    break
    
    @api.onchange('odoo_field_name')
    def _onchange_odoo_field_name(self):
        """Auto-fill Odoo field label when field is selected"""
        if self.odoo_field_name:

            for field_code, field_label in self._get_odoo_field_selection():
                if field_code == self.odoo_field_name:
                    self.odoo_field_label = field_label
                    break

    @api.model
    def _get_odoo_field_selection(self):
        """Dynamically get all product.template fields for selection"""
        try:

            product_model = self.env['product.template']
            

            all_fields = []
            priority_fields = ['name', 'list_price', 'default_code', 'description', 'description_sale', 'active', 'sale_ok', 'categ_id']
            

            excluded_fields = {
                'id', 'create_uid', 'write_uid', 'create_date', 'write_date',
                'display_name', '__last_update', 'access_url', 'access_token',
                'access_warning', 'activity_exception_decoration', 'activity_exception_icon',
                'activity_ids', 'activity_state', 'activity_summary', 'activity_type_id',
                'activity_user_id', 'message_attachment_count', 'message_has_error',
                'message_has_error_counter', 'message_has_suggestion_counter',
                'message_ids', 'message_is_follower', 'message_needaction',
                'message_needaction_counter', 'message_partner_ids', 'website_message_ids'
            }
            

            excluded_field_types = {
                'binary', 'image', 'html', 'reference', 'properties',
                'one2many', 'many2many', 'many2one_reference'
            }
            

            for field_name, field_obj in product_model._fields.items():

                if field_name in excluded_fields:
                    continue
                

                if field_obj.type in excluded_field_types:
                    continue
                

                if field_obj.compute and not field_obj.store:
                    continue
                

                if hasattr(field_obj, 'related') and field_obj.related:
                    continue
                

                field_label = field_obj.string or field_name
                if field_obj.type:
                    field_label += f" ({field_obj.type})"
                

                enhanced_label = f"{field_label} ({field_name})"
                
                all_fields.append((field_name, enhanced_label))
            

            sorted_fields = []
            

            for field_name, field_label in all_fields:
                if field_name in priority_fields:
                    sorted_fields.append((field_name, field_label))
            

            for field_name, field_label in all_fields:
                if field_name not in priority_fields:
                    sorted_fields.append((field_name, field_label))
            
            return sorted_fields
            
        except Exception as e:

            _logger.warning(f"Failed to dynamically load product.template fields: {e}")
            
            basic_fields = [
                ('name', 'Product Name (name)'),
                ('list_price', 'Sales Price (list_price)'),
                ('default_code', 'Internal Reference / SKU (default_code)'),
                ('description', 'Description (description)'),
                ('description_sale', 'Sales Description (description_sale)'),
                ('active', 'Active (active)'),
                ('sale_ok', 'Can be Sold (sale_ok)'),
                ('categ_id', 'Product Category (categ_id)'),
            ]
            
            return basic_fields
    
    @api.model
    def _get_wc_field_selection(self):
        """Get WooCommerce product fields for selection with search functionality"""

        connection_id = self.env.context.get('default_connection_id')
        discovered_fields = []
        
        if connection_id:
            try:
                connection = self.env['woocommerce.connection'].browse(connection_id)
                if connection.exists() and connection.discovered_wc_fields:
                    import json
                    try:
                        discovered_data = json.loads(connection.discovered_wc_fields)
                        discovered_fields = discovered_data.get('all_fields', [])

                        if not isinstance(discovered_fields, list):
                            discovered_fields = []
                    except (json.JSONDecodeError, KeyError, TypeError):
                        discovered_fields = []
            except Exception:
                discovered_fields = []
        

        static_fields = [

            ('name', 'Product Name'),
            ('slug', 'Product Slug'),
            ('permalink', 'Product Permalink'),
            ('date_created', 'Date Created'),
            ('date_created_gmt', 'Date Created GMT'),
            ('date_modified', 'Date Modified'),
            ('date_modified_gmt', 'Date Modified GMT'),
            ('type', 'Product Type'),
            ('status', 'Product Status'),
            ('featured', 'Featured Product'),
            ('catalog_visibility', 'Catalog Visibility'),
            ('description', 'Description'),
            ('short_description', 'Short Description'),
            ('sku', 'SKU'),
            ('price', 'Price'),
            ('regular_price', 'Regular Price'),
            ('sale_price', 'Sale Price'),
            ('date_on_sale_from', 'Sale Start Date'),
            ('date_on_sale_to', 'Sale End Date'),
            ('price_html', 'Price HTML'),
            ('on_sale', 'On Sale'),
            ('purchasable', 'Purchasable'),
            ('total_sales', 'Total Sales'),
            ('virtual', 'Virtual Product'),
            ('downloadable', 'Downloadable Product'),
            ('downloads', 'Downloads'),
            ('download_limit', 'Download Limit'),
            ('download_expiry', 'Download Expiry'),
            ('external_url', 'External URL'),
            ('button_text', 'Button Text'),
            ('tax_status', 'Tax Status'),
            ('tax_class', 'Tax Class'),
            ('manage_stock', 'Manage Stock'),
            ('stock_quantity', 'Stock Quantity'),
            ('stock_status', 'Stock Status'),
            ('backorders', 'Backorders'),
            ('backorders_allowed', 'Backorders Allowed'),
            ('backordered', 'Backordered'),
            ('sold_individually', 'Sold Individually'),
            ('weight', 'Weight'),
            ('dimensions', 'Dimensions'),
            ('dimensions.length', 'Length'),
            ('dimensions.width', 'Width'),
            ('dimensions.height', 'Height'),
            ('shipping_required', 'Shipping Required'),
            ('shipping_taxable', 'Shipping Taxable'),
            ('shipping_class', 'Shipping Class'),
            ('shipping_class_id', 'Shipping Class ID'),
            ('reviews_allowed', 'Reviews Allowed'),
            ('average_rating', 'Average Rating'),
            ('rating_count', 'Rating Count'),
            ('related_ids', 'Related Products'),
            ('upsell_ids', 'Upsell Products'),
            ('cross_sell_ids', 'Cross-sell Products'),
            ('parent_id', 'Parent Product'),
            ('purchase_note', 'Purchase Note'),
            ('categories', 'Categories'),
            ('tags', 'Tags'),
            ('images', 'Images'),
            ('attributes', 'Attributes'),
            ('default_attributes', 'Default Attributes'),
            ('variations', 'Variations'),
            ('grouped_products', 'Grouped Products'),
            ('menu_order', 'Menu Order'),
            ('meta_data', 'Meta Data'),
            ('store', 'Store'),
            

            ('attributes.pa_choix-de-bois', 'Attribute: Choix de bois (pa_choix-de-bois)'),
            ('attributes.pa_classement-dusage', 'Attribute: Classement d\'usage (pa_classement-dusage)'),
            ('attributes.pa_coloris', 'Attribute: Coloris (pa_coloris)'),
            ('attributes.pa_compatible-sol-chauffant', 'Attribute: Compatible sol chauffant (pa_compatible-sol-chauffant)'),
            ('attributes.pa_dimensions', 'Attribute: Dimensions (pa_dimensions)'),
            ('attributes.pa_epaisseur', 'Attribute: Épaisseur (pa_epaisseur)'),
            ('attributes.pa_essence-de-bois', 'Attribute: Essence de bois (pa_essence-de-bois)'),
            ('attributes.pa_garantie', 'Attribute: Garantie (pa_garantie)'),
            ('attributes.pa_largeur', 'Attribute: Largeur (pa_largeur)'),
            ('attributes.pa_longueur', 'Attribute: Longueur (pa_longueur)'),
            ('attributes.pa_pattern', 'Attribute: Pattern (pa_pattern)'),
            ('attributes.pa_origine', 'Attribute: Origine (pa_origine)'),
            ('attributes.pa_packaging', 'Attribute: Packaging (pa_packaging)'),
            ('attributes.pa_marque', 'Attribute: Marque (pa_marque)'),
            

            ('meta_data._custom_field', 'Custom Field (Example)'),
            ('meta_data._product_custom_field', 'Product Custom Field'),
            ('meta_data._additional_info', 'Additional Information'),
            ('meta_data._product_features', 'Product Features'),
            ('meta_data._technical_specs', 'Technical Specifications'),
            ('meta_data._warranty_info', 'Warranty Information'),
            ('meta_data._shipping_info', 'Shipping Information'),
            ('meta_data._product_dimensions', 'Product Dimensions'),
            ('meta_data._material', 'Material'),
            ('meta_data._color', 'Color'),
            ('meta_data._size', 'Size'),
            ('meta_data._brand', 'Brand'),
            ('meta_data._model', 'Model'),
            ('meta_data._sku_custom', 'Custom SKU'),
            ('meta_data._ean', 'EAN Code'),
            ('meta_data._upc', 'UPC Code'),
            ('meta_data._isbn', 'ISBN'),
            ('meta_data._gtin', 'GTIN'),
            ('meta_data._mpn', 'MPN'),
            ('meta_data._custom_taxonomy', 'Custom Taxonomy'),
            ('meta_data._product_condition', 'Product Condition'),
            ('meta_data._availability_status', 'Availability Status'),
            ('meta_data._lead_time', 'Lead Time'),
            ('meta_data._minimum_order_qty', 'Minimum Order Quantity'),
            ('meta_data._maximum_order_qty', 'Maximum Order Quantity'),
            ('meta_data._product_rating', 'Product Rating'),
            ('meta_data._review_count', 'Review Count'),
            ('meta_data._featured_image', 'Featured Image URL'),
            ('meta_data._gallery_images', 'Gallery Images'),
            ('meta_data._product_video', 'Product Video URL'),
            ('meta_data._download_link', 'Download Link'),
            ('meta_data._product_manual', 'Product Manual'),
            ('meta_data._safety_info', 'Safety Information'),
            ('meta_data._compliance_cert', 'Compliance Certificate'),
            ('meta_data._environmental_info', 'Environmental Information'),
            ('meta_data._recyclable', 'Recyclable'),
            ('meta_data._energy_efficiency', 'Energy Efficiency Rating'),
            ('meta_data._country_of_origin', 'Country of Origin'),
            ('meta_data._manufacturer', 'Manufacturer'),
            ('meta_data._supplier', 'Supplier'),
            ('meta_data._distributor', 'Distributor'),
            ('meta_data._product_line', 'Product Line'),
            ('meta_data._season', 'Season'),
            ('meta_data._collection', 'Collection'),
            ('meta_data._style', 'Style'),
            ('meta_data._theme', 'Theme'),
            ('meta_data._occasion', 'Occasion'),
            ('meta_data._target_audience', 'Target Audience'),
            ('meta_data._age_range', 'Age Range'),
            ('meta_data._gender', 'Gender'),
            ('meta_data._product_usage', 'Product Usage'),
            ('meta_data._care_instructions', 'Care Instructions'),
            ('meta_data._maintenance_info', 'Maintenance Information'),
            ('meta_data._installation_info', 'Installation Information'),
            ('meta_data._product_benefits', 'Product Benefits'),
            ('meta_data._key_features', 'Key Features'),
            ('meta_data._whats_included', 'What\'s Included'),
            ('meta_data._product_highlights', 'Product Highlights'),
            ('meta_data._special_offer', 'Special Offer'),
            ('meta_data._discount_code', 'Discount Code'),
            ('meta_data._promo_text', 'Promotional Text'),
            ('meta_data._cross_sell_reason', 'Cross-sell Reason'),
            ('meta_data._upsell_reason', 'Upsell Reason'),
            ('meta_data._bundle_items', 'Bundle Items'),
            ('meta_data._related_products', 'Related Products'),
            ('meta_data._frequently_bought_together', 'Frequently Bought Together'),
            ('meta_data._product_comparison', 'Product Comparison'),
            ('meta_data._customer_reviews', 'Customer Reviews'),
            ('meta_data._testimonials', 'Testimonials'),
            ('meta_data._faq', 'Frequently Asked Questions'),
            ('meta_data._product_tutorials', 'Product Tutorials'),
            ('meta_data._support_info', 'Support Information'),
            ('meta_data._return_policy', 'Return Policy'),
            ('meta_data._exchange_policy', 'Exchange Policy'),
            ('meta_data._refund_policy', 'Refund Policy'),
        ]
        


        all_fields = []
        for field_item in static_fields:
            if isinstance(field_item, (list, tuple)) and len(field_item) >= 2:
                all_fields.append((field_item[0], field_item[1]))
        

        static_field_codes = [field[0] for field in static_fields]
        for field_item in discovered_fields:

            if isinstance(field_item, (list, tuple)) and len(field_item) >= 2:
                try:
                    field_code, field_label = str(field_item[0]), str(field_item[1])
                    if field_code and field_label and field_code not in static_field_codes:

                        enhanced_label = f"{field_label} ({field_code})"
                        all_fields.append((field_code, enhanced_label))
                except (IndexError, TypeError, AttributeError) as e:
                    _logger.warning(f"Invalid field item in discovered fields: {field_item}, error: {e}")
                    continue
            else:
                _logger.warning(f"Invalid field item format in discovered fields: {field_item}")
                continue
        

        priority_fields = ['name', 'price', 'regular_price', 'sale_price', 'sku', 'status', 'description', 'short_description']
        sorted_fields = []
        priority_sorted = []
        

        for field_item in all_fields:

            if isinstance(field_item, (list, tuple)) and len(field_item) >= 2:
                field_code, field_label = field_item[0], field_item[1]
                if field_code in priority_fields:
                    priority_sorted.append((field_code, field_label))
        

        for field_item in all_fields:

            if isinstance(field_item, (list, tuple)) and len(field_item) >= 2:
                field_code, field_label = field_item[0], field_item[1]
                if field_code not in priority_fields:
                    priority_sorted.append((field_code, field_label))
        

        if not priority_sorted:
            return static_fields
        

        validated_fields = []
        for field_item in priority_sorted:
            if isinstance(field_item, (list, tuple)) and len(field_item) >= 2:
                validated_fields.append((str(field_item[0]), str(field_item[1])))
            else:
                _logger.warning(f"Invalid field item in final result: {field_item}")
        

        if not validated_fields:
            _logger.error("All field items were invalid, falling back to static fields")
            return static_fields
        
        return validated_fields
    
    @api.model
    def get_default_mappings(self):
        """Get default field mappings for a new connection"""
        return [
            {
                'name': 'Product Name',
                'wc_field_name': 'name',
                'wc_field_label': 'Product Name',
                'odoo_field_name': 'name',
                'odoo_field_label': 'Product Name',
                'field_type': 'string',
                'mapping_direction': 'bidirectional',
                'is_required': True,
                'sequence': 10,
            },
            {
                'name': 'Regular Price',
                'wc_field_name': 'regular_price',
                'wc_field_label': 'Regular Price',
                'odoo_field_name': 'list_price',
                'odoo_field_label': 'Sales Price',
                'field_type': 'float',
                'mapping_direction': 'bidirectional',
                'is_required': True,
                'sequence': 20,
            },
            {
                'name': 'SKU',
                'wc_field_name': 'sku',
                'wc_field_label': 'SKU',
                'odoo_field_name': 'default_code',
                'odoo_field_label': 'Internal Reference',
                'field_type': 'string',
                'mapping_direction': 'bidirectional',
                'sequence': 30,
            },
            {
                'name': 'Description',
                'wc_field_name': 'description',
                'wc_field_label': 'Description',
                'odoo_field_name': 'description',
                'odoo_field_label': 'Description',
                'field_type': 'string',
                'mapping_direction': 'bidirectional',
                'sequence': 40,
            },
            {
                'name': 'Short Description',
                'wc_field_name': 'short_description',
                'wc_field_label': 'Short Description',
                'odoo_field_name': 'description_sale',
                'odoo_field_label': 'Sales Description',
                'field_type': 'string',
                'mapping_direction': 'bidirectional',
                'sequence': 50,
            },
            {
                'name': 'Product Status',
                'wc_field_name': 'status',
                'wc_field_label': 'Product Status',
                'odoo_field_name': 'sale_ok',
                'odoo_field_label': 'Can be Sold',
                'field_type': 'boolean',
                'mapping_direction': 'bidirectional',
                'transform_function': 'custom',
                'custom_function': 'True if value == "publish" else False',
                'sequence': 60,
            },
            {
                'name': 'Weight',
                'wc_field_name': 'weight',
                'wc_field_label': 'Weight',
                'odoo_field_name': 'weight',
                'odoo_field_label': 'Weight',
                'field_type': 'float',
                'mapping_direction': 'bidirectional',
                'sequence': 70,
            },
            {
                'name': 'Stock Status',
                'wc_field_name': 'stock_status',
                'wc_field_label': 'Stock Status',
                'odoo_field_name': 'qty_available',
                'odoo_field_label': 'Quantity on Hand',
                'field_type': 'string',
                'mapping_direction': 'wc_to_odoo',
                'transform_function': 'custom',
                'custom_function': '1 if value == "instock" else 0',
                'sequence': 80,
            },
        ]

    def apply_transform(self, value, direction='wc_to_odoo'):
        """Transform a value according to the mapping rules"""
        self.ensure_one()
        
        if not value and self.default_value:
            return self.default_value
        
        if not value:
            return value
        
        try:
            if self.transform_function == 'none':
                return value
            
            elif self.transform_function == 'uppercase':
                return str(value).upper()
            
            elif self.transform_function == 'lowercase':
                return str(value).lower()
            
            elif self.transform_function == 'title':
                return str(value).title()
            
            elif self.transform_function == 'trim':
                return str(value).strip()
            
            elif self.transform_function == 'normalize_choice':

                value_str = str(value).lower()

                import unicodedata
                normalized = unicodedata.normalize('NFD', value_str)
                normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
                return normalized
            
            elif self.transform_function == 'multiply':
                factor = float(self.transform_value or 1)
                return float(value) * factor
            
            elif self.transform_function == 'divide':
                factor = float(self.transform_value or 1)
                return float(value) / factor if factor != 0 else value
            
            elif self.transform_function == 'round':
                decimals = int(self.transform_value or 2)
                return round(float(value), decimals)
            
            elif self.transform_function == 'custom':
                if self.custom_function:

                    safe_globals = {
                        '__builtins__': {},
                        'value': value,
                        'str': str,
                        'int': int,
                        'float': float,
                        'bool': bool,
                        'len': len,
                    }
                    return eval(self.custom_function, safe_globals)
            
            return value
            
        except Exception as e:
            _logger.error(f"Error transforming value {value}: {e}")
            return value

    def apply_mapping(self, source_data, target_model, direction='wc_to_odoo'):
        """Apply field mapping to transform data"""
        self.ensure_one()
        
        if direction not in ['wc_to_odoo', 'odoo_to_wc']:
            raise ValidationError(_('Invalid mapping direction'))
        

        if self.mapping_direction not in [direction, 'bidirectional']:
            return {}
        

        if direction == 'wc_to_odoo':
            source_field = self.wc_field_name
            target_field = self.odoo_field_name
        else:
            source_field = self.odoo_field_name
            target_field = self.wc_field_name
        

        source_value = source_data.get(source_field)
        

        transformed_value = self.apply_transform(source_value, direction)
        

        if hasattr(target_model, '_fields') and target_field not in target_model._fields:
            _logger.warning(f"Field {target_field} does not exist in target model")
            return {}
        
        return {target_field: transformed_value}

    @api.model
    def apply_all_mappings(self, source_data, target_model, connection_id, direction='wc_to_odoo'):
        """Apply all active mappings for a connection"""
        mappings = self.search([
            ('connection_id', '=', connection_id),
            ('is_active', '=', True),
            ('mapping_direction', 'in', [direction, 'bidirectional'])
        ], order='sequence')
        
        result = {}
        for mapping in mappings:
            try:
                mapped_data = mapping.apply_mapping(source_data, target_model, direction)
                result.update(mapped_data)
            except Exception as e:
                _logger.error(f"Error applying mapping {mapping.name}: {e}")
        
        return result

    def action_create_default_mappings(self):
        """Create default field mappings for this connection"""
        self.ensure_one()
        
        default_mappings = self.get_default_mappings()
        for mapping_data in default_mappings:
            mapping_data['connection_id'] = self.connection_id.id
            self.create(mapping_data)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Default Mappings Created'),
                'message': _('Default field mappings have been created for this connection.'),
                'type': 'success',
            }
        }
    
    def action_test_mapping(self):
        """Test the field mapping with sample data"""
        self.ensure_one()
        

        test_data_wc = {
            'name': 'Test Product',
            'regular_price': '29.99',
            'sku': 'TEST-001',
            'description': 'Test description',
            'status': 'publish',
            'weight': '1.5',
            'stock_status': 'instock',
        }
        
        test_data_odoo = {
            'name': 'Test Product',
            'list_price': 29.99,
            'default_code': 'TEST-001',
            'description': 'Test description',
            'sale_ok': True,
            'weight': 1.5,
            'qty_available': 10,
        }
        
        result_wc_to_odoo = {}
        result_odoo_to_wc = {}
        
        try:
            if self.mapping_direction in ['wc_to_odoo', 'bidirectional']:
                result_wc_to_odoo = self.apply_mapping(test_data_wc, self.env['product.template'], 'wc_to_odoo')
            
            if self.mapping_direction in ['odoo_to_wc', 'bidirectional']:
                result_odoo_to_wc = self.apply_mapping(test_data_odoo, self.env['product.template'], 'odoo_to_wc')
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Mapping Test Failed'),
                    'message': _('Error testing mapping: %s') % str(e),
                    'type': 'danger',
                }
            }
        
        message = _('Mapping test completed successfully!\n\n')
        
        if result_wc_to_odoo:
            message += _('WooCommerce → Odoo:\n')
            for field, value in result_wc_to_odoo.items():
                message += f'  {field}: {value}\n'
            message += '\n'
        
        if result_odoo_to_wc:
            message += _('Odoo → WooCommerce:\n')
            for field, value in result_odoo_to_wc.items():
                message += f'  {field}: {value}\n'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mapping Test Results'),
                'message': message,
                'type': 'success',
                'sticky': True,
            }
        }
