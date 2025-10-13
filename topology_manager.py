import networkx as nx
import matplotlib.pyplot as plt
from ssh_utils import SSHConnection


def draw_topology(topology, title):
    plt.figure(figsize=(10, 8))
    pos = nx.spring_layout(topology, k=2, iterations=50)
    nx.draw(
        topology,
        pos,
        with_labels=True,
        node_size=2000,
        node_color="skyblue",
        font_size=10,
        font_weight="bold",
        edge_color="gray",
        width=2
    )
    plt.title(title)
    plt.show()


def draw_interconnected_topology(topology_groups, interconnections):
    """Dibuja todas las topologias con sus interconexiones"""
    G = nx.Graph()
    
    # Agregar todas las topologias al grafo
    colors = ['lightblue', 'lightgreen', 'lightcoral', 'lightyellow', 'lightpink']
    node_colors = {}
    
    for i, group in enumerate(topology_groups):
        color = colors[i % len(colors)]
        vms = group['vms']
        topo_type = group['type']
        
        # Crear el subgrafo segun el tipo
        if topo_type == 'lineal':
            edges = [(vms[j], vms[j+1]) for j in range(len(vms)-1)]
        elif topo_type == 'anillo':
            edges = [(vms[j], vms[(j+1) % len(vms)]) for j in range(len(vms))]
        elif topo_type == 'bus':
            if len(vms) > 1:
                edges = [(vms[0], vm) for vm in vms[1:]]
            else:
                edges = []
        elif topo_type == 'arbol':
            edges = []
            for j in range(len(vms)):
                left = 2*j + 1
                right = 2*j + 2
                if left < len(vms):
                    edges.append((vms[j], vms[left]))
                if right < len(vms):
                    edges.append((vms[j], vms[right]))
        else:
            edges = []
        
        G.add_edges_from(edges)
        
        # Asignar color a los nodos
        for vm in vms:
            node_colors[vm] = color
    
    # Agregar interconexiones (en rojo)
    interconnect_edges = [(conn['vm1'], conn['vm2']) for conn in interconnections]
    G.add_edges_from(interconnect_edges)
    
    # Preparar colores de nodos
    color_map = [node_colors.get(node, 'gray') for node in G.nodes()]
    
    # Dibujar
    plt.figure(figsize=(12, 10))
    pos = nx.spring_layout(G, k=3, iterations=100)
    
    # Dibujar nodos
    nx.draw_networkx_nodes(G, pos, node_color=color_map, node_size=2500)
    
    # Dibujar aristas normales
    normal_edges = [edge for edge in G.edges() if edge not in interconnect_edges and tuple(reversed(edge)) not in interconnect_edges]
    nx.draw_networkx_edges(G, pos, edgelist=normal_edges, edge_color='gray', width=2)
    
    # Dibujar aristas de interconexion (en rojo y mas gruesas)
    if interconnect_edges:
        nx.draw_networkx_edges(G, pos, edgelist=interconnect_edges, edge_color='red', width=4, style='dashed')
    
    # Dibujar etiquetas
    nx.draw_networkx_labels(G, pos, font_size=10, font_weight='bold')
    
    plt.title("Topologia Completa con Interconexiones")
    plt.axis('off')
    plt.tight_layout()
    plt.show()


def create_tree(nodes):
    topology = nx.balanced_tree(r=2, h=2)
    mapping = {i: nodes[i] for i in range(min(len(nodes), len(topology.nodes)))}
    topology = nx.relabel_nodes(topology, mapping, copy=False)
    draw_topology(topology, "Topologia Arbol")


def create_ring(nodes):
    topology = nx.cycle_graph(nodes)
    draw_topology(topology, "Topologia Anillo")


def create_linear(nodes):
    topology = nx.path_graph(nodes)
    draw_topology(topology, "Topologia Lineal")


def create_bus(nodes):
    topology = nx.star_graph(len(nodes) - 1)
    mapping = {i: nodes[i] for i in range(len(nodes))}
    topology = nx.relabel_nodes(topology, mapping)
    draw_topology(topology, "Topologia Bus")


