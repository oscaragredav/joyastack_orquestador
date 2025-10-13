from werkzeug.security import generate_password_hash
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import SQLALCHEMY_DATABASE_URI
from app_models import User  # importa tus modelos desde el archivo donde están definidos

# Crear engine y sesión
engine = create_engine(SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)
session = Session()

# Definir los usuarios
users = [
    {"username": "admin", "password": "admin123", "role": "admin"},
    {"username": "user", "password": "user123", "role": "user"}
]

for data in users:
    # Verifica si el usuario ya existe
    existing = session.query(User).filter_by(username=data["username"]).first()
    if not existing:
        new_user = User(
            username=data["username"],
            hash_password=generate_password_hash(data["password"]),
            role=data["role"]
        )
        session.add(new_user)
        print(f"✅ Usuario '{data['username']}' con rol '{data['role']}' agregado.")
    else:
        print(f"⚠️ Usuario '{data['username']}' ya existe, omitido.")

# Guardar cambios
session.commit()
session.close()
print("🎉 Usuarios iniciales insertados correctamente.")
