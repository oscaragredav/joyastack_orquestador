import random
from ssh_utils import SSHConnection


class WorkerManager:
    def __init__(self, workers, gateway_ip, ssh_user, ssh_pass):
        self.workers = workers
        self.gateway_ip = gateway_ip
        self.ssh_user = ssh_user
        self.ssh_pass = ssh_pass
        self.vm_inventory = []
        self.counter = 0

    def create_vms(self, num_vms):
        """Crea N VMs con distribución round-robin en los workers"""
        worker_names = list(self.workers.keys())
        pending = []
        results = []

        # Recopilación de datos de VMs
        for i in range(num_vms):
            # CORREGIDO: Usar ID secuencial simple en lugar de contador global
            #vm_id = i + 1
            self.counter += 1
            vm_id = self.counter
            w_name = worker_names[i % len(worker_names)]
            wdata = self.workers[w_name]

            print()
            print(f"\nConfiguración de VM{vm_id} (asignada a {w_name})")
            cpus = int(input("   CPUs: "))
            ram = int(input("   RAM (MB): "))
            disk = int(input("   Disco (GB): "))

            vnc_port = vm_id
            mac_suffix = f"{random.randint(0, 255):02x}"
            tap_name = f"br-int-VM{vm_id}-tap"

            vm_info = {
                "name": f"VM{vm_id}",
                "worker": w_name,
                "ip": wdata["ip"],
                "ssh_port": wdata["ssh_port"],
                "cpus": cpus,
                "ram": ram,
                "disk": disk,
                "vlan": None,
                "tap": tap_name,
                "vnc_port": vnc_port,
                "mac": f"20:19:37:33:ee:{mac_suffix}",
            }
            pending.append(vm_info)

        # Creación secuencial de VMs
        for vm_info in pending:
            w_name = vm_info["worker"]
            wdata = self.workers[w_name]

            try:
                ssh = SSHConnection(
                    self.gateway_ip, wdata["ssh_port"], self.ssh_user, self.ssh_pass
                )
                if not ssh.connect():
                    print(f"❌ No se pudo conectar a {w_name}")
                    results.append((vm_info, "Error de conexión SSH"))
                    continue

                # Transferir script
                sftp = ssh.client.open_sftp()
                sftp.put("vm_create.sh", "/tmp/vm_create.sh")
                sftp.chmod("/tmp/vm_create.sh", 0o755)
                sftp.close()

                # CORREGIDO: Usar vm_info['vnc_port'] en lugar de variable local
                num_ifaces = 1
                cmd = (
                    f"/tmp/vm_create.sh {vm_info['name']} br-int 0 {vm_info['vnc_port']} "
                    f"{vm_info['cpus']} {vm_info['ram']} {vm_info['disk']} {num_ifaces}"
                )
                
                print(f"\n🔧 Ejecutando {vm_info['name']} en {w_name}:")
                print(f"   Comando: {cmd}")
                out, err = ssh.exec_sudo(cmd)

                # Debug: Mostrar siempre el output completo
                print("📋 Output del script:")
                print(out)
                if err:
                    print("⚠️  Stderr:")
                    print(err)

                # Obtener PID (esto indica si QEMU realmente arrancó)
                pid_cmd = f"pgrep -f 'qemu-system-x86_64.*-name {vm_info['name']}'"
                pid_out, pid_err = ssh.exec_sudo(pid_cmd)
                
                if pid_out.strip():
                    vm_info["pid"] = pid_out.strip()
                    print(f"✅ {vm_info['name']} creada en {w_name}, PID={vm_info['pid']}")
                    
                    # Mostrar info de acceso VNC
                    vnc_local_port = 30010 + vm_info['vnc_port']
                    vnc_remote_port = 5900 + vm_info['vnc_port']
                    print(f"   📺 Acceso VNC local: vnc://127.0.0.1:{vnc_local_port}")
                    print(f"   🔗 SSH Tunnel: ssh -NL :{vnc_local_port}:127.0.0.1:{vnc_remote_port} "
                          f"{self.ssh_user}@{self.gateway_ip} -p {wdata['ssh_port']}")
                    
                    self.vm_inventory.append(vm_info)
                    results.append((vm_info, None))
                else:
                    print(f"❌ QEMU no inició para {vm_info['name']}")
                    print("   Revisa el output anterior para detalles del error")
                    vm_info["pid"] = None
                    results.append((vm_info, "QEMU no inició"))

                ssh.close()

            except Exception as e:
                print(f"❌ Excepción creando VM en {w_name}: {e}")
                results.append((vm_info, str(e)))

        # Resumen
        print()
        print("=" * 60)
        print("=== RESUMEN DE CREACIÓN DE VMs ===")
        print("=" * 60)

        success_count = sum(1 for _, err in results if err is None)
        fail_count = len(results) - success_count

        for vm_info, error in results:
            wdata = self.workers[vm_info["worker"]]
            
            if error:
                print(f"❌ {vm_info['name']} en {vm_info['worker']}: ERROR - {error}")
            else:
                vnc_local_port = 30010 + vm_info['vnc_port']
                vnc_remote_port = 5900 + vm_info['vnc_port']
                
                print(f"✅ {vm_info['name']} en {vm_info['worker']}: OK (PID={vm_info.get('pid', 'N/A')})")
                print(f"   SSH Tunnel: ssh -NL :{vnc_local_port}:127.0.0.1:{vnc_remote_port} "
                      f"{self.ssh_user}@{self.gateway_ip} -p {wdata['ssh_port']}")
                print(f"   VNC: vnc://127.0.0.1:{vnc_local_port}")

        print("=" * 60)
        print(f"✅ Exitosas: {success_count} | ❌ Fallidas: {fail_count}")
        print("=" * 60)
        print()

    def list_vms(self):
        if not self.vm_inventory:
            print("\n❌ No hay VMs desplegadas")
            return
        
        print("\n=== VMs DESPLEGADAS ===")
        for vm in self.vm_inventory:
            print(
                f"• {vm['name']} en {vm['worker']} | "
                f"CPUs={vm['cpus']} RAM={vm['ram']}MB DISK={vm['disk']}GB "
                f"VNC-Port={vm['vnc_port']} PID={vm.get('pid', 'N/A')}"
            )
        print()

    def delete_vm(self, vm_info):
        """Borra una VM específica en su worker"""
        ssh = SSHConnection(
            self.gateway_ip,
            vm_info["ssh_port"],
            self.ssh_user,
            self.ssh_pass,
        )
        if ssh.connect():
            # Matar proceso QEMU
            if vm_info.get("pid"):
                print(f"🔪 Matando proceso QEMU (PID={vm_info['pid']})...")
                ssh.exec_sudo(f"kill {vm_info['pid']}")
                ssh.exec_sudo(f"sleep 1")  # Dar tiempo para que termine

            # Limpiar interfaz TAP y puerto OvS
            print(f"🧹 Limpiando interfaz {vm_info['tap']}...")
            ssh.exec_sudo(f"ovs-vsctl --if-exists del-port br-int {vm_info['tap']}")
            ssh.exec_sudo(f"ip link delete {vm_info['tap']} 2>/dev/null || true")
            
            print(f"✅ VM {vm_info['name']} eliminada en {vm_info['worker']}")
            ssh.close()
        else:
            print(f"❌ No se pudo conectar a {vm_info['worker']} para borrar VM")

    def reset_cluster(self):
        confirm = input("⚠️  ¿Seguro que deseas borrar TODAS las VMs? (yes/no): ")
        if confirm.lower() == "yes":
            print(f"\n🧹 Eliminando {len(self.vm_inventory)} VMs...")
            for vm in self.vm_inventory:
                self.delete_vm(vm)
            self.vm_inventory = []
            print("✅ Cluster reiniciado\n")
        else:
            print("❌ Operación cancelada\n")
    
    