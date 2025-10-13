"""
Módulo para manejar conexiones SSH y túneles sin dependencia de sshtunnel
Evita problemas con DSSKey en versiones modernas de paramiko
"""
import paramiko
import socket
import threading
import select
import time


class SSHTunnel:
    """Túnel SSH sin usar sshtunnel (evita problemas con DSSKey)"""
    
    def __init__(self, ssh_host, ssh_port, ssh_user, ssh_pass, 
                 remote_host, remote_port):
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_pass = ssh_pass
        self.remote_host = remote_host
        self.remote_port = remote_port
        
        self.local_port = self._get_free_port()
        self.client = None
        self.transport = None
        self.server_socket = None
        self.running = False
        self.threads = []
        
    def _get_free_port(self):
        """Obtener puerto local disponible"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    def start(self):
        """Iniciar túnel SSH"""
        try:
            # Crear cliente SSH
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Conectar (sin buscar claves DSS/RSA)
            self.client.connect(
                hostname=self.ssh_host,
                port=self.ssh_port,
                username=self.ssh_user,
                password=self.ssh_pass,
                look_for_keys=False,  # IMPORTANTE: evita buscar DSSKey
                allow_agent=False,
                timeout=10
            )
            
            self.transport = self.client.get_transport()
            
            # Crear socket servidor local
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('127.0.0.1', self.local_port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1)  # Timeout para poder detener
            
            self.running = True
            
            # Thread para aceptar conexiones
            accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
            accept_thread.start()
            self.threads.append(accept_thread)
            
            # Dar tiempo a que el servidor inicie
            time.sleep(0.5)
            
            return True
            
        except paramiko.AuthenticationException:
            raise Exception("Autenticación SSH fallida")
        except paramiko.SSHException as e:
            raise Exception(f"Error SSH: {e}")
        except Exception as e:
            self.stop()
            raise Exception(f"Error al crear túnel: {e}")
    
    def _accept_connections(self):
        """Aceptar conexiones entrantes y crear forwards"""
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
                
                # Crear thread para manejar esta conexión
                handler_thread = threading.Thread(
                    target=self._handle_connection,
                    args=(client_socket,),
                    daemon=True
                )
                handler_thread.start()
                self.threads.append(handler_thread)
                
            except socket.timeout:
                continue  # Reintentar
            except Exception as e:
                if self.running:
                    print(f"Error aceptando conexión: {e}")
                break
    
    def _handle_connection(self, client_socket):
        """Manejar una conexión individual (forward bidireccional)"""
        channel = None
        try:
            # Abrir canal SSH hacia destino remoto
            channel = self.transport.open_channel(
                kind='direct-tcpip',
                dest_addr=(self.remote_host, self.remote_port),
                src_addr=('127.0.0.1', self.local_port)
            )
            
            # Forward bidireccional
            while self.running:
                # Esperar datos de cualquier lado
                ready_sockets, _, _ = select.select([client_socket, channel], [], [], 1)
                
                if not ready_sockets:
                    continue
                
                # Cliente -> Servidor remoto
                if client_socket in ready_sockets:
                    try:
                        data = client_socket.recv(8192)
                        if not data:
                            break
                        channel.send(data)
                    except:
                        break
                
                # Servidor remoto -> Cliente
                if channel in ready_sockets:
                    try:
                        data = channel.recv(8192)
                        if not data:
                            break
                        client_socket.send(data)
                    except:
                        break
                        
        except Exception as e:
            pass  # Conexión terminada
        finally:
            if channel:
                channel.close()
            client_socket.close()
    
    def stop(self):
        """Detener túnel y limpiar recursos"""
        self.running = False
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        if self.client:
            try:
                self.client.close()
            except:
                pass
        
        # Esperar threads (máximo 2 segundos)
        for thread in self.threads:
            thread.join(timeout=2)
    
    @property
    def local_bind_port(self):
        """Puerto local del túnel"""
        return self.local_port
    
    def __enter__(self):
        """Context manager support"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup"""
        self.stop()


# Función auxiliar para facilitar uso
def create_ssh_tunnel(ssh_host, ssh_port, ssh_user, ssh_pass, 
                      remote_host, remote_port):
    """
    Crear y retornar un túnel SSH activo
    
    Uso:
        tunnel = create_ssh_tunnel('10.20.12.28', 5803, 'ubuntu', 'pass', 
                                   '127.0.0.1', 5432)
        # Usar tunnel.local_bind_port para conectar
        tunnel.stop()
    """
    tunnel = SSHTunnel(ssh_host, ssh_port, ssh_user, ssh_pass, 
                      remote_host, remote_port)
    tunnel.start()
    return tunnel