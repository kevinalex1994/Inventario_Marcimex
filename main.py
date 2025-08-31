#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema Avanzado de Gestión de Inventario — Almacenes Marcimex
----------------------------------------------------------
Características solicitadas:
- POO con clases Producto e Inventario.
- Uso de colecciones (dict, list, set, tuple) para gestionar ítems en memoria.
- Persistencia en SQLite (CRUD completo).
- Menú de consola interactivo.

Estructura general y diseño
---------------------------
1) Producto: entidad simple con ID, nombre, cantidad y precio. Usa @property para getters/setters
   con validaciones básicas.
2) Inventario: mantiene un diccionario {id: Producto} para búsquedas O(1) por ID. Además
   expone métodos CRUD y sincroniza los cambios con SQLite.
3) SQLite: una tabla 'productos' con columnas (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE,
   cantidad INTEGER, precio REAL). Se inicializa automáticamente si no existe.
4) Colecciones:
   - dict[int, Producto] para el índice principal del inventario.
   - list[Producto] como resultados de consultas (mostrar todo, buscar por nombre).
   - set[str] para nombres ya usados (apoya validación y ejemplo de colección).
   - tuple para retornos inmutables (por ejemplo, snapshots con to_tuple()).
5) Interfaz de usuario por consola (menú): añade, elimina, actualiza, busca y lista productos.

Nota: Este script es autocontenido. Basta con ejecutar `python main.py` para crear/usar la BD
en el archivo `inventario.db` (en el mismo directorio del script).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


DB_PATH = Path(__file__).with_name("inventario.db")


class DB:
    """Capa delgada para manejar la conexión SQLite y garantizar la tabla."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS productos (
                    id       INTEGER PRIMARY KEY,
                    nombre   TEXT UNIQUE NOT NULL,
                    cantidad INTEGER NOT NULL CHECK (cantidad >= 0),
                    precio   REAL    NOT NULL CHECK (precio >= 0)
                );
                """
            )
            conn.commit()


@dataclass(frozen=True)
class ProductoSnapshot:
    """Instantánea inmutable de un producto (ejemplo de tuple-like dataclass)."""
    id: int
    nombre: str
    cantidad: int
    precio: float

    def to_tuple(self) -> tuple:
        return (self.id, self.nombre, self.cantidad, self.precio)


class Producto:
    """Entidad de dominio con validaciones mediante propiedades."""

    def __init__(self, id: int, nombre: str, cantidad: int, precio: float):
        self._id = None
        self._nombre = None
        self._cantidad = None
        self._precio = None

        # Asignar vía setters para validar
        self.id = id
        self.nombre = nombre
        self.cantidad = cantidad
        self.precio = precio

    # --- ID ---
    @property
    def id(self) -> int:
        return self._id

    @id.setter
    def id(self, value: int) -> None:
        if not isinstance(value, int) or value <= 0:
            raise ValueError("ID debe ser un entero positivo.")
        self._id = value

    # --- Nombre ---
    @property
    def nombre(self) -> str:
        return self._nombre

    @nombre.setter
    def nombre(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Nombre no puede estar vacío.")
        self._nombre = value.strip()

    # --- Cantidad ---
    @property
    def cantidad(self) -> int:
        return self._cantidad

    @cantidad.setter
    def cantidad(self, value: int) -> None:
        if not isinstance(value, int) or value < 0:
            raise ValueError("Cantidad debe ser un entero >= 0.")
        self._cantidad = value

    # --- Precio ---
    @property
    def precio(self) -> float:
        return self._precio

    @precio.setter
    def precio(self, value: float) -> None:
        try:
            val = float(value)
        except (TypeError, ValueError):
            raise ValueError("Precio debe ser numérico.")
        if val < 0:
            raise ValueError("Precio debe ser >= 0.")
        self._precio = val

    # utilidades
    def to_snapshot(self) -> ProductoSnapshot:
        return ProductoSnapshot(self.id, self.nombre, self.cantidad, self.precio)

    def to_dict(self) -> dict:
        return {"id": self.id, "nombre": self.nombre, "cantidad": self.cantidad, "precio": self.precio}

    def __repr__(self) -> str:
        return f"Producto(id={self.id}, nombre={self.nombre!r}, cantidad={self.cantidad}, precio={self.precio:.2f})"


class Inventario:
    """
    Inventario respaldado por:
      - Memoria: dict[int, Producto] para acceso rápido por ID.
      - SQLite: tabla productos para persistencia.
    """

    def __init__(self, db: Optional[DB] = None):
        self.db = db or DB()
        self.items: Dict[int, Producto] = {}  # Colección principal (dict)
        self._nombres_usados: set[str] = set()  # Colección auxiliar (set)
        self._load_from_db()

    # --- Carga inicial ---
    def _load_from_db(self) -> None:
        self.items.clear()
        self._nombres_usados.clear()
        with self.db.connect() as conn:
            cur = conn.execute("SELECT id, nombre, cantidad, precio FROM productos ORDER BY id;")
            for row in cur.fetchall():
                p = Producto(id=row[0], nombre=row[1], cantidad=row[2], precio=row[3])
                self.items[p.id] = p
                self._nombres_usados.add(p.nombre)

    # --- CRUD ---
    def add_producto(self, p: Producto) -> None:
        if p.id in self.items:
            raise ValueError(f"Ya existe un producto con ID {p.id}.")
        if p.nombre in self._nombres_usados:
            raise ValueError(f"Ya existe un producto con nombre '{p.nombre}'.")

        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO productos (id, nombre, cantidad, precio) VALUES (?, ?, ?, ?);",
                (p.id, p.nombre, p.cantidad, p.precio),
            )
            conn.commit()

        self.items[p.id] = p
        self._nombres_usados.add(p.nombre)

    def remove_producto(self, id_: int) -> None:
        if id_ not in self.items:
            raise KeyError(f"No existe producto con ID {id_}.")
        nombre = self.items[id_].nombre

        with self.db.connect() as conn:
            conn.execute("DELETE FROM productos WHERE id = ?;", (id_,))
            conn.commit()

        del self.items[id_]
        self._nombres_usados.discard(nombre)

    def update_cantidad(self, id_: int, nueva_cantidad: int) -> None:
        if id_ not in self.items:
            raise KeyError(f"No existe producto con ID {id_}.")
        if not isinstance(nueva_cantidad, int) or nueva_cantidad < 0:
            raise ValueError("La nueva cantidad debe ser un entero >= 0.")

        with self.db.connect() as conn:
            conn.execute("UPDATE productos SET cantidad = ? WHERE id = ?;", (nueva_cantidad, id_))
            conn.commit()

        self.items[id_].cantidad = nueva_cantidad

    def update_precio(self, id_: int, nuevo_precio: float) -> None:
        if id_ not in self.items:
            raise KeyError(f"No existe producto con ID {id_}.")
        try:
            nuevo = float(nuevo_precio)
        except (TypeError, ValueError):
            raise ValueError("El nuevo precio debe ser numérico.")
        if nuevo < 0:
            raise ValueError("El nuevo precio debe ser >= 0.")

        with self.db.connect() as conn:
            conn.execute("UPDATE productos SET precio = ? WHERE id = ?;", (nuevo, id_))
            conn.commit()

        self.items[id_].precio = nuevo

    # --- Consultas ---
    def buscar_por_nombre(self, texto: str) -> List[Producto]:
        """Búsqueda en memoria por coincidencia parcial (case-insensitive)."""
        if not texto:
            return []
        t = texto.lower()
        return [p for p in self.items.values() if t in p.nombre.lower()]

    def listar_todos(self) -> List[Producto]:
        return list(self.items.values())

    # --- Helpers de presentación ---
    @staticmethod
    def formatear_producto(p: Producto) -> str:
        return f"[{p.id}] {p.nombre} — Cant: {p.cantidad} — Precio: ${p.precio:.2f}"

    def imprimir_todos(self) -> None:
        productos = self.listar_todos()
        if not productos:
            print("Inventario vacío.")
            return
        print("\n== Inventario ==")
        for p in productos:
            print(self.formatear_producto(p))
        print("")
        

