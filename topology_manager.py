import networkx as nx
import matplotlib.pyplot as plt
from ssh_utils import SSHConnection


def draw_topology(topology, title):
    plt.figure(figsize=(6, 6))
    pos = nx.spring_layout(topology)
    nx.draw(
        topology,
        pos,
        with_labels=True,
        node_size=2000,
        node_color="skyblue",
        font_size=10,
        font_weight="bold",
    )
    plt.title(title)
    plt.show()


def create_tree(nodes):
    # Árbol binario simple, hay que ajustar r y h según los nodos (nodes)
    topology = nx.balanced_tree(r=2, h=2)
    mapping = {i: nodes[i] for i in range(min(len(nodes), len(topology.nodes)))}
    topology = nx.relabel_nodes(topology, mapping, copy=False)
    draw_topology(topology, "Topología Árbol")


def create_ring(nodes):
    topology = nx.cycle_graph(nodes)
    draw_topology(topology, "Topología Anillo")


def create_linear(nodes):
    topology = nx.path_graph(nodes)
    draw_topology(topology, "Topología Lineal")


class TopologyManager:
    def __init__(self, vm_inventory, gateway_ip, ssh_user, ssh_pass):
        self.vm_inventory = vm_inventory
        self.ssh_user = ssh_user
        self.ssh_pass = ssh_pass
        self.gateway_ip = gateway_ip
        self.next_vlan_id = 100

    def create_composite(self):
        print("En topología compuesta, debe definir subconjuntos por topología")
        # Ejemplo simple: VM1 y VM2 lineal, VM3 y VM4 en anillo
        groups_raw = input(
            "Ingrese grupos como 'VM1,VM2:lineal ; VM3,VM4:anillo' : "
        ).split(";")

        topology = nx.Graph()

        for g in groups_raw:
            try:
                vms, topo = g.split(":")
                vm_list = [v.strip() for v in vms.split(",")]
                ttype = topo.lower().strip()

                # Generar grafo parcial solo para visualización
                if ttype == "lineal":
                    sub_g = nx.path_graph(vm_list)
                elif ttype == "anillo":
                    sub_g = nx.cycle_graph(vm_list)
                elif ttype == "bus":
                    sub_g = nx.complete_graph(vm_list)  # bus = mismo dominio
                else:
                    print(f"Topología '{ttype}' aún no implementada, continuando... \n")
                    continue

                topology = nx.compose(topology, sub_g)

                # Aplica la configuración para el subconjunto de VMs
                subset_inventory = [
                    vm for vm in self.vm_inventory if vm["name"] in vm_list
                ]
                if subset_inventory:
                    # Temporalmente limitamos vm_inventory al subset
                    old_inv = self.vm_inventory
                    self.vm_inventory = subset_inventory
                    self.apply_vlan_topology(ttype, self.gateway_ip, self.ssh_user, self.ssh_pass)
                    self.vm_inventory = old_inv
                else:
                    print("Ninguna VM del subconjunto está desplegada.")

            except Exception as e:
                print(f" Error parseando grupo '{g}': {e}")

        draw_topology(topology, "Topología Compuesta")

    def define_topology(self):
        try:
            if not self.vm_inventory:
                print()
                print("No hay VMs para definir alguna topología")
                return

            vm_names = [vm["name"] for vm in self.vm_inventory]
            print("\nVMs disponibles:", ", ".join(vm_names))

            print("Seleccione topología:")
            print("1) Simple - Lineal")
            print("2) Simple - Anillo")
            print("3) Simple - Árbol")
            print("4) Compuesta")

            option = input("> ")

            if option == "1":
                self.apply_vlan_topology("lineal", self.gateway_ip, self.ssh_user, self.ssh_pass)
                create_linear(vm_names)
            elif option == "2":
                self.apply_vlan_topology("anillo", self.gateway_ip, self.ssh_user, self.ssh_pass)
                create_ring(vm_names)
            elif option == "3":
                self.apply_vlan_topology("arbol", self.gateway_ip, self.ssh_user, self.ssh_pass)
                create_tree(vm_names)
            elif option == "4":
                self.create_composite()
            else:
                print("Opción inválida")
        except Exception as e:
            print(f"Error definiendo topología: {e}")

    def apply_vlan_topology(
            self, topo_type, gateway_ip, ssh_user, ssh_pass
    ):
        """
        Aplica una topología real en los bridges OvS de los workers mediante VLAN.
        Topo_type: 'lineal' | 'anillo' | 'bus'
        """

        if not self.vm_inventory:
            print("No hay VMs desplegadas para aplicar topología")
            return

        print(f"\n=== Aplicando topología tipo '{topo_type}' ===")

        # Limpieza previa de VLAN tags existentes
        print("Limpiando etiquetas VLAN existentes...")
        for vm in self.vm_inventory:
            print(vm["name"], vm["worker"])
            conn = SSHConnection(gateway_ip, vm["ssh_port"], ssh_user, ssh_pass)
            if conn.connect():
                conn.exec_sudo(f"ovs-vsctl clear port {vm['tap']} tag")
                conn.close()

        vlan_id = self.next_vlan_id
        print(f"Siguiente VLAN ID a usar: {vlan_id}")

        # ---------------------- TOPOLOGÍA LINEAL ----------------------
        if topo_type == "lineal":
            print("\nConfigurando topología LINEAL...")
            for i in range(len(self.vm_inventory) - 1):
                vm_a = self.vm_inventory[i]
                vm_b = self.vm_inventory[i + 1]

                print(f"  VLAN {vlan_id}: {vm_a['name']} <-> {vm_b['name']}")
                for vm in (vm_a, vm_b):
                    conn = SSHConnection(
                        gateway_ip, vm["ssh_port"], ssh_user, ssh_pass
                    )
                    if conn.connect():
                        conn.exec_sudo(
                            f"ovs-vsctl set port {vm['tap']} tag={vlan_id}"
                        )
                        conn.close()
                vlan_id += 100

        # ---------------------- TOPOLOGÍA ANILLO ----------------------
        elif topo_type == "anillo":
            print("\nConfigurando topología ANILLO...")
            n = len(self.vm_inventory)
            for i in range(n):
                vm_a = self.vm_inventory[i]
                vm_b = self.vm_inventory[(i + 1) % n]  # Siguiente, o vuelve al inicio
                print(f"  VLAN {vlan_id}: {vm_a['name']} <-> {vm_b['name']}")
                for vm in (vm_a, vm_b):
                    conn = SSHConnection(
                        gateway_ip, vm["ssh_port"], ssh_user, ssh_pass
                    )
                    if conn.connect():
                        conn.exec_sudo(
                            f"ovs-vsctl set port {vm['tap']} tag={vlan_id}"
                        )
                        conn.close()
                vlan_id += 100

        # ---------------------- TOPOLOGÍA BUS ----------------------
        elif topo_type == "bus":
            print("\nConfigurando topología BUS (una sola VLAN)...")
            print("  VLAN", vlan_id, ":", ", ".join([v["name"] for v in self.vm_inventory]))
            for vm in self.vm_inventory:
                conn = SSHConnection(gateway_ip, vm["ssh_port"], ssh_user, ssh_pass)
                if conn.connect():
                    conn.exec_sudo(f"ovs-vsctl set port {vm['tap']} tag={vlan_id}")
                    conn.close()

        else:
            print("Topología aún no soportada")
            return

        self.next_vlan_id = vlan_id

        print("\nTopología aplicada exitosamente.\n")
