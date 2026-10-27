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

DB_PATH = "sistema_transporte.db"

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
    
    # Insertar datos de prueba iniciales
    cursor.execute("SELECT COUNT(*) FROM vehiculos")
    if cursor.fetchone()[0] == 0:
        cursor.executemany('''
            INSERT INTO vehiculos (id, placa, capacidad_max_kg, estado) VALUES (?, ?, ?, ?)
        ''', [
            ('VEH-001', 'ABC-123', 1500.0, 'DISPONIBLE'),
            ('VEH-002', 'XYZ-789', 3000.0, 'DISPONIBLE')
        ])
        
        cursor.executemany('''
            INSERT INTO conductores (id, nombre, licencia, estado) VALUES (?, ?, ?, ?)
        ''', [
            ('CND-001', 'Carlos Pérez', 'LIC-A2', 'DISPONIBLE'),
            ('CND-002', 'Ana Gómez', 'LIC-A2', 'DISPONIBLE')
        ])
        
        cursor.executemany('''
            INSERT INTO ordenes_transporte (id, orden_manufactura_id, cliente_nombre, direccion_destino, peso_total_kg, estado) VALUES (?, ?, ?, ?, ?, ?)
        ''', [
            ('OT-1001', 'MANUF-8801', 'Industrias del Norte S.A.', 'Av. Industrial 450, Lima', 1200.0, 'CREADA'),
            ('OT-1002', 'MANUF-8802', 'Comercializadora Global', 'Calle Comercio 12, Arequipa', 2500.0, 'CREADA')
        ])
    
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
        return {"exito": True, "codigo": 200, "orden": orden, "historial_eventos": historial}


# ==============================================================================
# 3. CAPA DE PRESENTACIÓN / API REST (PRESENTATION TIER - PUERTA DE ENTRADA)
# ==============================================================================

app = Flask(__name__)

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