def _ensure_tap_exists(conn, vm, tap_name):
    if not conn.connect():
        print(f"No se pudo conectar a {vm['name']}")
        return

    out, err = conn.exec_command(f"ip link show {tap_name}")
    if "does not exist" in err or not out.strip():
        print(f"Creando interfaz TAP faltante {tap_name} en {vm['name']}")
        conn.exec_sudo(f"ip tuntap add mode tap name {tap_name}")
        conn.exec_sudo(f"ip link set dev {tap_name} up")
        conn.exec_sudo(f"ovs-vsctl add-port br-int {tap_name}")
        print(f"{tap_name} creada y conectada a br-int")
    else:
        print(f"{tap_name} ya existe en {vm['name']}")

    conn.close()


class TopologyManager:
    def __init__(self, vm_inventory, gateway_ip, ssh_user, ssh_pass):
        self.vm_inventory = vm_inventory
        self.ssh_user = ssh_user
        self.ssh_pass = ssh_pass
        self.gateway_ip = gateway_ip
        self.next_vlan_id = 100
        self.topology_groups = []  # Para almacenar grupos de topologias creadas
        self.interconnections = []  # Para almacenar conexiones entre topologias

    def select_vms_for_topology(self):
        """Permite al usuario seleccionar un subconjunto de VMs"""
        if not self.vm_inventory:
            print("\nNo hay VMs disponibles")
            return []

        vm_names = [vm["name"] for vm in self.vm_inventory]
        print("\n=== Seleccion de VMs para Topologia ===")
        print("VMs disponibles:", ", ".join(vm_names))
        print("\nOpciones de seleccion:")
        print("1) Seleccionar VMs individuales (ej: VM1,VM3,VM5)")
        print("2) Seleccionar por rango (ej: VM1-VM4)")
        print("3) Seleccionar todas las VMs")
        
        option = input("\nSeleccione opcion: ").strip()
        
        if option == "1":
            selected_input = input("Ingrese nombres separados por comas (ej: VM1,VM2,VM3): ").strip()
            selected_names = [name.strip() for name in selected_input.split(",")]
            selected_vms = [vm for vm in self.vm_inventory if vm["name"] in selected_names]
            
        elif option == "2":
            range_input = input("Ingrese rango (ej: VM1-VM5): ").strip()
            try:
                start, end = range_input.split("-")
                start_num = int(start.replace("VM", ""))
                end_num = int(end.replace("VM", ""))
                selected_names = [f"VM{i}" for i in range(start_num, end_num + 1)]
                selected_vms = [vm for vm in self.vm_inventory if vm["name"] in selected_names]
            except:
                print("Error en el formato del rango")
                return []
                
        elif option == "3":
            selected_vms = self.vm_inventory.copy()
            
        else:
            print("Opcion invalida")
            return []
        
        if not selected_vms:
            print("No se encontraron VMs con los nombres especificados")
            return []
        
        print(f"\nVMs seleccionadas: {', '.join([vm['name'] for vm in selected_vms])}")
        confirm = input("Confirmar seleccion? (yes/no): ").strip().lower()
        
        if confirm == "yes":
            return selected_vms
        else:
            print("Seleccion cancelada")
            return []

    def create_composite(self):
        print("\n=== Creacion de Topologia Compuesta ===")
        print("Defina multiples grupos de VMs con diferentes topologias")
        print("Formato: 'VM1,VM2,VM3:lineal' para cada grupo")
        print("Separe grupos con punto y coma (;)")
        print("\nEjemplo: VM1,VM2:lineal ; VM3,VM4,VM5:anillo ; VM6:bus")
        
        groups_raw = input("\nIngrese grupos: ").split(";")

        topology = nx.Graph()

        for g in groups_raw:
            try:
                vms, topo = g.split(":")
                vm_list = [v.strip() for v in vms.split(",")]
                ttype = topo.lower().strip()

                if ttype == "lineal":
                    sub_g = nx.path_graph(vm_list)
                elif ttype == "anillo":
                    sub_g = nx.cycle_graph(vm_list)
                elif ttype == "bus":
                    sub_g = nx.star_graph(len(vm_list) - 1)
                    mapping = {i: vm_list[i] for i in range(len(vm_list))}
                    sub_g = nx.relabel_nodes(sub_g, mapping)
                elif ttype == "arbol":
                    sub_g = nx.balanced_tree(r=2, h=1)
                    mapping = {i: vm_list[i] for i in range(min(len(vm_list), len(sub_g.nodes)))}
                    sub_g = nx.relabel_nodes(sub_g, mapping)
                else:
                    print(f"Topologia '{ttype}' no reconocida, omitiendo...")
                    continue

                topology = nx.compose(topology, sub_g)

                subset_inventory = [
                    vm for vm in self.vm_inventory if vm["name"] in vm_list
                ]
                if subset_inventory:
                    old_inv = self.vm_inventory
                    self.vm_inventory = subset_inventory
                    self.apply_vlan_topology(ttype, self.gateway_ip, self.ssh_user, self.ssh_pass)
                    self.vm_inventory = old_inv
                else:
                    print("Ninguna VM del subconjunto esta desplegada.")

            except Exception as e:
                print(f"Error parseando grupo '{g}': {e}")

        draw_topology(topology, "Topologia Compuesta")

    def define_topology(self):
        try:
            if not self.vm_inventory:
                print("\nNo hay VMs para definir alguna topologia")
                return

            print("\n=== Definicion de Topologia ===")
            print("Seleccione tipo de topologia:")
            print("1) Simple - Lineal")
            print("2) Simple - Anillo")
            print("3) Simple - Arbol")
            print("4) Simple - Bus")
            print("5) Compuesta (multiple topologias)")
            print("6) Interconectar topologias existentes")
            print("7) Ver topologias creadas")
            print("8) Visualizar topologia completa")
            print("9) Volver al menu principal")

            option = input("\n> ").strip()

            if option == "9":
                return

            # Para topologias simples (1-4), seleccionar VMs
            if option in ["1", "2", "3", "4"]:
                selected_vms = self.select_vms_for_topology()
                
                if not selected_vms:
                    print("No se seleccionaron VMs. Operacion cancelada.")
                    return
                
                # Validacion de numero minimo de VMs segun topologia
                min_vms = {
                    "1": 2,  # Lineal
                    "2": 3,  # Anillo
                    "3": 3,  # Arbol
                    "4": 2,  # Bus
                }
                
                if len(selected_vms) < min_vms.get(option, 2):
                    print(f"\nError: Esta topologia requiere al menos {min_vms.get(option, 2)} VMs")
                    return
                
                # IMPORTANTE: Guardar nombres ANTES de modificar el inventario
                vm_names = [vm["name"] for vm in selected_vms]
                
                # Guardar inventario original y trabajar con el subconjunto
                original_inventory = self.vm_inventory
                self.vm_inventory = selected_vms

            if option == "1":
                vlan_before = self.next_vlan_id
                self.apply_vlan_topology("lineal", self.gateway_ip, self.ssh_user, self.ssh_pass)
                # Guardar grupo de topologia
                self.topology_groups.append({
                    "type": "lineal",
                    "vms": vm_names.copy(),
                    "vlan_start": vlan_before
                })
                create_linear(vm_names)
                print(f"\nTopologia LINEAL guardada con VMs: {', '.join(vm_names)}")
                
            elif option == "2":
                vlan_before = self.next_vlan_id
                self.apply_vlan_topology("anillo", self.gateway_ip, self.ssh_user, self.ssh_pass)
                self.topology_groups.append({
                    "type": "anillo",
                    "vms": vm_names.copy(),
                    "vlan_start": vlan_before
                })
                create_ring(vm_names)
                print(f"\nTopologia ANILLO guardada con VMs: {', '.join(vm_names)}")
                
            elif option == "3":
                vlan_before = self.next_vlan_id
                self.apply_vlan_topology("arbol", self.gateway_ip, self.ssh_user, self.ssh_pass)
                self.topology_groups.append({
                    "type": "arbol",
                    "vms": vm_names.copy(),
                    "vlan_start": vlan_before
                })
                create_tree(vm_names)
                print(f"\nTopologia ARBOL guardada con VMs: {', '.join(vm_names)}")
                
            elif option == "4":
                vlan_before = self.next_vlan_id
                self.apply_vlan_topology("bus", self.gateway_ip, self.ssh_user, self.ssh_pass)
                self.topology_groups.append({
                    "type": "bus",
                    "vms": vm_names.copy(),
                    "vlan_start": vlan_before
                })
                create_bus(vm_names)
                print(f"\nTopologia BUS guardada con VMs: {', '.join(vm_names)}")
                
            elif option == "5":
                self.create_composite()
                
            elif option == "6":
                self.interconnect_topologies()
                
            elif option == "7":
                self.list_topology_groups()
                
            elif option == "8":
                if not self.topology_groups:
                    print("\nNo hay topologias creadas para visualizar")
                else:
                    draw_interconnected_topology(self.topology_groups, self.interconnections)
                
            else:
                print("Opcion invalida")
                return

            # Restaurar inventario original si se modifico
            if option in ["1", "2", "3", "4"]:
                self.vm_inventory = original_inventory
                print(f"Total de topologias guardadas: {len(self.topology_groups)}")

        except Exception as e:
            print(f"Error definiendo topologia: {e}")

    def apply_vlan_topology(self, topo_type, gateway_ip, ssh_user, ssh_pass):
        """
        Aplica una topologia real en los bridges OvS mediante VLAN.
        topo_type: 'lineal' | 'anillo' | 'bus' | 'arbol'
        """

        if not self.vm_inventory:
            print("No hay VMs desplegadas para aplicar topologia")
            return

        print(f"\n=== Aplicando topologia tipo '{topo_type}' ===")

        # Limpieza previa de VLAN tags existentes solo para las VMs seleccionadas
        print("Limpiando etiquetas VLAN de VMs seleccionadas...")
        for vm in self.vm_inventory:
            conn = SSHConnection(gateway_ip, vm["ssh_port"], ssh_user, ssh_pass)
            if conn.connect():
                conn.exec_sudo(f"ovs-vsctl clear port {vm['tap']} tag")
                conn.close()

        vlan_id = self.next_vlan_id
        print(f"VLAN ID inicial: {vlan_id}")

        # ---------------------- TOPOLOGIA LINEAL ----------------------
        if topo_type == "lineal":
            print("\nConfigurando topologia LINEAL...")
            vms_sorted = sorted(self.vm_inventory, key=lambda v: v["name"])

            for i in range(len(vms_sorted) - 1):
                vm_a = vms_sorted[i]
                vm_b = vms_sorted[i + 1]

                tap_a = f"br-int-{vm_a['name']}-tap{2 if i > 0 else 1}"
                tap_b = f"br-int-{vm_b['name']}-tap{1 if (i + 1) < len(vms_sorted) - 1 else 1}"

                print(f"  VLAN {vlan_id}: {vm_a['name']}({tap_a}) <-> {vm_b['name']}({tap_b})")

                for vm, tap_name in ((vm_a, tap_a), (vm_b, tap_b)):
                    conn = SSHConnection(gateway_ip, vm["ssh_port"], self.ssh_user, self.ssh_pass)
                    _ensure_tap_exists(conn, vm, tap_name)
                    if conn.connect():
                        conn.exec_sudo(f"ovs-vsctl set port {tap_name} tag={vlan_id}")
                        conn.close()

                vlan_id += 1

        # ---------------------- TOPOLOGIA ANILLO ----------------------
        elif topo_type == "anillo":
            print("\nConfigurando topologia ANILLO...")
            vms_sorted = sorted(self.vm_inventory, key=lambda v: v["name"])
            n = len(vms_sorted)

            for i in range(n):
                vm_a = vms_sorted[i]
                vm_b = vms_sorted[(i + 1) % n]

                tap_a = f"br-int-{vm_a['name']}-tap{min(2, i + 1)}"
                tap_b = f"br-int-{vm_b['name']}-tap{1 if (i + 1) == n else min(2, i + 1)}"

                print(f"  VLAN {vlan_id}: {vm_a['name']}({tap_a}) <-> {vm_b['name']}({tap_b})")

                for vm, tap_name in ((vm_a, tap_a), (vm_b, tap_b)):
                    conn = SSHConnection(gateway_ip, vm["ssh_port"], self.ssh_user, self.ssh_pass)
                    _ensure_tap_exists(conn, vm, tap_name)
                    if conn.connect():
                        conn.exec_sudo(f"ovs-vsctl set port {tap_name} tag={vlan_id}")
                        conn.close()

                vlan_id += 1

        # ---------------------- TOPOLOGIA BUS ----------------------
        elif topo_type == "bus":
            print("\nConfigurando topologia BUS (una sola VLAN)...")
            print(f"  VLAN {vlan_id}: {', '.join([v['name'] for v in self.vm_inventory])}")
            for vm in self.vm_inventory:
                conn = SSHConnection(gateway_ip, vm["ssh_port"], ssh_user, ssh_pass)
                if conn.connect():
                    conn.exec_sudo(f"ovs-vsctl set port {vm['tap']} tag={vlan_id}")
                    conn.close()
            vlan_id += 1

        # ---------------------- TOPOLOGIA ARBOL ----------------------
        elif topo_type == "arbol":
            print("\nConfigurando topologia ARBOL...")
            vms_sorted = sorted(self.vm_inventory, key=lambda v: v["name"])
            
            # Estructura de arbol binario simple
            for i in range(len(vms_sorted)):
                left_child = 2 * i + 1
                right_child = 2 * i + 2
                
                if left_child < len(vms_sorted):
                    vm_parent = vms_sorted[i]
                    vm_child = vms_sorted[left_child]
                    
                    tap_parent = f"br-int-{vm_parent['name']}-tap{left_child + 1}"
                    tap_child = f"br-int-{vm_child['name']}-tap1"
                    
                    print(f"  VLAN {vlan_id}: {vm_parent['name']}({tap_parent}) <-> {vm_child['name']}({tap_child})")
                    
                    for vm, tap_name in ((vm_parent, tap_parent), (vm_child, tap_child)):
                        conn = SSHConnection(gateway_ip, vm["ssh_port"], self.ssh_user, self.ssh_pass)
                        _ensure_tap_exists(conn, vm, tap_name)
                        if conn.connect():
                            conn.exec_sudo(f"ovs-vsctl set port {tap_name} tag={vlan_id}")
                            conn.close()
                    
                    vlan_id += 1
                
                if right_child < len(vms_sorted):
                    vm_parent = vms_sorted[i]
                    vm_child = vms_sorted[right_child]
                    
                    tap_parent = f"br-int-{vm_parent['name']}-tap{right_child + 1}"
                    tap_child = f"br-int-{vm_child['name']}-tap1"
                    
                    print(f"  VLAN {vlan_id}: {vm_parent['name']}({tap_parent}) <-> {vm_child['name']}({tap_child})")
                    
                    for vm, tap_name in ((vm_parent, tap_parent), (vm_child, tap_child)):
                        conn = SSHConnection(gateway_ip, vm["ssh_port"], self.ssh_user, self.ssh_pass)
                        _ensure_tap_exists(conn, vm, tap_name)
                        if conn.connect():
                            conn.exec_sudo(f"ovs-vsctl set port {tap_name} tag={vlan_id}")
                            conn.close()
                    
                    vlan_id += 1

        else:
            print("Topologia aun no soportada")
            return

        self.next_vlan_id = vlan_id

        print("\nTopologia aplicada exitosamente.")

    def list_topology_groups(self):
        """Muestra las topologias creadas hasta el momento"""
        print(f"\nDebug: self.topology_groups tiene {len(self.topology_groups)} elementos")
        
        if not self.topology_groups:
            print("No hay topologias creadas aun")
            return
        
        print("\n=== Topologias Creadas ===")
        for i, group in enumerate(self.topology_groups, 1):
            print(f"\n[{i}] Topologia {group['type'].upper()}")
            print(f"    VMs: {', '.join(group['vms'])}")
            print(f"    VLAN inicial: {group['vlan_start']}")
        
        if self.interconnections:
            print("\n=== Interconexiones ===")
            for i, conn in enumerate(self.interconnections, 1):
                print(f"[{i}] {conn['vm1']} <-> {conn['vm2']} (VLAN {conn['vlan']})")
        
        print()

    def interconnect_topologies(self):
        """Permite interconectar dos topologias a traves de VMs especificas"""
        if len(self.topology_groups) < 2:
            print("\nDebe tener al menos 2 topologias creadas para interconectar")
            print(f"Actualmente tiene {len(self.topology_groups)} topologia(s)")
            return
        
        print("\n=== Interconexion de Topologias ===")
        
        # Mostrar topologias disponibles
        self.list_topology_groups()
        
        print("\nSeleccione las VMs que actuaran como puentes entre topologias")
        print("Estas VMs deben pertenecer a topologias diferentes")
        
        # Obtener todas las VMs que ya estan en topologias
        all_topo_vms = set()
        for group in self.topology_groups:
            all_topo_vms.update(group['vms'])
        
        print(f"\nVMs en topologias: {', '.join(sorted(all_topo_vms))}")
        
        # Seleccionar primera VM
        vm1_name = input("\nIngrese nombre de la primera VM (ej: VM3): ").strip()
        if vm1_name not in all_topo_vms:
            print(f"Error: {vm1_name} no pertenece a ninguna topologia")
            return
        
        # Seleccionar segunda VM
        vm2_name = input("Ingrese nombre de la segunda VM (ej: VM6): ").strip()
        if vm2_name not in all_topo_vms:
            print(f"Error: {vm2_name} no pertenece a ninguna topologia")
            return
        
        if vm1_name == vm2_name:
            print("Error: Debe seleccionar VMs diferentes")
            return
        
        # Verificar que pertenecen a topologias diferentes
        vm1_topo = None
        vm2_topo = None
        
        for i, group in enumerate(self.topology_groups):
            if vm1_name in group['vms']:
                vm1_topo = i
            if vm2_name in group['vms']:
                vm2_topo = i
        
        if vm1_topo == vm2_topo:
            print("Advertencia: Ambas VMs pertenecen a la misma topologia")
            confirm = input("Desea continuar de todos modos? (yes/no): ").strip().lower()
            if confirm != "yes":
                return
        
        # Obtener objetos VM del inventario
        vm1_obj = next((vm for vm in self.vm_inventory if vm['name'] == vm1_name), None)
        vm2_obj = next((vm for vm in self.vm_inventory if vm['name'] == vm2_name), None)
        
        if not vm1_obj or not vm2_obj:
            print("Error: No se encontraron las VMs en el inventario")
            return
        
        print(f"\nCreando interconexion entre {vm1_name} y {vm2_name}...")
        
        # Asignar nueva VLAN para la interconexion
        interconnect_vlan = self.next_vlan_id
        self.next_vlan_id += 1
        
        # Determinar numero de tap a usar para cada VM
        # Buscar el siguiente tap disponible
        tap1_num = self._get_next_available_tap(vm1_obj)
        tap2_num = self._get_next_available_tap(vm2_obj)
        
        tap1_name = f"br-int-{vm1_name}-tap{tap1_num}"
        tap2_name = f"br-int-{vm2_name}-tap{tap2_num}"
        
        print(f"Usando {tap1_name} y {tap2_name}")
        print(f"VLAN de interconexion: {interconnect_vlan}")
        
        # Crear las interfaces TAP y conectarlas con la misma VLAN
        for vm_obj, tap_name in [(vm1_obj, tap1_name), (vm2_obj, tap2_name)]:
            conn = SSHConnection(
                self.gateway_ip, 
                vm_obj["ssh_port"], 
                self.ssh_user, 
                self.ssh_pass
            )
            
            _ensure_tap_exists(conn, vm_obj, tap_name)
            
            if conn.connect():
                conn.exec_sudo(f"ovs-vsctl set port {tap_name} tag={interconnect_vlan}")
                print(f"  {tap_name} configurado en VLAN {interconnect_vlan}")
                conn.close()
        
        # Guardar la interconexion
        self.interconnections.append({
            'vm1': vm1_name,
            'vm2': vm2_name,
            'vlan': interconnect_vlan,
            'tap1': tap1_name,
            'tap2': tap2_name
        })
        
        print(f"\nInterconexion creada exitosamente!")
        print(f"{vm1_name} <-> {vm2_name} via VLAN {interconnect_vlan}")
    
    def _get_next_available_tap(self, vm_obj):
        """Determina el siguiente numero de TAP disponible para una VM"""
        # Buscar en las interconexiones existentes
        used_taps = set()
        
        for conn_info in self.interconnections:
            if conn_info['vm1'] == vm_obj['name']:
                # Extraer numero del tap1
                tap_num = int(conn_info['tap1'].split('tap')[1])
                used_taps.add(tap_num)
            elif conn_info['vm2'] == vm_obj['name']:
                # Extraer numero del tap2
                tap_num = int(conn_info['tap2'].split('tap')[1])
                used_taps.add(tap_num)
        
        # El tap1 ya existe (creado con la VM), buscar desde tap2 en adelante
        next_tap = 2
        while next_tap in used_taps:
            next_tap += 1
        
        return next_tap