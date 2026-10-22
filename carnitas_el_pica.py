import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import uuid
import os
import io
import streamlit.components.v1 as components

# --- CONFIGURACIÓN BASE DE DATOS Y MIGRACIONES ---
DB_NAME = "carnitas_el_pica.db"


def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        # 1. Compras
        cursor.execute('''CREATE TABLE IF NOT EXISTS compras 
                          (id TEXT PRIMARY KEY, fecha TEXT, concepto TEXT, tipo TEXT, 
                           cantidad REAL, unidad TEXT, costo_total REAL)''')

        # 2. Inventario
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventario 
                          (concepto TEXT PRIMARY KEY, cantidad REAL, unidad TEXT, costo_promedio REAL)''')

        # 3. Preparaciones
        cursor.execute('''CREATE TABLE IF NOT EXISTS preparaciones 
                          (id TEXT PRIMARY KEY, fecha TEXT, carne_utilizada_kg REAL, tipo_carne TEXT)''')

        # 4. Ventas
        cursor.execute('''CREATE TABLE IF NOT EXISTS ventas 
                          (transaccion_id TEXT, fecha TEXT, hora TEXT, concepto TEXT, 
                           cantidad REAL, p_unitario REAL, total REAL, estado TEXT)''')

        # --- MIGRACIÓN AUTOMÁTICA DE COLUMNAS NUEVAS EN VENTAS ---
        columnas_nuevas = [
            ("metodo_pago", "TEXT DEFAULT 'Efectivo'"),
            ("cliente", "TEXT DEFAULT 'Público General'"),
            ("monto_pagado", "REAL DEFAULT 0.0"),
            ("saldo_pendiente", "REAL DEFAULT 0.0")
        ]
        for col, tipo in columnas_nuevas:
            try:
                cursor.execute(f"ALTER TABLE ventas ADD COLUMN {col} {tipo}")
            except sqlite3.OperationalError:
                pass  # Si la columna ya existe, continúa sin error

        # 5. Cierre de Día
        cursor.execute('''CREATE TABLE IF NOT EXISTS cierres_dia 
                          (fecha TEXT PRIMARY KEY, carne_sobrante_kg REAL, tortillas_sobrantes INT, notas TEXT)''')

        # 6. Movimientos de Caja
        cursor.execute('''CREATE TABLE IF NOT EXISTS movimientos_caja 
                          (id TEXT PRIMARY KEY, fecha TEXT, hora TEXT, tipo TEXT, 
                           concepto TEXT, monto REAL, usuario_notas TEXT)''')

        # 7. Consumo Interno
        cursor.execute('''CREATE TABLE IF NOT EXISTS consumo_interno 
                          (id TEXT PRIMARY KEY, fecha TEXT, hora TEXT, concepto TEXT, cantidad REAL)''')

        conn.commit()


def run_query(query, params=()):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()


def get_df(query, params=()):
    with sqlite3.connect(DB_NAME) as conn:
        return pd.read_sql_query(query, conn, params=params)


def actualizar_inventario(concepto, cantidad, unidad, costo_total=0.0):
    df_inv = get_df("SELECT * FROM inventario WHERE concepto = ?", (concepto,))
    if df_inv.empty:
        if cantidad > 0:
            run_query("INSERT INTO inventario VALUES (?, ?, ?, ?)",
                      (concepto, cantidad, unidad, costo_total / cantidad if cantidad > 0 else 0))
    else:
        cant_actual = df_inv.iloc[0]['cantidad']
        nueva_cant = max(0.0, cant_actual + cantidad)
        run_query("UPDATE inventario SET cantidad = ? WHERE concepto = ?", (nueva_cant, concepto))


# --- SISTEMA DE IMPRESIÓN DE TICKETS ---
def generar_ticket_html(titulo, id_doc, items, total, cliente="Público General", estado="COMPLETADA"):
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    filas = "".join([
        f"<tr><td style='padding:3px 0;'>{it['concepto']}</td><td align='center'>{it['cantidad']}</td><td align='right'>${it['subtotal']:,.2f}</td></tr>"
        for it in items
    ])

    nota_fiado = f"<p style='color:red; font-size:11px; margin:2px 0;'><b>ESTADO:</b> {estado}<br><b>CLIENTE:</b> {cliente}</p>" if estado != "COMPLETADA" else ""

    return f"""
    <div id="print-area" style="font-family: Arial, sans-serif; width: 260px; padding: 10px; background: white; color: black; border: 1px solid #ccc; margin: auto;">
        <center>
            <h2 style="margin:0; font-size: 18px; color: #053787;">ZUSCARNITAS</h2>
            <h4 style="margin:0; font-size: 12px; color: #FF6600;">EL PICA</h4>
            <p style="font-size:10px; margin:2px 0; color: #555;">¡Sabor Incomparable!</p>
            <hr style="border: 1px dashed #053787;">
        </center>
        <p style="font-size:11px; margin: 4px 0;"><b>{titulo}:</b> #{id_doc}<br><b>Fecha:</b> {fecha}</p>
        {nota_fiado}
        <table style="width:100%; font-size:11px; border-collapse: collapse;">
            <tr style="border-bottom: 1px solid #053787; color: #053787;">
                <th align="left">Producto</th>
                <th>Cant</th>
                <th align="right">Total</th>
            </tr>
            {filas}
        </table>
        <hr style="border: 1px dashed #053787;">
        <h3 align="right" style="margin: 5px 0; color: #053787;">TOTAL: ${total:,.2f}</h3>
        <center>
            <p style="font-size:11px; margin:5px 0; color:#FF6600;"><b>¡GRACIAS POR SU COMPRA!</b></p>
        </center>
    </div>
    """


def generar_ticket_compra_html(id_compra, concepto, categoria, cantidad, unidad, costo_total):
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    costo_unitario = costo_total / cantidad if cantidad > 0 else 0.0

    return f"""
    <div id="print-area" style="font-family: Arial, sans-serif; width: 260px; padding: 10px; background: white; color: black; border: 1px solid #ccc; margin: auto;">
        <center>
            <h2 style="margin:0; font-size: 18px; color: #053787;">ZUSCARNITAS</h2>
            <h4 style="margin:0; font-size: 12px; color: #FF6600;">EL PICA</h4>
            <p style="font-size:10px; margin:2px 0; color: #555;">COMPROBANTE DE COMPRA DE INSUMOS</p>
            <hr style="border: 1px dashed #053787;">
        </center>
        <p style="font-size:11px; margin: 4px 0;"><b>FOLIO COMPRA:</b> #{id_compra}<br><b>Fecha:</b> {fecha}<br><b>Categoría:</b> {categoria}</p>
        <table style="width:100%; font-size:11px; border-collapse: collapse;">
            <tr style="border-bottom: 1px solid #053787; color: #053787;">
                <th align="left">Insumo</th>
                <th>Cant</th>
                <th align="right">Total</th>
            </tr>
            <tr>
                <td style='padding:5px 0;'>{concepto}</td>
                <td align='center'>{cantidad} {unidad}</td>
                <td align='right'>${costo_total:,.2f}</td>
            </tr>
        </table>
        <p style="font-size:10px; margin: 4px 0; color: #555;">Costo Unitario: ${costo_unitario:,.2f} / {unidad}</p>
        <hr style="border: 1px dashed #053787;">
        <h3 align="right" style="margin: 5px 0; color: #053787;">TOTAL PAGADO: ${costo_total:,.2f}</h3>
        <center>
            <p style="font-size:10px; margin:5px 0; color:#555;">--- Entrada a Inventario ---</p>
        </center>
    </div>
    """


def imprimir_ticket_js(html_content):
    component_script = f"""
    <div>
        {html_content}
        <br>
        <center>
            <button onclick="window.print()" style="background-color: #FF6600; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 5px; cursor: pointer;">
                🖨️ IMPRIMIR TICKET
            </button>
        </center>
    </div>
    <style>
        @media print {{
            body * {{ visibility: hidden; }}
            #print-area, #print-area * {{ visibility: visible; }}
            #print-area {{ position: absolute; left: 0; top: 0; width: 100%; }}
            button {{ display: none !important; }}
        }}
    </style>
    """
    components.html(component_script, height=360, scrolling=True)


# --- CONFIGURACIÓN E INTERFAZ ---
st.set_page_config(page_title="ZUSCARNITAS EL PICA", layout="wide", page_icon="🥩")
init_db()

PATH_LOGO = "carnitas.jpeg"

if os.path.exists(PATH_LOGO):
    st.sidebar.image(PATH_LOGO, use_container_width=True)

st.markdown("""
    <style>
        .stApp { background-color: #F0F4F8; }
        .header-container {
            background: linear-gradient(135deg, #053787 0%, #0A52C5 100%);
            padding: 15px; border-radius: 12px; text-align: center; color: white;
            margin-bottom: 15px; border-bottom: 4px solid #FF6600;
        }
        .header-title { font-size: 32px; font-weight: 900; margin: 0; color: #FFFFFF; font-family: 'Arial Black', sans-serif; }
        .header-subtitle { font-size: 18px; font-weight: bold; margin: 0; color: #FFCC00; }
        [data-testid="stSidebar"] { background-color: #053787; color: white; }
        [data-testid="stSidebar"] * { color: white !important; }
        .stButton>button {
            background-color: #FF6600 !important; color: white !important;
            font-weight: bold !important; border-radius: 8px !important; border: none !important;
        }
    </style>
""", unsafe_allow_html=True)

if 'carrito' not in st.session_state: st.session_state.carrito = []


# --- ALERTAS DE STOCK BAJO EN BARRA LATERAL ---
def mostrar_alertas_stock():
    df_inv = get_df("SELECT * FROM inventario")
    if not df_inv.empty:
        alertas = []
        for idx, row in df_inv.iterrows():
            concepto = row['concepto']
            cant = float(row['cantidad'])

            if "Tortillas" in concepto and cant < 50:
                alertas.append(f"⚠️ **{concepto}**: {cant:.0f} pzas quedantes")
            elif "Bolillo" in concepto and cant < 10:
                alertas.append(f"⚠️ **{concepto}**: {cant:.0f} pzas quedantes")
            elif cant <= 5.0 and row['unidad'] == 'Kg':
                alertas.append(f"🔴 **{concepto}**: ¡Solo quedán {cant:.1f} Kg!")

        if alertas:
            st.sidebar.error("🚨 **ALERTAS DE STOCK BAJO**")
            for a in alertas:
                st.sidebar.warning(a)


st.markdown("""
    <div class="header-container">
        <h1 class="header-title">ZUSCARNITAS</h1>
        <h3 class="header-subtitle">🐷 EL PICA 🐷</h3>
    </div>
""", unsafe_allow_html=True)

st.sidebar.caption(f"📅 Fecha: {datetime.now().strftime('%d/%m/%Y')}")
mostrar_alertas_stock()

menu = [
    "🛒 Punto de Venta",
    "📌 Cuentas por Cobrar (Fiados)",
    "💸 Entradas y Salidas de Caja",
    "🍽️ Consumo Interno (Personal)",
    "🛍️ Compras e Insumos",
    "🔥 Preparación (Cocinado)",
    "📦 Inventario y Almacén",
    "📊 Corte / Reporte del Día",
    "📉 Historial / Exportar Excel",
    "💾 Respaldos"
]
choice = st.sidebar.selectbox("Seleccione Módulo", menu)

# ==========================================
# 1. PUNTO DE VENTA
# ==========================================
if choice == "🛒 Punto de Venta":
    st.header("🛒 Registrar Venta en Mostrador")
    c1, c2 = st.columns([1.1, 0.9])

    with c1:
        st.subheader("Seleccionar Producto")
        tipo_venta = st.radio("Tipo de Orden:",
                              ["🌮 Tacos ($30 c/u)", "🥖 Tortas ($35 c/u)", "🥩 Carnitas por Dinero/Kilo",
                               "🥓 Cuero Puro ($180/kg)", "🍖 Pata ($25 c/u)", "🥤 Refresco / Varios Tienda"],
                              horizontal=True)

        concepto, precio_unitario, cantidad, subtotal = "", 0.0, 1.0, 0.0

        if "Tacos" in tipo_venta:
            concepto = "Taco de Carnitas"
            precio_unitario = 30.0
            cant_tacos = st.number_input("Número de Tacos", min_value=1, value=1, step=1)

            if st.checkbox("¿Aplicar precio especial/descuento?"):
                subtotal = st.number_input("Monto Total Cobrado ($)", min_value=1.0, value=100.0, step=5.0)
                precio_unitario = subtotal / cant_tacos
            else:
                subtotal = cant_tacos * precio_unitario
            cantidad = float(cant_tacos)

        elif "Tortas" in tipo_venta:
            concepto = "Torta de Carnitas"
            precio_unitario = 35.0
            cant = st.number_input("Número de Tortas", min_value=1, value=1, step=1)
            cantidad = float(cant)
            subtotal = cantidad * precio_unitario

        elif "Pata" in tipo_venta:
            concepto = "Pata de Puerco"
            precio_unitario = 25.0
            cant = st.number_input("Número de Patas", min_value=1, value=1, step=1)
            cantidad = float(cant)
            subtotal = cantidad * precio_unitario

        elif "Carnitas por Dinero/Kilo" in tipo_venta:
            modo_kilo = st.radio("Cobrar por:", ["Monto en Dinero ($)", "Peso en Kilos (Kg)"], horizontal=True)
            precio_kilo = 270.0
            if modo_kilo == "Monto en Dinero ($)":
                monto = st.number_input("Monto Total ($)", min_value=10.0, value=100.0, step=10.0)
                subtotal = monto
                cantidad = round(monto / precio_kilo, 3)
                concepto = f"Carnitas Surtidas (${monto:,.0f})"
                precio_unitario = monto
            else:
                kilos = st.number_input("Kilos de Carnitas", min_value=0.1, value=0.5, step=0.1)
                cantidad = kilos
                subtotal = kilos * precio_kilo
                concepto = f"Carnitas Surtidas ({kilos} kg)"
                precio_unitario = precio_kilo

        elif "Cuero Puro" in tipo_venta:
            precio_kilo = 180.0
            kilos = st.number_input("Kilos de Cuero Puro", min_value=0.1, value=0.5, step=0.1)
            cantidad = kilos
            subtotal = kilos * precio_kilo
            concepto = f"Cuero Puro ({kilos} kg)"
            precio_unitario = precio_kilo

        elif "Refresco" in tipo_venta:
            concepto = st.text_input("Detalle de Bebida / Artículo", value="Coca-Cola 600ml")
            subtotal = st.number_input("Precio ($)", min_value=1.0, value=22.0, step=1.0)
            cantidad = 1.0
            precio_unitario = subtotal

        if st.button("➕ AGREGAR A LA CUENTA", use_container_width=True):
            st.session_state.carrito.append({
                'concepto': concepto, 'cantidad': cantidad,
                'precio': precio_unitario, 'subtotal': subtotal
            })
            st.rerun()

        if st.button("🗑️ Limpiar Cuenta", type="secondary", use_container_width=True):
            st.session_state.carrito = []
            st.rerun()

    with c2:
        st.subheader("📋 Resumen del Pedido")
        if st.session_state.carrito:
            df_carrito = pd.DataFrame(st.session_state.carrito)
            st.table(df_carrito[['concepto', 'cantidad', 'subtotal']])

            total_venta = sum(i['subtotal'] for i in st.session_state.carrito)
            st.markdown(f"<h2 style='color:#053787; text-align:right;'>Total: ${total_venta:,.2f}</h2>",
                        unsafe_allow_html=True)

            metodo_pago = st.selectbox("Método de Pago:", ["Efectivo", "Fiado / A Cuenta", "Transferencia"])

            cliente_nombre = "Público General"
            monto_abonado = total_venta
            estado_venta = "COMPLETADA"

            if metodo_pago == "Fiado / A Cuenta":
                estado_venta = "FIADO"
                cliente_nombre = st.text_input("Nombre o Apodo del Cliente:", placeholder="Ej: Tía Marta, Gus")
                monto_abonado = st.number_input("Monto Abonado HOY ($):", min_value=0.0, max_value=total_venta,
                                                value=0.0, step=5.0)
                saldo_pendiente = total_venta - monto_abonado
            else:
                saldo_pendiente = 0.0

            if st.button("✅ FINALIZAR Y GENERAR TICKET", use_container_width=True):
                if metodo_pago == "Fiado / A Cuenta" and not cliente_nombre.strip():
                    st.error("⚠️ Debe escribir el nombre del cliente cuando es fiado.")
                else:
                    t_id = "V-" + str(uuid.uuid4())[:6].upper()
                    now = datetime.now()

                    for item in st.session_state.carrito:
                        run_query("INSERT INTO ventas VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (t_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"),
                                   item['concepto'], item['cantidad'], item['precio'], item['subtotal'],
                                   estado_venta, metodo_pago, cliente_nombre, monto_abonado, saldo_pendiente))

                        if "Taco" in item['concepto']:
                            actualizar_inventario("Tortillas (piezas)", -(item['cantidad'] * 2), "Pza")
                        elif "Torta" in item['concepto']:
                            actualizar_inventario("Bolillo/Telera", -item['cantidad'], "Pza")

                    ticket_html = generar_ticket_html("TICKET DE VENTA", t_id, st.session_state.carrito, total_venta,
                                                      cliente_nombre, estado_venta)
                    st.session_state.carrito = []

                    st.success("¡Venta registrada con éxito!")
                    st.markdown("### 🖨️ Imprimir Ticket")
                    imprimir_ticket_js(ticket_html)
        else:
            st.info("El carrito está vacío.")


# ==========================================
# 2. CUENTAS POR COBRAR (FIADOS)
# ==========================================
elif choice == "📌 Cuentas por Cobrar (Fiados)":
    st.header("📌 Gestión de Cuentas por Cobrar (Fiados)")

    df_fiados = get_df("""SELECT transaccion_id, fecha, cliente, concepto, total, saldo_pendiente 
                          FROM ventas WHERE estado = 'FIADO' AND saldo_pendiente > 0 ORDER BY fecha DESC""")

    if not df_fiados.empty:
        df_resumen = df_fiados.groupby('cliente')['saldo_pendiente'].sum().reset_index()
        df_resumen.columns = ['Cliente / Deudor', 'Saldo Total Pendiente ($)']
        st.dataframe(df_resumen, use_container_width=True)

        cliente_sel = st.selectbox("Seleccionar Cliente:", df_resumen['Cliente / Deudor'].unique())
        deuda_cliente = float(
            df_resumen[df_resumen['Cliente / Deudor'] == cliente_sel]['Saldo Total Pendiente ($)'].values[0])

        st.info(f"Deuda actual de **{cliente_sel}**: ${deuda_cliente:,.2f}")

        with st.form("form_abono"):
            monto_abono = st.number_input("Monto a Abonar ($):", min_value=1.0, max_value=deuda_cliente,
                                          value=deuda_cliente, step=5.0)
            if st.form_submit_button("💰 Registrar Pago / Abono"):
                ventas_cliente = get_df(
                    "SELECT transaccion_id, saldo_pendiente FROM ventas WHERE cliente = ? AND estado = 'FIADO' AND saldo_pendiente > 0",
                    (cliente_sel,))

                restante_abono = monto_abono
                for idx, row in ventas_cliente.iterrows():
                    if restante_abono <= 0: break
                    saldo_actual = float(row['saldo_pendiente'])
                    pago_a_esta_venta = min(restante_abono, saldo_actual)
                    nuevo_saldo = saldo_actual - pago_a_esta_venta
                    nuevo_estado = "COMPLETADA" if nuevo_saldo == 0 else "FIADO"

                    run_query("UPDATE ventas SET saldo_pendiente = ?, estado = ? WHERE transaccion_id = ?",
                              (nuevo_saldo, nuevo_estado, row['transaccion_id']))
                    restante_abono -= pago_a_esta_venta

                m_id = "M-" + str(uuid.uuid4())[:6].upper()
                now = datetime.now()
                run_query("INSERT INTO movimientos_caja VALUES (?,?,?,?,?,?,?)",
                          (m_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), "ENTRADA",
                           f"Abono de fiado: {cliente_sel}", monto_abono, "Cobro de deuda"))

                st.success(f"Abono de ${monto_abono:,.2f} registrado.")
                st.rerun()
    else:
        st.success("🎉 ¡No hay cuentas pendientes por cobrar!")


# ==========================================
# 3. ENTRADAS Y SALIDAS DE CAJA
# ==========================================
elif choice == "💸 Entradas y Salidas de Caja":
    st.header("💸 Entradas y Salidas de Dinero de Caja Chica")
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("🔴 Registrar SALIDA de Dinero")
        with st.form("form_salida"):
            concepto_salida = st.text_input("Concepto:", placeholder="Ej: Coca de tienda, Tortillas, Tomates")
            monto_salida = st.number_input("Monto ($):", min_value=1.0, value=25.0, step=5.0)
            notas_salida = st.text_input("Notas:", value="")
            if st.form_submit_button("➖ Registrar Salida"):
                if concepto_salida:
                    m_id = "M-" + str(uuid.uuid4())[:6].upper()
                    now = datetime.now()
                    run_query("INSERT INTO movimientos_caja VALUES (?,?,?,?,?,?,?)",
                              (m_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), "SALIDA", concepto_salida,
                               monto_salida, notas_salida))
                    st.success("Salida registrada.")
                    st.rerun()

    with c2:
        st.subheader("🟢 Registrar ENTRADA de Dinero")
        with st.form("form_entrada"):
            concepto_entrada = st.text_input("Concepto:", placeholder="Ej: Fondo de caja, Aportación")
            monto_entrada = st.number_input("Monto ($):", min_value=1.0, value=800.0, step=50.0)
            notas_entrada = st.text_input("Notas:", value="")
            if st.form_submit_button("➕ Registrar Entrada"):
                if concepto_entrada:
                    m_id = "M-" + str(uuid.uuid4())[:6].upper()
                    now = datetime.now()
                    run_query("INSERT INTO movimientos_caja VALUES (?,?,?,?,?,?,?)",
                              (m_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), "ENTRADA", concepto_entrada,
                               monto_entrada, notas_entrada))
                    st.success("Entrada registrada.")
                    st.rerun()


# ==========================================
# 4. CONSUMO INTERNO (PERSONAL)
# ==========================================
elif choice == "🍽️ Consumo Interno (Personal)":
    st.header("🍽️ Registro de Consumo del Equipo ('Nosotros comimos')")
    st.caption("Descuenta los productos e insumos del inventario sin registrar dinero de venta.")

    with st.form("form_consumo"):
        c1, c2 = st.columns(2)
        with c1:
            item_consumo = st.selectbox("Producto consumido:", ["Taco", "Torta", "Pata", "Kilos de Carnitas", "Bebida"])
            cantidad_consumo = st.number_input("Cantidad:", min_value=0.1, value=1.0, step=0.5)
        with c2:
            detalle_consumo = st.text_input("Notas / Quién comió:", placeholder="Ej: Comida del equipo de trabajo")

        if st.form_submit_button("🍽️ Registrar Consumo Interno"):
            c_id = "CI-" + str(uuid.uuid4())[:6].upper()
            now = datetime.now()
            concepto_final = f"{item_consumo} ({cantidad_consumo})"

            run_query("INSERT INTO consumo_interno VALUES (?,?,?,?,?)",
                      (c_id, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"), concepto_final, cantidad_consumo))

            if "Taco" in item_consumo:
                actualizar_inventario("Tortillas (piezas)", -(cantidad_consumo * 2), "Pza")
            elif "Torta" in item_consumo:
                actualizar_inventario("Bolillo/Telera", -cantidad_consumo, "Pza")

            st.success(f"Consumo de {concepto_final} registrado correctamente.")
            st.rerun()

    st.divider()
    st.subheader("📜 Registro de Consumo Interno Reciente")
    df_ci = get_df(
        "SELECT fecha AS Fecha, hora AS Hora, concepto AS Consumo FROM consumo_interno ORDER BY fecha DESC, hora DESC")
    st.dataframe(df_ci, use_container_width=True)


# ==========================================
# 5. COMPRAS E INSUMOS
# ==========================================
elif choice == "🛍️ Compras e Insumos":
    st.header("🛍️ Registro de Compras e Insumos")

    with st.form("form_compras"):
        c1, c2 = st.columns(2)
        with c1:
            tipo_compra = st.selectbox("Categoría:",
                                       ["Puerco Entero / Canal (Kg)", "Carne Directa ($ / Kg)", "Insumos / Consumibles",
                                        "Gas"])
            concepto = st.text_input("Detalle Insumo", placeholder="Ej: Puerco 120kg, Tortillas, Limones")
        with c2:
            cantidad = st.number_input("Cantidad", min_value=0.1, value=1.0, step=0.5)
            unidad = st.selectbox("Unidad:", ["Kg", "Piezas", "Botellas", "Cargas"])
            costo_total = st.number_input("Costo Total ($)", min_value=0.0, value=0.0, step=10.0)

        guardar_compra = st.form_submit_button("💾 Registrar y Generar Ticket de Compra")

    if guardar_compra and concepto:
        c_id = "C-" + str(uuid.uuid4())[:6].upper()
        fecha_hoy = datetime.now().strftime("%Y-%m-%d")

        run_query("INSERT INTO compras VALUES (?,?,?,?,?,?,?)",
                  (c_id, fecha_hoy, concepto, tipo_compra, cantidad, unidad, costo_total))
        actualizar_inventario(concepto, cantidad, unidad, costo_total)

        st.success("✅ Compra registrada e ingresada al inventario correctamente.")

        # Generar ticket de compra
        ticket_compra_html = generar_ticket_compra_html(c_id, concepto, tipo_compra, cantidad, unidad, costo_total)
        st.markdown("### 🖨️ Ticket de Compra / Entrada a Almacén")
        imprimir_ticket_js(ticket_compra_html)

    st.divider()
    st.subheader("📜 ÚLTIMAS COMPRAS REGISTRADAS")
    df_compras_recientes = get_df(
        "SELECT id AS 'Folio', fecha AS 'Fecha', concepto AS 'Insumo', tipo AS 'Categoría', cantidad AS 'Cantidad', unidad AS 'Unidad', costo_total AS 'Total ($)' FROM compras ORDER BY fecha DESC LIMIT 10")
    if not df_compras_recientes.empty:
        st.dataframe(df_compras_recientes, use_container_width=True)


# ==========================================
# 6. PREPARACIÓN (COCINADO DEL DÍA)
# ==========================================
elif choice == "🔥 Preparación (Cocinado)":
    st.header("🔥 Registro de Carnitas Cocinadas hoy")
    st.write("Descuenta la carne cruda o canal del almacén para el cazo del día.")

    df_carne = get_df("SELECT * FROM inventario WHERE unidad = 'Kg' AND cantidad > 0")

    if not df_carne.empty:
        with st.form("form_prep"):
            prenda_sel = st.selectbox("Seleccionar Carne/Puerco en Almacén:", df_carne['concepto'].unique())
            r_item = df_carne[df_carne['concepto'] == prenda_sel].iloc[0]

            st.info(f"Disponible en almacén: {r_item['cantidad']} Kg")

            tipo_preparacion = st.radio("Porción a preparar:",
                                        ["Kilos exactos", "1/2 Canal (60 kg aprox)", "1 Canal Entero"], horizontal=True)

            if tipo_preparacion == "1/2 Canal (60 kg aprox)":
                val_def = min(60.0, float(r_item['cantidad']))
            elif tipo_preparacion == "1 Canal Entero":
                val_def = min(120.0, float(r_item['cantidad']))
            else:
                val_def = min(30.0, float(r_item['cantidad']))

            kg_a_preparar = st.number_input("Kilos de carne cruda a preparar hoy:", min_value=0.1,
                                            max_value=float(r_item['cantidad']),
                                            value=val_def)

            if st.form_submit_button("🔥 Iniciar Preparación / Descontar de Almacén"):
                p_id = "P-" + str(uuid.uuid4())[:6].upper()
                fecha_hoy = datetime.now().strftime("%Y-%m-%d")

                run_query("INSERT INTO preparaciones VALUES (?,?,?,?)", (p_id, fecha_hoy, kg_a_preparar, prenda_sel))
                actualizar_inventario(prenda_sel, -kg_a_preparar, "Kg")

                st.success(f"Se descontaron {kg_a_preparar} Kg de {prenda_sel} del almacén.")
                st.rerun()
    else:
        st.warning("No hay registro de carne cruda en almacén.")

# ==========================================
# 7. INVENTARIO Y ALMACÉN
# ==========================================
elif choice == "📦 Inventario y Almacén":
    st.header("📦 Existencias en Almacén / Congelador e Insumos")

    df_inv = get_df(
        "SELECT concepto AS 'Concepto / Material', cantidad AS 'Cantidad Disponible', unidad AS 'Unidad' FROM inventario")
    st.dataframe(df_inv, use_container_width=True)

    st.subheader("🌙 Registro de Sobrantes al Cierre del Día")

    with st.form("form_cierre"):
        fecha_cierre = datetime.now().strftime("%Y-%m-%d")
        carne_sobrante = st.number_input("Carne cocida que sobró (Kg):", min_value=0.0, value=0.0, step=0.5)
        tortillas_sobrantes = st.number_input("Tortillas que sobraron (Piezas):", min_value=0, value=0)
        notas = st.text_area("Notas (Ej: 'Se guardó para tamales')", value="")

        if st.form_submit_button("💾 Guardar Sobrantes del Día"):
            run_query("INSERT OR REPLACE INTO cierres_dia VALUES (?,?,?,?)",
                      (fecha_cierre, carne_sobrante, tortillas_sobrantes, notas))
            st.success("Sobrantes registrados correctamente.")


# ==========================================
# 8. CORTE / REPORTE DEL DÍA
# ==========================================
elif choice == "📊 Corte / Reporte del Día":
    st.header("📊 Balance de Caja y Utilidades")

    periodo = st.radio("Periodo de consulta:", ["Hoy", "Esta Semana", "Este Mes"], horizontal=True)
    hoy = datetime.now()

    if periodo == "Hoy":
        f_inicio = hoy.strftime("%Y-%m-%d")
    elif periodo == "Esta Semana":
        f_inicio = (hoy - timedelta(days=hoy.weekday())).strftime("%Y-%m-%d")
    else:
        f_inicio = hoy.strftime("%Y-%m-01")

    df_ventas = get_df("SELECT * FROM ventas WHERE fecha >= ?", (f_inicio,))
    df_gastos = get_df("SELECT * FROM compras WHERE fecha >= ?", (f_inicio,))
    df_movs = get_df("SELECT * FROM movimientos_caja WHERE fecha >= ?", (f_inicio,))

    total_ventas_caja = df_ventas['monto_pagado'].sum() if not df_ventas.empty else 0.0
    total_compras = df_gastos['costo_total'].sum() if not df_gastos.empty else 0.0

    salidas_caja = df_movs[df_movs['tipo'] == 'SALIDA']['monto'].sum() if not df_movs.empty else 0.0
    entradas_caja = df_movs[df_movs['tipo'] == 'ENTRADA']['monto'].sum() if not df_movs.empty else 0.0

    efectivo_en_caja = (total_ventas_caja + entradas_caja) - salidas_caja

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 Cobrado en Caja", f"${total_ventas_caja:,.2f}")
    m2.metric("💸 Salidas / Gastos Caja", f"${salidas_caja:,.2f}")
    m3.metric("🟢 Entradas Extra Caja", f"${entradas_caja:,.2f}")
    m4.metric("💵 EFECTIVO EN CAJA", f"${efectivo_en_caja:,.2f}")

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🌮 Ventas Registradas")
        if not df_ventas.empty:
            st.dataframe(df_ventas[['hora', 'concepto', 'cantidad', 'total', 'estado', 'cliente']],
                         use_container_width=True)
        else:
            st.info("Sin ventas registradas en el periodo.")

    with col_b:
        st.subheader("💸 Salidas de Caja Chica")
        if not df_movs.empty:
            st.dataframe(df_movs[['hora', 'tipo', 'concepto', 'monto']], use_container_width=True)
        else:
            st.info("Sin salidas registradas en el periodo.")


# ==========================================
# 9. HISTORIAL Y EXPORTACIÓN A EXCEL
# ==========================================
elif choice == "📉 Historial / Exportar Excel":
    st.header("📉 Historial General y Exportación")


    def generar_excel():
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            get_df("SELECT * FROM ventas").to_excel(writer, sheet_name='Ventas', index=False)
            get_df("SELECT * FROM compras").to_excel(writer, sheet_name='Compras', index=False)
            get_df("SELECT * FROM movimientos_caja").to_excel(writer, sheet_name='Movimientos_Caja', index=False)
            get_df("SELECT * FROM inventario").to_excel(writer, sheet_name='Inventario', index=False)
            get_df("SELECT * FROM consumo_interno").to_excel(writer, sheet_name='Consumo_Interno', index=False)
        return output.getvalue()


    st.download_button(
        label="📊 DESCARGAR REPORTE COMPLETO EN EXCEL (.XLSX)",
        data=generar_excel(),
        file_name=f"Reporte_Carnitas_El_Pica_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    st.divider()
    tab1, tab2, tab3 = st.tabs(["Ventas", "Movimientos Caja", "Compras"])
    with tab1:
        st.dataframe(get_df("SELECT * FROM ventas ORDER BY fecha DESC, hora DESC"), use_container_width=True)
    with tab2:
        st.dataframe(get_df("SELECT * FROM movimientos_caja ORDER BY fecha DESC, hora DESC"), use_container_width=True)
    with tab3:
        st.dataframe(get_df("SELECT * FROM compras ORDER BY fecha DESC"), use_container_width=True)


# ==========================================
# 10. RESPALDOS
# ==========================================
elif choice == "💾 Respaldos":
    st.header("💾 Respaldos de la Base de Datos")
    if os.path.exists(DB_NAME):
        with open(DB_NAME, "rb") as f:
            st.download_button("📥 Descargar Base de Datos (.db)", f,
                               f"Respaldo_Carnitas_{datetime.now().strftime('%Y%m%d')}.db")