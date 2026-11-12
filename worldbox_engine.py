import os
import time
import subprocess
import threading
import random
from PIL import Image, ImageDraw
import mss
import signal

class WorldboxEngine:
    def __init__(self, fps=30):
        self.fps = fps
        self.running = False
        self.xvfb_proc = None
        self.wb_proc = None
        self.ai_thread = None
        self.log_thread = None
        self.current_action = "Inicializando Motor..."
        self.mouse_x = 240
        self.mouse_y = 240
        
    def start(self):
        self.running = True
        
        # INYECCIÓN DE PARTIDA GUARDADA
        # Para evitar problemas de UI en 480x480, copiamos el save1 al autosave
        # para que WorldBox lo cargue automáticamente al arrancar.
        print("[WorldBox AI] Inyectando save1 en autosave para carga automática...")
        saves_dir = os.path.expanduser("~/.config/unity3d/mkarpenko/WorldBox/saves/")
        save1 = os.path.join(saves_dir, "save1")
        autosaves_dir = os.path.expanduser("~/.config/unity3d/mkarpenko/WorldBox/autosaves/")
        
        try:
            import shutil
            import glob
            
            os.makedirs(autosaves_dir, exist_ok=True)
            existing_saves = glob.glob(os.path.join(autosaves_dir, "*"))
            
            # Solo inyectamos el save1 original si la carpeta de autoguardado está vacía.
            # Si ya hay partidas, dejamos que el juego cargue la última automáticamente.
            if not existing_saves and os.path.exists(save1):
                timestamp = str(int(time.time()))
                target = os.path.join(autosaves_dir, timestamp)
                shutil.copytree(save1, target)
                print(f"[WorldBox AI] Carpeta vacía, save1 inyectado en {target}")
            else:
                print(f"[WorldBox AI] Autoguardados previos detectados. Conservando progreso de la IA.")
                
        except Exception as e:
            print(f"[WorldBox AI] Error al gestionar autoguardados: {e}")
        
        # Limpiar cualquier rastro de Xvfb zombie
        subprocess.run(["killall", "-9", "Xvfb"], stderr=subprocess.DEVNULL)
        subprocess.run(["rm", "-f", "/tmp/.X99-lock"], stderr=subprocess.DEVNULL)
        subprocess.run(["rm", "-f", "/tmp/.X11-unix/X99"], stderr=subprocess.DEVNULL)
        
        # Iniciar Monitor Fantasma a 480x480 (Resolución nativa de la pantallita)
        print("[WorldBox] Iniciando Xvfb en :99 a 480x480...")
        self.xvfb_proc = subprocess.Popen(["Xvfb", ":99", "-screen", "0", "480x480x24"])
        time.sleep(2) # Esperar a que el servidor X inicie completamente
        
        # Iniciar WorldBox atrapado en :99
        print("[WorldBox] Iniciando binario de Unity sin audio...")
        env = os.environ.copy()
        env["DISPLAY"] = ":99"
        if "WAYLAND_DISPLAY" in env:
            del env["WAYLAND_DISPLAY"]
            
        # Desactivar Audio forzando drivers nulos/falsos y rompiendo la conexión
        env["PULSE_SERVER"] = "tcp:127.0.0.1:9999" # Puerto cerrado, fallará sí o sí
        env["ALSA_CARD"] = "99" # Tarjeta inexistente
        env["SDL_AUDIODRIVER"] = "dummy"
        env["ALSO_NONE"] = "1"
        env["FMOD_ALSA_DEVICE"] = "null"
        env["FMOD_OUTPUTTYPE"] = "NOSOUND" # Mute FMOD completely
        
        # Esperar a que Steam esté corriendo para evitar que el juego falle al arrancar con el PC
        print("[WorldBox] Esperando a que Steam inicie...")
        for _ in range(60):
            try:
                output = subprocess.check_output(["pgrep", "steam"])
                if output:
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(1)
            
        # Forzamos resolución 480x480
        cmd = [
            "./worldbox/run_bepinex.sh", 
            "-screen-width", "480", 
            "-screen-height", "480",
            "-screen-fullscreen", "0"
        ]
        self.wb_proc = subprocess.Popen(cmd, env=env)
        
        # Iniciar Capturador con reintentos
        self.sct = None
        for i in range(5):
            try:
                import mss
                self.sct = mss.mss(display=":99")
                break
            except Exception as e:
                with open("/tmp/worldbox_debug.log", "a") as f:
                    f.write(f"[{time.ctime()}] Esperando a Xvfb... {e}\n")
                print(f"[WorldBox AI] Esperando a Xvfb... {e}")
                time.sleep(1)
                
        if not self.sct:
            with open("/tmp/worldbox_debug.log", "a") as f:
                f.write(f"[{time.ctime()}] FATAL: No se pudo conectar a Xvfb en :99\n")
            print("[WorldBox] FATAL: No se pudo conectar a Xvfb en :99")
            self.running = False
            return
            
        # Iniciar IA Poltergeist
        self.ai_thread = threading.Thread(target=self.ai_loop)
        self.ai_thread.daemon = True
        self.ai_thread.start()
        
        # Iniciar Logger de 1 segundo
        self.log_thread = threading.Thread(target=self.logger_loop)
        self.log_thread.daemon = True
        self.log_thread.start()

    def logger_loop(self):
        import os, time, glob
        from PIL import Image
        log_dir = "/tmp/wb_logs"
        os.makedirs(log_dir, exist_ok=True)
        while self.running:
            try:
                now = int(time.time())
                # Mantener solo los últimos 60 segundos
                old_files = glob.glob(f"{log_dir}/*")
                for f in old_files:
                    if os.path.getmtime(f) < time.time() - 60:
                        os.remove(f)
                        
                # Guardar txt con la acción actual
                with open(os.path.join(log_dir, f"{now}.txt"), "w") as f:
                    f.write(self.current_action)
                    
                # Guardar captura con el cursor dibujado
                if self.sct:
                    monitor = self.sct.monitors[1]
                    sct_img = self.sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    
                    # --- Dibujar el cursor ---
                    try:
                        env = os.environ.copy()
                        env["DISPLAY"] = ":99"
                        out = subprocess.check_output(["xdotool", "getmouselocation", "--shell"], env=env).decode()
                        mx, my = 0, 0
                        for line in out.splitlines():
                            if line.startswith("X="): mx = int(line.split("=")[1])
                            if line.startswith("Y="): my = int(line.split("=")[1])
                        
                        draw = ImageDraw.Draw(img)
                        r = 5
                        draw.ellipse((mx-r, my-r, mx+r, my+r), fill="red", outline="white")
                        draw.line((mx-10, my, mx+10, my), fill="white", width=2)
                        draw.line((mx, my-10, mx, my+10), fill="white", width=2)
                    except Exception as ex:
                        pass
                        
                    img.save(os.path.join(log_dir, f"{now}.png"))
            except Exception as e:
                print(f"[Logger] Error: {e}")
            time.sleep(1.0)

    def xdo(self, *args):
        env = os.environ.copy()
        env["DISPLAY"] = ":99"
        subprocess.run(["xdotool"] + list(args), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # Guardar captura extra inmediatamente si es un clic, para ver dónde hizo clic
        if "click" in args and self.sct:
            try:
                import time
                now = int(time.time())
                monitor = self.sct.monitors[1]
                sct_img = self.sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
                # --- Dibujar el cursor sacando X,Y de los argumentos ---
                try:
                    mx, my = 240, 240 # Centro por defecto
                    args_list = list(args)
                    if "mousemove" in args_list:
                        idx = args_list.index("mousemove")
                        mx = int(args_list[idx+1])
                        my = int(args_list[idx+2])
                        self.mouse_x = mx
                        self.mouse_y = my
                    
                    draw = ImageDraw.Draw(img)
                    r = 5
                    draw.ellipse((mx-r, my-r, mx+r, my+r), fill="yellow", outline="red")
                    draw.line((mx-10, my, mx+10, my), fill="red", width=2)
                    draw.line((mx, my-10, mx, my+10), fill="red", width=2)
                except Exception as ex:
                    print(f"[Logger] Error dibujando cursor: {ex}")
                
                log_dir = "/tmp/wb_logs"
                os.makedirs(log_dir, exist_ok=True)
                img.save(os.path.join(log_dir, f"click_{now}.png"))
                with open(os.path.join(log_dir, f"click_{now}.txt"), "w") as f:
                    f.write(self.current_action + " (CLIC REALIZADO)")
            except Exception as e:
                print(f"[Logger] Error guardando clic: {e}")

    def capture_debug(self, prefix):
        try:
            import mss
            from PIL import Image
            import os, time
            os.makedirs("/tmp/wb_screenshots", exist_ok=True)
            # Limpiar capturas antiguas si hay más de 20
            files = sorted(os.listdir("/tmp/wb_screenshots"))
            if len(files) > 20:
                os.remove(f"/tmp/wb_screenshots/{files[0]}")
                
            with mss.mss(display=":99") as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img.save(f"/tmp/wb_screenshots/{prefix}_{int(time.time())}.png")
        except Exception as e:
            print(f"[WorldBox AI] Error al capturar log visual: {e}")



    def send_api_command(self, action, x, y, extra_params=None):
        import requests
        try:
            payload = {"action": action, "x": x, "y": y}
            if extra_params:
                payload.update(extra_params)
            requests.post("http://127.0.0.1:8085/", json=payload, timeout=2.0)
        except Exception as e:
            print(f"[API] Error enviando comando: {e}")

    def ai_loop(self):
        time.sleep(15) # Esperar a que el juego cargue completamente
        self.capture_debug("00_antes_de_cerrar_popup")
        
        # 1. Cerrar Menú de Bienvenida
        print("[WorldBox AI] Intentando cerrar menú de bienvenida...")
        self.xdo("mousemove", "10", "10", "click", "1")
        time.sleep(0.5)
        
        time.sleep(1.0)
        self.capture_debug("01_despues_de_cerrar_popup")
        
        # 2. Cargar el mundo (Aún necesitamos usar Xdotool para UI inicial porque la UI no se expone a Mod tan fácil, o sí?)
        # Pero podemos usar Xdotool para el click, es fijo.
        print("[WorldBox AI] Seleccionando Guardados...")
        self.xdo("mousemove", "240", "390", "click", "1")
        time.sleep(2.0)
        
        print("[WorldBox AI] Seleccionando Slot 1...")
        self.xdo("mousemove", "145", "290", "click", "1")
        time.sleep(2.0)

        print("[WorldBox AI] Cargar Mundo...")
        self.xdo("mousemove", "240", "400", "click", "1")
        time.sleep(2.0)

        print("[WorldBox AI] Confirmar Carga...")
        # Clic en el botón rojo CARGAR inferior izquierdo
        self.xdo("mousemove", "160", "405", "click", "1")
        time.sleep(4.0)
            
        self.capture_debug("01_5_despues_de_cargar")
        print("[WorldBox AI] Esperando a que el mapa termine de renderizarse...")
        time.sleep(3.0) 

        print("[WorldBox AI] Mapa cargado correctamente. Iniciando bucle de IA (API)...")
        time.sleep(1.0)
        
        # Ocultar la interfaz mediante API
        print("[WorldBox AI] Minimizando interfaz y ajustando zoom (API)...")
        self.send_api_command("hide_ui", 240, 240)
        time.sleep(0.5)
        # Menor valor = más zoom (acercar). Ajustamos un pelín más de zoom a 31.0.
        self.send_api_command("zoom_set", 240, 240, {"level": "30.0"})
        time.sleep(0.5)
        self.send_api_command("show_kingdoms", 240, 240)
        time.sleep(0.5)
        
        print("[WorldBox AI] Inyectando minerales y poblaciones iniciales...")
        # 4 toques de oro
        for _ in range(4):
            self.send_api_command("gold_ore", random.randint(150, 330), random.randint(150, 330))
            time.sleep(0.1)
        # 3 toques de hierro
        for _ in range(3):
            self.send_api_command("iron_ore", random.randint(150, 330), random.randint(150, 330))
            time.sleep(0.1)
            
        # Esquina Superior Izquierda: Humanos
        for _ in range(10): 
            self.send_api_command("spawn", random.randint(100, 150), random.randint(100, 150), {"type": "human"})
            time.sleep(0.1)
        # Esquina Inferior Derecha: Humanos
        for _ in range(10): 
            self.send_api_command("spawn", random.randint(330, 380), random.randint(330, 380), {"type": "human"})
            time.sleep(0.1)
        # Esquina Superior Derecha: Orcos
        for _ in range(10): 
            self.send_api_command("spawn", random.randint(330, 380), random.randint(100, 150), {"type": "orc"})
            time.sleep(0.1)
        # Esquina Inferior Izquierda: Duendes (elf)
        for _ in range(10): 
            self.send_api_command("spawn", random.randint(100, 150), random.randint(330, 380), {"type": "elf"})
            time.sleep(0.1)
        
        last_civ_time = 0
        last_species_time = 0
        last_save_time = time.time()
        next_disaster_time = time.time() + random.randint(600, 1800) # Evento destructivo aleatorio entre 10 y 30 minutos
        
        species = ["human", "elf", "orc", "dwarf", "sheep", "cow", "chicken"]
        disasters = ["earthquake", "lightning", "meteorite", "tornado", "tnt", "grenade", "napalm_bomb", "antimatter_bomb", "nuke"]
        
        while self.running:
            now = time.time()
            
            # Autoguardado cada 5 minutos (300 segundos)
            if now - last_save_time > 300:
                print("[WorldBox AI] Realizando autoguardado de 5 minutos...")
                self.send_api_command("save", 240, 240)
                last_save_time = now
            
            # Evento: Generación de Especies (Cada 5-12 minutos)
            if now - last_species_time > random.randint(300, 720):
                self.current_action = "Generación de Especies (API)"
                print("[WorldBox AI] Iniciando generación de especies (API)...")
                specie = random.choice(species)
                spawns = random.randint(3, 6)
                
                for _ in range(spawns):
                    tx = random.randint(100, 380)
                    ty = random.randint(100, 380)
                    self.send_api_command("spawn", tx, ty, {"type": specie})
                    time.sleep(0.2)
                    
                last_species_time = now
                
            # Evento: Desastre Aleatorio Mayor (Cada 10-30 minutos)
            if now > next_disaster_time:
                self.current_action = "Desastre Mayor Aleatorio (API)"
                disaster = random.choice(disasters)
                tx = random.randint(150, 330)
                ty = random.randint(150, 330)
                print(f"[WorldBox AI] ⚠️ EVENTO ALEATORIO: ¡Lanzando {disaster} en {tx},{ty}!")
                self.send_api_command(disaster, tx, ty)
                
                # Ocasionalmente tirar más de uno
                if random.random() < 0.3:
                    time.sleep(1.0)
                    self.send_api_command(disaster, random.randint(150, 330), random.randint(150, 330))
                
                # Programar próximo desastre
                next_disaster_time = time.time() + random.randint(600, 1800)
                
            # Comportamiento Pasivo (Mover la cámara y mirar)
            self.current_action = "Inactivo: Explorando cámara libremente"
            self.xdo("mousemove", "240", "240", "mousedown", "3") # Clic derecho
            self.xdo("mousemove_relative", "--", str(random.randint(-100, 100)), str(random.randint(-100, 100)))
            self.xdo("mouseup", "3")
            time.sleep(random.uniform(5.0, 10.0))

    def get_frame(self):
        if not self.running or not getattr(self, 'sct', None):
            return Image.new('RGB', (480, 480), (0,0,0))
            
        try:
            # Capturar el monitor 1 (el único que hay en Xvfb)
            monitor = self.sct.monitors[1]
            sct_img = self.sct.grab(monitor)
            # mss devuelve BGRA, convertimos a RGB para Pillow
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Dibujar el "ratón" virtual para el stream
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            r = 5
            mx, my = self.mouse_x, self.mouse_y
            draw.ellipse((mx-r, my-r, mx+r, my+r), outline="yellow", width=2)
            draw.line((mx-10, my, mx+10, my), fill="red", width=2)
            draw.line((mx, my-10, mx, my+10), fill="red", width=2)
            
            return img
        except Exception as e:
            # Si el juego todavía no ha creado la ventana o hay fallo
            return Image.new('RGB', (480, 480), (0,0,0))

    def is_alive(self):
        if not self.running:
            return False
        if getattr(self, 'wb_proc', None):
            return self.wb_proc.poll() is None
        return True

    def stop(self):
        self.running = False
        print("[WorldBox] Matando procesos...")
        if self.wb_proc:
            self.wb_proc.terminate()
            try:
                self.wb_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.wb_proc.kill()
        
        if hasattr(self, 'sct') and self.sct:
            try:
                self.sct.close()
            except Exception:
                pass
                
        if self.xvfb_proc:
            self.xvfb_proc.terminate()
            try:
                self.xvfb_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.xvfb_proc.kill()
