# Complete Odoo Development Guide - From Zero to First Module

## Table of Contents
1. [Understanding Odoo](#understanding-odoo)
2. [Odoo Architecture](#odoo-architecture)
3. [Development Environment Setup](#development-environment-setup)
4. [Creating Your First Module](#creating-your-first-module)
5. [Understanding Odoo Components](#understanding-odoo-components)
6. [Step-by-Step Module Creation](#step-by-step-module-creation)
7. [Testing and Debugging](#testing-and-debugging)
8. [Best Practices](#best-practices)

## Understanding Odoo

### What is Odoo?
Odoo is an open-source business management software that includes:
- **ERP** (Enterprise Resource Planning)
- **CRM** (Customer Relationship Management)
- **E-commerce**
- **Website Builder**
- **Project Management**
- **And much more...**

### Key Concepts
- **Apps/Modules**: Extensions that add functionality
- **Models**: Database tables with business logic
- **Views**: User interface components
- **Records**: Individual database entries
- **Fields**: Columns in database tables

## Odoo Architecture

### Core Components
```
┌─────────────────────────────────────────┐
│                Web Interface            │
├─────────────────────────────────────────┤
│                ORM Layer                │
├─────────────────────────────────────────┤
│                Business Logic           │
├─────────────────────────────────────────┤
│                Database                 │
└─────────────────────────────────────────┘
```

### Module Structure
```
my_module/
├── __manifest__.py          # Module definition
├── __init__.py              # Module initialization
├── models/                  # Database models
│   ├── __init__.py
│   └── my_model.py
├── views/                   # User interface
│   └── my_views.xml
├── security/                # Access control
│   ├── ir.model.access.csv
│   └── groups.xml
├── data/                    # Initial data
│   └── my_data.xml
└── static/                  # Static files
    └── description/
        └── icon.png
```

## Development Environment Setup

### 1. Install Odoo
```bash
# Download Odoo 18
wget https://nightly.odoo.com/18.0/nightly/src/odoo_18.0.latest.tar.gz
tar -xzf odoo_18.0.latest.tar.gz

# Install Python dependencies
pip3 install -r requirements.txt
```

### 2. Configure Odoo
Create `odoo.conf`:
```ini
[options]
addons_path = /path/to/odoo/addons,/path/to/custom/addons
db_host = localhost
db_port = 5432
db_user = odoo
db_password = odoo
admin_passwd = admin
xmlrpc_port = 8069
```

### 3. Start Odoo
```bash
python3 odoo-bin -c odoo.conf
```

## Creating Your First Module

Let's create a simple "Book Management" module step by step.

### Step 1: Create Module Directory
```bash
mkdir -p /path/to/custom/addons/book_management
cd /path/to/custom/addons/book_management
```

### Step 2: Create Module Manifest
Create `__manifest__.py`:
```python
{
    'name': 'Book Management',
    'version': '1.0.0',
    'category': 'Tools',
    'summary': 'Manage books in your library',
    'description': """
        Book Management Module
        =====================
        This module allows you to:
        * Manage books
        * Track book details
        * Categorize books
    """,
    'author': 'Your Name',
    'website': 'https://www.yourwebsite.com',
    'depends': ['base'],  # Dependencies
    'data': [
        'security/ir.model.access.csv',
        'views/book_views.xml',
        'data/book_data.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
```

### Step 3: Create Module Initialization
Create `__init__.py`:
```python
from . import models
```

### Step 4: Create Models Directory
```bash
mkdir models
touch models/__init__.py
```

### Step 5: Create Book Model
Create `models/book.py`:
```python
from odoo import models, fields, api

class Book(models.Model):
    _name = 'book.management'
    _description = 'Book Management'
    _order = 'name'
    
    # Basic Fields
    name = fields.Char(
        string='Book Title',
        required=True,
        help='The title of the book'
    )
    
    author = fields.Char(
        string='Author',
        required=True,
        help='The author of the book'
    )
    
    isbn = fields.Char(
        string='ISBN',
        help='International Standard Book Number'
    )
    
    # Selection Field
    status = fields.Selection([
        ('available', 'Available'),
        ('borrowed', 'Borrowed'),
        ('lost', 'Lost'),
        ('damaged', 'Damaged'),
    ], string='Status', default='available', required=True)
    
    # Numeric Fields
    pages = fields.Integer(
        string='Number of Pages',
        help='Total number of pages in the book'
    )
    
    price = fields.Float(
        string='Price',
        digits=(16, 2),
        help='Book price in local currency'
    )
    
    # Date Fields
    publication_date = fields.Date(
        string='Publication Date',
        help='When the book was published'
    )
    
    purchase_date = fields.Datetime(
        string='Purchase Date',
        default=fields.Datetime.now,
        help='When the book was purchased'
    )
    
    # Text Fields
    description = fields.Text(
        string='Description',
        help='Detailed description of the book'
    )
    
    summary = fields.Html(
        string='Summary',
        help='HTML formatted summary'
    )
    
    # Boolean Fields
    is_fiction = fields.Boolean(
        string='Is Fiction',
        default=False,
        help='Check if this is a fiction book'
    )
    
    # Binary Fields
    cover_image = fields.Binary(
        string='Cover Image',
        help='Book cover image'
    )
    
    # Relational Fields
    category_id = fields.Many2one(
        'book.category',
        string='Category',
        help='Book category'
    )
    
    # Computed Fields
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    
    # Constraints
    _sql_constraints = [
        ('isbn_unique', 'UNIQUE(isbn)', 'ISBN must be unique!'),
        ('pages_positive', 'CHECK(pages > 0)', 'Pages must be positive!'),
    ]
    
    @api.depends('name', 'author')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} - {record.author}"
    
    # Methods
    def action_mark_borrowed(self):
        """Mark book as borrowed"""
        self.write({'status': 'borrowed'})
    
    def action_mark_returned(self):
        """Mark book as returned"""
        self.write({'status': 'available'})
    
    @api.model
    def create(self, vals):
        """Override create method"""
        # Add custom logic before creation
        if 'name' in vals:
            vals['name'] = vals['name'].title()
        
        return super(Book, self).create(vals)
    
    def write(self, vals):
        """Override write method"""
        # Add custom logic before update
        if 'name' in vals:
            vals['name'] = vals['name'].title()
        
        return super(Book, self).write(vals)
```

### Step 6: Create Category Model
Create `models/book_category.py`:
```python
from odoo import models, fields

class BookCategory(models.Model):
    _name = 'book.category'
    _description = 'Book Category'
    _order = 'name'
    
    name = fields.Char(
        string='Category Name',
        required=True
    )
    
    description = fields.Text(
        string='Description'
    )
    
    book_ids = fields.One2many(
        'book.management',
        'category_id',
        string='Books'
    )
    
    book_count = fields.Integer(
        string='Book Count',
        compute='_compute_book_count'
    )
    
    def _compute_book_count(self):
        for record in self:
            record.book_count = len(record.book_ids)
```

### Step 7: Update Models Init
Update `models/__init__.py`:
```python
from . import book
from . import book_category
```

### Step 8: Create Views Directory
```bash
mkdir views
```

### Step 9: Create Book Views
Create `views/book_views.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data>
        <!-- Book Tree View -->
        <record id="view_book_tree" model="ir.ui.view">
            <field name="name">book.management.tree</field>
            <field name="model">book.management</field>
            <field name="arch" type="xml">
                <list string="Books" default_order="name">
                    <field name="name"/>
                    <field name="author"/>
                    <field name="isbn"/>
                    <field name="category_id"/>
                    <field name="status" widget="badge"
                           decoration-success="status == 'available'"
                           decoration-warning="status == 'borrowed'"
                           decoration-danger="status in ['lost', 'damaged']"/>
                    <field name="pages"/>
                    <field name="price"/>
                </list>
            </field>
        </record>

        <!-- Book Form View -->
        <record id="view_book_form" model="ir.ui.view">
            <field name="name">book.management.form</field>
            <field name="model">book.management</field>
            <field name="arch" type="xml">
                <form string="Book">
                    <header>
                        <button name="action_mark_borrowed" type="object" 
                                string="Mark as Borrowed" 
                                class="btn-primary"
                                invisible="status != 'available'"/>
                        <button name="action_mark_returned" type="object" 
                                string="Mark as Returned" 
                                class="btn-secondary"
                                invisible="status != 'borrowed'"/>
                        <field name="status" widget="statusbar" 
                               statusbar_visible="available,borrowed,lost"/>
                    </header>
                    <sheet>
                        <div class="oe_button_box" name="button_box">
                            <button name="action_mark_borrowed" type="object" 
                                    class="oe_stat_button" icon="fa-book">
                                <div class="o_field_widget o_stat_info">
                                    <span class="o_stat_text">Available</span>
                                </div>
                            </button>
                        </div>
                        <group>
                            <group>
                                <field name="name"/>
                                <field name="author"/>
                                <field name="isbn"/>
                                <field name="category_id"/>
                            </group>
                            <group>
                                <field name="status"/>
                                <field name="pages"/>
                                <field name="price"/>
                                <field name="is_fiction"/>
                            </group>
                        </group>
                        <group>
                            <field name="publication_date"/>
                            <field name="purchase_date"/>
                        </group>
                        <group>
                            <field name="description"/>
                        </group>
                        <group>
                            <field name="summary"/>
                        </group>
                        <group>
                            <field name="cover_image" widget="image" class="oe_avatar"/>
                        </group>
                    </sheet>
                </form>
            </field>
        </record>

        <!-- Book Search View -->
        <record id="view_book_search" model="ir.ui.view">
            <field name="name">book.management.search</field>
            <field name="model">book.management</field>
            <field name="arch" type="xml">
                <search string="Search Books">
                    <field name="name"/>
                    <field name="author"/>
                    <field name="isbn"/>
                    <field name="category_id"/>
                    <filter string="Available" name="available" 
                            domain="[('status', '=', 'available')]"/>
                    <filter string="Borrowed" name="borrowed" 
                            domain="[('status', '=', 'borrowed')]"/>
                    <filter string="Fiction" name="fiction" 
                            domain="[('is_fiction', '=', True)]"/>
                    <group expand="0" string="Group By">
                        <filter string="Category" name="category" 
                                context="{'group_by': 'category_id'}"/>
                        <filter string="Status" name="status" 
                                context="{'group_by': 'status'}"/>
                        <filter string="Author" name="author" 
                                context="{'group_by': 'author'}"/>
                    </group>
                </search>
            </field>
        </record>

        <!-- Book Action -->
        <record id="action_book" model="ir.actions.act_window">
            <field name="name">Books</field>
            <field name="res_model">book.management</field>
            <field name="view_mode">list,form</field>
            <field name="search_view_id" ref="view_book_search"/>
            <field name="context">{}</field>
            <field name="help" type="html">
                <p class="o_view_nocontent_smiling_face">
                    Create your first book!
                </p>
                <p>
                    Books can be organized by categories and tracked by status.
                </p>
            </field>
        </record>

        <!-- Category Tree View -->
        <record id="view_book_category_tree" model="ir.ui.view">
            <field name="name">book.category.tree</field>
            <field name="model">book.category</field>
            <field name="arch" type="xml">
                <list string="Book Categories">
                    <field name="name"/>
                    <field name="book_count"/>
                    <field name="description"/>
                </list>
            </field>
        </record>

        <!-- Category Form View -->
        <record id="view_book_category_form" model="ir.ui.view">
            <field name="name">book.category.form</field>
            <field name="model">book.category</field>
            <field name="arch" type="xml">
                <form string="Book Category">
                    <sheet>
                        <group>
                            <field name="name"/>
                            <field name="description"/>
                        </group>
                        <group>
                            <field name="book_ids">
                                <list>
                                    <field name="name"/>
                                    <field name="author"/>
                                    <field name="status"/>
                                </list>
                            </field>
                        </group>
                    </sheet>
                </form>
            </field>
        </record>

        <!-- Category Action -->
        <record id="action_book_category" model="ir.actions.act_window">
            <field name="name">Book Categories</field>
            <field name="res_model">book.category</field>
            <field name="view_mode">list,form</field>
        </record>

        <!-- Menu Items -->
        <menuitem id="menu_book_management" 
                  name="Book Management" 
                  web_icon="book_management,static/description/icon.png"/>
        
        <menuitem id="menu_book_management_books" 
                  name="Books" 
                  parent="menu_book_management" 
                  action="action_book"/>
        
        <menuitem id="menu_book_management_categories" 
                  name="Categories" 
                  parent="menu_book_management" 
                  action="action_book_category"/>
    </data>
</odoo>
```

### Step 10: Create Security Directory
```bash
mkdir security
```

### Step 11: Create Access Rights
Create `security/ir.model.access.csv`:
```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_book_management_user,book.management.user,model_book_management,base.group_user,1,1,1,0
access_book_management_manager,book.management.manager,model_book_management,base.group_system,1,1,1,1
access_book_category_user,book.category.user,model_book_category,base.group_user,1,1,1,0
access_book_category_manager,book.category.manager,model_book_category,base.group_system,1,1,1,1
```

### Step 12: Create Groups
Create `security/groups.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data>
        <record id="group_book_user" model="res.groups">
            <field name="name">Book User</field>
            <field name="category_id" ref="base.module_category_tools"/>
        </record>

        <record id="group_book_manager" model="res.groups">
            <field name="name">Book Manager</field>
            <field name="category_id" ref="base.module_category_tools"/>
            <field name="implied_ids" eval="[(4, ref('group_book_user'))]"/>
        </record>
    </data>
</odoo>
```

### Step 13: Create Data Directory
```bash
mkdir data
```

### Step 14: Create Initial Data
Create `data/book_data.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">
        <!-- Book Categories -->
        <record id="category_fiction" model="book.category">
            <field name="name">Fiction</field>
            <field name="description">Fictional books and novels</field>
        </record>

        <record id="category_non_fiction" model="book.category">
            <field name="name">Non-Fiction</field>
            <field name="description">Non-fictional books and references</field>
        </record>

        <record id="category_science" model="book.category">
            <field name="name">Science</field>
            <field name="description">Scientific books and research</field>
        </record>

        <!-- Sample Books -->
        <record id="book_1984" model="book.management">
            <field name="name">1984</field>
            <field name="author">George Orwell</field>
            <field name="isbn">978-0-452-28423-4</field>
            <field name="category_id" ref="category_fiction"/>
            <field name="pages">328</field>
            <field name="price">12.99</field>
            <field name="status">available</field>
            <field name="is_fiction">True</field>
            <field name="description">A dystopian novel set in a totalitarian society.</field>
        </record>

        <record id="book_cosmos" model="book.management">
            <field name="name">Cosmos</field>
            <field name="author">Carl Sagan</field>
            <field name="isbn">978-0-345-33135-9</field>
            <field name="category_id" ref="category_science"/>
            <field name="pages">384</field>
            <field name="price">15.99</field>
            <field name="status">available</field>
            <field name="is_fiction">False</field>
            <field name="description">A journey through the universe and scientific discovery.</field>
        </record>
    </data>
</odoo>
```

### Step 15: Create Static Directory
```bash
mkdir -p static/description
```

### Step 16: Add Module Icon
Add an icon file: `static/description/icon.png`

## Understanding Odoo Components

### Fields Explained

#### Basic Field Types
```python
# Text Fields
name = fields.Char('Title', required=True, help='Book title')
description = fields.Text('Description')  # Multi-line text
summary = fields.Html('Summary')  # Rich text with HTML

# Numeric Fields
pages = fields.Integer('Pages')  # Whole numbers
price = fields.Float('Price', digits=(16, 2))  # Decimal numbers

# Date Fields
publication_date = fields.Date('Publication Date')  # Date only
purchase_date = fields.Datetime('Purchase Date')  # Date and time

# Boolean Fields
is_fiction = fields.Boolean('Is Fiction', default=False)

# Selection Fields
status = fields.Selection([
    ('available', 'Available'),
    ('borrowed', 'Borrowed'),
], string='Status', default='available')

# Binary Fields
cover_image = fields.Binary('Cover Image')  # File upload
```

#### Relational Fields
```python
# Many2one (Foreign Key)
category_id = fields.Many2one('book.category', 'Category')

# One2many (Reverse Foreign Key)
book_ids = fields.One2many('book.management', 'category_id', 'Books')

# Many2many (Many-to-Many)
tag_ids = fields.Many2many('book.tag', 'book_tag_rel', 'book_id', 'tag_id', 'Tags')
```

#### Computed Fields
```python
display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)

@api.depends('name', 'author')
def _compute_display_name(self):
    for record in self:
        record.display_name = f"{record.name} - {record.author}"
```

### Views Explained

#### Tree View (List View)
```xml
<list string="Books" default_order="name">
    <field name="name"/>
    <field name="author"/>
    <field name="status" widget="badge"/>
</list>
```

#### Form View
```xml
<form string="Book">
    <header>
        <button name="action_method" type="object" string="Action"/>
        <field name="status" widget="statusbar"/>
    </header>
    <sheet>
        <group>
            <field name="name"/>
            <field name="author"/>
        </group>
    </sheet>
</form>
```

#### Search View
```xml
<search string="Search Books">
    <field name="name"/>
    <filter string="Available" domain="[('status', '=', 'available')]"/>
    <group expand="0" string="Group By">
        <filter string="Category" context="{'group_by': 'category_id'}"/>
    </group>
</search>
```

### Methods Explained

#### CRUD Methods
```python
@api.model
def create(self, vals):
    """Override create method"""
    # Custom logic before creation
    return super(Book, self).create(vals)

def write(self, vals):
    """Override write method"""
    # Custom logic before update
    return super(Book, self).write(vals)

def unlink(self):
    """Override delete method"""
    # Custom logic before deletion
    return super(Book, self).unlink()
```

#### Business Logic Methods
```python
def action_mark_borrowed(self):
    """Business method"""
    self.write({'status': 'borrowed'})

@api.model
def get_available_books(self):
    """Class method"""
    return self.search([('status', '=', 'available')])
```

## Testing and Debugging

### 1. Install Module
```bash
# Restart Odoo
python3 odoo-bin -c odoo.conf

# Install from Apps menu or command line
python3 odoo-bin -c odoo.conf -i book_management --stop-after-init
```

### 2. Debug Module
```python
import logging
_logger = logging.getLogger(__name__)

def debug_method(self):
    _logger.info("Debug message")
    print("Debug info")
```

### 3. Update Module
```bash
# Update module
python3 odoo-bin -c odoo.conf -u book_management --stop-after-init
```

### 4. Common Issues and Solutions

#### Module Not Found
- Check `addons_path` in `odoo.conf`
- Verify module directory structure
- Check `__manifest__.py` syntax

#### Import Errors
- Check `__init__.py` files
- Verify model names and imports
- Check Python syntax

#### View Errors
- Validate XML syntax
- Check field names match model
- Verify view inheritance

## Best Practices

### 1. Code Organization
- Keep models in separate files
- Use descriptive names
- Add comments and docstrings
- Follow PEP 8 style guide

### 2. Security
- Define proper access rights
- Use groups for permissions
- Validate user input
- Use `@api.model` and `@api.multi` decorators

### 3. Performance
- Use `@api.depends` for computed fields
- Avoid N+1 queries
- Use `search()` with proper domains
- Cache frequently used data

### 4. User Experience
- Provide helpful error messages
- Use appropriate widgets
- Add help text to fields
- Create intuitive menu structures

### 5. Maintenance
- Version your modules
- Document your code
- Test thoroughly
- Keep dependencies minimal

## Next Steps

### Advanced Topics
1. **Inheritance**: Extending existing models and views
2. **Wizards**: Creating popup dialogs
3. **Reports**: Generating PDF and Excel reports
4. **Automation**: Scheduled actions and workflows
5. **API**: Creating REST APIs
6. **Webhooks**: Real-time integrations
7. **Multi-company**: Handling multiple companies
8. **Localization**: Multi-language support

### Resources
- [Odoo Documentation](https://www.odoo.com/documentation/18.0/)
- [Odoo Community](https://www.odoo.com/community)
- [GitHub Examples](https://github.com/odoo/odoo)
- [Odoo Development Tutorials](https://www.odoo.com/documentation/18.0/developer.html)

This guide provides a solid foundation for Odoo development. Start with this simple book management module and gradually add more complex features as you become comfortable with the framework.


