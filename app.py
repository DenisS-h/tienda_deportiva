from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from unidecode import unidecode
from flask_migrate import Migrate
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tu-clave-secreta-aqui'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

# Modelo para usuarios
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.now)
    # Relaciones
    pedidos = db.relationship('Pedido', backref='usuario', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Modelo para productos
class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    precio = db.Column(db.Float, nullable=False)
    imagen = db.Column(db.String(200))
    categoria = db.Column(db.String(50), nullable=False)
    stock = db.Column(db.Integer, default=0)
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    en_oferta = db.Column(db.Boolean, default=False)
    precio_oferta = db.Column(db.Float)
    # Relaciones
    items_pedido = db.relationship('ItemPedido', backref='producto', lazy=True)

# Modelo para pedidos
class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.now)
    estado = db.Column(db.String(50), default='pendiente')
    total = db.Column(db.Float, nullable=False)
    # Relaciones
    items = db.relationship('ItemPedido', backref='pedido', lazy=True, cascade="all, delete-orphan")

# Modelo para items de pedido
class ItemPedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('producto.id'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_unitario = db.Column(db.Float, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Inicialización del carrito en la sesión
@app.before_request
def inicializar_carrito():
    if 'carrito' not in session:
        session['carrito'] = []

# Rutas principales
@app.route('/')
def index():
    orden = request.args.get('orden', '')
    productos_query = Producto.query
    
    if orden == 'precio_asc':
        productos_query = productos_query.order_by(Producto.precio.asc())
    elif orden == 'precio_desc':
        productos_query = productos_query.order_by(Producto.precio.desc())
    elif orden == 'recientes':
        productos_query = productos_query.order_by(Producto.fecha_creacion.desc())
    
    productos = productos_query.all()
    return render_template('index.html', productos=productos)

@app.route('/buscar')
def buscar_productos():
    busqueda = request.args.get('q', '')
    if not busqueda:
        return redirect(url_for('index'))
        
    # Buscar en nombre y descripción
    productos = Producto.query.filter(
        (Producto.nombre.ilike(f'%{busqueda}%')) | 
        (Producto.descripcion.ilike(f'%{busqueda}%'))
    ).all()
    
    return render_template('busqueda.html', productos=productos, busqueda=busqueda)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            flash('¡Inicio de sesión exitoso!', 'success')
            return redirect(next_page or url_for('index'))
        flash('Email o contraseña incorrectos', 'danger')
    
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validaciones
        if not name or not email or not password:
            flash('Todos los campos son obligatorios', 'danger')
            return redirect(url_for('registro'))
            
        if password != confirm_password:
            flash('Las contraseñas no coinciden', 'danger')
            return redirect(url_for('registro'))
            
        if User.query.filter_by(email=email).first():
            flash('Este correo electrónico ya está registrado', 'danger')
            return redirect(url_for('registro'))
        
        # Crear nuevo usuario
        new_user = User(name=name, email=email)
        new_user.set_password(password)
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('¡Registro exitoso! Ahora puedes iniciar sesión', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Error al registrar el usuario', 'danger')
    
    return render_template('registro.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión exitosamente', 'success')
    return redirect(url_for('index'))

# Rutas de productos y categorías
@app.route('/categoria/<categoria>')
def productos_por_categoria(categoria):
    # Verificar que la categoría sea válida
    categorias_validas = ['top', 'legging', 'short', 'camiseta', 'pantalon', 'soporte', 'guante', 'banda', 'toalla']
    
    if categoria not in categorias_validas:
        flash('Categoría no válida', 'danger')
        return redirect(url_for('index'))
    
    # Obtener productos de la categoría
    productos = Producto.query.filter_by(categoria=categoria).all()
    
    # Determinar el nombre de visualización de la categoría
    nombres_categorias = {
        'top': 'Tops Deportivos',
        'legging': 'Leggings',
        'short': 'Shorts',
        'camiseta': 'Camisetas Dry-Fit',
        'pantalon': 'Pantalones Training',
        'soporte': 'Soportes',
        'guante': 'Guantes',
        'banda': 'Bandas Elásticas',
        'toalla': 'Toallas'
    }
    
    titulo_categoria = nombres_categorias.get(categoria, categoria.capitalize())
    
    return render_template('categoria.html', productos=productos, categoria=titulo_categoria)

@app.route('/nuevos')
def nuevos_lanzamientos():
    # Productos de los últimos 30 días
    limite_tiempo = datetime.now() - timedelta(days=30)
    productos = Producto.query.filter(Producto.fecha_creacion >= limite_tiempo).all()
    return render_template('categoria.html', productos=productos, categoria="Nuevos Lanzamientos")

@app.route('/ofertas')
def ofertas():
    # Productos en oferta
    productos = Producto.query.filter_by(en_oferta=True).all()
    return render_template('categoria.html', productos=productos, categoria="Ofertas Especiales")

@app.route('/producto/<int:producto_id>')
def detalles_producto(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    return render_template('detalles_producto.html', producto=producto)

# Gestión del carrito
@app.route('/carrito')
def ver_carrito():
    carrito = session.get('carrito', [])
    total = 0
    productos_carrito = []
    
    for item in carrito:
        producto = Producto.query.get(item['id'])
        if producto:
            cantidad = item['cantidad']
            precio = producto.precio_oferta if producto.en_oferta and producto.precio_oferta else producto.precio
            subtotal = precio * cantidad
            total += subtotal
            
            productos_carrito.append({
                'id': producto.id,
                'nombre': producto.nombre,
                'precio': precio,
                'cantidad': cantidad,
                'subtotal': subtotal,
                'imagen': producto.imagen
            })
    
    return render_template('carrito.html', productos=productos_carrito, total=total)

@app.route('/añadir_al_carrito', methods=['POST'])
def añadir_al_carrito():
    producto_id = request.form.get('producto_id', type=int)
    cantidad = request.form.get('cantidad', 1, type=int)
    
    if not producto_id or cantidad < 1:
        flash('Datos inválidos', 'danger')
        return redirect(url_for('index'))
    
    producto = Producto.query.get_or_404(producto_id)
    
    # Verificar stock
    if producto.stock < cantidad:
        flash(f'Lo sentimos, solo tenemos {producto.stock} unidades disponibles', 'warning')
        return redirect(url_for('detalles_producto', producto_id=producto_id))
    
    carrito = session.get('carrito', [])
    
    # Buscar si el producto ya está en el carrito
    item_existente = next((item for item in carrito if item['id'] == producto_id), None)
    
    if item_existente:
        # Actualizar cantidad
        nueva_cantidad = item_existente['cantidad'] + cantidad
        if nueva_cantidad > producto.stock:
            flash(f'No se puede añadir más unidades. Stock disponible: {producto.stock}', 'warning')
            return redirect(url_for('detalles_producto', producto_id=producto_id))
        
        item_existente['cantidad'] = nueva_cantidad
    else:
        # Añadir nuevo item
        carrito.append({'id': producto_id, 'cantidad': cantidad})
    
    session['carrito'] = carrito
    flash(f'¡{producto.nombre} añadido al carrito!', 'success')
    
    # Redireccionar según el botón presionado
    if 'comprar_ahora' in request.form:
        return redirect(url_for('ver_carrito'))
    return redirect(request.referrer or url_for('index'))

@app.route('/actualizar_carrito', methods=['POST'])
def actualizar_carrito():
    producto_id = request.form.get('producto_id', type=int)
    cantidad = request.form.get('cantidad', 1, type=int)
    
    if not producto_id or cantidad < 0:
        flash('Datos inválidos', 'danger')
        return redirect(url_for('ver_carrito'))
    
    producto = Producto.query.get_or_404(producto_id)
    carrito = session.get('carrito', [])
    
    # Encontrar el producto en el carrito
    for item in carrito:
        if item['id'] == producto_id:
            if cantidad == 0:
                # Eliminar producto
                carrito.remove(item)
                flash(f'{producto.nombre} eliminado del carrito', 'info')
            else:
                # Verificar stock
                if cantidad > producto.stock:
                    flash(f'Stock disponible: {producto.stock}', 'warning')
                    cantidad = producto.stock
                
                # Actualizar cantidad
                item['cantidad'] = cantidad
                flash('Carrito actualizado', 'success')
            break
    
    session['carrito'] = carrito
    return redirect(url_for('ver_carrito'))

@app.route('/eliminar_del_carrito/<int:producto_id>')
def eliminar_del_carrito(producto_id):
    carrito = session.get('carrito', [])
    
    # Encontrar y eliminar el producto
    for item in carrito:
        if item['id'] == producto_id:
            carrito.remove(item)
            break
    
    session['carrito'] = carrito
    flash('Producto eliminado del carrito', 'info')
    return redirect(url_for('ver_carrito'))

@app.route('/vaciar_carrito')
def vaciar_carrito():
    session['carrito'] = []
    flash('Carrito vaciado', 'info')
    return redirect(url_for('ver_carrito'))

# Proceso de compra
@app.route('/checkout')
@login_required
def checkout():
    carrito = session.get('carrito', [])
    
    if not carrito:
        flash('Tu carrito está vacío', 'warning')
        return redirect(url_for('index'))
    
    total = 0
    productos_checkout = []
    
    for item in carrito:
        producto = Producto.query.get(item['id'])
        if producto:
            cantidad = item['cantidad']
            precio = producto.precio_oferta if producto.en_oferta and producto.precio_oferta else producto.precio
            subtotal = precio * cantidad
            total += subtotal
            
            productos_checkout.append({
                'id': producto.id,
                'nombre': producto.nombre,
                'precio': precio,
                'cantidad': cantidad,
                'subtotal': subtotal
            })
    
    return render_template('checkout.html', productos=productos_checkout, total=total)

@app.route('/procesar_pedido', methods=['POST'])
@login_required
def procesar_pedido():
    carrito = session.get('carrito', [])
    
    if not carrito:
        flash('Tu carrito está vacío', 'warning')
        return redirect(url_for('index'))
    
    # Calcular total
    total = 0
    items_pedido = []
    
    for item in carrito:
        producto = Producto.query.get(item['id'])
        if producto:
            cantidad = item['cantidad']
            
            # Verificar stock antes de confirmar
            if producto.stock < cantidad:
                flash(f'Stock insuficiente para {producto.nombre}', 'danger')
                return redirect(url_for('checkout'))
            
            # Calcular precio
            precio = producto.precio_oferta if producto.en_oferta and producto.precio_oferta else producto.precio
            subtotal = precio * cantidad
            total += subtotal
            
            # Guardar datos del item
            items_pedido.append({
                'producto_id': producto.id,
                'cantidad': cantidad,
                'precio_unitario': precio
            })
            
            # Actualizar stock
            producto.stock -= cantidad
    
    try:
        # Crear pedido
        nuevo_pedido = Pedido(
            user_id=current_user.id,
            total=total,
            estado='pendiente'
        )
        db.session.add(nuevo_pedido)
        db.session.flush()  # Para obtener el ID del pedido
        
        # Añadir items al pedido
        for item in items_pedido:
            nuevo_item = ItemPedido(
                pedido_id=nuevo_pedido.id,
                producto_id=item['producto_id'],
                cantidad=item['cantidad'],
                precio_unitario=item['precio_unitario']
            )
            db.session.add(nuevo_item)
        
        # Guardar cambios y vaciar carrito
        db.session.commit()
        session['carrito'] = []
        
        flash('¡Pedido realizado con éxito!', 'success')
        return redirect(url_for('confirmacion_pedido', pedido_id=nuevo_pedido.id))
        
    except Exception as e:
        db.session.rollback()
        flash('Error al procesar el pedido', 'danger')
        return redirect(url_for('checkout'))

@app.route('/confirmacion/<int:pedido_id>')
@login_required
def confirmacion_pedido(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Verificar que el pedido pertenezca al usuario actual
    if pedido.user_id != current_user.id:
        flash('No tienes permiso para ver este pedido', 'danger')
        return redirect(url_for('index'))
    
    # Obtener items del pedido
    items = []
    for item in pedido.items:
        producto = Producto.query.get(item.producto_id)
        if producto:
            items.append({
                'nombre': producto.nombre,
                'cantidad': item.cantidad,
                'precio': item.precio_unitario,
                'subtotal': item.precio_unitario * item.cantidad
            })
    
    return render_template('confirmacion.html', pedido=pedido, items=items)

@app.route('/mis_pedidos')
@login_required
def mis_pedidos():
    pedidos = Pedido.query.filter_by(user_id=current_user.id).order_by(Pedido.fecha.desc()).all()
    return render_template('mis_pedidos.html', pedidos=pedidos)

@app.route('/detalles_pedido/<int:pedido_id>')
@login_required
def detalles_pedido(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    
    # Verificar que el pedido pertenezca al usuario actual
    if pedido.user_id != current_user.id:
        flash('No tienes permiso para ver este pedido', 'danger')
        return redirect(url_for('mis_pedidos'))
    
    # Obtener items del pedido con detalles
    items_pedido = []
    for item in pedido.items:
        producto = Producto.query.get(item.producto_id)
        if producto:
            items_pedido.append({
                'nombre': producto.nombre,
                'imagen': producto.imagen,
                'cantidad': item.cantidad,
                'precio': item.precio_unitario,
                'subtotal': item.precio_unitario * item.cantidad
            })
    
    return render_template('detalles_pedido.html', pedido=pedido, items=items_pedido)

# Rutas para AJAX (actualizaciones en tiempo real)
@app.route('/api/actualizar_cantidad', methods=['POST'])
def api_actualizar_cantidad():
    data = request.get_json()
    producto_id = data.get('producto_id')
    nueva_cantidad = data.get('cantidad', 1)
    
    if not producto_id or nueva_cantidad < 1:
        return jsonify({'error': 'Datos inválidos'}), 400
    
    producto = Producto.query.get_or_404(producto_id)
    carrito = session.get('carrito', [])
    
    # Verificar stock
    if nueva_cantidad > producto.stock:
        return jsonify({
            'error': 'Stock insuficiente',
            'stock_disponible': producto.stock
        }), 400
    
    # Actualizar cantidad en el carrito
    item_actualizado = False
    for item in carrito:
        if item['id'] == producto_id:
            item['cantidad'] = nueva_cantidad
            item_actualizado = True
            break
    
    if not item_actualizado:
        return jsonify({'error': 'Producto no encontrado en el carrito'}), 404
    
    # Calcular nuevo total
    total = 0
    for item in carrito:
        p = Producto.query.get(item['id'])
        if p:
            precio = p.precio_oferta if p.en_oferta and p.precio_oferta else p.precio
            total += precio * item['cantidad']
    
    session['carrito'] = carrito
    
    return jsonify({
        'success': True,
        'subtotal': round(nueva_cantidad * (producto.precio_oferta if producto.en_oferta and producto.precio_oferta else producto.precio), 2),
        'total': round(total, 2)
    })

@app.route('/comprar/<int:producto_id>')
def comprar(producto_id):
    producto = Producto.query.get_or_404(producto_id)
    
    # Crear carrito con solo este producto
    session['carrito'] = [{'id': producto_id, 'cantidad': 1}]
    
    # Redireccionar al checkout
    return redirect(url_for('checkout'))

# Página de perfil y gestión de cuenta
@app.route('/perfil')
@login_required
def perfil():
    return render_template('perfil.html')

@app.route('/actualizar_perfil', methods=['POST'])
@login_required
def actualizar_perfil():
    name = request.form.get('name')
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not name:
        flash('El nombre es obligatorio', 'danger')
        return redirect(url_for('perfil'))
    
    # Actualizar nombre
    current_user.name = name
    
    # Actualizar contraseña si se proporciona
    if current_password and new_password:
        if not current_user.check_password(current_password):
            flash('Contraseña actual incorrecta', 'danger')
            return redirect(url_for('perfil'))
            
        if new_password != confirm_password:
            flash('Las nuevas contraseñas no coinciden', 'danger')
            return redirect(url_for('perfil'))
            
        current_user.set_password(new_password)
        flash('Contraseña actualizada correctamente', 'success')
    
    try:
        db.session.commit()
        flash('Perfil actualizado correctamente', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error al actualizar el perfil', 'danger')
    
    return redirect(url_for('perfil'))

# Rutas para páginas estáticas (info, ayuda, etc.)
@app.route('/nosotros')
def nosotros():
    return render_template('nosotros.html')

@app.route('/contacto', methods=['GET', 'POST'])
def contacto():
    if request.method == 'POST':
        # Procesar formulario de contacto
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        mensaje = request.form.get('mensaje')
        
        # Aquí podrías enviar un email o guardar en la base de datos
        
        flash('Mensaje enviado correctamente. Nos pondremos en contacto contigo pronto.', 'success')
        return redirect(url_for('contacto'))
    
    return render_template('contacto.html')

@app.route('/preguntas_frecuentes')
def preguntas_frecuentes():
    return render_template('faq.html')

# Crear contexto para las plantillas
@app.context_processor
def utility_processor():
    def categoria_nombre(codigo):
        nombres = {
            'top': 'Tops Deportivos',
            'legging': 'Leggings',
            'short': 'Shorts',
            'camiseta': 'Camisetas',
            'pantalon': 'Pantalones',
            'soporte': 'Soportes',
            'guante': 'Guantes',
            'banda': 'Bandas Elásticas',
            'toalla': 'Toallas'
        }
        return nombres.get(codigo, codigo.capitalize())
    
    return dict(categoria_nombre=categoria_nombre)

# Manejador de errores
@app.errorhandler(404)
def pagina_no_encontrada(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def error_servidor(e):
    return render_template('500.html'), 500

# Solo ejecutar si es el archivo principal
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Asegurar que las tablas estén creadas
    app.run(debug=True)