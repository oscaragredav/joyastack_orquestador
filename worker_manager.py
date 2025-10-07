import random
from ssh_utils import SSHConnection


class WorkerManager:
    def __init__(self, workers, gateway_ip, ssh_user, ssh_pass):
        self.workers = workers  # dict con {worker1: {ip, ssh_port}, ...}
        self.gateway_ip = gateway_ip  # IP del gateway
        self.ssh_user = ssh_user
        self.ssh_pass = ssh_pass
        self.vm_inventory = []  # lista de dicts con info de VMs
        self.counter = 0

    def create_vms(self, num_vms):
        """
        Crea N VMs con distribución round-robin en los workers
        """
        worker_names = list(self.workers.keys())
        for i in range(num_vms):
            vm_id = i + 1
            w_name = worker_names[i % len(worker_names)]
            wdata = self.workers[w_name]

            print()
            print(f"\nConfiguración de VM{vm_id} (asignada a {w_name})")
            cpus = int(input("   CPUs: "))
            ram = int(input("   RAM (MB): "))
            disk = int(input("   Disco (GB): "))
            # vlan = int(input("   VLAN ID: "))

            vnc_port = vm_id  # VNC único
            mac_suffix = f"{random.randint(0, 255):02x}"  # Sufijo de MAC único para evitar conflictos
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
                "mac": f"20:19:37:33:ee:{mac_suffix}",  # OJO: acá la MAC empieza con mi código :V
            }

            ssh = SSHConnection(
                self.gateway_ip, wdata["ssh_port"], self.ssh_user, self.ssh_pass
            )
            if not ssh.connect():
                print(f"No se pudo conectar a {w_name}")
                continue

            sftp = ssh.client.open_sftp()
            sftp.put("vm_create.sh", "/tmp/vm_create.sh")
            sftp.chmod("/tmp/vm_create.sh", 0o755)
            sftp.close()

            # Número de interfaces para la VM (por ahora 1, se ampliará en topología)
            num_ifaces = 1
            cmd = (
                f"/tmp/vm_create.sh {vm_info['name']} br-int 0 {vnc_port} "
                f"{vm_info['cpus']} {vm_info['ram']} {vm_info['disk']} {num_ifaces}"
            )
            print(f"Ejecutando en {w_name}: {cmd}")
            out, err = ssh.exec_sudo(cmd)

            # if err:
            #     print(f"Error creando VM en {w_name}: {err}")

            print("Output:", out, err)

            # Obtener el PID QEMU remoto
            pid_cmd = f"pgrep -f 'qemu-system-x86_64.*-name {vm_info['name']}'"
            out, err = ssh.exec_sudo(pid_cmd)
            if out.strip():
                vm_info["pid"] = out.strip()
            else:
                vm_info["pid"] = None

            ssh.close()

            print(
                f"{vm_info['name']} creada en {w_name}, PID={vm_info['pid']}"
            )
            print(
                f"   Acceso VNC local: vnc://127.0.0.1:{30010+vm_id}\n"
                f"   ssh -NL :{30010+vm_id}:127.0.0.1:{5900+vnc_port} "
                f"{self.ssh_user}@10.20.12.28 -p {wdata['ssh_port']}"
            )

            self.vm_inventory.append(vm_info)

    def list_vms(self):
        if not self.vm_inventory:
            print()
            print("No hay VMs desplegadas")
            return
        print()
        print("\n=== VMs desplegadas ===")
        for vm in self.vm_inventory:
            print(
                f"{vm['name']} en {vm['worker']} | "
                f"CPUs={vm['cpus']} RAM={vm['ram']}MB DISK={vm['disk']}GB "
                f"VLAN={vm['vlan']} VNC-Port={vm['vnc_port']}"
            )

    def delete_vm(self, vm_info):
        """Borra una VM específica en su worker"""
        ssh = SSHConnection(
            self.gateway_ip,
            vm_info["ssh_port"],
            self.ssh_user,
            self.ssh_pass,
        )
        if ssh.connect():
            if vm_info.get("pid"):
                ssh.exec_sudo(f"kill {vm_info['pid']}")

            ssh.exec_sudo(
                f"sudo ovs-vsctl --if-exists del-port br-int {vm_info['tap']}"
            )
            ssh.exec_sudo(f"sudo ip link delete {vm_info['tap']}")
            print(f"VM {vm_info['name']} eliminada en {vm_info['worker']}")
            ssh.close()
        else:
            print(
                f"No se pudo conectar a {vm_info['worker']} para borrar VM"
            )

    def reset_cluster(self):
        confirm = input("Seguro que deseas borrar todas las VMs? (yes/no): ")
        if confirm.lower() == "yes":
            for vm in self.vm_inventory:
                self.delete_vm(vm)
            self.vm_inventory = []
        else:
            print("Cancelado.")
