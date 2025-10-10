from config import SQLALCHEMY_DATABASE_URI
from sqlalchemy import create_engine

# Crear engine y probar conexión
engine = create_engine(SQLALCHEMY_DATABASE_URI)

try:
    with engine.connect() as conn:
        print("Conexión exitosa a la base de datos!")
except Exception as e:
    print("Error de conexión:", e)
