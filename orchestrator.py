import getpass
import sys
from worker_manager import WorkerManager
from topology_manager import TopologyManager

# Definición de los workers
WORKERS = {
    "worker1": {"ip": "10.0.10.1", "ssh_port": 5801},
    "worker2": {"ip": "10.0.10.2", "ssh_port": 5802},
    "worker3": {"ip": "10.0.10.3", "ssh_port": 5803},
}
HEADNODE = {"ip": "10.0.10.4", "ssh_port": 5804}


def main():
    print("=== Orquestador Cloud ===")
    user = input("Usuario SSH: ")
    passwd = getpass.getpass("Contraseña SSH: ")
    gateway_ip = input("IP del Gateway: ")  # 10.20.12.28

    worker_mgr = WorkerManager(WORKERS, gateway_ip, user, passwd)

    while True:
        print("\nOpciones:")
        print("1) Inicializar Workers (simulación)")
        print("2) Crear VMs (Round-Robin)")
        print("3) Definir Topología")
        print("4) Listar VMs desplegadas")
        print("5) Reiniciar cluster (borrar VMs)")
        print("6) Eliminar VM específica")
        print("7) Salir")

        option = input("> ")

        match option:
            case "1":
                print()
                print("Workers inicializados (solo para ejemplo)")
            case "2":
                print()
                num_vms = int(input("¿Cuántas VMs deseas crear?: "))
                worker_mgr.create_vms(num_vms)
            case "3":
                topo_mgr = TopologyManager(worker_mgr.vm_inventory, gateway_ip, user, passwd)
                topo_mgr.define_topology()
            case "4":
                worker_mgr.list_vms()
            case "5":
                worker_mgr.reset_cluster()
            case "6":
                worker_mgr.list_vms()
                vmn = input("Ingrese nombre de VM a eliminar (ej: VM1): ")
                vm_to_kill = next((v for v in worker_mgr.vm_inventory if v["name"] == vmn), None)
                if vm_to_kill:
                    worker_mgr.delete_vm(vm_to_kill)
                    worker_mgr.vm_inventory = [v for v in worker_mgr.vm_inventory if v["name"] != vmn]
                else:
                    print("No existe esa VM")
            case "7":
                print("Saliendo...")
                sys.exit(0)
            case _:
                print("Opción inválida")


# Alternativa sin usar match-case (Python < 3.10), comentado por si acaso!
# if option == "1":
#     print("Inicialización de Workers (solo para ejemplo)")
# elif option == "2":
#     num_vms = int(input("¿Cuántas VMs deseas crear?: "))
#     worker_mgr.create_vms(num_vms)
# elif option == "3":
#     topo_mgr = TopologyManager(worker_mgr.vm_inventory)
#     topo_mgr.define_topology()
# elif option == "4":
#     worker_mgr.list_vms()
# elif option == "5":
#     worker_mgr.reset_cluster()
# elif option == "6":
#     print("Saliendo...")
#     sys.exit(0)
# else:
#     print("Opción inválida")


if __name__ == "__main__":
    main()
