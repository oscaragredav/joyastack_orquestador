import networkx as nx
import matplotlib.pyplot as plt


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


def create_composite():
    print("En topología compuesta, debe definir subconjuntos por topología")
    # Ejemplo simple: VM1 y VM2 en línea, VM3 y VM4 en anillo
    groups = input(
        "Ingrese grupos como 'VM1,VM2:lineal ; VM3,VM4:anillo' : "
    ).split(";")

    topology = nx.Graph()
    for g in groups:
        try:
            vms, topo = g.split(":")
            vm_list = [v.strip() for v in vms.split(",")]
            if topo.lower() == "lineal":
                topology_2 = nx.path_graph(vm_list)
            elif topo.lower() == "anillo":
                topology_2 = nx.cycle_graph(vm_list)
            else:
                continue
            topology = nx.compose(topology, topology_2)
        except Exception as e:
            print(f"Error parseando grupo {g}: {e}")

    draw_topology(topology, "Topología Compuesta")


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
    def __init__(self, vm_inventory):
        self.vm_inventory = vm_inventory

    def define_topology(self):
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
            create_linear(vm_names)
        elif option == "2":
            create_ring(vm_names)
        elif option == "3":
            create_tree(vm_names)
        elif option == "4":
            create_composite()
        else:
            print("Opción inválida")

