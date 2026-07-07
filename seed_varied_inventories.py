import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
from app.core.database import async_session_maker
from app.models.workshop import Workshop
from app.models.inventory_category import InventoryCategory
from app.models.supplier import Supplier
from app.models.inventory_product import InventoryProduct
from app.models.inventory_movement import InventoryMovement
from app.models.marketplace_listing import MarketplaceListing
from app.models.promotion import Promotion
from app.models.stock_alert import StockAlert

# Clean all existing seed inventory and marketplace tables first to avoid unique constraints
async def clean_existing_data(session):
    print("Cleaning existing inventory and marketplace data...")
    await session.execute(delete(Promotion))
    await session.execute(delete(MarketplaceListing))
    await session.execute(delete(StockAlert))
    await session.execute(delete(InventoryMovement))
    await session.execute(delete(InventoryProduct))
    await session.execute(delete(InventoryCategory))
    await session.execute(delete(Supplier))
    await session.commit()
    print("Cleaning complete.")

async def main():
    async with async_session_maker()() as session:
        # 1. Clean existing seed data
        await clean_existing_data(session)

        # 2. Get registered workshops
        stmt = select(Workshop)
        res = await session.execute(stmt)
        workshops = res.scalars().all()
        
        if not workshops:
            print("No workshops found to seed.")
            return

        print(f"Seeding inventory and marketplace for {len(workshops)} workshops.")

        # Define varied seed configuration for each workshop tenant
        # Workshop ID: 50 (Tenant 2), 60 (Tenant 3), 51 (Tenant 1), 62 (Tenant 5), 61 (Tenant 4), 63 (Tenant 6)
        seed_configs = {
            2: { # Brotors
                "suppliers": [
                    {"name": "Importadora Japonesa Repuestos", "contact_name": "Kenji Sato", "email": "kenji@japonesa.bo", "phone": "77112233", "notes": "Especialista en repuestos de motor japoneses"},
                    {"name": "Transmisiones Warnes S.R.L.", "contact_name": "Carlos Gomez", "email": "carlos@warnestrans.bo", "phone": "70114455", "notes": "Cajas y repuestos de transmisión"}
                ],
                "categories": [
                    {"name": "Motor y Culata", "description": "Pistones, anillos, empaques y partes internas de motor", "icon": "build"},
                    {"name": "Transmisión y Cajas", "description": "Cajas de cambio, kits de embrague y cardanes", "icon": "settings"},
                    {"name": "Mantenimiento Express", "description": "Filtros y bujías", "icon": "speed"}
                ],
                "products": [
                    {
                        "name": "Pistones Toyota Hilux 2.7 2TR-FE", "sku": "BR-PIS-01", "barcode": "7891011120010", "brand": "Toyota", "part_number": "13101-75120",
                        "current_stock": 8, "min_stock": 2, "unit": "juego", "location": "Estante A-3", "cost_price": 120.00,
                        "compatible_brands": ["Toyota"], "compatible_models": ["Hilux", "Tacoma"], "compatible_years": {"start": 2005, "end": 2020},
                        "universal": False, "image_url": "https://images.unsplash.com/photo-1486006920555-c77dce18193b?q=80&w=300",
                        "market_price": 160.00, "is_featured": True, "market_desc": "Juego de pistones estándar originales para motor Toyota 2.7L gasolina."
                    },
                    {
                        "name": "Kit de Embrague Nissan Frontier", "sku": "BR-EMB-02", "barcode": "7891011120027", "brand": "Exedy", "part_number": "NSK-7236",
                        "current_stock": 3, "min_stock": 1, "unit": "unidad", "location": "Estante B-1", "cost_price": 180.00,
                        "compatible_brands": ["Nissan"], "compatible_models": ["Frontier", "Navara"], "compatible_years": {"start": 2008, "end": 2018},
                        "universal": False, "image_url": "https://images.unsplash.com/photo-1517524206127-48bbd363f3d7?q=80&w=300",
                        "market_price": 235.00, "is_featured": False, "market_desc": "Kit completo de embrague Exedy reforzado japonés para trabajo pesado."
                    },
                    {
                        "name": "Caja de Cambios Manual Suzuki Grand Vitara", "sku": "BR-CAJ-03", "barcode": "7891011120034", "brand": "Suzuki", "part_number": "20005-65D10",
                        "current_stock": 1, "min_stock": 2, # Low stock alert!
                        "unit": "unidad", "location": "Bodega Piso 1", "cost_price": 750.00,
                        "compatible_brands": ["Suzuki"], "compatible_models": ["Grand Vitara", "Vitara"], "compatible_years": {"start": 2006, "end": 2015},
                        "universal": False, "image_url": "https://images.unsplash.com/photo-1581092160607-ee22621dd758?q=80&w=300",
                        "market_price": 950.00, "is_featured": True, "market_desc": "Caja de cambios manual de 5 velocidades reconstruida con garantía de 6 meses."
                    }
                ],
                "discount": 10.0 # 10% promo
            },
            3: { # AlfreTors
                "suppliers": [
                    {"name": "Frenos La Paz Import", "contact_name": "Alfredo Siles", "email": "siles@frenoslp.bo", "phone": "73030400", "notes": "Pastillas, discos y cilindros de freno"},
                    {"name": "Amortiguadores del Sur", "contact_name": "Raul Vargas", "email": "raul@amorsur.bo", "phone": "68010203", "notes": "Distribuidor oficial KYB y Tokico"}
                ],
                "categories": [
                    {"name": "Frenos y Seguridad", "description": "Discos, pastillas, zapatas e hidráulica de frenos", "icon": "warning"},
                    {"name": "Suspensión y Dirección", "description": "Amortiguadores, resortes y terminales de dirección", "icon": "swap_vert"}
                ],
                "products": [
                    {
                        "name": "Pastillas de Freno Cerámicas Corolla", "sku": "AL-PAS-01", "barcode": "7892011120019", "brand": "Bosch", "part_number": "BP1210",
                        "current_stock": 25, "min_stock": 5, "unit": "juego", "location": "Caja F-12", "cost_price": 22.00,
                        "compatible_brands": ["Toyota"], "compatible_models": ["Corolla", "Auris"], "compatible_years": {"start": 2008, "end": 2019},
                        "universal": False, "image_url": "https://images.unsplash.com/photo-1619642751034-765dfdf7c58e?q=80&w=300",
                        "market_price": 32.00, "is_featured": True, "market_desc": "Pastillas de freno Bosch cerámicas. Frenado óptimo sin ruidos ni polvo."
                    },
                    {
                        "name": "Amortiguadores Traseros KYB Rav4", "sku": "AL-AMO-02", "barcode": "7892011120026", "brand": "KYB", "part_number": "341492",
                        "current_stock": 4, "min_stock": 2, "unit": "par", "location": "Estante S-1", "cost_price": 105.00,
                        "compatible_brands": ["Toyota"], "compatible_models": ["Rav4"], "compatible_years": {"start": 2006, "end": 2016},
                        "universal": False, "image_url": "https://images.unsplash.com/photo-1616788494707-ec28f08d05a1?q=80&w=300",
                        "market_price": 140.00, "is_featured": True, "market_desc": "Amortiguadores de gas KYB Excel-G, restituyen el control original de fábrica."
                    },
                    {
                        "name": "Discos de Freno Delanteros Civic", "sku": "AL-DIS-03", "barcode": "7892011120033", "brand": "Brembo", "part_number": "09.A451.10",
                        "current_stock": 0, "min_stock": 3, # Out of stock!
                        "unit": "par", "location": "Estante F-2", "cost_price": 80.00,
                        "compatible_brands": ["Honda"], "compatible_models": ["Civic"], "compatible_years": {"start": 2006, "end": 2015},
                        "universal": False, "image_url": "https://images.unsplash.com/photo-1549399542-7e3f8b79c341?q=80&w=300",
                        "market_price": 115.00, "is_featured": False, "market_desc": "Discos de freno Brembo lisos premium con ventilación interna."
                    }
                ],
                "discount": 15.0
            },
            1: { # PepeMot
                "suppliers": [
                    {"name": "Baterías Toyo y Varta", "contact_name": "Enrique Toyo", "email": "enrique@toyo.bo", "phone": "78945612", "notes": "Proveedor de baterías selladas"},
                    {"name": "Autoelectro Santa Cruz", "contact_name": "Luis Vaca", "email": "luis@autoelectrosc.bo", "phone": "70750600", "notes": "Motores de arranque, fusibles y cables"}
                ],
                "categories": [
                    {"name": "Baterías", "description": "Baterías para autos y camionetas de 12V", "icon": "battery_charging_full"},
                    {"name": "Iluminación y Eléctrico", "description": "Focos, alternadores, arrancadores y sensores", "icon": "flash_on"}
                ],
                "products": [
                    {
                        "name": "Batería Varta Blue 75AH", "sku": "PE-BAT-01", "barcode": "7893011120018", "brand": "Varta", "part_number": "E11-75",
                        "current_stock": 15, "min_stock": 3, "unit": "unidad", "location": "Piso Baterías", "cost_price": 90.00,
                        "compatible_brands": [], "compatible_models": [], "compatible_years": {},
                        "universal": True, "image_url": "https://images.unsplash.com/photo-1620939514049-63a591e38466?q=80&w=300",
                        "market_price": 125.00, "is_featured": True, "market_desc": "Batería sellada Varta alemana de 75 Amperios. Mayor fiabilidad en arranque."
                    },
                    {
                        "name": "Focos LED H4 Philips Ultinon", "sku": "PE-LED-02", "barcode": "7893011120025", "brand": "Philips", "part_number": "11342ULX2",
                        "current_stock": 30, "min_stock": 5, "unit": "juego", "location": "Caja L-02", "cost_price": 18.00,
                        "compatible_brands": [], "compatible_models": [], "compatible_years": {},
                        "universal": True, "image_url": "https://images.unsplash.com/photo-1508974239320-0a029497e820?q=80&w=300",
                        "market_price": 26.00, "is_featured": False, "market_desc": "Kit de focos luces LED Philips H4. Iluminación blanca brillante y nítida."
                    },
                    {
                        "name": "Alternador Denso Suzuki Swift", "sku": "PE-ALT-03", "barcode": "7893011120032", "brand": "Denso", "part_number": "102211-1960",
                        "current_stock": 1, "min_stock": 2, # Low stock alert!
                        "unit": "unidad", "location": "Estante E-4", "cost_price": 135.00,
                        "compatible_brands": ["Suzuki"], "compatible_models": ["Swift", "Dzire"], "compatible_years": {"start": 2010, "end": 2018},
                        "universal": False, "image_url": "https://images.unsplash.com/photo-1605559424843-9e4c228bf1c2?q=80&w=300",
                        "market_price": 175.00, "is_featured": True, "market_desc": "Alternador original Denso para motores Suzuki Swift M13A/M15A."
                    }
                ],
                "discount": 5.0
            },
            5: { # GoTorners
                "suppliers": [
                    {"name": "Llantas Continental Bolivia", "contact_name": "Mario Rivas", "email": "mario@continental.bo", "phone": "72090800", "notes": "Distribución directa llantas alemanas"}
                ],
                "categories": [
                    {"name": "Neumáticos y Llantas", "description": "Llantas de auto, SUV y camioneta de varias medidas", "icon": "adjust"},
                    {"name": "Accesorios de Rueda", "description": "Pernos de seguridad y válvulas", "icon": "build"}
                ],
                "products": [
                    {
                        "name": "Llanta Continental 205/55R16 MC6", "sku": "GO-LLA-01", "barcode": "7894011120017", "brand": "Continental", "part_number": "0356205",
                        "current_stock": 20, "min_stock": 4, "unit": "unidad", "location": "Rack Principal", "cost_price": 68.00,
                        "compatible_brands": [], "compatible_models": [], "compatible_years": {},
                        "universal": True, "image_url": "https://images.unsplash.com/photo-1578844251758-2f71da64c96f?q=80&w=300",
                        "market_price": 89.00, "is_featured": True, "market_desc": "Llanta Continental MaxContact MC6. Alto agarre, frenado seguro y estabilidad."
                    },
                    {
                        "name": "Pernos Antirrobo de Seguridad Rueda", "sku": "GO-PER-02", "barcode": "7894011120024", "brand": "McGard", "part_number": "24157",
                        "current_stock": 15, "min_stock": 3, "unit": "juego", "location": "Caja P-4", "cost_price": 14.00,
                        "compatible_brands": [], "compatible_models": [], "compatible_years": {},
                        "universal": True, "image_url": "https://images.unsplash.com/photo-1590674899484-d5640e854abe?q=80&w=300",
                        "market_price": 22.00, "is_featured": False, "market_desc": "Juego de 4 pernos de seguridad con llave única para proteger tus llantas."
                    }
                ],
                "discount": 12.0
            },
            4: { # GroveMotors
                "suppliers": [
                    {"name": "Lubricantes Mobil Bolivia", "contact_name": "Julio Castro", "email": "julio@mobil.bo", "phone": "71155000", "notes": "Lubricantes y aditivos sintéticos"},
                    {"name": "Importadora Mann Filter", "contact_name": "Gunter Schultz", "email": "gunter@mann.bo", "phone": "76600888", "notes": "Filtros de aire, aceite, cabina y diesel"}
                ],
                "categories": [
                    {"name": "Lubricantes y Aditivos", "description": "Aceites de motor sintéticos y minerales, líquidos de freno", "icon": "opacity"},
                    {"name": "Filtros", "description": "Filtros de aire, aceite y combustible automotriz", "icon": "filter_alt"}
                ],
                "products": [
                    {
                        "name": "Aceite Sintético Mobil 1 5W-30 4L", "sku": "GR-ACE-01", "barcode": "7895011120016", "brand": "Mobil", "part_number": "124317",
                        "current_stock": 40, "min_stock": 8, "unit": "unidad", "location": "Estante Aceites", "cost_price": 38.00,
                        "compatible_brands": [], "compatible_models": [], "compatible_years": {},
                        "universal": True, "image_url": "https://images.unsplash.com/photo-1527631746610-bca00a040d60?q=80&w=300",
                        "market_price": 54.00, "is_featured": True, "market_desc": "Aceite para motor 100% sintético avanzado. Protege contra el desgaste."
                    },
                    {
                        "name": "Filtro de Aire Mann Toyota Corolla", "sku": "GR-FIL-02", "barcode": "7895011120023", "brand": "Mann Filter", "part_number": "C 24 016",
                        "current_stock": 2, "min_stock": 5, # Low stock alert!
                        "unit": "unidad", "location": "Caja M-1", "cost_price": 10.00,
                        "compatible_brands": ["Toyota"], "compatible_models": ["Corolla"], "compatible_years": {"start": 2008, "end": 2018},
                        "universal": False, "image_url": "https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?q=80&w=300",
                        "market_price": 15.00, "is_featured": False, "market_desc": "Filtro de aire Mann-Filter de alto flujo. Protege el motor del polvo."
                    }
                ],
                "discount": 8.0
            },
            6: { # VertolPern
                "suppliers": [
                    {"name": "Carrocerías del Oriente", "contact_name": "Fabio Soliz", "email": "fabio@carrocerias.bo", "phone": "75040900", "notes": "Parachoques, capots y guardabarros"},
                    {"name": "Importadora AutoLuz", "contact_name": "Oscar Ortiz", "email": "oscar@autoluz.bo", "phone": "79012345", "notes": "Faros, guiñadores y neblineros"}
                ],
                "categories": [
                    {"name": "Faros y Ópticas", "description": "Faros principales, traseros y lámparas auxiliares", "icon": "lightbulb"},
                    {"name": "Carrocería Exterior", "description": "Guardabarros, parachoques y espejos laterales", "icon": "directions_car"}
                ],
                "products": [
                    {
                        "name": "Faro Derecho Hilux 2020-2023", "sku": "VE-FAR-01", "barcode": "7896011120015", "brand": "TYC", "part_number": "20-9283-00-1A",
                        "current_stock": 5, "min_stock": 1, "unit": "unidad", "location": "Cajas Grandes", "cost_price": 85.00,
                        "compatible_brands": ["Toyota"], "compatible_models": ["Hilux"], "compatible_years": {"start": 2020, "end": 2023},
                        "universal": False, "image_url": "https://images.unsplash.com/photo-1549399542-7e3f8b79c341?q=80&w=300",
                        "market_price": 120.00, "is_featured": True, "market_desc": "Faro delantero derecho de reemplazo marca TYC homologado."
                    },
                    {
                        "name": "Espejo Lateral Eléctrico Swift", "sku": "VE-ESP-02", "barcode": "7896011120022", "brand": "Suzuki", "part_number": "84701-58M10",
                        "current_stock": 0, "min_stock": 2, # Out of stock alert!
                        "unit": "unidad", "location": "Estante Espejos", "cost_price": 45.00,
                        "compatible_brands": ["Suzuki"], "compatible_models": ["Swift"], "compatible_years": {"start": 2011, "end": 2017},
                        "universal": False, "image_url": "https://images.unsplash.com/photo-1502877338535-766e1452684a?q=80&w=300",
                        "market_price": 68.00, "is_featured": False, "market_desc": "Espejo retrovisor izquierdo eléctrico con acabado negro original."
                    }
                ],
                "discount": 10.0
            }
        }

        # Seed data loop
        for w in workshops:
            tenant_id = w.tenant_id
            if tenant_id not in seed_configs:
                continue
            
            config = seed_configs[tenant_id]
            print(f"Seeding for {w.workshop_name} (Tenant {tenant_id})...")

            # 2.1 Seed Suppliers
            db_suppliers = []
            for sup in config["suppliers"]:
                db_sup = Supplier(
                    tenant_id=tenant_id,
                    name=sup["name"],
                    contact_name=sup["contact_name"],
                    email=sup["email"],
                    phone=sup["phone"],
                    address="Av. Banzer 4to Anillo",
                    city="Santa Cruz",
                    country="Bolivia",
                    notes=sup["notes"],
                    is_active=True
                )
                session.add(db_sup)
                db_suppliers.append(db_sup)
            
            # Flush to get supplier IDs
            await session.flush()

            # 2.2 Seed Categories
            db_categories = []
            for cat in config["categories"]:
                db_cat = InventoryCategory(
                    tenant_id=tenant_id,
                    name=cat["name"],
                    description=cat["description"],
                    icon=cat["icon"],
                    is_active=True
                )
                session.add(db_cat)
                db_categories.append(db_cat)
            
            await session.flush()

            # 2.3 Seed Products, Movements, Alerts and Listings
            for idx, prod in enumerate(config["products"]):
                cat_obj = db_categories[idx % len(db_categories)]
                sup_obj = db_suppliers[idx % len(db_suppliers)]

                db_prod = InventoryProduct(
                    tenant_id=tenant_id,
                    category_id=cat_obj.id,
                    supplier_id=sup_obj.id,
                    sku=prod["sku"],
                    barcode=prod["barcode"],
                    name=prod["name"],
                    description="Repuesto de alta calidad garantizado.",
                    brand=prod["brand"],
                    part_number=prod["part_number"],
                    current_stock=prod["current_stock"],
                    min_stock=prod["min_stock"],
                    unit=prod["unit"],
                    location=prod["location"],
                    cost_price=prod["cost_price"],
                    avg_cost_price=prod["cost_price"],
                    compatible_brands=prod["compatible_brands"],
                    compatible_models=prod["compatible_models"],
                    compatible_years=prod["compatible_years"],
                    universal=prod["universal"],
                    is_active=True,
                    is_published=True, # Published to marketplace
                    image_url=prod["image_url"]
                )
                session.add(db_prod)
                await session.flush()

                # Add initial InventoryMovement (setting stock)
                if prod["current_stock"] > 0:
                    movement = InventoryMovement(
                        tenant_id=tenant_id,
                        product_id=db_prod.id,
                        type="entrada",
                        quantity=prod["current_stock"],
                        unit_cost=prod["cost_price"],
                        total_cost=prod["cost_price"] * prod["current_stock"],
                        reference_type="compra",
                        stock_before=0,
                        stock_after=prod["current_stock"],
                        notes="Inventario inicial seed.",
                        created_by=w.id # Workshop user ID
                    )
                    session.add(movement)

                # Add StockAlert if current stock is low or out of stock
                if prod["current_stock"] <= prod["min_stock"]:
                    alert = StockAlert(
                        tenant_id=tenant_id,
                        product_id=db_prod.id,
                        alert_type="out_of_stock" if prod["current_stock"] == 0 else "low_stock",
                        current_stock=prod["current_stock"],
                        threshold=prod["min_stock"],
                        is_read=False,
                        is_resolved=False
                    )
                    session.add(alert)

                # Create Marketplace Listing
                listing = MarketplaceListing(
                    tenant_id=tenant_id,
                    product_id=db_prod.id,
                    public_price=prod["market_price"],
                    compare_at_price=prod["market_price"] * 1.15, # Set a past higher price
                    is_visible=True,
                    is_featured=prod["is_featured"],
                    title=prod["name"],
                    description=prod["market_desc"],
                    slug=prod["name"].lower().replace(" ", "-"),
                    status="active" if prod["current_stock"] > 0 else "sold_out",
                    published_at=datetime.utcnow() - timedelta(days=5)
                )
                session.add(listing)
                await session.flush()

                # Create active promotion for some items
                if prod["is_featured"] and "discount" in config:
                    promo = Promotion(
                        tenant_id=tenant_id,
                        name=f"Descuento Especial {config['discount']}%",
                        description=f"Descuento en repuestos seleccionados del taller {w.workshop_name}.",
                        type="percentage",
                        value=config["discount"],
                        applies_to="listing",
                        target_ids=[listing.id],
                        starts_at=datetime.utcnow() - timedelta(days=2),
                        ends_at=datetime.utcnow() + timedelta(days=10),
                        is_active=True
                    )
                    session.add(promo)

        await session.commit()
        print("Inventory and Marketplace tables seeded successfully with unique and varied records per workshop!")

if __name__ == "__main__":
    asyncio.run(main())
