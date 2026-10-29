"""
================================================================================
MÓDULO FUNCIONAL COMPLETO: TRANSPORTE Y ENTREGAS (ARQUITECTURA DE 3 CAPAS)
Empresa Manufacturera -> Módulo de Logística y Entregas
================================================================================
Estructura del Código:
1. CAPA 3: PERSISTENCIA (SQLite - Modelos, Repositorio y Trazabilidad)
2. CAPA 2: LÓGICA DE NEGOCIO (Reglas Operativas, Capacidades y Máquina de Estados)
3. CAPA 1: PRESENTACIÓN / PUERTA DE ENTRADA (API REST Flask)
4. CLIENTE DE PRUEBAS Y SIMULACIÓN (End-to-End)
================================================================================
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
import webbrowser
from threading import Timer

# ==============================================================================
# 1. CAPA DE PERSISTENCIA (DATABASE & REPOSITORY TIER)
# ==============================================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sistema_transporte.db")

def obtener_conexion():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_bd():
    conn = obtener_conexion()
    cursor = conn.cursor()
    
    # Tabla Vehículos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vehiculos (
            id TEXT PRIMARY KEY,
            placa TEXT NOT NULL,
            capacidad_max_kg REAL NOT NULL,
            estado TEXT CHECK(estado IN ('DISPONIBLE', 'EN_RUTA', 'MANTENIMIENTO')) DEFAULT 'DISPONIBLE'
        )
    ''')
    
    # Tabla Conductores
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conductores (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            licencia TEXT NOT NULL,
            estado TEXT CHECK(estado IN ('DISPONIBLE', 'ASIGNADO', 'LICENCIA')) DEFAULT 'DISPONIBLE'
        )
    ''')
    
    # Tabla Ordenes de Transporte
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ordenes_transporte (
            id TEXT PRIMARY KEY,
            orden_manufactura_id TEXT NOT NULL,
            cliente_nombre TEXT NOT NULL,
            direccion_destino TEXT NOT NULL,
            peso_total_kg REAL NOT NULL,
            vehiculo_id TEXT,
            conductor_id TEXT,
            estado TEXT CHECK(estado IN ('CREADA', 'ASIGNADA', 'EN_TRANSITO', 'ENTREGADO', 'NOVEDAD')) DEFAULT 'CREADA',
            ubicacion_actual TEXT DEFAULT '-12.046374, -77.042793',
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (vehiculo_id) REFERENCES vehiculos(id),
            FOREIGN KEY (conductor_id) REFERENCES conductores(id)
        )
    ''')
    
    # Tabla Historial de Entregas (Log de Trazabilidad)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_entregas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orden_transporte_id TEXT NOT NULL,
            estado_anterior TEXT,
            estado_nuevo TEXT NOT NULL,
            ubicacion_gps TEXT,
            observaciones TEXT,
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (orden_transporte_id) REFERENCES ordenes_transporte(id)
        )
    ''')
    
    # Insertar datos de prueba iniciales si están vacías
    cursor.execute("SELECT COUNT(*) FROM vehiculos")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT OR IGNORE INTO vehiculos (id, placa, capacidad_max_kg, estado) VALUES (?, ?, ?, ?)", [
            ('VEH-001', 'ABC-123', 1500.0, 'DISPONIBLE'),
            ('VEH-002', 'XYZ-789', 3000.0, 'DISPONIBLE'),
            ('VEH-003', 'MNO-456', 5000.0, 'DISPONIBLE')
        ])
    cursor.execute("SELECT COUNT(*) FROM conductores")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT OR IGNORE INTO conductores (id, nombre, licencia, estado) VALUES (?, ?, ?, ?)", [
            ('CND-001', 'Carlos Pérez', 'LIC-A2', 'DISPONIBLE'),
            ('CND-002', 'Ana Gómez', 'LIC-A2', 'DISPONIBLE'),
            ('CND-003', 'Luis Martínez', 'LIC-A3', 'DISPONIBLE')
        ])
    cursor.execute("SELECT COUNT(*) FROM ordenes_transporte")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("INSERT OR IGNORE INTO ordenes_transporte (id, orden_manufactura_id, cliente_nombre, direccion_destino, peso_total_kg, estado) VALUES (?, ?, ?, ?, ?, ?)", [
            ('OT-1001', 'MANUF-8801', 'Industrias del Norte S.A.', 'Av. Industrial 450, Lima', 1200.0, 'CREADA'),
            ('OT-1002', 'MANUF-8802', 'Comercializadora Global', 'Calle Comercio 12, Arequipa', 2500.0, 'CREADA'),
            ('OT-1003', 'MANUF-8803', 'Distribuidora del Sur', 'Av. del Sol 890, Cusco', 800.0, 'CREADA')
        ])
    # Ensure ubicacion_actual column exists if DB was created previously
    try:
        cursor.execute("ALTER TABLE ordenes_transporte ADD COLUMN ubicacion_actual TEXT DEFAULT '-12.046374, -77.042793'")
    except Exception:
        pass

    conn.commit()
    conn.close()


class PersistenciaTransporte:
    """Capa de Persistencia: Métodos directos de consulta y modificación en la base de datos."""
    
    @staticmethod
    def obtener_vehiculo(vehiculo_id):
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vehiculos WHERE id = ?", (vehiculo_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def obtener_conductor(conductor_id):
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM conductores WHERE id = ?", (conductor_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def obtener_orden(orden_id):
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ordenes_transporte WHERE id = ?", (orden_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def asignar_recursos_orden(orden_id, vehiculo_id, conductor_id):
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE ordenes_transporte
            SET vehiculo_id = ?, conductor_id = ?, estado = 'ASIGNADA'
            WHERE id = ?
        ''', (vehiculo_id, conductor_id, orden_id))
        
        cursor.execute("UPDATE vehiculos SET estado = 'EN_RUTA' WHERE id = ?", (vehiculo_id,))
        cursor.execute("UPDATE conductores SET estado = 'ASIGNADO' WHERE id = ?", (conductor_id,))
        
        conn.commit()
        conn.close()

    @staticmethod
    def actualizar_estado_entrega(orden_id, nuevo_estado, ubicacion_gps, observaciones):
        conn = obtener_conexion()
        cursor = conn.cursor()
        
        cursor.execute("SELECT estado, vehiculo_id, conductor_id FROM ordenes_transporte WHERE id = ?", (orden_id,))
        orden = cursor.fetchone()
        estado_anterior = orden['estado'] if orden else None
        
        cursor.execute('''
            UPDATE ordenes_transporte
            SET estado = ?
            WHERE id = ?
        ''', (nuevo_estado, orden_id))
        
        cursor.execute('''
            INSERT INTO historial_entregas (orden_transporte_id, estado_anterior, estado_nuevo, ubicacion_gps, observaciones)
            VALUES (?, ?, ?, ?, ?)
        ''', (orden_id, estado_anterior, nuevo_estado, ubicacion_gps, observaciones))
        
        if nuevo_estado == 'ENTREGADO':
            cursor.execute("UPDATE vehiculos SET estado = 'DISPONIBLE' WHERE id = ?", (orden['vehiculo_id'],))
            cursor.execute("UPDATE conductores SET estado = 'DISPONIBLE' WHERE id = ?", (orden['conductor_id'],))
            
        conn.commit()
        conn.close()
        return estado_anterior

    @staticmethod
    def obtener_historial_orden(orden_id):
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM historial_entregas WHERE orden_transporte_id = ? ORDER BY fecha_registro ASC", (orden_id,))
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]


# ==============================================================================
# 2. CAPA DE LÓGICA DE NEGOCIO (BUSINESS LOGIC TIER)
# ==============================================================================


    @staticmethod
    def crear_orden(orden_id, orden_manufactura_id, cliente_nombre, direccion_destino, peso_total_kg):
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ordenes_transporte (id, orden_manufactura_id, cliente_nombre, direccion_destino, peso_total_kg, estado, ubicacion_actual)
            VALUES (?, ?, ?, ?, ?, 'CREADA', '-12.046374, -77.042793')
        ''', (orden_id, orden_manufactura_id, cliente_nombre, direccion_destino, peso_total_kg))
        conn.commit()
        conn.close()

    @staticmethod
    def editar_orden(orden_id, direccion_destino, vehiculo_id, conductor_id):
        conn = obtener_conexion()
        cursor = conn.cursor()
        cursor.execute("SELECT vehiculo_id, conductor_id FROM ordenes_transporte WHERE id = ?", (orden_id,))
        actual = cursor.fetchone()
        old_v = actual['vehiculo_id'] if actual else None
        old_c = actual['conductor_id'] if actual else None

        if old_v and old_v != vehiculo_id:
            cursor.execute("UPDATE vehiculos SET estado = 'DISPONIBLE' WHERE id = ?", (old_v,))
            cursor.execute("UPDATE vehiculos SET estado = 'EN_RUTA' WHERE id = ?", (vehiculo_id,))
        if old_c and old_c != conductor_id:
            cursor.execute("UPDATE conductores SET estado = 'DISPONIBLE' WHERE id = ?", (old_c,))
            cursor.execute("UPDATE conductores SET estado = 'ASIGNADO' WHERE id = ?", (conductor_id,))

        cursor.execute('''
            UPDATE ordenes_transporte 
            SET direccion_destino = ?, vehiculo_id = ?, conductor_id = ? 
            WHERE id = ?
        ''', (direccion_destino, vehiculo_id, conductor_id, orden_id))

        cursor.execute('''
            INSERT INTO historial_entregas (orden_transporte_id, estado_anterior, estado_nuevo, observaciones)
            VALUES (?, 'EDICION', 'ACTUALIZADA', ?)
        ''', (orden_id, f"Modificación administrativa: Destino '{direccion_destino}', Vehículo '{vehiculo_id}', Conductor '{conductor_id}'"))

        conn.commit()
        conn.close()


class LogicaNegocioTransporte:
    """Capa de Lógica de Negocio: Ejecuta reglas operativas y valida la máquina de estados."""

    TRANSICIONES_PERMITIDAS = {
        'CREADA': ['ASIGNADA'],
        'ASIGNADA': ['EN_TRANSITO', 'NOVEDAD'],
        'EN_TRANSITO': ['ENTREGADO', 'NOVEDAD'],
        'NOVEDAD': ['EN_TRANSITO', 'ENTREGADO'],
        'ENTREGADO': []
    }

    @classmethod
    def asignar_despacho(cls, orden_id: str, vehiculo_id: str, conductor_id: str) -> dict:
        orden = PersistenciaTransporte.obtener_orden(orden_id)
        if not orden:
            return {"exito": False, "codigo": 404, "mensaje": f"La orden '{orden_id}' no existe."}
        
        if orden['estado'] != 'CREADA':
            return {"exito": False, "codigo": 400, "mensaje": f"La orden '{orden_id}' ya procesada."}

        vehiculo = PersistenciaTransporte.obtener_vehiculo(vehiculo_id)
        if not vehiculo or vehiculo['estado'] != 'DISPONIBLE':
            return {"exito": False, "codigo": 409, "mensaje": "Vehículo no disponible."}

        # Regla de Negocio: Validación de Carga
        if orden['peso_total_kg'] > vehiculo['capacidad_max_kg']:
            return {
                "exito": False, 
                "codigo": 422, 
                "mensaje": f"Exceso de carga: Orden ({orden['peso_total_kg']} kg) supera capacidad ({vehiculo['capacidad_max_kg']} kg)."
            }

        conductor = PersistenciaTransporte.obtener_conductor(conductor_id)
        if not conductor or conductor['estado'] != 'DISPONIBLE':
            return {"exito": False, "codigo": 409, "mensaje": "Conductor no disponible."}

        PersistenciaTransporte.asignar_recursos_orden(orden_id, vehiculo_id, conductor_id)
        return {"exito": True, "codigo": 200, "mensaje": "Asignación realizada exitosamente."}

    @classmethod
    def actualizar_estado_entrega(cls, orden_id: str, nuevo_estado: str, ubicacion_gps: str = "N/A", observaciones: str = "") -> dict:
        orden = PersistenciaTransporte.obtener_orden(orden_id)
        if not orden:
            return {"exito": False, "codigo": 404, "mensaje": f"La orden '{orden_id}' no existe."}

        estado_actual = orden['estado']
        permitidos = cls.TRANSICIONES_PERMITIDAS.get(estado_actual, [])
        if nuevo_estado not in permitidos:
            return {
                "exito": False,
                "codigo": 400,
                "mensaje": f"Transición no permitida de '{estado_actual}' a '{nuevo_estado}'. Válidos: {permitidos}"
            }

        estado_anterior = PersistenciaTransporte.actualizar_estado_entrega(orden_id, nuevo_estado, ubicacion_gps, observaciones)
        return {
            "exito": True,
            "codigo": 200,
            "mensaje": f"Estado actualizado de '{estado_anterior}' a '{nuevo_estado}'.",
            "datos": {
                "orden_id": orden_id,
                "estado_nuevo": nuevo_estado,
                "ubicacion_gps": ubicacion_gps
            }
        }

    @classmethod
    def consultar_trazabilidad(cls, orden_id: str) -> dict:
        orden = PersistenciaTransporte.obtener_orden(orden_id)
        if not orden:
            return {"exito": False, "codigo": 404, "mensaje": "Orden no encontrada."}
        historial = PersistenciaTransporte.obtener_historial_orden(orden_id)
        return {"exito": True, "codigo": 200, "orden": orden, "historial_eventos": historial, "historial": historial}


# ==============================================================================
# 3. CAPA DE PRESENTACIÓN / API REST (PRESENTATION TIER - PUERTA DE ENTRADA)
# ==============================================================================


    @classmethod
    def crear_orden(cls, orden_id, orden_manufactura_id, cliente_nombre, direccion_destino, peso_total_kg):
        if not orden_id or not cliente_nombre or not direccion_destino:
            return {"exito": False, "codigo": 400, "mensaje": "Todos los campos obligatorios deben ser completados."}
        try:
            peso_total_kg = float(peso_total_kg)
            if peso_total_kg <= 0:
                return {"exito": False, "codigo": 400, "mensaje": "El peso debe ser mayor a 0 kg."}
        except ValueError:
            return {"exito": False, "codigo": 400, "mensaje": "El peso ingresado no es un número válido."}

        existente = PersistenciaTransporte.obtener_orden(orden_id)
        if existente:
            return {"exito": False, "codigo": 409, "mensaje": f"La orden '{orden_id}' ya existe en el sistema."}

        PersistenciaTransporte.crear_orden(orden_id, orden_manufactura_id, cliente_nombre, direccion_destino, peso_total_kg)
        return {"exito": True, "codigo": 201, "mensaje": f"Orden de Transporte '{orden_id}' registrada exitosamente desde Manufactura."}

    @classmethod
    def editar_orden(cls, orden_id, direccion_destino, vehiculo_id, conductor_id):
        orden = PersistenciaTransporte.obtener_orden(orden_id)
        if not orden:
            return {"exito": False, "codigo": 404, "mensaje": f"Orden '{orden_id}' no encontrada."}

        vehiculo = PersistenciaTransporte.obtener_vehiculo(vehiculo_id)
        if vehiculo and orden['peso_total_kg'] > vehiculo['capacidad_max_kg']:
            return {
                "exito": False,
                "codigo": 422,
                "mensaje": f"RECHAZADO: El nuevo vehículo ({vehiculo['capacidad_max_kg']} kg) no soporta el peso de la orden ({orden['peso_total_kg']} kg)."
            }

        PersistenciaTransporte.editar_orden(orden_id, direccion_destino, vehiculo_id, conductor_id)
        return {"exito": True, "codigo": 200, "mensaje": f"Orden '{orden_id}' actualizada correctamente."}


app = Flask(__name__)
try:
    inicializar_bd()
except Exception:
    pass

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"modulo": "Transporte y Entregas", "estado": "Activo"}), 200

@app.route('/api/v1/transporte/ordenes/<string:orden_id>', methods=['GET'])
def get_orden(orden_id):
    res = LogicaNegocioTransporte.consultar_trazabilidad(orden_id)
    return jsonify(res), res.get("codigo", 200)

@app.route('/api/v1/transporte/asignar', methods=['POST'])
def post_asignar():
    data = request.get_json() or {}
    res = LogicaNegocioTransporte.asignar_despacho(data.get("orden_id"), data.get("vehiculo_id"), data.get("conductor_id"))
    return jsonify(res), res.get("codigo", 200)

@app.route('/api/v1/transporte/entregas/actualizar-estado', methods=['POST'])
def post_actualizar_estado():
    """
    PUERTA DE ENTRADA REST API:
    Recibe actualizaciones de estado desde dispositivos móviles / GPS de conductores.
    """
    data = request.get_json() or {}
    res = LogicaNegocioTransporte.actualizar_estado_entrega(
        orden_id=data.get("orden_id"),
        nuevo_estado=data.get("nuevo_estado"),
        ubicacion_gps=data.get("ubicacion_gps", "N/A"),
        observaciones=data.get("observaciones", "")
    )
    return jsonify(res), res.get("codigo", 200)


# ==============================================================================
# 4. SIMULACIÓN Y EJECUCIÓN PRÁCTICA
# ==============================================================================



import base64


@app.route('/api/v1/transporte/ordenes', methods=['POST'])
def post_crear_orden():
    data = request.get_json() or {}
    res = LogicaNegocioTransporte.crear_orden(
        data.get("orden_id"),
        data.get("orden_manufactura_id", "MANUF-000"),
        data.get("cliente_nombre"),
        data.get("direccion_destino"),
        data.get("peso_total_kg")
    )
    return jsonify(res), res.get("codigo", 200)

@app.route('/api/v1/transporte/ordenes/<string:orden_id>', methods=['PUT'])
def put_editar_orden(orden_id):
    data = request.get_json() or {}
    res = LogicaNegocioTransporte.editar_orden(
        orden_id,
        data.get("direccion_destino"),
        data.get("vehiculo_id"),
        data.get("conductor_id")
    )
    return jsonify(res), res.get("codigo", 200)


B64_UI = 'PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVzIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPHRpdGxlPk3Ds2R1bG8gZGUgVHJhbnNwb3J0ZSB5IEVudHJlZ2FzIHY2IC0gRW1wcmVzYSBNYW51ZmFjdHVyZXJhPC90aXRsZT4KPGxpbmsgcmVsPSJzdHlsZXNoZWV0IiBocmVmPSJodHRwczovL3VucGtnLmNvbS9sZWFmbGV0QDEuOS40L2Rpc3QvbGVhZmxldC5jc3MiIC8+CjxzdHlsZT4KKiB7IGJveC1zaXppbmc6IGJvcmRlci1ib3g7IH0KYm9keSB7IGZvbnQtZmFtaWx5OiAnU2Vnb2UgVUknLCBzeXN0ZW0tdWksIC1hcHBsZS1zeXN0ZW0sIHNhbnMtc2VyaWY7IGJhY2tncm91bmQtY29sb3I6ICMwZjE3MmE7IGNvbG9yOiAjZjhmYWZjOyBtYXJnaW46IDA7IHBhZGRpbmc6IDIwcHg7IGxpbmUtaGVpZ2h0OiAxLjU7IH0KLmNvbnRhaW5lciB7IG1heC13aWR0aDogMTI4MHB4OyBtYXJnaW46IDAgYXV0bzsgfQouaGVhZGVyIHsgYmFja2dyb3VuZDogbGluZWFyLWdyYWRpZW50KDEzNWRlZywgIzFlMWI0YiAwJSwgIzMxMmU4MSA1MCUsICM0MzM4Y2EgMTAwJSk7IHBhZGRpbmc6IDI0cHg7IGJvcmRlci1yYWRpdXM6IDE2cHg7IG1hcmdpbi1ib3R0b206IDI0cHg7IGJvcmRlcjogMXB4IHNvbGlkICMzNzMwYTM7IGJveC1zaGFkb3c6IDAgMTBweCAyNXB4IC01cHggcmdiYSgwLCAwLCAwLCAwLjUpOyBkaXNwbGF5OiBmbGV4OyBqdXN0aWZ5LWNvbnRlbnQ6IHNwYWNlLWJldHdlZW47IGFsaWduLWl0ZW1zOiBjZW50ZXI7IH0KLmhlYWRlci1pbmZvIGgxIHsgbWFyZ2luOiAwIDAgNnB4IDA7IGZvbnQtc2l6ZTogMjZweDsgZm9udC13ZWlnaHQ6IDgwMDsgY29sb3I6ICNmZmZmZmY7IGxldHRlci1zcGFjaW5nOiAtMC41cHg7IH0KLmhlYWRlci1pbmZvIHAgeyBtYXJnaW46IDA7IGNvbG9yOiAjYzdkMmZlOyBmb250LXNpemU6IDE0cHg7IGZvbnQtd2VpZ2h0OiA1MDA7IH0KLmJhZGdlLWNhcGEgeyBiYWNrZ3JvdW5kOiAjMzEyZTgxOyBjb2xvcjogIzgxOGNmODsgYm9yZGVyOiAxcHggc29saWQgIzYzNjZmMTsgcGFkZGluZzogNnB4IDE0cHg7IGJvcmRlci1yYWRpdXM6IDIwcHg7IGZvbnQtc2l6ZTogMTJweDsgZm9udC13ZWlnaHQ6IDcwMDsgdGV4dC10cmFuc2Zvcm06IHVwcGVyY2FzZTsgbGV0dGVyLXNwYWNpbmc6IDAuNXB4OyB9Ci5ncmlkIHsgZGlzcGxheTogZ3JpZDsgZ3JpZC10ZW1wbGF0ZS1jb2x1bW5zOiAxZnIgMWZyOyBnYXA6IDIwcHg7IG1hcmdpbi1ib3R0b206IDI0cHg7IH0KLmNhcmQgeyBiYWNrZ3JvdW5kOiAjMWUyOTNiOyBwYWRkaW5nOiAyMnB4OyBib3JkZXItcmFkaXVzOiAxNHB4OyBib3JkZXI6IDFweCBzb2xpZCAjMzM0MTU1OyBib3gtc2hhZG93OiAwIDRweCA2cHggLTFweCByZ2JhKDAsIDAsIDAsIDAuMyk7IH0KLmNhcmQgaDIgeyBtYXJnaW4tdG9wOiAwOyBmb250LXNpemU6IDE3cHg7IGZvbnQtd2VpZ2h0OiA3MDA7IGNvbG9yOiAjMzhiZGY4OyBib3JkZXItYm90dG9tOiAxcHggc29saWQgIzMzNDE1NTsgcGFkZGluZy1ib3R0b206IDEycHg7IG1hcmdpbi1ib3R0b206IDE2cHg7IGRpc3BsYXk6IGZsZXg7IGFsaWduLWl0ZW1zOiBjZW50ZXI7IGdhcDogOHB4OyB9CmxhYmVsIHsgZm9udC13ZWlnaHQ6IDYwMDsgZm9udC1zaXplOiAxM3B4OyBkaXNwbGF5OiBibG9jazsgbWFyZ2luLXRvcDogMTJweDsgY29sb3I6ICM5NGEzYjg7IH0Kc2VsZWN0LCBpbnB1dCwgYnV0dG9uIHsgd2lkdGg6IDEwMCU7IHBhZGRpbmc6IDExcHggMTRweDsgbWFyZ2luLXRvcDogNnB4OyBib3JkZXItcmFkaXVzOiA4cHg7IGJvcmRlcjogMXB4IHNvbGlkICM0NzU1Njk7IGJhY2tncm91bmQ6ICMwZjE3MmE7IGNvbG9yOiAjZjhmYWZjOyBmb250LXNpemU6IDE0cHg7IG91dGxpbmU6IG5vbmU7IHRyYW5zaXRpb246IGFsbCAwLjJzOyB9CnNlbGVjdDpmb2N1cywgaW5wdXQ6Zm9jdXMgeyBib3JkZXItY29sb3I6ICMzOGJkZjg7IGJveC1zaGFkb3c6IDAgMCAwIDNweCByZ2JhKDU2LCAxODksIDI0OCwgMC4yKTsgfQpidXR0b24geyBiYWNrZ3JvdW5kOiBsaW5lYXItZ3JhZGllbnQoMTM1ZGVnLCAjMjU2M2ViLCAjMWQ0ZWQ4KTsgY29sb3I6IHdoaXRlOyBib3JkZXI6IG5vbmU7IGZvbnQtd2VpZ2h0OiA3MDA7IG1hcmdpbi10b3A6IDE4cHg7IGN1cnNvcjogcG9pbnRlcjsgYm9yZGVyLXJhZGl1czogOHB4OyB0cmFuc2l0aW9uOiB0cmFuc2Zvcm0gMC4xcywgYm94LXNoYWRvdyAwLjJzOyB9CmJ1dHRvbjpob3ZlciB7IGJhY2tncm91bmQ6IGxpbmVhci1ncmFkaWVudCgxMzVkZWcsICMzYjgyZjYsICMyNTYzZWIpOyBib3gtc2hhZG93OiAwIDRweCAxMnB4IHJnYmEoMzcsIDk5LCAyMzUsIDAuNCk7IHRyYW5zZm9ybTogdHJhbnNsYXRlWSgtMXB4KTsgfQouYnRuLWFwaSB7IGJhY2tncm91bmQ6IGxpbmVhci1ncmFkaWVudCgxMzVkZWcsICMwNTk2NjksICMwNDc4NTcpOyB9Ci5idG4tYXBpOmhvdmVyIHsgYmFja2dyb3VuZDogbGluZWFyLWdyYWRpZW50KDEzNWRlZywgIzEwYjk4MSwgIzA1OTY2OSk7IGJveC1zaGFkb3c6IDAgNHB4IDEycHggcmdiYSgxNiwgMTg1LCAxMjksIDAuNCk7IH0KLmJ0bi1hZGQgeyBiYWNrZ3JvdW5kOiBsaW5lYXItZ3JhZGllbnQoMTM1ZGVnLCAjZDk3NzA2LCAjYjQ1MzA5KTsgfQouYnRuLWFkZDpob3ZlciB7IGJhY2tncm91bmQ6IGxpbmVhci1ncmFkaWVudCgxMzVkZWcsICNmNTllMGIsICNkOTc3MDYpOyB9Ci5hbGVydCB7IHBhZGRpbmc6IDEycHggMTZweDsgYm9yZGVyLXJhZGl1czogOHB4OyBtYXJnaW4tdG9wOiAxNnB4OyBmb250LXNpemU6IDEzcHg7IGZvbnQtd2VpZ2h0OiA2MDA7IGRpc3BsYXk6IG5vbmU7IH0KLmFsZXJ0LXN1Y2Nlc3MgeyBiYWNrZ3JvdW5kOiByZ2JhKDE2LCAxODUsIDEyOSwgMC4xNSk7IGNvbG9yOiAjMzRkMzk5OyBib3JkZXI6IDFweCBzb2xpZCByZ2JhKDE2LCAxODUsIDEyOSwgMC4zKTsgfQouYWxlcnQtZGFuZ2VyIHsgYmFja2dyb3VuZDogcmdiYSgyMzksIDY4LCA2OCwgMC4xNSk7IGNvbG9yOiAjZjg3MTcxOyBib3JkZXI6IDFweCBzb2xpZCByZ2JhKDIzOSwgNjgsIDY4LCAwLjMpOyB9Ci5mdWxsLWNhcmQgeyBtYXJnaW4tYm90dG9tOiAyNHB4OyB9Ci5maWx0ZXItYmFyIHsgZGlzcGxheTogZmxleDsgZ2FwOiAxMnB4OyBtYXJnaW4tYm90dG9tOiAxNnB4OyBmbGV4LXdyYXA6IHdyYXA7IH0KLmZpbHRlci1iYXIgaW5wdXQsIC5maWx0ZXItYmFyIHNlbGVjdCB7IHdpZHRoOiBhdXRvOyBmbGV4OiAxOyBtaW4td2lkdGg6IDIwMHB4OyBtYXJnaW4tdG9wOiAwOyB9CnRhYmxlIHsgd2lkdGg6IDEwMCU7IGJvcmRlci1jb2xsYXBzZTogY29sbGFwc2U7IG1hcmdpbi10b3A6IDEwcHg7IGZvbnQtc2l6ZTogMTNweDsgfQp0aCwgdGQgeyBwYWRkaW5nOiAxMnB4IDE0cHg7IHRleHQtYWxpZ246IGxlZnQ7IGJvcmRlci1ib3R0b206IDFweCBzb2xpZCAjMzM0MTU1OyB9CnRoIHsgYmFja2dyb3VuZDogIzBmMTcyYTsgY29sb3I6ICM5NGEzYjg7IGZvbnQtd2VpZ2h0OiA3MDA7IHRleHQtdHJhbnNmb3JtOiB1cHBlcmNhc2U7IGZvbnQtc2l6ZTogMTFweDsgbGV0dGVyLXNwYWNpbmc6IDAuNXB4OyB9CnRyOmhvdmVyIHsgYmFja2dyb3VuZDogcmdiYSg1MSwgNjUsIDg1LCAwLjUpOyB9Ci5iYWRnZSB7IHBhZGRpbmc6IDRweCAxMHB4OyBib3JkZXItcmFkaXVzOiAxMnB4OyBmb250LXNpemU6IDExcHg7IGZvbnQtd2VpZ2h0OiA4MDA7IHRleHQtdHJhbnNmb3JtOiB1cHBlcmNhc2U7IGxldHRlci1zcGFjaW5nOiAwLjVweDsgZGlzcGxheTogaW5saW5lLWJsb2NrOyB9Ci5iYWRnZS1DUkVBREEgeyBiYWNrZ3JvdW5kOiByZ2JhKDE0OCwgMTYzLCAxODQsIDAuMik7IGNvbG9yOiAjY2JkNWUxOyBib3JkZXI6IDFweCBzb2xpZCAjNjQ3NDhiOyB9Ci5iYWRnZS1BU0lHTkFEQSB7IGJhY2tncm91bmQ6IHJnYmEoNTksIDEzMCwgMjQ2LCAwLjIpOyBjb2xvcjogIzYwYTVmYTsgYm9yZGVyOiAxcHggc29saWQgIzNiODJmNjsgfQouYmFkZ2UtRU5fVFJBTlNJVE8geyBiYWNrZ3JvdW5kOiByZ2JhKDI0NSwgMTU4LCAxMSwgMC4yKTsgY29sb3I6ICNmYmJmMjQ7IGJvcmRlcjogMXB4IHNvbGlkICNmNTllMGI7IH0KLmJhZGdlLUVOVFJFR0FETyB7IGJhY2tncm91bmQ6IHJnYmEoMTYsIDE4NSwgMTI5LCAwLjIpOyBjb2xvcjogIzM0ZDM5OTsgYm9yZGVyOiAxcHggc29saWQgIzEwYjk4MTsgfQouYmFkZ2UtTk9WRURBRCB7IGJhY2tncm91bmQ6IHJnYmEoMjM5LCA2OCwgNjgsIDAuMik7IGNvbG9yOiAjZjg3MTcxOyBib3JkZXI6IDFweCBzb2xpZCAjZWY0NDQ0OyB9Ci5iYWRnZS1DQU5DRUxBREEgeyBiYWNrZ3JvdW5kOiByZ2JhKDEwMCwgMTE2LCAxMzksIDAuMik7IGNvbG9yOiAjOTRhM2I4OyBib3JkZXI6IDFweCBzb2xpZCAjNDc1NTY5OyB9Ci5idG4tc20geyBwYWRkaW5nOiA1cHggMTBweDsgbWFyZ2luLXRvcDogMDsgZm9udC1zaXplOiAxMXB4OyB3aWR0aDogYXV0bzsgYm9yZGVyLXJhZGl1czogNnB4OyBjdXJzb3I6IHBvaW50ZXI7IH0KLmJ0bi1ncHMgeyBiYWNrZ3JvdW5kOiAjMDI4NGM3OyBjb2xvcjogd2hpdGU7IGJvcmRlcjogbm9uZTsgfQouYnRuLWVkaXQgeyBiYWNrZ3JvdW5kOiAjNjM2NmYxOyBjb2xvcjogd2hpdGU7IGJvcmRlcjogbm9uZTsgfQoubWFwLWNvbnRhaW5lciB7IGhlaWdodDogMzIwcHg7IHdpZHRoOiAxMDAlOyBib3JkZXItcmFkaXVzOiAxMHB4OyBtYXJnaW4tdG9wOiAxNXB4OyBib3JkZXI6IDFweCBzb2xpZCAjMzM0MTU1OyB9Ci5tb2RhbCB7IGRpc3BsYXk6IG5vbmU7IHBvc2l0aW9uOiBmaXhlZDsgei1pbmRleDogMTAwMDsgbGVmdDogMDsgdG9wOiAwOyB3aWR0aDogMTAwJTsgaGVpZ2h0OiAxMDAlOyBiYWNrZ3JvdW5kOiByZ2JhKDAsMCwwLDAuOCk7IGJhY2tkcm9wLWZpbHRlcjogYmx1cig0cHgpOyB9Ci5tb2RhbC1jb250ZW50IHsgYmFja2dyb3VuZDogIzFlMjkzYjsgbWFyZ2luOiA1JSBhdXRvOyBwYWRkaW5nOiAyNHB4OyBib3JkZXItcmFkaXVzOiAxNnB4OyB3aWR0aDogOTAlOyBtYXgtd2lkdGg6IDY1MHB4OyBib3JkZXI6IDFweCBzb2xpZCAjNDc1NTY5OyBib3gtc2hhZG93OiAwIDIwcHggMjVweCAtNXB4IHJnYmEoMCwgMCwgMCwgMC41KTsgfQouY2xvc2UgeyBjb2xvcjogIzk0YTNiODsgZmxvYXQ6IHJpZ2h0OyBmb250LXNpemU6IDI4cHg7IGZvbnQtd2VpZ2h0OiBib2xkOyBjdXJzb3I6IHBvaW50ZXI7IH0KLmNsb3NlOmhvdmVyIHsgY29sb3I6IHdoaXRlOyB9Cjwvc3R5bGU+CjwvaGVhZD4KPGJvZHk+Cgo8ZGl2IGNsYXNzPSJjb250YWluZXIiPgogICAgPGRpdiBjbGFzcz0iaGVhZGVyIj4KICAgICAgICA8ZGl2IGNsYXNzPSJoZWFkZXItaW5mbyI+CiAgICAgICAgICAgIDxoMT7wn5qbIE3Ds2R1bG8gZGUgVHJhbnNwb3J0ZSB5IEVudHJlZ2FzICh2NiBSb2J1c3QpPC9oMT4KICAgICAgICAgICAgPHA+U2lzdGVtYSBkZSBJbmZvcm1hY2nDs24gcGFyYSBFbXByZXNhIE1hbnVmYWN0dXJlcmEg4oCUIEFycXVpdGVjdHVyYSBlbiAzIENhcGFzPC9wPgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9ImJhZGdlLWNhcGEiPkNhcGEgMTogSW50ZXJmYXogV2ViPC9kaXY+CiAgICA8L2Rpdj4KCiAgICA8IS0tIE1BUEEgR1BTIFkgUkFTVFJFTyBFTiBUSUVNUE8gUkVBTCAtLT4KICAgIDxkaXYgY2xhc3M9ImNhcmQgZnVsbC1jYXJkIj4KICAgICAgICA8aDI+8J+TjSBNb25pdG9yZW8geSBSYXN0cmVvIEdQUyBlbiBUaWVtcG8gUmVhbCAoR2VvbG9jYWxpemFjacOzbik8L2gyPgogICAgICAgIDxkaXYgc3R5bGU9ImRpc3BsYXk6IGZsZXg7IGdhcDogMTVweDsgYWxpZ24taXRlbXM6IGNlbnRlcjsgZmxleC13cmFwOiB3cmFwOyI+CiAgICAgICAgICAgIDxsYWJlbCBzdHlsZT0ibWFyZ2luLXRvcDowOyBtaW4td2lkdGg6IDE4MHB4OyI+U2VsZWNjaW9uYXIgT3JkZW4gcGFyYSBSYXN0cmVvOjwvbGFiZWw+CiAgICAgICAgICAgIDxzZWxlY3QgaWQ9InNlbGVjdEdwc09yZGVyIiBvbmNoYW5nZT0iYWN0dWFsaXphck1hcGFHcHMoKSIgc3R5bGU9ImZsZXg6MTsgbWFyZ2luLXRvcDowOyI+PC9zZWxlY3Q+CiAgICAgICAgICAgIDxzcGFuIGlkPSJncHNTdGF0dXNJbmZvIiBzdHlsZT0iZm9udC1zaXplOiAxM3B4OyBjb2xvcjogIzM4YmRmODsgZm9udC13ZWlnaHQ6IDYwMDsiPjwvc3Bhbj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IGlkPSJtYXAiIGNsYXNzPSJtYXAtY29udGFpbmVyIj48L2Rpdj4KICAgIDwvZGl2PgoKICAgIDxkaXYgY2xhc3M9ImdyaWQiPgogICAgICAgIDwhLS0gRk9STVVMQVJJTyAxOiBBU0lHTkFSIERFU1BBQ0hPIC0tPgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8aDI+8J+TpiAxLiBBc2lnbmFyIERlc3BhY2hvIChHZXN0b3IgTG9nw61zdGljbyk8L2gyPgogICAgICAgICAgICA8Zm9ybSBpZD0iZm9ybUFzaWduYXIiPgogICAgICAgICAgICAgICAgPGxhYmVsPk9yZGVuIGRlIFRyYW5zcG9ydGUgKE1hbnVmYWN0dXJhKTo8L2xhYmVsPgogICAgICAgICAgICAgICAgPHNlbGVjdCBpZD0ib3JkZW5Bc2lnbmFyIiByZXF1aXJlZD48L3NlbGVjdD4KICAgICAgICAgICAgICAgIDxsYWJlbD5WZWjDrWN1bG8gKFBsYWNhIC8gQ2FwYWNpZGFkIE3DoXhpbWEpOjwvbGFiZWw+CiAgICAgICAgICAgICAgICA8c2VsZWN0IGlkPSJ2ZWhpY3Vsb0FzaWduYXIiIHJlcXVpcmVkPjwvc2VsZWN0PgogICAgICAgICAgICAgICAgPGxhYmVsPkNvbmR1Y3RvciBBdXRvcml6YWRvOjwvbGFiZWw+CiAgICAgICAgICAgICAgICA8c2VsZWN0IGlkPSJjb25kdWN0b3JBc2lnbmFyIiByZXF1aXJlZD48L3NlbGVjdD4KICAgICAgICAgICAgICAgIDxidXR0b24gdHlwZT0ic3VibWl0Ij5WYWxpZGFyIENhcGFjaWRhZCB5IEFzaWduYXI8L2J1dHRvbj4KICAgICAgICAgICAgPC9mb3JtPgogICAgICAgICAgICA8ZGl2IGlkPSJtc2dBc2lnbmFyIiBjbGFzcz0iYWxlcnQiPjwvZGl2PgogICAgICAgIDwvZGl2PgoKICAgICAgICA8IS0tIEZPUk1VTEFSSU8gMjogUFVFUlRBIERFIEVOVFJBREEgQVBJIFJFU1QgLS0+CiAgICAgICAgPGRpdiBjbGFzcz0iY2FyZCI+CiAgICAgICAgICAgIDxoMj7wn4yQIDIuIFB1ZXJ0YSBkZSBFbnRyYWRhIC8gQVBJIFJFU1QgKEFwcCBDb25kdWN0b3IgLyBHUFMpPC9oMj4KICAgICAgICAgICAgPGZvcm0gaWQ9ImZvcm1BcGkiPgogICAgICAgICAgICAgICAgPGxhYmVsPk9yZGVuIGRlIFRyYW5zcG9ydGU6PC9sYWJlbD4KICAgICAgICAgICAgICAgIDxzZWxlY3QgaWQ9Im9yZGVuQXBpIiByZXF1aXJlZD48L3NlbGVjdD4KICAgICAgICAgICAgICAgIDxsYWJlbD5OdWV2byBFc3RhZG8gZGUgRW50cmVnYTo8L2xhYmVsPgogICAgICAgICAgICAgICAgPHNlbGVjdCBpZD0iZXN0YWRvQXBpIiByZXF1aXJlZD4KICAgICAgICAgICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSJFTl9UUkFOU0lUTyI+RU5fVFJBTlNJVE8gKEVuIGNhbWlubyk8L29wdGlvbj4KICAgICAgICAgICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSJFTlRSRUdBRE8iPkVOVFJFR0FETyAoRmluYWxpemFyIHkgbGliZXJhciByZWN1cnNvcyk8L29wdGlvbj4KICAgICAgICAgICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSJOT1ZFREFEIj5OT1ZFREFEIChSZXBvcnRhciBpbmNpZGVuY2lhKTwvb3B0aW9uPgogICAgICAgICAgICAgICAgICAgIDxvcHRpb24gdmFsdWU9IkNBTkNFTEFEQSI+Q0FOQ0VMQURBIChDYW5jZWxhciB5IGxpYmVyYXIgcmVjdXJzb3MpPC9vcHRpb24+CiAgICAgICAgICAgICAgICA8L3NlbGVjdD4KICAgICAgICAgICAgICAgIDxsYWJlbD5Db29yZGVuYWRhcyBHUFMgKFNlbnNvcik6PC9sYWJlbD4KICAgICAgICAgICAgICAgIDxpbnB1dCB0eXBlPSJ0ZXh0IiBpZD0iZ3BzQXBpIiB2YWx1ZT0iLTEyLjA0NjM3NCwgLTc3LjA0Mjc5MyIgcmVxdWlyZWQ+CiAgICAgICAgICAgICAgICA8bGFiZWw+T2JzZXJ2YWNpb25lcyAvIENvbmZpcm1hY2nDs246PC9sYWJlbD4KICAgICAgICAgICAgICAgIDxpbnB1dCB0eXBlPSJ0ZXh0IiBpZD0ib2JzQXBpIiB2YWx1ZT0iTm90aWZpY2FjacOzbiByZWNpYmlkYSBkZXNkZSBHUFMgZGUgdmVow61jdWxvIiByZXF1aXJlZD4KICAgICAgICAgICAgICAgIDxidXR0b24gdHlwZT0ic3VibWl0IiBjbGFzcz0iYnRuLWFwaSI+RW52aWFyIFBldGljacOzbiBhIEFQSSBSRVNUPC9idXR0b24+CiAgICAgICAgICAgIDwvZm9ybT4KICAgICAgICAgICAgPGRpdiBpZD0ibXNnQXBpIiBjbGFzcz0iYWxlcnQiPjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgPC9kaXY+CgogICAgPCEtLSBGT1JNVUxBUklPIDM6IElOVEVHUkFDScOTTiBDT04gTUFOVUZBQ1RVUkEgLS0+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGZ1bGwtY2FyZCI+CiAgICAgICAgPGgyPvCfj60gMy4gQ3JlYXIgTnVldmEgT3JkZW4gKFNpbXVsYWNpw7NuIEludGVncmFjacOzbiBjb24gTWFudWZhY3R1cmEpPC9oMj4KICAgICAgICA8Zm9ybSBpZD0iZm9ybU51ZXZhT3JkZW4iIHN0eWxlPSJkaXNwbGF5OiBncmlkOyBncmlkLXRlbXBsYXRlLWNvbHVtbnM6IHJlcGVhdChhdXRvLWZpdCwgbWlubWF4KDIwMHB4LCAxZnIpKTsgZ2FwOiAxNXB4OyBhbGlnbi1pdGVtczogZW5kOyI+CiAgICAgICAgICAgIDxkaXY+CiAgICAgICAgICAgICAgICA8bGFiZWw+SUQgT3JkZW4gVHJhbnNwb3J0ZTo8L2xhYmVsPgogICAgICAgICAgICAgICAgPGlucHV0IHR5cGU9InRleHQiIGlkPSJudWV2YUlkIiB2YWx1ZT0iT1QtMTAwNCIgcmVxdWlyZWQ+CiAgICAgICAgICAgIDwvZGl2PgogICAgICAgICAgICA8ZGl2PgogICAgICAgICAgICAgICAgPGxhYmVsPklEIE1hbnVmYWN0dXJhOjwvbGFiZWw+CiAgICAgICAgICAgICAgICA8aW5wdXQgdHlwZT0idGV4dCIgaWQ9Im51ZXZhTWFudWYiIHZhbHVlPSJNQU5VRi04ODA0IiByZXF1aXJlZD4KICAgICAgICAgICAgPC9kaXY+CiAgICAgICAgICAgIDxkaXY+CiAgICAgICAgICAgICAgICA8bGFiZWw+Q2xpZW50ZSBEZXN0aW5vOjwvbGFiZWw+CiAgICAgICAgICAgICAgICA8aW5wdXQgdHlwZT0idGV4dCIgaWQ9Im51ZXZvQ2xpZW50ZSIgdmFsdWU9IkFsbWFjZW5lcyBDZW50cmFsZXMgUy5BLiIgcmVxdWlyZWQ+CiAgICAgICAgICAgIDwvZGl2PgogICAgICAgICAgICA8ZGl2PgogICAgICAgICAgICAgICAgPGxhYmVsPkRpcmVjY2nDs24gRGVzdGlubzo8L2xhYmVsPgogICAgICAgICAgICAgICAgPGlucHV0IHR5cGU9InRleHQiIGlkPSJudWV2YURpcmVjY2lvbiIgdmFsdWU9IkF2LiBMYSBNYXJpbmEgMTUwMCwgQ2FsbGFvIiByZXF1aXJlZD4KICAgICAgICAgICAgPC9kaXY+CiAgICAgICAgICAgIDxkaXY+CiAgICAgICAgICAgICAgICA8bGFiZWw+UGVzbyBUb3RhbCAoa2cpOjwvbGFiZWw+CiAgICAgICAgICAgICAgICA8aW5wdXQgdHlwZT0ibnVtYmVyIiBpZD0ibnVldm9QZXNvIiB2YWx1ZT0iMTgwMCIgcmVxdWlyZWQ+CiAgICAgICAgICAgIDwvZGl2PgogICAgICAgICAgICA8ZGl2PgogICAgICAgICAgICAgICAgPGJ1dHRvbiB0eXBlPSJzdWJtaXQiIGNsYXNzPSJidG4tYWRkIj5SZWdpc3RyYXIgT3JkZW4gZGUgTWFudWZhY3R1cmE8L2J1dHRvbj4KICAgICAgICAgICAgPC9kaXY+CiAgICAgICAgPC9mb3JtPgogICAgICAgIDxkaXYgaWQ9Im1zZ051ZXZhIiBjbGFzcz0iYWxlcnQiPjwvZGl2PgogICAgPC9kaXY+CgogICAgPCEtLSBUQUJMQSBERSBNT05JVE9SRU8gWSBFRElUQUJJTElEQUQgLS0+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIGZ1bGwtY2FyZCI+CiAgICAgICAgPGgyPvCfk4ogNC4gTW9uaXRvciwgRWRpY2nDs24gRGlyZWN0YSB5IEF1ZGl0b3LDrWEgZGUgw5NyZGVuZXM8L2gyPgogICAgICAgIDxkaXYgY2xhc3M9ImZpbHRlci1iYXIiPgogICAgICAgICAgICA8aW5wdXQgdHlwZT0idGV4dCIgaWQ9InNlYXJjaEZpbHRlciIgcGxhY2Vob2xkZXI9IvCflI0gQnVzY2FyIHBvciBJRCwgY2xpZW50ZSBvIGRlc3Rpbm8uLi4iIG9ua2V5dXA9ImZpbHRyYXJUYWJsYSgpIj4KICAgICAgICAgICAgPHNlbGVjdCBpZD0ic3RhdHVzRmlsdGVyIiBvbmNoYW5nZT0iZmlsdHJhclRhYmxhKCkiPgogICAgICAgICAgICAgICAgPG9wdGlvbiB2YWx1ZT0iVE9ET1MiPlRvZG9zIGxvcyBlc3RhZG9zPC9vcHRpb24+CiAgICAgICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSJDUkVBREEiPkNSRUFEQTwvb3B0aW9uPgogICAgICAgICAgICAgICAgPG9wdGlvbiB2YWx1ZT0iQVNJR05BREEiPkFTSUdOQURBPC9vcHRpb24+CiAgICAgICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSJFTl9UUkFOU0lUTyI+RU5fVFJBTlNJVE88L29wdGlvbj4KICAgICAgICAgICAgICAgIDxvcHRpb24gdmFsdWU9IkVOVFJFR0FETyI+RU5UUkVHQURPPC9vcHRpb24+CiAgICAgICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSJOT1ZFREFEIj5OT1ZFREFEPC9vcHRpb24+CiAgICAgICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSJDQU5DRUxBREEiPkNBTkNFTEFEQTwvb3B0aW9uPgogICAgICAgICAgICA8L3NlbGVjdD4KICAgICAgICA8L2Rpdj4KICAgICAgICA8dGFibGU+CiAgICAgICAgICAgIDx0aGVhZD4KICAgICAgICAgICAgICAgIDx0cj4KICAgICAgICAgICAgICAgICAgICA8dGg+SUQgT3JkZW48L3RoPgogICAgICAgICAgICAgICAgICAgIDx0aD5NYW51ZmFjdHVyYTwvdGg+CiAgICAgICAgICAgICAgICAgICAgPHRoPkNsaWVudGUgLyBEZXN0aW5vPC90aD4KICAgICAgICAgICAgICAgICAgICA8dGg+UGVzbzwvdGg+CiAgICAgICAgICAgICAgICAgICAgPHRoPlZlaMOtY3VsbzwvdGg+CiAgICAgICAgICAgICAgICAgICAgPHRoPkNvbmR1Y3RvcjwvdGg+CiAgICAgICAgICAgICAgICAgICAgPHRoPkVzdGFkbzwvdGg+CiAgICAgICAgICAgICAgICAgICAgPHRoPlViaWNhY2nDs24gR1BTPC90aD4KICAgICAgICAgICAgICAgICAgICA8dGg+QWNjaW9uZXM8L3RoPgogICAgICAgICAgICAgICAgPC90cj4KICAgICAgICAgICAgPC90aGVhZD4KICAgICAgICAgICAgPHRib2R5IGlkPSJ0YWJsYU9yZGVuZXMiPjwvdGJvZHk+CiAgICAgICAgPC90YWJsZT4KICAgIDwvZGl2Pgo8L2Rpdj4KCjwhLS0gTU9EQUwgRURJQ0nDk04gUkVBU0lHTkFDScOTTiAtLT4KPGRpdiBpZD0ibW9kYWxFZGl0IiBjbGFzcz0ibW9kYWwiPgogICAgPGRpdiBjbGFzcz0ibW9kYWwtY29udGVudCI+CiAgICAgICAgPHNwYW4gY2xhc3M9ImNsb3NlIiBvbmNsaWNrPSJjZXJyYXJNb2RhbCgnbW9kYWxFZGl0JykiPiZ0aW1lczs8L3NwYW4+CiAgICAgICAgPGgyIHN0eWxlPSJjb2xvcjojMzhiZGY4OyBtYXJnaW4tdG9wOjA7Ij7inI/vuI8gRWRpdGFyIC8gUmVhc2lnbmFyIE9yZGVuIGRlIFRyYW5zcG9ydGU8L2gyPgogICAgICAgIDxmb3JtIGlkPSJmb3JtRWRpdCI+CiAgICAgICAgICAgIDxpbnB1dCB0eXBlPSJoaWRkZW4iIGlkPSJlZGl0T3JkZW5JZCI+CiAgICAgICAgICAgIDxsYWJlbD5EaXJlY2Npw7NuIGRlIERlc3Rpbm86PC9sYWJlbD4KICAgICAgICAgICAgPGlucHV0IHR5cGU9InRleHQiIGlkPSJlZGl0RGlyZWNjaW9uIiByZXF1aXJlZD4KICAgICAgICAgICAgPGxhYmVsPlJlYXNpZ25hciBWZWjDrWN1bG86PC9sYWJlbD4KICAgICAgICAgICAgPHNlbGVjdCBpZD0iZWRpdFZlaGljdWxvIj48L3NlbGVjdD4KICAgICAgICAgICAgPGxhYmVsPlJlYXNpZ25hciBDb25kdWN0b3I6PC9sYWJlbD4KICAgICAgICAgICAgPHNlbGVjdCBpZD0iZWRpdENvbmR1Y3RvciI+PC9zZWxlY3Q+CiAgICAgICAgICAgIDxidXR0b24gdHlwZT0ic3VibWl0IiBzdHlsZT0iYmFja2dyb3VuZDojNjM2NmYxOyI+R3VhcmRhciBDYW1iaW9zIEFkbWluaXN0cmF0aXZvczwvYnV0dG9uPgogICAgICAgIDwvZm9ybT4KICAgICAgICA8ZGl2IGlkPSJtc2dFZGl0IiBjbGFzcz0iYWxlcnQiPjwvZGl2PgogICAgPC9kaXY+CjwvZGl2PgoKPCEtLSBNT0RBTCBUUkFaQUJJTElEQUQgLyBBVURJVE9Sw41BIC0tPgo8ZGl2IGlkPSJtb2RhbFRyYWNlIiBjbGFzcz0ibW9kYWwiPgogICAgPGRpdiBjbGFzcz0ibW9kYWwtY29udGVudCIgc3R5bGU9Im1heC13aWR0aDogNzUwcHg7Ij4KICAgICAgICA8c3BhbiBjbGFzcz0iY2xvc2UiIG9uY2xpY2s9ImNlcnJhck1vZGFsKCdtb2RhbFRyYWNlJykiPiZ0aW1lczs8L3NwYW4+CiAgICAgICAgPGgyIHN0eWxlPSJjb2xvcjojMzhiZGY4OyBtYXJnaW4tdG9wOjA7Ij7wn5OcIEhpc3RvcmlhbCBkZSBBdWRpdG9yw61hIHkgVHJhemFiaWxpZGFkIEluYWx0ZXJhYmxlPC9oMj4KICAgICAgICA8ZGl2IGlkPSJ0cmFjZUNvbnRlbnQiIHN0eWxlPSJtYXgtaGVpZ2h0OiA0MDBweDsgb3ZlcmZsb3cteTogYXV0bzsiPjwvZGl2PgogICAgPC9kaXY+CjwvZGl2PgoKPHNjcmlwdCBzcmM9Imh0dHBzOi8vdW5wa2cuY29tL2xlYWZsZXRAMS45LjQvZGlzdC9sZWFmbGV0LmpzIj48L3NjcmlwdD4KPHNjcmlwdD4KbGV0IGdsb2JhbERhdGEgPSB7IG9yZGVuZXM6IFtdLCB2ZWhpY3Vsb3M6IFtdLCBjb25kdWN0b3JlczogW10gfTsKbGV0IG1hcCwgbWFya2VyOwoKZnVuY3Rpb24gaW5pdE1hcCgpIHsKICAgIG1hcCA9IEwubWFwKCdtYXAnKS5zZXRWaWV3KFstMTIuMDQ2Mzc0LCAtNzcuMDQyNzkzXSwgMTMpOwogICAgTC50aWxlTGF5ZXIoJ2h0dHBzOi8ve3N9LnRpbGUub3BlbnN0cmVldG1hcC5vcmcve3p9L3t4fS97eX0ucG5nJywgewogICAgICAgIGF0dHJpYnV0aW9uOiAnJmNvcHk7IE9wZW5TdHJlZXRNYXAnCiAgICB9KS5hZGRUbyhtYXApOwogICAgbWFya2VyID0gTC5tYXJrZXIoWy0xMi4wNDYzNzQsIC03Ny4wNDI3OTNdKS5hZGRUbyhtYXApCiAgICAgICAgLmJpbmRQb3B1cCgnUGxhbnRhIFByaW5jaXBhbCBkZSBNYW51ZmFjdHVyYScpCiAgICAgICAgLm9wZW5Qb3B1cCgpOwp9Cgphc3luYyBmdW5jdGlvbiBjYXJnYXJEYXRvcygpIHsKICAgIGNvbnN0IHJlcyA9IGF3YWl0IGZldGNoKCcvYXBpL3YxL3RyYW5zcG9ydGUvZGF0b3MnKTsKICAgIGdsb2JhbERhdGEgPSBhd2FpdCByZXMuanNvbigpOwogICAgCiAgICBjb25zdCBzZWxPMSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdvcmRlbkFzaWduYXInKTsKICAgIGNvbnN0IHNlbE8yID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ29yZGVuQXBpJyk7CiAgICBjb25zdCBzZWxHcHMgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VsZWN0R3BzT3JkZXInKTsKICAgIAogICAgc2VsTzEuaW5uZXJIVE1MID0gJyc7IHNlbE8yLmlubmVySFRNTCA9ICcnOyBzZWxHcHMuaW5uZXJIVE1MID0gJyc7CiAgICAKICAgIGdsb2JhbERhdGEub3JkZW5lcy5mb3JFYWNoKG8gPT4gewogICAgICAgIGNvbnN0IG9wdFRleHQgPSBgJHtvLmlkfSAtICR7by5jbGllbnRlX25vbWJyZX0gKCR7by5wZXNvX3RvdGFsX2tnfSBrZykgWyR7by5lc3RhZG99XWA7CiAgICAgICAgc2VsTzEuaW5uZXJIVE1MICs9IGA8b3B0aW9uIHZhbHVlPSIke28uaWR9Ij4ke29wdFRleHR9PC9vcHRpb24+YDsKICAgICAgICBzZWxPMi5pbm5lckhUTUwgKz0gYDxvcHRpb24gdmFsdWU9IiR7by5pZH0iPiR7b3B0VGV4dH08L29wdGlvbj5gOwogICAgICAgIHNlbEdwcy5pbm5lckhUTUwgKz0gYDxvcHRpb24gdmFsdWU9IiR7by5pZH0iPiR7by5pZH0gKCR7by5lc3RhZG99KSAtICR7by5jbGllbnRlX25vbWJyZX08L29wdGlvbj5gOwogICAgfSk7CgogICAgY29uc3Qgc2VsViA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd2ZWhpY3Vsb0FzaWduYXInKTsKICAgIHNlbFYuaW5uZXJIVE1MID0gJyc7CiAgICBnbG9iYWxEYXRhLnZlaGljdWxvcy5mb3JFYWNoKHYgPT4gewogICAgICAgIHNlbFYuaW5uZXJIVE1MICs9IGA8b3B0aW9uIHZhbHVlPSIke3YuaWR9Ij4ke3YuaWR9ICgke3YucGxhY2F9KSAtIENhcDogJHt2LmNhcGFjaWRhZF9tYXhfa2d9IGtnIFske3YuZXN0YWRvfV08L29wdGlvbj5gOwogICAgfSk7CgogICAgY29uc3Qgc2VsQyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjb25kdWN0b3JBc2lnbmFyJyk7CiAgICBzZWxDLmlubmVySFRNTCA9ICcnOwogICAgZ2xvYmFsRGF0YS5jb25kdWN0b3Jlcy5mb3JFYWNoKGMgPT4gewogICAgICAgIHNlbEMuaW5uZXJIVE1MICs9IGA8b3B0aW9uIHZhbHVlPSIke2MuaWR9Ij4ke2Mubm9tYnJlfSAoJHtjLmxpY2VuY2lhfSkgWyR7Yy5lc3RhZG99XTwvb3B0aW9uPmA7CiAgICB9KTsKCiAgICByZW5kZXJUYWJsYShnbG9iYWxEYXRhLm9yZGVuZXMpOwogICAgYWN0dWFsaXphck1hcGFHcHMoKTsKfQoKZnVuY3Rpb24gcmVuZGVyVGFibGEobGlzdGEpIHsKICAgIGNvbnN0IHRiID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RhYmxhT3JkZW5lcycpOwogICAgdGIuaW5uZXJIVE1MID0gJyc7CiAgICBsaXN0YS5mb3JFYWNoKG8gPT4gewogICAgICAgIHRiLmlubmVySFRNTCArPSBgCiAgICAgICAgICAgIDx0cj4KICAgICAgICAgICAgICAgIDx0ZD48Yj4ke28uaWR9PC9iPjwvdGQ+CiAgICAgICAgICAgICAgICA8dGQ+JHtvLm9yZGVuX21hbnVmYWN0dXJhX2lkfTwvdGQ+CiAgICAgICAgICAgICAgICA8dGQ+PGI+JHtvLmNsaWVudGVfbm9tYnJlfTwvYj48YnI+PHNtYWxsIHN0eWxlPSJjb2xvcjojOTRhM2I4Ij4ke28uZGlyZWNjaW9uX2Rlc3Rpbm99PC9zbWFsbD48L3RkPgogICAgICAgICAgICAgICAgPHRkPiR7by5wZXNvX3RvdGFsX2tnfSBrZzwvdGQ+CiAgICAgICAgICAgICAgICA8dGQ+JHtvLnZlaGljdWxvX2lkIHx8ICc8c3BhbiBzdHlsZT0iY29sb3I6IzY0NzQ4YiI+U2luIGFzaWduYXI8L3NwYW4+J308L3RkPgogICAgICAgICAgICAgICAgPHRkPiR7by5jb25kdWN0b3JfaWQgfHwgJzxzcGFuIHN0eWxlPSJjb2xvcjojNjQ3NDhiIj5TaW4gYXNpZ25hcjwvc3Bhbj4nfTwvdGQ+CiAgICAgICAgICAgICAgICA8dGQ+PHNwYW4gY2xhc3M9ImJhZGdlIGJhZGdlLSR7by5lc3RhZG99Ij4ke28uZXN0YWRvfTwvc3Bhbj48L3RkPgogICAgICAgICAgICAgICAgPHRkPjxzbWFsbCBzdHlsZT0iY29sb3I6IzM4YmRmOCI+JHtvLnViaWNhY2lvbl9hY3R1YWx9PC9zbWFsbD48L3RkPgogICAgICAgICAgICAgICAgPHRkPgogICAgICAgICAgICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0bi1zbSBidG4tZ3BzIiBvbmNsaWNrPSJ2ZXJIaXN0b3JpYWwoJyR7by5pZH0nKSI+8J+TnCBIaXN0b3JpYWw8L2J1dHRvbj4KICAgICAgICAgICAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4tc20gYnRuLWVkaXQiIG9uY2xpY2s9ImFicmlyRWRpdGFyKCcke28uaWR9JykiPuKcj++4jyBFZGl0YXI8L2J1dHRvbj4KICAgICAgICAgICAgICAgICAgICAke28uZXN0YWRvID09PSAnRU5fVFJBTlNJVE8nID8gYDxidXR0b24gY2xhc3M9ImJ0bi1zbSBidG4tYXBpIiBvbmNsaWNrPSJmaW5hbGl6YXJSYXBpZG8oJyR7by5pZH0nKSI+4pyFIEVudHJlZ2FyPC9idXR0b24+YCA6ICcnfQogICAgICAgICAgICAgICAgPC90ZD4KICAgICAgICAgICAgPC90cj4KICAgICAgICBgOwogICAgfSk7Cn0KCmZ1bmN0aW9uIGFjdHVhbGl6YXJNYXBhR3BzKCkgewogICAgY29uc3Qgc2VsZWN0ZWRJZCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZWxlY3RHcHNPcmRlcicpLnZhbHVlOwogICAgY29uc3Qgb3JkZW4gPSBnbG9iYWxEYXRhLm9yZGVuZXMuZmluZChvID0+IG8uaWQgPT09IHNlbGVjdGVkSWQpOwogICAgaWYgKCFvcmRlbikgcmV0dXJuOwoKICAgIGNvbnN0IGNvb3JkcyA9IG9yZGVuLnViaWNhY2lvbl9hY3R1YWwuc3BsaXQoJywnKS5tYXAoYyA9PiBwYXJzZUZsb2F0KGMudHJpbSgpKSk7CiAgICBpZiAoY29vcmRzLmxlbmd0aCA9PT0gMiAmJiAhaXNOYU4oY29vcmRzWzBdKSAmJiAhaXNOYU4oY29vcmRzWzFdKSkgewogICAgICAgIG1hcC5zZXRWaWV3KGNvb3JkcywgMTQpOwogICAgICAgIG1hcmtlci5zZXRMYXRMbmcoY29vcmRzKQogICAgICAgICAgICAuYmluZFBvcHVwKGA8Yj4ke29yZGVuLmlkfTwvYj48YnI+RXN0YWRvOiAke29yZGVuLmVzdGFkb308YnI+Q2xpZW50ZTogJHtvcmRlbi5jbGllbnRlX25vbWJyZX1gKQogICAgICAgICAgICAub3BlblBvcHVwKCk7CiAgICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2dwc1N0YXR1c0luZm8nKS5pbm5lclRleHQgPSBg8J+TjSBHUFM6ICR7b3JkZW4udWJpY2FjaW9uX2FjdHVhbH0gfCBWZWjDrWN1bG86ICR7b3JkZW4udmVoaWN1bG9faWQgfHwgJ04vQSd9YDsKICAgIH0KfQoKZnVuY3Rpb24gZmlsdHJhclRhYmxhKCkgewogICAgY29uc3QgcSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZWFyY2hGaWx0ZXInKS52YWx1ZS50b0xvd2VyQ2FzZSgpOwogICAgY29uc3Qgc3QgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RhdHVzRmlsdGVyJykudmFsdWU7CiAgICBjb25zdCBmaWx0cmFkYXMgPSBnbG9iYWxEYXRhLm9yZGVuZXMuZmlsdGVyKG8gPT4gewogICAgICAgIGNvbnN0IG1hdGNoU2VhcmNoID0gby5pZC50b0xvd2VyQ2FzZSgpLmluY2x1ZGVzKHEpIHx8IG8uY2xpZW50ZV9ub21icmUudG9Mb3dlckNhc2UoKS5pbmNsdWRlcyhxKSB8fCBvLmRpcmVjY2lvbl9kZXN0aW5vLnRvTG93ZXJDYXNlKCkuaW5jbHVkZXMocSk7CiAgICAgICAgY29uc3QgbWF0Y2hTdGF0dXMgPSAoc3QgPT09ICdUT0RPUycgfHwgby5lc3RhZG8gPT09IHN0KTsKICAgICAgICByZXR1cm4gbWF0Y2hTZWFyY2ggJiYgbWF0Y2hTdGF0dXM7CiAgICB9KTsKICAgIHJlbmRlclRhYmxhKGZpbHRyYWRhcyk7Cn0KCmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmb3JtQXNpZ25hcicpLm9uc3VibWl0ID0gYXN5bmMgKGUpID0+IHsKICAgIGUucHJldmVudERlZmF1bHQoKTsKICAgIGNvbnN0IG1zZyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtc2dBc2lnbmFyJyk7CiAgICBtc2cuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICAgIGNvbnN0IHBheWxvYWQgPSB7CiAgICAgICAgb3JkZW5faWQ6IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdvcmRlbkFzaWduYXInKS52YWx1ZSwKICAgICAgICB2ZWhpY3Vsb19pZDogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3ZlaGljdWxvQXNpZ25hcicpLnZhbHVlLAogICAgICAgIGNvbmR1Y3Rvcl9pZDogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NvbmR1Y3RvckFzaWduYXInKS52YWx1ZQogICAgfTsKICAgIGNvbnN0IHJlcyA9IGF3YWl0IGZldGNoKCcvYXBpL3YxL3RyYW5zcG9ydGUvYXNpZ25hcicsIHsKICAgICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgICBoZWFkZXJzOiB7J0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkocGF5bG9hZCkKICAgIH0pOwogICAgY29uc3QgcmVzdWx0ID0gYXdhaXQgcmVzLmpzb24oKTsKICAgIG1zZy5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsKICAgIG1zZy5jbGFzc05hbWUgPSAnYWxlcnQgJyArIChyZXN1bHQuZXhpdG8gPyAnYWxlcnQtc3VjY2VzcycgOiAnYWxlcnQtZGFuZ2VyJyk7CiAgICBtc2cuaW5uZXJUZXh0ID0gcmVzdWx0Lm1lbnNhamU7CiAgICBjYXJnYXJEYXRvcygpOwp9OwoKZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2Zvcm1BcGknKS5vbnN1Ym1pdCA9IGFzeW5jIChlKSA9PiB7CiAgICBlLnByZXZlbnREZWZhdWx0KCk7CiAgICBjb25zdCBtc2cgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbXNnQXBpJyk7CiAgICBtc2cuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICAgIGNvbnN0IHBheWxvYWQgPSB7CiAgICAgICAgb3JkZW5faWQ6IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdvcmRlbkFwaScpLnZhbHVlLAogICAgICAgIG51ZXZvX2VzdGFkbzogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2VzdGFkb0FwaScpLnZhbHVlLAogICAgICAgIHViaWNhY2lvbl9ncHM6IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdncHNBcGknKS52YWx1ZSwKICAgICAgICBvYnNlcnZhY2lvbmVzOiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnb2JzQXBpJykudmFsdWUKICAgIH07CiAgICBjb25zdCByZXMgPSBhd2FpdCBmZXRjaCgnL2FwaS92MS90cmFuc3BvcnRlL2VudHJlZ2FzL2FjdHVhbGl6YXItZXN0YWRvJywgewogICAgICAgIG1ldGhvZDogJ1BPU1QnLAogICAgICAgIGhlYWRlcnM6IHsnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICBib2R5OiBKU09OLnN0cmluZ2lmeShwYXlsb2FkKQogICAgfSk7CiAgICBjb25zdCByZXN1bHQgPSBhd2FpdCByZXMuanNvbigpOwogICAgbXNnLnN0eWxlLmRpc3BsYXkgPSAnYmxvY2snOwogICAgbXNnLmNsYXNzTmFtZSA9ICdhbGVydCAnICsgKHJlc3VsdC5leGl0byA/ICdhbGVydC1zdWNjZXNzJyA6ICdhbGVydC1kYW5nZXInKTsKICAgIG1zZy5pbm5lclRleHQgPSByZXN1bHQubWVuc2FqZTsKICAgIGNhcmdhckRhdG9zKCk7Cn07Cgpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZm9ybU51ZXZhT3JkZW4nKS5vbnN1Ym1pdCA9IGFzeW5jIChlKSA9PiB7CiAgICBlLnByZXZlbnREZWZhdWx0KCk7CiAgICBjb25zdCBtc2cgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbXNnTnVldmEnKTsKICAgIG1zZy5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgY29uc3QgcGF5bG9hZCA9IHsKICAgICAgICBvcmRlbl9pZDogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ251ZXZhSWQnKS52YWx1ZSwKICAgICAgICBvcmRlbl9tYW51ZmFjdHVyYV9pZDogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ251ZXZhTWFudWYnKS52YWx1ZSwKICAgICAgICBjbGllbnRlX25vbWJyZTogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ251ZXZvQ2xpZW50ZScpLnZhbHVlLAogICAgICAgIGRpcmVjY2lvbl9kZXN0aW5vOiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbnVldmFEaXJlY2Npb24nKS52YWx1ZSwKICAgICAgICBwZXNvX3RvdGFsX2tnOiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbnVldm9QZXNvJykudmFsdWUKICAgIH07CiAgICBjb25zdCByZXMgPSBhd2FpdCBmZXRjaCgnL2FwaS92MS90cmFuc3BvcnRlL29yZGVuZXMnLCB7CiAgICAgICAgbWV0aG9kOiAnUE9TVCcsCiAgICAgICAgaGVhZGVyczogeydDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbid9LAogICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHBheWxvYWQpCiAgICB9KTsKICAgIGNvbnN0IHJlc3VsdCA9IGF3YWl0IHJlcy5qc29uKCk7CiAgICBtc2cuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICBtc2cuY2xhc3NOYW1lID0gJ2FsZXJ0ICcgKyAocmVzdWx0LmV4aXRvID8gJ2FsZXJ0LXN1Y2Nlc3MnIDogJ2FsZXJ0LWRhbmdlcicpOwogICAgbXNnLmlubmVyVGV4dCA9IHJlc3VsdC5tZW5zYWplOwogICAgaWYocmVzdWx0LmV4aXRvKSB7CiAgICAgICAgY2FyZ2FyRGF0b3MoKTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbnVldmFJZCcpLnZhbHVlID0gJ09ULScgKyBNYXRoLmZsb29yKDEwMDUgKyBNYXRoLnJhbmRvbSgpKjEwMCk7CiAgICB9CiAgICBjYXJnYXJEYXRvcygpOwp9OwoKYXN5bmMgZnVuY3Rpb24gdmVySGlzdG9yaWFsKG9yZGVuSWQpIHsKICAgIGNvbnN0IHJlcyA9IGF3YWl0IGZldGNoKGAvYXBpL3YxL3RyYW5zcG9ydGUvb3JkZW5lcy8ke29yZGVuSWR9YCk7CiAgICBjb25zdCBkYXRhID0gYXdhaXQgcmVzLmpzb24oKTsKICAgIGlmICghZGF0YS5leGl0bykgcmV0dXJuOwogICAgCiAgICBsZXQgaHRtbCA9IGA8cD48Yj5PcmRlbjo8L2I+ICR7ZGF0YS5vcmRlbi5pZH0gfCA8Yj5DbGllbnRlOjwvYj4gJHtkYXRhLm9yZGVuLmNsaWVudGVfbm9tYnJlfTwvcD5gOwogICAgaHRtbCArPSBgPHRhYmxlPjx0aGVhZD48dHI+PHRoPkZlY2hhIC8gSG9yYTwvdGg+PHRoPkVzdGFkbyBBbnRlcmlvcjwvdGg+PHRoPk51ZXZvIEVzdGFkbzwvdGg+PHRoPlViaWNhY2nDs24gR1BTPC90aD48dGg+T2JzZXJ2YWNpb25lczwvdGg+PC90cj48L3RoZWFkPjx0Ym9keT5gOwogICAgY29uc3QgaGlzdExpc3QgPSBkYXRhLmhpc3RvcmlhbF9ldmVudG9zIHx8IGRhdGEuaGlzdG9yaWFsIHx8IFtdOwogICAgaWYgKGhpc3RMaXN0Lmxlbmd0aCA9PT0gMCkgewogICAgICAgIGh0bWwgKz0gYDx0cj48dGQgY29sc3Bhbj0iNSIgc3R5bGU9InRleHQtYWxpZ246Y2VudGVyOyBjb2xvcjojOTRhM2I4OyI+Tm8gaGF5IHJlZ2lzdHJvcyBkZSBoaXN0b3JpYWwgYcO6biBwYXJhIGVzdGEgb3JkZW4uPC90ZD48L3RyPmA7CiAgICB9IGVsc2UgewogICAgICAgIGhpc3RMaXN0LmZvckVhY2goaCA9PiB7CiAgICAgICAgaHRtbCArPSBgPHRyPjx0ZD4ke2guZmVjaGFfcmVnaXN0cm99PC90ZD48dGQ+JHtoLmVzdGFkb19hbnRlcmlvciB8fCAnSU5JQ0lBTCd9PC90ZD48dGQ+PHNwYW4gY2xhc3M9ImJhZGdlIGJhZGdlLSR7aC5lc3RhZG9fbnVldm99Ij4ke2guZXN0YWRvX251ZXZvfTwvc3Bhbj48L3RkPjx0ZD4ke2gudWJpY2FjaW9uX2dwcyB8fCAnTi9BJ308L3RkPjx0ZD4ke2gub2JzZXJ2YWNpb25lc308L3RkPjwvdHI+YDsKICAgICAgICB9KTsKICAgIH0KICAgIGh0bWwgKz0gYDwvdGJvZHk+PC90YWJsZT5gOwogICAgCiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndHJhY2VDb250ZW50JykuaW5uZXJIVE1MID0gaHRtbDsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtb2RhbFRyYWNlJykuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7Cn0KCmZ1bmN0aW9uIGFicmlyRWRpdGFyKG9yZGVuSWQpIHsKICAgIGNvbnN0IG8gPSBnbG9iYWxEYXRhLm9yZGVuZXMuZmluZChpdGVtID0+IGl0ZW0uaWQgPT09IG9yZGVuSWQpOwogICAgaWYgKCFvKSByZXR1cm47CiAgICAKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdlZGl0T3JkZW5JZCcpLnZhbHVlID0gby5pZDsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdlZGl0RGlyZWNjaW9uJykudmFsdWUgPSBvLmRpcmVjY2lvbl9kZXN0aW5vOwogICAgCiAgICBjb25zdCBzZWxWID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2VkaXRWZWhpY3VsbycpOwogICAgc2VsVi5pbm5lckhUTUwgPSAnJzsKICAgIGdsb2JhbERhdGEudmVoaWN1bG9zLmZvckVhY2godiA9PiB7CiAgICAgICAgY29uc3Qgc2VsID0gKHYuaWQgPT09IG8udmVoaWN1bG9faWQpID8gJ3NlbGVjdGVkJyA6ICcnOwogICAgICAgIHNlbFYuaW5uZXJIVE1MICs9IGA8b3B0aW9uIHZhbHVlPSIke3YuaWR9IiAke3NlbH0+JHt2LmlkfSAoJHt2LnBsYWNhfSkgLSBDYXA6ICR7di5jYXBhY2lkYWRfbWF4X2tnfSBrZyBbJHt2LmVzdGFkb31dPC9vcHRpb24+YDsKICAgIH0pOwoKICAgIGNvbnN0IHNlbEMgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZWRpdENvbmR1Y3RvcicpOwogICAgc2VsQy5pbm5lckhUTUwgPSAnJzsKICAgIGdsb2JhbERhdGEuY29uZHVjdG9yZXMuZm9yRWFjaChjID0+IHsKICAgICAgICBjb25zdCBzZWwgPSAoYy5pZCA9PT0gby5jb25kdWN0b3JfaWQpID8gJ3NlbGVjdGVkJyA6ICcnOwogICAgICAgIHNlbEMuaW5uZXJIVE1MICs9IGA8b3B0aW9uIHZhbHVlPSIke2MuaWR9IiAke3NlbH0+JHtjLm5vbWJyZX0gKCR7Yy5saWNlbmNpYX0pIFske2MuZXN0YWRvfV08L29wdGlvbj5gOwogICAgfSk7CgogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21vZGFsRWRpdCcpLnN0eWxlLmRpc3BsYXkgPSAnYmxvY2snOwp9Cgpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZm9ybUVkaXQnKS5vbnN1Ym1pdCA9IGFzeW5jIChlKSA9PiB7CiAgICBlLnByZXZlbnREZWZhdWx0KCk7CiAgICBjb25zdCBvcmRlbklkID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2VkaXRPcmRlbklkJykudmFsdWU7CiAgICBjb25zdCBwYXlsb2FkID0gewogICAgICAgIGRpcmVjY2lvbl9kZXN0aW5vOiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZWRpdERpcmVjY2lvbicpLnZhbHVlLAogICAgICAgIHZlaGljdWxvX2lkOiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZWRpdFZlaGljdWxvJykudmFsdWUsCiAgICAgICAgY29uZHVjdG9yX2lkOiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZWRpdENvbmR1Y3RvcicpLnZhbHVlCiAgICB9OwogICAgY29uc3QgcmVzID0gYXdhaXQgZmV0Y2goYC9hcGkvdjEvdHJhbnNwb3J0ZS9vcmRlbmVzLyR7b3JkZW5JZH1gLCB7CiAgICAgICAgbWV0aG9kOiAnUFVUJywKICAgICAgICBoZWFkZXJzOiB7J0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkocGF5bG9hZCkKICAgIH0pOwogICAgY29uc3QgcmVzdWx0ID0gYXdhaXQgcmVzLmpzb24oKTsKICAgIGNvbnN0IG1zZyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtc2dFZGl0Jyk7CiAgICBtc2cuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICBtc2cuY2xhc3NOYW1lID0gJ2FsZXJ0ICcgKyAocmVzdWx0LmV4aXRvID8gJ2FsZXJ0LXN1Y2Nlc3MnIDogJ2FsZXJ0LWRhbmdlcicpOwogICAgbXNnLmlubmVyVGV4dCA9IHJlc3VsdC5tZW5zYWplOwogICAgY2FyZ2FyRGF0b3MoKTsKICAgIHNldFRpbWVvdXQoKCkgPT4gY2VycmFyTW9kYWwoJ21vZGFsRWRpdCcpLCAxMjAwKTsKfTsKCmFzeW5jIGZ1bmN0aW9uIGZpbmFsaXphclJhcGlkbyhvcmRlbklkKSB7CiAgICBpZiAoIWNvbmZpcm0oYMK/Q29uZmlybWFyIGVudHJlZ2EgZmluYWwgZGUgbGEgb3JkZW4gJHtvcmRlbklkfT8gU2UgbGliZXJhcsOhbiBlbCB2ZWjDrWN1bG8geSBlbCBjb25kdWN0b3IuYCkpIHJldHVybjsKICAgIGNvbnN0IHBheWxvYWQgPSB7CiAgICAgICAgb3JkZW5faWQ6IG9yZGVuSWQsCiAgICAgICAgbnVldm9fZXN0YWRvOiAnRU5UUkVHQURPJywKICAgICAgICB1YmljYWNpb25fZ3BzOiAnLTEyLjA4MDExMiwgLTc3LjAyMTE0NScsCiAgICAgICAgb2JzZXJ2YWNpb25lczogJ0VudHJlZ2EgZmluYWxpemFkYSBkaXJlY3RhbWVudGUgZGVzZGUgZWwgTW9uaXRvci4nCiAgICB9OwogICAgYXdhaXQgZmV0Y2goJy9hcGkvdjEvdHJhbnNwb3J0ZS9lbnRyZWdhcy9hY3R1YWxpemFyLWVzdGFkbycsIHsKICAgICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgICBoZWFkZXJzOiB7J0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkocGF5bG9hZCkKICAgIH0pOwogICAgY2FyZ2FyRGF0b3MoKTsKfQoKZnVuY3Rpb24gY2VycmFyTW9kYWwoaWQpIHsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKS5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwp9Cgp3aW5kb3cub25sb2FkID0gKCkgPT4gewogICAgaW5pdE1hcCgpOwogICAgY2FyZ2FyRGF0b3MoKTsKfTsKPC9zY3JpcHQ+CjwvYm9keT4KPC9odG1sPg=='
HTML_UI = base64.b64decode(B64_UI).decode('utf-8')

@app.route('/')
def index_ui():
    return render_template_string(HTML_UI)

@app.route('/api/v1/transporte/datos', methods=['GET'])
def get_datos_completos():
    conn = obtener_conexion()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ordenes_transporte")
    ordenes = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM vehiculos")
    vehiculos = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM conductores")
    conductores = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"ordenes": ordenes, "vehiculos": vehiculos, "conductores": conductores})

def abrir_navegador():
    webbrowser.open_new("http://127.0.0.1:5000/")

if __name__ == '__main__':
    inicializar_bd()
    print("=" * 72)
    print("🚀 SERVIDOR WEB INICIADO: MÓDULO DE TRANSPORTE Y ENTREGAS")
    print("=" * 72)
    print("Servidor activo en: http://127.0.0.1:5000/  o  http://localhost:5000/")
    print("Instrucciones:")
    print("1. Abre tu navegador web (Chrome, Edge o Firefox).")
    print("2. Escribe en la barra de direcciones: localhost:5000")
    print("3. Para cerrar el servidor, presiona Ctrl+C en esta terminal.")
    print("=" * 72 + "\n")
    
    Timer(1.2, abrir_navegador).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