B64_UI = "PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVzIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9IlVURi04Ij4KPHRpdGxlPk1vZHVsbyBkZSBUcmFuc3BvcnRlIHkgRW50cmVnYXMgLSBFbXByZXNhIE1hbnVmYWN0dXJlcmE8L3RpdGxlPgo8c3R5bGU+CmJvZHkgeyBmb250LWZhbWlseTogJ1NlZ29lIFVJJywgVGFob21hLCBHZW5ldmEsIFZlcmRhbmEsIHNhbnMtc2VyaWY7IGJhY2tncm91bmQtY29sb3I6ICNmMGY0Zjg7IG1hcmdpbjogMDsgcGFkZGluZzogMjBweDsgY29sb3I6ICMxZTI5M2I7IH0KLmNvbnRhaW5lciB7IG1heC13aWR0aDogMTEwMHB4OyBtYXJnaW46IDAgYXV0bzsgfQouaGVhZGVyIHsgYmFja2dyb3VuZDogbGluZWFyLWdyYWRpZW50KDEzNWRlZywgIzFlM2E4YSwgIzI1NjNlYik7IGNvbG9yOiB3aGl0ZTsgcGFkZGluZzogMjVweDsgYm9yZGVyLXJhZGl1czogMTJweDsgbWFyZ2luLWJvdHRvbTogMjVweDsgfQouaGVhZGVyIGgxIHsgbWFyZ2luOiAwIDAgOHB4IDA7IGZvbnQtc2l6ZTogMjZweDsgfQouaGVhZGVyIHAgeyBtYXJnaW46IDA7IG9wYWNpdHk6IDAuOTsgZm9udC1zaXplOiAxNHB4OyB9Ci5ncmlkIHsgZGlzcGxheTogZ3JpZDsgZ3JpZC10ZW1wbGF0ZS1jb2x1bW5zOiAxZnIgMWZyOyBnYXA6IDIwcHg7IG1hcmdpbi1ib3R0b206IDI1cHg7IH0KLmNhcmQgeyBiYWNrZ3JvdW5kOiB3aGl0ZTsgcGFkZGluZzogMjBweDsgYm9yZGVyLXJhZGl1czogMTBweDsgYm94LXNoYWRvdzogMCAycHggNHB4IHJnYmEoMCwwLDAsMC4wNSk7IGJvcmRlcjogMXB4IHNvbGlkICNlMmU4ZjA7IH0KLmNhcmQgaDIgeyBtYXJnaW4tdG9wOiAwOyBmb250LXNpemU6IDE4cHg7IGNvbG9yOiAjMWUzYThhOyBib3JkZXItYm90dG9tOiAycHggc29saWQgI2UyZThmMDsgcGFkZGluZy1ib3R0b206IDEwcHg7IH0KbGFiZWwgeyBmb250LXdlaWdodDogNjAwOyBmb250LXNpemU6IDEzcHg7IGRpc3BsYXk6IGJsb2NrOyBtYXJnaW4tdG9wOiAxMnB4OyBjb2xvcjogIzQ3NTU2OTsgfQpzZWxlY3QsIGlucHV0LCBidXR0b24geyB3aWR0aDogMTAwJTsgcGFkZGluZzogMTBweDsgbWFyZ2luLXRvcDogNXB4OyBib3JkZXItcmFkaXVzOiA2cHg7IGJvcmRlcjogMXB4IHNvbGlkICNjYmQ1ZTE7IGJveC1zaXppbmc6IGJvcmRlci1ib3g7IGZvbnQtc2l6ZTogMTRweDsgfQpidXR0b24geyBiYWNrZ3JvdW5kLWNvbG9yOiAjMjU2M2ViOyBjb2xvcjogd2hpdGU7IGJvcmRlcjogbm9uZTsgZm9udC13ZWlnaHQ6IDYwMDsgbWFyZ2luLXRvcDogMThweDsgY3Vyc29yOiBwb2ludGVyOyB9CmJ1dHRvbjpob3ZlciB7IGJhY2tncm91bmQtY29sb3I6ICMxZDRlZDg7IH0KLmJ0bi1hcGkgeyBiYWNrZ3JvdW5kLWNvbG9yOiAjMDU5NjY5OyB9Ci5idG4tYXBpOmhvdmVyIHsgYmFja2dyb3VuZC1jb2xvcjogIzA0Nzg1NzsgfQouYWxlcnQgeyBwYWRkaW5nOiAxMnB4OyBib3JkZXItcmFkaXVzOiA2cHg7IG1hcmdpbi10b3A6IDE1cHg7IGZvbnQtc2l6ZTogMTNweDsgZm9udC13ZWlnaHQ6IDUwMDsgZGlzcGxheTogbm9uZTsgfQouYWxlcnQtc3VjY2VzcyB7IGJhY2tncm91bmQtY29sb3I6ICNkY2ZjZTc7IGNvbG9yOiAjMTY2NTM0OyBib3JkZXI6IDFweCBzb2xpZCAjYmJmN2QwOyB9Ci5hbGVydC1kYW5nZXIgeyBiYWNrZ3JvdW5kLWNvbG9yOiAjZmVlMmUyOyBjb2xvcjogIzk5MWIxYjsgYm9yZGVyOiAxcHggc29saWQgI2ZlY2FjYTsgfQp0YWJsZSB7IHdpZHRoOiAxMDAlOyBib3JkZXItY29sbGFwc2U6IGNvbGxhcHNlOyBtYXJnaW4tdG9wOiAxNXB4OyBmb250LXNpemU6IDEzcHg7IH0KdGgsIHRkIHsgcGFkZGluZzogMTBweCAxMnB4OyB0ZXh0LWFsaWduOiBsZWZ0OyBib3JkZXItYm90dG9tOiAxcHggc29saWQgI2UyZThmMDsgfQp0aCB7IGJhY2tncm91bmQtY29sb3I6ICNmOGZhZmM7IGNvbG9yOiAjNDc1NTY5OyBmb250LXdlaWdodDogNjAwOyB9Ci5iYWRnZSB7IHBhZGRpbmc6IDRweCA4cHg7IGJvcmRlci1yYWRpdXM6IDEycHg7IGZvbnQtc2l6ZTogMTFweDsgZm9udC13ZWlnaHQ6IDcwMDsgdGV4dC10cmFuc2Zvcm06IHVwcGVyY2FzZTsgfQouYmFkZ2UtQ1JFQURBIHsgYmFja2dyb3VuZDogI2UyZThmMDsgY29sb3I6ICM0NzU1Njk7IH0KLmJhZGdlLUFTSUdOQURBIHsgYmFja2dyb3VuZDogI2RiZWFmZTsgY29sb3I6ICMxZTQwYWY7IH0KLmJhZGdlLUVOX1RSQU5TSVRPIHsgYmFja2dyb3VuZDogI2ZlZjNjNzsgY29sb3I6ICM5MjQwMGU7IH0KLmJhZGdlLUVOVFJFR0FETyB7IGJhY2tncm91bmQ6ICNkY2ZjZTc7IGNvbG9yOiAjMTY2NTM0OyB9Ci5iYWRnZS1OT1ZFREFEIHsgYmFja2dyb3VuZDogI2ZlZTJlMjsgY29sb3I6ICM5OTFiMWI7IH0KPC9zdHlsZT4KPC9oZWFkPgo8Ym9keT4KPGRpdiBjbGFzcz0iY29udGFpbmVyIj4KICAgIDxkaXYgY2xhc3M9ImhlYWRlciI+CiAgICAgICAgPGgxPvCfmpsgTcOzZHVsbyBkZSBUcmFuc3BvcnRlIHkgRW50cmVnYXMgKENhcGEgMTogSW50ZXJmYXogV2ViKTwvaDE+CiAgICAgICAgPHA+U2lzdGVtYSBkZSBJbmZvcm1hY2nDs24gcGFyYSBFbXByZXNhIE1hbnVmYWN0dXJlcmEg4oCUIEFycXVpdGVjdHVyYSBlbiAzIENhcGFzPC9wPgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJncmlkIj4KICAgICAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICAgICAgPGgyPjEuIEFzaWduYXIgRGVzcGFjaG8gKEdlc3RvciBMb2fDrXN0aWNvKTwvaDI+CiAgICAgICAgICAgIDxmb3JtIGlkPSJmb3JtQXNpZ25hciI+CiAgICAgICAgICAgICAgICA8bGFiZWw+T3JkZW4gZGUgVHJhbnNwb3J0ZSAoTWFudWZhY3R1cmEpOjwvbGFiZWw+CiAgICAgICAgICAgICAgICA8c2VsZWN0IGlkPSJvcmRlbkFzaWduYXIiIHJlcXVpcmVkPjwvc2VsZWN0PgogICAgICAgICAgICAgICAgPGxhYmVsPlZlaMOtY3VsbyBEaXNwb25pYmxlIChQbGFjYSAtIENhcGFjaWRhZCk6PC9sYWJlbD4KICAgICAgICAgICAgICAgIDxzZWxlY3QgaWQ9InZlaGljdWxvQXNpZ25hciIgcmVxdWlyZWQ+PC9zZWxlY3Q+CiAgICAgICAgICAgICAgICA8bGFiZWw+Q29uZHVjdG9yIEFzaWduYWRvOjwvbGFiZWw+CiAgICAgICAgICAgICAgICA8c2VsZWN0IGlkPSJjb25kdWN0b3JBc2lnbmFyIiByZXF1aXJlZD48L3NlbGVjdD4KICAgICAgICAgICAgICAgIDxidXR0b24gdHlwZT0ic3VibWl0Ij5WYWxpZGFyIENhcGFjaWRhZCB5IEFzaWduYXI8L2J1dHRvbj4KICAgICAgICAgICAgPC9mb3JtPgogICAgICAgICAgICA8ZGl2IGlkPSJtc2dBc2lnbmFyIiBjbGFzcz0iYWxlcnQiPjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgY2xhc3M9ImNhcmQiPgogICAgICAgICAgICA8aDI+Mi4gUHVlcnRhIGRlIEVudHJhZGEgLyBBUEkgUkVTVCAoQXBwIENvbmR1Y3Rvcik8L2gyPgogICAgICAgICAgICA8Zm9ybSBpZD0iZm9ybUFwaSI+CiAgICAgICAgICAgICAgICA8bGFiZWw+T3JkZW4gZGUgVHJhbnNwb3J0ZTo8L2xhYmVsPgogICAgICAgICAgICAgICAgPHNlbGVjdCBpZD0ib3JkZW5BcGkiIHJlcXVpcmVkPjwvc2VsZWN0PgogICAgICAgICAgICAgICAgPGxhYmVsPk51ZXZvIEVzdGFkbyBkZSBFbnRyZWdhOjwvbGFiZWw+CiAgICAgICAgICAgICAgICA8c2VsZWN0IGlkPSJlc3RhZG9BcGkiIHJlcXVpcmVkPgogICAgICAgICAgICAgICAgICAgIDxvcHRpb24gdmFsdWU9IkVOX1RSQU5TSVRPIj5FTl9UUkFOU0lUTzwvb3B0aW9uPgogICAgICAgICAgICAgICAgICAgIDxvcHRpb24gdmFsdWU9IkVOVFJFR0FETyI+RU5UUkVHQURPPC9vcHRpb24+CiAgICAgICAgICAgICAgICAgICAgPG9wdGlvbiB2YWx1ZT0iTk9WRURBRCI+Tk9WRURBRDwvb3B0aW9uPgogICAgICAgICAgICAgICAgPC9zZWxlY3Q+CiAgICAgICAgICAgICAgICA8bGFiZWw+Q29vcmRlbmFkYXMgR1BTIChTZW5zb3IpOjwvbGFiZWw+CiAgICAgICAgICAgICAgICA8aW5wdXQgdHlwZT0idGV4dCIgaWQ9Imdwc0FwaSIgdmFsdWU9Ii0xMi4wNDYzNzQsIC03Ny4wNDI3OTMiIHJlcXVpcmVkPgogICAgICAgICAgICAgICAgPGxhYmVsPk9ic2VydmFjaW9uZXMgLyBGaXJtYSBEaWdpdGFsOjwvbGFiZWw+CiAgICAgICAgICAgICAgICA8aW5wdXQgdHlwZT0idGV4dCIgaWQ9Im9ic0FwaSIgdmFsdWU9IlNhbGlkYSBhdXRvcml6YWRhIGRlc2RlIGFsbWFjw6luIHByaW5jaXBhbCIgcmVxdWlyZWQ+CiAgICAgICAgICAgICAgICA8YnV0dG9uIHR5cGU9InN1Ym1pdCIgY2xhc3M9ImJ0bi1hcGkiPkVudmlhciBQZXRpY2nDs24gYSBQdWVydGEgZGUgRW50cmFkYSAoQVBJIFJFU1QpPC9idXR0b24+CiAgICAgICAgICAgIDwvZm9ybT4KICAgICAgICAgICAgPGRpdiBpZD0ibXNnQXBpIiBjbGFzcz0iYWxlcnQiPjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJjYXJkIj4KICAgICAgICA8aDI+My4gTW9uaXRvciBkZSDDk3JkZW5lcyBkZSBUcmFuc3BvcnRlIChQZXJzaXN0ZW5jaWEgZW4gVGllbXBvIFJlYWwpPC9oMj4KICAgICAgICA8dGFibGU+CiAgICAgICAgICAgIDx0aGVhZD48dHI+PHRoPklEIE9yZGVuPC90aD48dGg+TWFudWZhY3R1cmEgSUQ8L3RoPjx0aD5DbGllbnRlIC8gRGVzdGlubzwvdGg+PHRoPlBlc28gKGtnKTwvdGg+PHRoPlZlaMOtY3VsbzwvdGg+PHRoPkNvbmR1Y3RvcjwvdGg+PHRoPkVzdGFkbzwvdGg+PC90cj48L3RoZWFkPgogICAgICAgICAgICA8dGJvZHkgaWQ9InRhYmxhT3JkZW5lcyI+PC90Ym9keT4KICAgICAgICA8L3RhYmxlPgogICAgPC9kaXY+CjwvZGl2Pgo8c2NyaXB0Pgphc3luYyBmdW5jdGlvbiBjYXJnYXJEYXRvcygpIHsKICAgIGNvbnN0IHJlcyA9IGF3YWl0IGZldGNoKCcvYXBpL3YxL3RyYW5zcG9ydGUvZGF0b3MnKTsKICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXMuanNvbigpOwogICAgY29uc3Qgc2VsTzEgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnb3JkZW5Bc2lnbmFyJyk7CiAgICBjb25zdCBzZWxPMiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdvcmRlbkFwaScpOwogICAgc2VsTzEuaW5uZXJIVE1MID0gJyc7IHNlbE8yLmlubmVySFRNTCA9ICcnOwogICAgZGF0YS5vcmRlbmVzLmZvckVhY2gobyA9PiB7CiAgICAgICAgY29uc3Qgb3B0ID0gIjxvcHRpb24gdmFsdWU9JyIgKyBvLmlkICsgIic+IiArIG8uaWQgKyAiIC0gIiArIG8uY2xpZW50ZV9ub21icmUgKyAiICgiICsgby5wZXNvX3RvdGFsX2tnICsgIiBrZykgWyIgKyBvLmVzdGFkbyArICJdPC9vcHRpb24+IjsKICAgICAgICBzZWxPMS5pbm5lckhUTUwgKz0gb3B0OwogICAgICAgIHNlbE8yLmlubmVySFRNTCArPSBvcHQ7CiAgICB9KTsKICAgIGNvbnN0IHNlbFYgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndmVoaWN1bG9Bc2lnbmFyJyk7CiAgICBzZWxWLmlubmVySFRNTCA9ICcnOwogICAgZGF0YS52ZWhpY3Vsb3MuZm9yRWFjaCh2ID0+IHsKICAgICAgICBzZWxWLmlubmVySFRNTCArPSAiPG9wdGlvbiB2YWx1ZT0nIiArIHYuaWQgKyAiJz4iICsgdi5pZCArICIgKCIgKyB2LnBsYWNhICsgIikgLSBDYXA6ICIgKyB2LmNhcGFjaWRhZF9tYXhfa2cgKyAiIGtnIFsiICsgdi5lc3RhZG8gKyAiXTwvb3B0aW9uPiI7CiAgICB9KTsKICAgIGNvbnN0IHNlbEMgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY29uZHVjdG9yQXNpZ25hcicpOwogICAgc2VsQy5pbm5lckhUTUwgPSAnJzsKICAgIGRhdGEuY29uZHVjdG9yZXMuZm9yRWFjaChjID0+IHsKICAgICAgICBzZWxDLmlubmVySFRNTCArPSAiPG9wdGlvbiB2YWx1ZT0nIiArIGMuaWQgKyAiJz4iICsgYy5ub21icmUgKyAiICgiICsgYy5saWNlbmNpYSArICIpIFsiICsgYy5lc3RhZG8gKyAiXTwvb3B0aW9uPiI7CiAgICB9KTsKICAgIGNvbnN0IHRiID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RhYmxhT3JkZW5lcycpOwogICAgdGIuaW5uZXJIVE1MID0gJyc7CiAgICBkYXRhLm9yZGVuZXMuZm9yRWFjaChvID0+IHsKICAgICAgICB0Yi5pbm5lckhUTUwgKz0gIjx0cj48dGQ+PGI+IiArIG8uaWQgKyAiPC9iPjwvdGQ+PHRkPiIgKyBvLm9yZGVuX21hbnVmYWN0dXJhX2lkICsgIjwvdGQ+PHRkPiIgKyBvLmNsaWVudGVfbm9tYnJlICsgIjxicj48c21hbGwgc3R5bGU9J2NvbG9yOiM2NDc0OGInPiIgKyBvLmRpcmVjY2lvbl9kZXN0aW5vICsgIjwvc21hbGw+PC90ZD48dGQ+IiArIG8ucGVzb190b3RhbF9rZyArICIga2c8L3RkPjx0ZD4iICsgKG8udmVoaWN1bG9faWQgfHwgJ1NpbiBhc2lnbmFyJykgKyAiPC90ZD48dGQ+IiArIChvLmNvbmR1Y3Rvcl9pZCB8fCAnU2luIGFzaWduYXInKSArICI8L3RkPjx0ZD48c3BhbiBjbGFzcz0nYmFkZ2UgYmFkZ2UtIiArIG8uZXN0YWRvICsgIic+IiArIG8uZXN0YWRvICsgIjwvc3Bhbj48L3RkPjwvdHI+IjsKICAgIH0pOwp9CmRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmb3JtQXNpZ25hcicpLm9uc3VibWl0ID0gYXN5bmMgKGUpID0+IHsKICAgIGUucHJldmVudERlZmF1bHQoKTsKICAgIGNvbnN0IG1zZyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtc2dBc2lnbmFyJyk7CiAgICBtc2cuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICAgIGNvbnN0IHBheWxvYWQgPSB7CiAgICAgICAgb3JkZW5faWQ6IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdvcmRlbkFzaWduYXInKS52YWx1ZSwKICAgICAgICB2ZWhpY3Vsb19pZDogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3ZlaGljdWxvQXNpZ25hcicpLnZhbHVlLAogICAgICAgIGNvbmR1Y3Rvcl9pZDogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NvbmR1Y3RvckFzaWduYXInKS52YWx1ZQogICAgfTsKICAgIGNvbnN0IHJlcyA9IGF3YWl0IGZldGNoKCcvYXBpL3YxL3RyYW5zcG9ydGUvYXNpZ25hcicsIHsKICAgICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgICBoZWFkZXJzOiB7J0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkocGF5bG9hZCkKICAgIH0pOwogICAgY29uc3QgcmVzdWx0ID0gYXdhaXQgcmVzLmpzb24oKTsKICAgIG1zZy5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsKICAgIG1zZy5jbGFzc05hbWUgPSAnYWxlcnQgJyArIChyZXN1bHQuZXhpdG8gPyAnYWxlcnQtc3VjY2VzcycgOiAnYWxlcnQtZGFuZ2VyJyk7CiAgICBtc2cuaW5uZXJUZXh0ID0gcmVzdWx0Lm1lbnNhamU7CiAgICBjYXJnYXJEYXRvcygpOwp9Owpkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZm9ybUFwaScpLm9uc3VibWl0ID0gYXN5bmMgKGUpID0+IHsKICAgIGUucHJldmVudERlZmF1bHQoKTsKICAgIGNvbnN0IG1zZyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtc2dBcGknKTsKICAgIG1zZy5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgY29uc3QgcGF5bG9hZCA9IHsKICAgICAgICBvcmRlbl9pZDogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ29yZGVuQXBpJykudmFsdWUsCiAgICAgICAgbnVldm9fZXN0YWRvOiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZXN0YWRvQXBpJykudmFsdWUsCiAgICAgICAgdWJpY2FjaW9uX2dwczogZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2dwc0FwaScpLnZhbHVlLAogICAgICAgIG9ic2VydmFjaW9uZXM6IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdvYnNBcGknKS52YWx1ZQogICAgfTsKICAgIGNvbnN0IHJlcyA9IGF3YWl0IGZldGNoKCcvYXBpL3YxL3RyYW5zcG9ydGUvZW50cmVnYXMvYWN0dWFsaXphci1lc3RhZG8nLCB7CiAgICAgICAgbWV0aG9kOiAnUE9TVCcsCiAgICAgICAgaGVhZGVyczogeydDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbid9LAogICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHBheWxvYWQpCiAgICB9KTsKICAgIGNvbnN0IHJlc3VsdCA9IGF3YWl0IHJlcy5qc29uKCk7CiAgICBtc2cuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICBtc2cuY2xhc3NOYW1lID0gJ2FsZXJ0ICcgKyAocmVzdWx0LmV4aXRvID8gJ2FsZXJ0LXN1Y2Nlc3MnIDogJ2FsZXJ0LWRhbmdlcicpOwogICAgbXNnLmlubmVyVGV4dCA9IHJlc3VsdC5tZW5zYWplOwogICAgY2FyZ2FyRGF0b3MoKTsKfTsKY2FyZ2FyRGF0b3MoKTsKPC9zY3JpcHQ+CjwvYm9keT4KPC9odG1sPg=="
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
