import getpass
import sys
from worker_manager import WorkerManager
from topology_manager import TopologyManager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import check_password_hash
from ssh_db_connector import SSHTunnel

# === Configuración SSH y DB remota ===
SSH_HOST = "10.20.12.28"
SSH_PORT = 5803
SSH_USER = "ubuntu"
DB_USER = "joya_user"
DB_PASS = "joya123"
DB_NAME = "joyastack_db"
DB_HOST_REMOTE = "127.0.0.1"  # desde la máquina remota
DB_PORT_REMOTE = 5432

# Definición de los workers
WORKERS = {
    "worker1": {"ip": "10.0.10.1", "ssh_port": 5801},
    "worker2": {"ip": "10.0.10.2", "ssh_port": 5802},
    "worker3": {"ip": "10.0.10.3", "ssh_port": 5803},
}
HEADNODE = {"ip": "10.0.10.4", "ssh_port": 5804}


def login_db():
    """Login a PostgreSQL remoto vía SSH"""
    username = input("Usuario DB: ")
    password = getpass.getpass("Contraseña DB: ")
    
    # Solicitar contraseña SSH
    ssh_password = "RedesCloud2025"

    try:
        # Usar túnel SSH manual (evita problemas con DSSKey)
        #print("🔌 Estableciendo túnel SSH...")
        tunnel = SSHTunnel(
            ssh_host=SSH_HOST,
            ssh_port=SSH_PORT,
            ssh_user=SSH_USER,
            ssh_pass=ssh_password,
            remote_host=DB_HOST_REMOTE,
            remote_port=DB_PORT_REMOTE
        )
        
        tunnel.start()
        #print(f"✅ Túnel SSH establecido en puerto local {tunnel.local_bind_port}")
        
        try:
            # Conectar a PostgreSQL a través del túnel
            local_port = tunnel.local_bind_port
            db_url = f"postgresql://{DB_USER}:{DB_PASS}@127.0.0.1:{local_port}/{DB_NAME}"
            engine = create_engine(db_url, echo=False)
            
            Session = sessionmaker(bind=engine)
            session = Session()
            
            # Consultar usuario
            result = session.execute(
                text("SELECT hash_password FROM \"user\" WHERE username=:username"),
                {"username": username}
            ).fetchone()
            
            session.close()
            engine.dispose()
            
            if result and check_password_hash(result[0], password):
                print(f"✅ Login exitoso, bienvenido {username}")
                return True
            else:
                print("❌ Usuario o contraseña incorrectos")
                return False
                
        except Exception as db_error:
            print(f"❌ Error al consultar la base de datos: {db_error}")
            return False
        finally:
            tunnel.stop()
            #print("🔒 Túnel SSH cerrado")

    except Exception as e:
        print(f"❌ Error al conectar: {type(e).__name__}: {e}")
        return False


def main():
    print("="*60)
    print("=== ORQUESTADOR CLOUD - JOYASTACK ===")
    print("="*60)

    # Intentar login hasta 3 veces
    for attempt in range(3):
        print(f"\n[Intento de login {attempt + 1}/3]")
        if login_db():
            break
    else:
        print("\n❌ Demasiados intentos fallidos. Saliendo...")
        sys.exit(1)

    # Inputs originales de SSH y gateway
    print("\n" + "="*60)
    print("CONFIGURACIÓN DE WORKERS")
    print("="*60)
    user = "ubuntu"
    passwd = "RedesCloud2025"
    gateway_ip = "10.20.12.28"

    worker_mgr = WorkerManager(WORKERS, gateway_ip, user, passwd)
    topo_mgr = TopologyManager(worker_mgr.vm_inventory, gateway_ip, user, passwd)

    while True:
        print("\n" + "="*60)
        print("MENÚ PRINCIPAL")
        print("="*60)
        print("1) Inicializar Workers (simulación)")
        print("2) Crear VMs (Round-Robin)")
        print("3) Definir Topología")
        print("4) Listar VMs desplegadas")
        print("5) Reiniciar cluster (borrar VMs)")
        print("6) Eliminar VM específica")
        print("7) Salir")
        print("="*60)

        option = input("Seleccione una opción: ").strip()

        match option:
            case "1":
                print("\n✅ Workers inicializados (solo para ejemplo)")
            case "2":
                try:
                    num_vms = int(input("\n¿Cuántas VMs deseas crear?: (Ingresar 0 para cancelar) "))
                    if num_vms <= 0:
                        print("❌ Debe ser un número mayor a 0")
                        continue
                    worker_mgr.create_vms(num_vms)
                except ValueError:
                    print("❌ Ingrese un número válido")
            case "3":
                topo_mgr.vm_inventory = worker_mgr.vm_inventory
                topo_mgr.define_topology()
            case "4":
                worker_mgr.list_vms()
            case "5":
                confirm = input("\n⚠️  ¿Está seguro de reiniciar el cluster? (yes/no): ")
                if confirm.lower() == 'yes':
                    worker_mgr.reset_cluster()
                else:
                    print("❌ Operación cancelada")
            case "6":
                worker_mgr.list_vms()
                vmn = input("\nIngrese nombre de VM a eliminar (ej: VM1): ").strip()
                vm_to_kill = next((v for v in worker_mgr.vm_inventory if v["name"] == vmn), None)
                if vm_to_kill:
                    confirm = input(f"⚠️  ¿Eliminar {vmn}? (yes/no): ")
                    if confirm.lower() == 'yes':
                        worker_mgr.delete_vm(vm_to_kill)
                        worker_mgr.vm_inventory = [
                            v for v in worker_mgr.vm_inventory if v["name"] != vmn
                        ]
                        print(f"✅ VM {vmn} eliminada")
                    else:
                        print("❌ Operación cancelada")
                else:
                    print(f"❌ No existe la VM: {vmn}")
            case "7":
                print("\n👋 Saliendo del orquestador...")
                sys.exit(0)
            case _:
                print("❌ Opción inválida. Intente nuevamente.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Programa interrumpido por el usuario")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)