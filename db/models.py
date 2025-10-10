from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
Base = declarative_base()
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    hash_password = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False)

    slices = db.relationship('Slice', backref='owner', lazy=True)

class Slice(db.Model):
    __tablename__ = 'slice'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='inactive')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vms = db.relationship('VM', backref='slice', lazy=True)
    network_links = db.relationship('NetworkLink', backref='slice', lazy=True)

class VM(db.Model):
    __tablename__ = 'vm'
    id = db.Column(db.Integer, primary_key=True)
    slice_id = db.Column(db.Integer, db.ForeignKey('slice.id'), nullable=False)
    worker_id = db.Column(db.Integer, db.ForeignKey('worker.id'), nullable=False)
    cpu = db.Column(db.Integer)
    ram = db.Column(db.Integer)
    disk = db.Column(db.Integer)
    state = db.Column(db.String(20))
    image_id = db.Column(db.Integer, db.ForeignKey('image.id'))

class NetworkLink(db.Model):
    __tablename__ = 'network_link'
    id = db.Column(db.Integer, primary_key=True)
    slice_id = db.Column(db.Integer, db.ForeignKey('slice.id'), nullable=False)
    vlan_id = db.Column(db.Integer)
    vm_a = db.Column(db.Integer, db.ForeignKey('vm.id'))
    vm_b = db.Column(db.Integer, db.ForeignKey('vm.id'))

class Worker(db.Model):
    __tablename__ = 'worker'
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(50), nullable=False)
    state = db.Column(db.String(20))
    capacity_cpu = db.Column(db.Integer)
    ram_total = db.Column(db.Integer)

    vms = db.relationship('VM', backref='worker', lazy=True)

class Logs(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    module = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    message = db.Column(db.Text)
    level = db.Column(db.String(20))

class Image(db.Model):
    __tablename__ = 'image'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    path = db.Column(db.String(200))
    hash = db.Column(db.String(64))
    size = db.Column(db.Integer)
    reference_count = db.Column(db.Integer)

    vms = db.relationship('VM', backref='image', lazy=True)
#Inicializar tablas
if __name__ == "__main__":
    engine = create_engine(SQLALCHEMY_DATABASE_URI)
    Base.metadata.create_all(engine)
    print(" Tablas creadas correctamente en joyastack_db")
    
