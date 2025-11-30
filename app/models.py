from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from .database import Base

class Celular(Base):
    __tablename__ = "celulares"

    imei = Column(String, primary_key=True, index=True)
    oc_id = Column(String, index=True)
    trm_compra = Column(Float)
    costo_cop = Column(Float)
    estado = Column(String, default="En Inventario") # Estados: 'En Inventario', 'Entregado Consignacion', 'Vendido'
    cliente_consignacion = Column(String, nullable=True)
    fecha_entrada = Column(DateTime, default=func.now())
    fecha_salida = Column(DateTime, nullable=True)
    precio_venta = Column(Float, nullable=True)