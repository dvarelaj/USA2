from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from . import models
from .database import engine, get_db

# Crear todas las tablas en la DB (solo si no existen)
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Montar los archivos estáticos (HTML/JS/CSS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Schemas (Pydantic) ---

class CelularEntry(BaseModel):
    imei: str

class BatchEntry(BaseModel):
    oc_id: str
    trm: float
    costo_usd: float
    imeis: List[CelularEntry]

class CelularSalida(BaseModel):
    imei: str
    tipo_cliente: str # Detal o Consignacion
    nombre_cliente: str
    precio_venta: float

# --- Endpoints ---

@app.get("/")
def read_root():
    # Redirige a la página principal/dashboard
    return {"message": "Go to /static/index.html or /static/sales.html"}


@app.post("/api/v1/inventario/entrada")
def entry_batch(data: BatchEntry, db: Session = Depends(get_db)):
    """Ingresa un lote de celulares al inventario."""
    try:
        celulares_creados = 0
        for item in data.imeis:
            # Calcular costo en COP
            costo_cop = data.trm * data.costo_usd
            
            db_celular = models.Celular(
                imei=item.imei,
                oc_id=data.oc_id,
                trm_compra=data.trm,
                costo_cop=costo_cop,
            )
            db.add(db_celular)
            celulares_creados += 1
        
        db.commit()
        return {"status": "success", "count": celulares_creados, "oc_id": data.oc_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error al ingresar lote: {e}")


@app.post("/api/v1/inventario/salida")
def register_sale(data: CelularSalida, db: Session = Depends(get_db)):
    """Registra una venta o entrega en consignación."""
    db_celular = db.query(models.Celular).filter(models.Celular.imei == data.imei).first()

    if not db_celular:
        raise HTTPException(status_code=404, detail="IMEI no encontrado.")
    
    if db_celular.estado != "En Inventario":
        raise HTTPException(status_code=400, detail=f"El celular ya tiene estado: {db_celular.estado}")

    # Definir el estado y la trazabilidad
    if data.tipo_cliente == "Consignacion":
        db_celular.estado = "Entregado Consignacion"
        db_celular.cliente_consignacion = data.nombre_cliente
    elif data.tipo_cliente == "Detal":
        db_celular.estado = "Vendido"
        # Para Detal, se registra la salida y el precio.
        db_celular.fecha_salida = func.now()
        db_celular.precio_venta = data.precio_venta
    else:
        raise HTTPException(status_code=400, detail="Tipo de cliente inválido.")

    db.add(db_celular)
    db.commit()
    db.refresh(db_celular)

    return {"status": "success", "imei": db_celular.imei, "nuevo_estado": db_celular.estado}


@app.get("/api/v1/inventario/dashboard")
def get_dashboard_data(db: Session = Depends(get_db)):
    """Retorna datos agregados para el dashboard."""
    total_inventario = db.query(models.Celular).count()
    
    # Datos de consignación
    consignacion = db.query(models.Celular).filter(
        models.Celular.estado == "Entregado Consignacion"
    ).all()
    
    # Datos por OC para el balance (simplificado)
    # Aquí se usarían agrupaciones (group_by) más complejas en SQL
    return {
        "total_unidades": total_inventario,
        "en_consignacion": len(consignacion),
        "detalle_consignacion": [
            {"imei": c.imei, "cliente": c.cliente_consignacion, "oc": c.oc_id} 
            for c in consignacion
        ]
    }