# ==============================
# Interfaz de usuario (consola)
# ==============================

def input_int(prompt: str) -> int:
    while True:
        try:
            return int(input(prompt).strip())
        except ValueError:
            print("⚠️  Ingresa un número entero válido.")


def input_float(prompt: str) -> float:
    while True:
        try:
            return float(input(prompt).strip())
        except ValueError:
            print("⚠️  Ingresa un número (usa punto decimal).")


def menu():
    inv = Inventario()

    opciones = {
        "1": "Añadir producto",
        "2": "Eliminar producto por ID",
        "3": "Actualizar cantidad",
        "4": "Actualizar precio",
        "5": "Buscar por nombre",
        "6": "Mostrar todos los productos",
        "0": "Salir",
    }

    while True:
        print("===== Menú Inventario — Almacenes Marcimex =====")
        for k, v in opciones.items():
            print(f"{k}. {v}")
        op = input("Selecciona una opción: ").strip()

        try:
            if op == "1":
                print("\n>> Añadir producto")
                id_ = input_int("ID (entero positivo): ")
                nombre = input("Nombre: ").strip()
                cantidad = input_int("Cantidad (>=0): ")
                precio = input_float("Precio (>=0): ")
                p = Producto(id_, nombre, cantidad, precio)
                inv.add_producto(p)
                print("✅ Producto añadido.\n")

            elif op == "2":
                print("\n>> Eliminar producto")
                id_ = input_int("ID a eliminar: ")
                inv.remove_producto(id_)
                print("🗑️  Producto eliminado.\n")

            elif op == "3":
                print("\n>> Actualizar cantidad")
                id_ = input_int("ID: ")
                nueva = input_int("Nueva cantidad (>=0): ")
                inv.update_cantidad(id_, nueva)
                print("🔁 Cantidad actualizada.\n")

            elif op == "4":
                print("\n>> Actualizar precio")
                id_ = input_int("ID: ")
                nuevo = input_float("Nuevo precio (>=0): ")
                inv.update_precio(id_, nuevo)
                print("💲 Precio actualizado.\n")

            elif op == "5":
                print("\n>> Buscar por nombre")
                texto = input("Texto a buscar: ").strip()
                resultados = inv.buscar_por_nombre(texto)
                if resultados:
                    print(f"\nResultados ({len(resultados)}):")
                    for p in resultados:
                        print(Inventario.formatear_producto(p))
                    print("")
                else:
                    print("Sin coincidencias.\n")

            elif op == "6":
                inv.imprimir_todos()

            elif op == "0":
                print("¡Hasta pronto!")
                break

            else:
                print("Opción no válida.\n")

        except (ValueError, KeyError) as e:
            print(f"❌ Error: {e}\n")
        except sqlite3.IntegrityError as e:
            # Errores comunes: UNIQUE en 'nombre', PK en 'id'
            print(f"❌ Error de integridad en la BD: {e}\n")


if __name__ == "__main__":
    menu()
