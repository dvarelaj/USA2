import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Obtener la URL de conexión del entorno de Render
# **CLAVE:** Si esta variable no está, el programa fallará.
DATABASE_URL = os.environ.get("postgresql://db_celular_r4jb_user:nOfwAq4fZ96WmRlDjE6WXrNIFghLtAC7@dpg-d4mcdqe3jp1c739r2fpg-a/db_celular_r4jb")

# Si la variable no está (como en el error anterior), hacemos que el error sea claro
if not DATABASE_URL:
    raise ValueError("La variable de entorno DATABASE_URL no está configurada. ¡Necesaria para Render!")

# Render proporciona 'postgresql://' pero SQLAlchemy requiere el driver especificado.
# Reemplazamos el inicio para usar 'postgresql+psycopg2://'
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)


# Crear el motor de la DB
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True # Recomendado para conexiones persistentes en Render
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    # ... (el resto de la función get_db es correcto)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()