import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import webbrowser
import time
import re
import json
import os
import sys
import random
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# --- KONFIGURACE ---
UIS_LOGIN_URL = "https://is.czu.cz/auth/"
OUTLOOK_URL = "https://outlook.office.com/mail/"
COFFEE_URL = "https://buymeacoffee.com/colorvant"

def get_config_path():
    """Vrátí cestu ke konfiguračnímu souboru vedle spustitelného souboru."""
    if getattr(sys, 'frozen', False):
        # Pokud běží jako .exe (PyInstaller)
        application_path = os.path.dirname(sys.executable)
    else:
        # Pokud běží jako .py skript
        application_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(application_path, "uis_config.json")

CONFIG_FILE = get_config_path()

# --- BARVY (DARK MODE) ---
COLOR_BG = "#1e1e1e"
COLOR_FRAME = "#2b2b2b"
COLOR_TEXT = "#ffffff"
COLOR_ENTRY_BG = "#3c3c3c"
COLOR_BTN_START = "#006400" 
COLOR_BTN_STOP = "#8b0000"  
COLOR_BTN_SCAN = "#005f9e"
COLOR_BTN_DOG = "#A0522D"
COLOR_ACCENT = "#FFD700"    
COLOR_INFO = "#4FC3F7"
COLOR_OUTLOOK = "#0078D4" 

class SniperApp:
    def __init__(self, root):
        self.root = root
        self.root.title("UIS Sniper - ČZU")
        self.root.geometry("700x980")
        self.root.resizable(True, True)
        self.root.configure(bg=COLOR_BG)
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        self.driver = None
        self.is_running = False
        self.thread = None
        
        self.saved_data = self.load_config()
        self.scanned_data = self.saved_data.get("scanned_data", {}) 
        self.all_subjects = self.saved_data.get("all_subjects", [])
        self.outlook_mode = tk.BooleanVar(value=False)

        style = ttk.Style()
        style.theme_use('clam') 
        
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabelframe", background=COLOR_BG, foreground=COLOR_TEXT)
        style.configure("TLabelframe.Label", background=COLOR_BG, foreground=COLOR_ACCENT)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 10))
        style.configure("TButton", padding=6, font=("Segoe UI", 10), background="#444", foreground="white", borderwidth=0)
        style.map("TButton", background=[('active', '#555')])
        style.configure("TCombobox", fieldbackground=COLOR_ENTRY_BG, background="#444", foreground=COLOR_TEXT, arrowcolor="white")
        style.map("TCombobox", fieldbackground=[('readonly', COLOR_ENTRY_BG)], selectbackground=[('readonly', '#555')])
        style.configure("TCheckbutton", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 10))

        main_canvas = tk.Canvas(root, bg=COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=main_canvas.yview)
        scrollable_frame = ttk.Frame(main_canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(
                scrollregion=main_canvas.bbox("all")
            )
        )

        main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)

        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            main_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        main_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        content_frame = ttk.Frame(scrollable_frame, padding="15")
        content_frame.pack(fill=tk.BOTH, expand=True)

        lbl_frame_login = ttk.LabelFrame(content_frame, text="1. Přihlašovací údaje (UIS)", padding="10")
        lbl_frame_login.pack(fill=tk.X, pady=5)

        ttk.Label(lbl_frame_login, text="Login:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.entry_user = tk.Entry(lbl_frame_login, width=25, bg=COLOR_ENTRY_BG, fg=COLOR_TEXT, insertbackground='white')
        self.entry_user.insert(0, self.saved_data.get("username", "")) 
        self.entry_user.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(lbl_frame_login, text="Heslo:").grid(row=0, column=2, sticky=tk.W, padx=5)
        self.entry_pass = tk.Entry(lbl_frame_login, width=25, show="*", bg=COLOR_ENTRY_BG, fg=COLOR_TEXT, insertbackground='white')
        self.entry_pass.grid(row=0, column=3, sticky=tk.W, padx=5)

        lbl_frame_scan = ttk.LabelFrame(content_frame, text="2. Automatické načtení (Doporučeno)", padding="10")
        lbl_frame_scan.pack(fill=tk.X, pady=5)
        
        lbl_scan_info = ttk.Label(lbl_frame_scan, text="Klikni pro načtení učitelů a předmětů + detekci tvé fakulty. Data se uloží pro příště.", wraplength=600)
        lbl_scan_info.pack(pady=(0, 5))
        
        self.btn_scan = tk.Button(lbl_frame_scan, text="🔄 Načíst data z UIS", bg=COLOR_BTN_SCAN, fg="white", font=("Segoe UI", 10, "bold"), command=self.start_scan)
        self.btn_scan.pack(fill=tk.X)

        lbl_frame_creator = ttk.LabelFrame(content_frame, text="3. Vybrat předmět ke sledování", padding="10")
        lbl_frame_creator.pack(fill=tk.X, pady=5)

        self.frame_detected = tk.Frame(lbl_frame_creator, bg=COLOR_BG)
        self.frame_detected.grid(row=1, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)
        
        tk.Label(self.frame_detected, text="Fakulta/Obor:", font=("Segoe UI", 9, "bold"), bg=COLOR_BG, fg=COLOR_TEXT).pack(side=tk.LEFT)
        saved_study_info = self.saved_data.get("study_info", "--- (Načte se po přihlášení) ---")
        self.lbl_study_info = tk.Label(self.frame_detected, text=saved_study_info, font=("Segoe UI", 9), bg=COLOR_BG, fg=COLOR_INFO)
        self.lbl_study_info.pack(side=tk.LEFT, padx=5)

        ttk.Label(lbl_frame_creator, text="Učitel:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.cb_teacher = ttk.Combobox(lbl_frame_creator, width=38)
        self.cb_teacher.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        self.cb_teacher.bind("<<ComboboxSelected>>", self.on_teacher_selected) 
        ttk.Label(lbl_frame_creator, text="(např. Jadrná)", font=("Segoe UI", 8), foreground="#888").grid(row=2, column=2, sticky=tk.W)

        ttk.Label(lbl_frame_creator, text="Předmět:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.cb_subject = ttk.Combobox(lbl_frame_creator, width=38) 
        self.cb_subject.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Label(lbl_frame_creator, text="(např. Teorie řízení)", font=("Segoe UI", 8), foreground="#888").grid(row=3, column=2, sticky=tk.W)

        if self.scanned_data:
            self.cb_teacher['values'] = sorted(list(self.scanned_data.keys()))
        if self.all_subjects:
            self.cb_subject['values'] = sorted(self.all_subjects)

        ttk.Label(lbl_frame_creator, text="Konkrétní datum:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
        self.entry_date = tk.Entry(lbl_frame_creator, width=15, bg=COLOR_ENTRY_BG, fg=COLOR_TEXT, insertbackground='white')
        self.entry_date.grid(row=4, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Label(lbl_frame_creator, text="(např. 22.01 nebo prázdné)", font=("Segoe UI", 8), foreground="#888").grid(row=4, column=2, sticky=tk.W)

        btn_add = tk.Button(lbl_frame_creator, text="⬇️ PŘIDAT DO SEZNAMU", bg="#444", fg="white", font=("Segoe UI", 9, "bold"), command=self.add_target_to_list)
        btn_add.grid(row=5, column=0, columnspan=3, pady=10, sticky=tk.EW)

        lbl_frame_targets = ttk.LabelFrame(content_frame, text="4. Seznam hlídaných termínů (Priorita shora dolů)", padding="10")
        lbl_frame_targets.pack(fill=tk.BOTH, expand=True, pady=5)
        
        container_list = tk.Frame(lbl_frame_targets, bg=COLOR_BG)
        container_list.pack(fill=tk.BOTH, expand=True)
        
        frame_list = tk.Frame(container_list, bg=COLOR_BG)
        frame_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar_list = tk.Scrollbar(frame_list)
        scrollbar_list.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.list_targets = tk.Listbox(frame_list, height=5, bg=COLOR_ENTRY_BG, fg=COLOR_TEXT, selectbackground=COLOR_ACCENT, selectforeground="black", font=("Consolas", 10), yscrollcommand=scrollbar_list.set)
        self.list_targets.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_list.config(command=self.list_targets.yview)
        
        frame_btns = tk.Frame(container_list, bg=COLOR_BG)
        frame_btns.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        
        tk.Button(frame_btns, text="⬆️", bg="#444", fg="white", width=4, command=self.move_up).pack(pady=2)
        tk.Button(frame_btns, text="⬇️", bg="#444", fg="white", width=4, command=self.move_down).pack(pady=2)
        tk.Button(frame_btns, text="🗑️", bg="#8b0000", fg="white", width=4, command=self.delete_item).pack(pady=(10, 2))

        saved_targets_str = self.saved_data.get("targets", "")
        if saved_targets_str:
            for line in saved_targets_str.split("\n"):
                if line.strip() and not line.startswith("#"):
                    self.list_targets.insert(tk.END, line.strip())

        lbl_frame_blacklist = ttk.LabelFrame(content_frame, text="5. Ignorované termíny (Blacklist)", padding="10")
        lbl_frame_blacklist.pack(fill=tk.X, pady=5)
        
        ttk.Label(lbl_frame_blacklist, text="Zde napiš co nechceš (odděl středníkem). Např: 24.01; 8:00; Novák").pack(anchor=tk.W)
        self.entry_blacklist = tk.Entry(lbl_frame_blacklist, bg=COLOR_ENTRY_BG, fg=COLOR_TEXT, insertbackground='white')
        self.entry_blacklist.pack(fill=tk.X, pady=2)
        self.entry_blacklist.insert(0, self.saved_data.get("blacklist", ""))

        lbl_frame_control = ttk.LabelFrame(content_frame, text="6. Ovládání", padding="10")
        lbl_frame_control.pack(fill=tk.X, pady=5)

        self.chk_outlook = ttk.Checkbutton(lbl_frame_control, text="📧 Aktivovat Outlook Watcher (Čekání na email)", variable=self.outlook_mode, onvalue=True, offvalue=False)
        self.chk_outlook.pack(anchor=tk.W, pady=(0, 5))
        ttk.Label(lbl_frame_control, text="Pozor: E-maily mají zpoždění. Vhodné jen pro nové termíny.", font=("Segoe UI", 8), foreground="gray").pack(anchor=tk.W, pady=(0, 10))

        btn_frame = ttk.Frame(lbl_frame_control)
        btn_frame.pack(fill=tk.X)

        self.btn_start = tk.Button(btn_frame, text="🚀 SPUSTIT SNIPER", bg=COLOR_BTN_START, fg="white", font=("Segoe UI", 12, "bold"), command=self.start_sniper)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Tlačítko pro Hlídacího psa
        self.btn_dog = tk.Button(btn_frame, text="🐶 NASTAVIT HLÍDACÍHO PSA", bg=COLOR_BTN_DOG, fg="white", font=("Segoe UI", 12, "bold"), command=self.start_dog_mode)
        self.btn_dog.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.btn_stop = tk.Button(btn_frame, text="🛑 ZASTAVIT", bg=COLOR_BTN_STOP, fg="white", font=("Segoe UI", 12, "bold"), command=self.stop_sniper, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        lbl_frame_log = ttk.LabelFrame(content_frame, text="Log (Průběh)", padding="10")
        lbl_frame_log.pack(fill=tk.BOTH, expand=True, pady=5)

        self.txt_log = scrolledtext.ScrolledText(lbl_frame_log, height=8, state='disabled', bg="#000000", fg="#00ff00", font=("Consolas", 9))
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        btn_coffee = tk.Button(content_frame, text="☕ Líbi se ti aplikace? Podpoř autora na Buy Me a Coffee", bg=COLOR_ACCENT, fg="black", font=("Segoe UI", 10, "bold"), command=self.open_coffee)
        btn_coffee.pack(fill=tk.X, pady=10)

    # --- PERSISTENCE ---
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_config(self):
        items = self.list_targets.get(0, tk.END)
        targets_str = "\n".join(items)
        blacklist_str = self.entry_blacklist.get().strip()
        study_info_text = self.lbl_study_info.cget("text")
        
        data = {
            "username": self.entry_user.get().strip(),
            "targets": targets_str,
            "blacklist": blacklist_str,
            "scanned_data": self.scanned_data,
            "all_subjects": self.all_subjects,
            "study_info": study_info_text
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    def on_close(self):
        self.save_config()
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
        self.root.destroy()

    def log(self, message):
        def _log():
            self.txt_log.config(state='normal')
            self.txt_log.insert(tk.END, f"{message}\n")
            self.txt_log.see(tk.END)
            self.txt_log.config(state='disabled')
        self.root.after(0, _log)

    def open_coffee(self):
        webbrowser.open(COFFEE_URL)

    def on_teacher_selected(self, event):
        selected_teacher = self.cb_teacher.get()
        if selected_teacher in self.scanned_data:
            subjects = self.scanned_data[selected_teacher]
            self.cb_subject['values'] = sorted(list(subjects))
            if subjects: self.cb_subject.current(0)
        else:
            self.cb_subject['values'] = sorted(self.all_subjects)

    def add_target_to_list(self):
        subj = self.cb_subject.get().strip()
        teach = self.cb_teacher.get().strip()
        date = self.entry_date.get().strip()
        
        if not subj:
            messagebox.showwarning("Chyba", "Musíš vybrat nebo napsat název předmětu!")
            return

        line = f"{subj};{date};{teach}"
        self.list_targets.insert(tk.END, line)
        
        self.cb_subject.set('')
        self.cb_teacher.set('')
        self.entry_date.delete(0, tk.END)
        self.save_config()

    def move_up(self):
        try:
            idxs = self.list_targets.curselection()
            if not idxs: return
            idx = idxs[0]
            if idx > 0:
                text = self.list_targets.get(idx)
                self.list_targets.delete(idx)
                self.list_targets.insert(idx-1, text)
                self.list_targets.selection_set(idx-1)
                self.save_config()
        except: pass

    def move_down(self):
        try:
            idxs = self.list_targets.curselection()
            if not idxs: return
            idx = idxs[0]
            if idx < self.list_targets.size() - 1:
                text = self.list_targets.get(idx)
                self.list_targets.delete(idx)
                self.list_targets.insert(idx+1, text)
                self.list_targets.selection_set(idx+1)
                self.save_config()
        except: pass

    def delete_item(self):
        try:
            idxs = self.list_targets.curselection()
            if not idxs: return
            self.list_targets.delete(idxs[0])
            self.save_config()
        except: pass

    def get_targets(self):
        raw_items = self.list_targets.get(0, tk.END)
        targets = []
        for line in raw_items:
            line = line.strip()
            if not line: continue
            parts = line.split(";")
            if len(parts) >= 1:
                subj = parts[0].strip()
                date = parts[1].strip() if len(parts) > 1 else ""
                filtr = parts[2].strip() if len(parts) > 2 else ""
                targets.append({"subject": subj, "date": date, "filter": filtr, "original_line": line})
        return targets

    def remove_target_from_gui(self, original_line):
        def _remove():
            try:
                items = self.list_targets.get(0, tk.END)
                if original_line in items:
                    idx = items.index(original_line)
                    self.list_targets.delete(idx)
                    self.save_config()
            except: pass
        self.root.after(0, _remove)

    def update_study_info_ui(self, info_text):
        def _update():
            self.lbl_study_info.config(text=info_text)
        self.root.after(0, _update)

    def start_scan(self):
        username = self.entry_user.get().strip()
        password = self.entry_pass.get().strip()
        
        if not username or not password:
            messagebox.showerror("Chyba", "Pro načtení dat musíš vyplnit přihlašovací údaje!")
            return
            
        self.btn_scan.config(state=tk.DISABLED, text="⏳ Načítám data...")
        self.log("--- SPUŠTĚNÍ SCANU DAT ---")
        threading.Thread(target=self.scan_process, args=(username, password)).start()

    def scan_process(self, username, password):
        driver = self.init_driver()
        if not driver:
            self.reset_scan_ui()
            return

        try:
            if not self.login_process(driver, username, password):
                driver.quit()
                self.reset_scan_ui()
                return

            self.navigate_to_exams(driver)
            self.detect_study_info(driver)
            
            self.log("🕵️ Analyzuji termíny...")
            
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "table_2")))
                
                rows = driver.find_elements(By.XPATH, "//table[@id='table_2']//tbody/tr")
                data_map = {}
                all_subjs = set()
                
                for row in rows:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) > 9: 
                        subj_text = cells[4].text.strip()
                        teach_text = cells[9].text.strip()
                        if subj_text:
                            all_subjs.add(subj_text)
                            if teach_text:
                                if teach_text not in data_map:
                                    data_map[teach_text] = set()
                                data_map[teach_text].add(subj_text)

                self.scanned_data = {k: sorted(list(v)) for k, v in data_map.items()}
                self.all_subjects = sorted(list(all_subjs))
                
                self.log(f"✅ Načteno: {len(data_map)} učitelů, {len(all_subjs)} předmětů.")
                
                self.root.after(0, self.save_config)
                self.root.after(0, self.update_comboboxes)
                
            except Exception as e:
                self.log(f"⚠️ Chyba při čtení tabulky: {e}")

        except Exception as e:
            self.log(f"🔴 Chyba scanu: {e}")
        finally:
            if driver: driver.quit()
            self.root.after(0, self.reset_scan_ui)

    def update_comboboxes(self):
        teachers = sorted(list(self.scanned_data.keys()))
        self.cb_teacher['values'] = teachers
        self.cb_subject['values'] = sorted(self.all_subjects)
        messagebox.showinfo("Hotovo", "Data z UIS byla načtena a uložena!")

    def reset_scan_ui(self):
        self.btn_scan.config(state=tk.NORMAL, text="🔄 Načíst data z UIS")

    def start_sniper(self):
        if self.is_running: return
        
        username = self.entry_user.get().strip()
        password = self.entry_pass.get().strip()
        targets = self.get_targets()

        if not username or not password:
            messagebox.showerror("Chyba", "Vyplň přihlašovací údaje!")
            return
        
        if not targets:
            messagebox.showerror("Chyba", "Seznam předmětů je prázdný!")
            return

        self.save_config()
        self.is_running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_dog.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_scan.config(state=tk.DISABLED)
        self.chk_outlook.config(state=tk.DISABLED) 
        
        use_outlook = self.outlook_mode.get()
        if use_outlook:
             self.log("--- SPUŠTĚNÍ V OUTLOOK REŽIMU 📧 ---")
             self.log("ℹ️ Přihlaste se v otevřeném okně do Outlooku.")
        else:
             self.log("--- SPUŠTĚNÍ V UIS REŽIMU 🚀 ---")
             self.log("ℹ️ Program pracuje. Nezasahuj do okna prohlížeče.")
        
        self.thread = threading.Thread(target=self.run_process, args=(username, password, targets, use_outlook))
        self.thread.daemon = True
        self.thread.start()

    def start_dog_mode(self):
        """Spustí režim pro nastavení hlídacího psa."""
        if self.is_running: return
        
        username = self.entry_user.get().strip()
        password = self.entry_pass.get().strip()
        targets = self.get_targets()

        if not username or not password:
            messagebox.showerror("Chyba", "Vyplň přihlašovací údaje!")
            return
        
        if not targets:
            messagebox.showerror("Chyba", "Seznam předmětů je prázdný!")
            return

        self.save_config()
        self.is_running = True
        self.btn_start.config(state=tk.DISABLED)
        self.btn_dog.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.btn_scan.config(state=tk.DISABLED)
        self.chk_outlook.config(state=tk.DISABLED) 
        
        self.log("--- SPUŠTĚNÍ REŽIMU HLÍDACÍ PES 🐶 ---")
        self.log("ℹ️ Program projde termíny a nastaví psa.")
        
        self.thread = threading.Thread(target=self.run_dog_process, args=(username, password, targets))
        self.thread.daemon = True
        self.thread.start()

    def stop_sniper(self):
        if not self.is_running: return
        self.is_running = False
        self.log("--- POŽADAVEK NA ZASTAVENÍ... ---")

    def reset_ui(self):
        self.is_running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_dog.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.btn_scan.config(state=tk.NORMAL)
        self.chk_outlook.config(state=tk.NORMAL)
        self.log("--- ZASTAVENO ---")

    def init_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            driver.maximize_window()
            return driver
        except Exception as e:
            self.log(f"CHYBA DRIVERU: {e}")
            return None

    def detect_study_info(self, driver):
        try:
            try:
                titulek_elem = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.ID, "titulek"))
                )
                full_text = titulek_elem.text
            except:
                full_text = driver.find_element(By.TAG_NAME, "body").text

            match = re.search(r"Studium\s*[-–—]?\s*(.+?)(?:,|$|\sobdobí)", full_text, re.IGNORECASE)
            
            if match:
                study_part = match.group(1).strip()
                study_part = study_part.split('[')[0].split('(')[0].strip()
                study_part = re.sub(r'\s+', ' ', study_part)
                self.update_study_info_ui(study_part)
                self.root.after(0, self.save_config)
            else:
                pass
        except Exception:
            pass

    def navigate_to_exams(self, driver):
        self.log("🧭 Naviguji na 'Přihlašování na zkoušky'...")
        try:
            if "moje_studium" not in driver.current_url:
                self.log("   -> Hledám 'Portál studenta'...")
                try:
                    portal_link = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Portál studenta"))
                    )
                    driver.execute_script("arguments[0].click();", portal_link)
                    time.sleep(2)
                except:
                    self.log("      ⚠️ Odkaz 'Portál studenta' nenalezen, zkusím 'Moje studium'...")
                    moje_studium = driver.find_element(By.XPATH, "//span[contains(text(), 'Moje studium')]")
                    driver.execute_script("arguments[0].click();", moje_studium)
                    time.sleep(2)

            self.detect_study_info(driver)

            self.log("   -> Hledám ikonu 'Přihlašování na zkoušky'...")
            try:
                xpath_icon = "//span[@data-sysid='prihlasovani-zkousky']/.."
                exam_link = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.XPATH, xpath_icon)))
                driver.execute_script("arguments[0].click();", exam_link)
                self.log("✅ Kliknuto na dlaždici zkoušek!")
                time.sleep(2)
                return True
            except:
                self.log("⚠️ Dlaždice nenalezena, zkouším text...")
                text_link = driver.find_element(By.PARTIAL_LINK_TEXT, "Přihlašování na zkoušky")
                driver.execute_script("arguments[0].click();", text_link)
                time.sleep(2)
                return True

        except Exception as e:
            self.log(f"⚠️ Navigace přes menu selhala ({e}).")
            self.log("🚀 Zkouším přímý skok na URL...")
            try:
                DIRECT_URL = "https://is.czu.cz/auth/student/terminy_seznam.pl?lang=cz"
                driver.get(DIRECT_URL)
                time.sleep(2)
                if "terminy_seznam" in driver.current_url:
                    self.log("✅ Přímý skok úspěšný!")
                    return True
                return False
            except Exception as e2:
                self.log(f"🔴 Chyba při navigaci: {e2}")
                return False

    def login_process(self, driver, username, password):
        self.log("🔵 Připojuji se k UIS...")
        driver.get(UIS_LOGIN_URL)
        time.sleep(2)

        try:
            cz_buttons = driver.find_elements(By.XPATH, "//a[contains(@href, 'lang=cz')]")
            if cz_buttons:
                self.log("🇨🇿 Přepínám na češtinu...")
                cz_buttons[0].click()
                time.sleep(2)
        except: pass

        try:
            self.log("🔍 Vybírám 'Login a heslo'...")
            login_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@data-sysid='email'] | //span[contains(text(), 'Login')]"))
            )
            login_btn.click()
            time.sleep(1)
        except: pass

        try:
            self.log("⌨️ Vyplňuji údaje...")
            user_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "credential_0")))
            pass_input = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "credential_1")))
            
            try:
                user_input.clear()
                user_input.send_keys(username)
            except:
                driver.execute_script("arguments[0].value = arguments[1];", user_input, username)
            
            try:
                pass_input.clear()
                pass_input.send_keys(password)
            except:
                driver.execute_script("arguments[0].value = arguments[1];", pass_input, password)
            
            time.sleep(0.5)
            
            try:
                submit = driver.find_element(By.ID, "login-btn")
                driver.execute_script("arguments[0].click();", submit)
            except:
                pass_input.send_keys(Keys.RETURN)
            
            time.sleep(5)
            
            if len(driver.find_elements(By.ID, "credential_1")) > 0:
                self.log("⚠️ CHYBA: Přihlášení asi selhalo.")
                return False
            else:
                self.log("✅ Přihlášeno úspěšně.")
                return True

        except Exception as e:
            self.log(f"🔴 Chyba při loginu: {e}")
            return False

    def check_outlook_for_email(self, driver, targets):
        try:
            for t in targets:
                subj = t["subject"]
                
                xpath = f"//div[@role='option' and contains(@aria-label, 'Unread') and (contains(@aria-label, 'Vypsání termínu') or contains(@aria-label, 'Uvolnění místa na termínu')) and contains(@aria-label, '{subj}')]"
                
                emails = driver.find_elements(By.XPATH, xpath)
                
                if emails:
                    self.log(f"📧 Nalezen nový e-mail pro: {subj}!")
                    return True
            
            return False
            
        except Exception:
            return False

    def run_process(self, username, password, targets, use_outlook=False):
        driver = self.init_driver()
        if not driver:
            self.root.after(0, self.reset_ui)
            return

        try:
            if use_outlook:
                self.log("🔵 Otevírám Outlook...")
                driver.get(OUTLOOK_URL)
                self.log("⏳ Čekám na ruční přihlášení do Outlooku...")
                
                try:
                    WebDriverWait(driver, 300).until(EC.presence_of_element_located((By.XPATH, "//div[@role='tree']")))
                    self.log("✅ Outlook načten! Sleduji příchozí poštu...")
                except TimeoutException:
                    self.log("❌ Nepodařilo se detekovat přihlášení do Outlooku včas.")
                    return

                while self.is_running:
                    if self.check_outlook_for_email(driver, targets):
                        self.log("🚀 DETEKOVÁN NOVÝ TERMÍN! Přepínám na UIS...")
                        break 
                    
                    time.sleep(10)
                    if self.is_running:
                        pass
                
                if not self.is_running: return

            if not self.login_process(driver, username, password):
                driver.quit()
                self.root.after(0, self.reset_ui)
                return

            self.navigate_to_exams(driver)
            
            blacklist_raw = self.entry_blacklist.get().strip()
            blacklist = [b.strip() for b in blacklist_raw.split(";") if b.strip()]

            cycle = 1
            while self.is_running:
                current_targets = self.get_targets()
                if not current_targets:
                    self.log("🎉 Všechny předměty úspěšně zapsány! Končím.")
                    self.is_running = False
                    break

                self.log(f"🔄 Cyklus {cycle}: Kontrola {len(current_targets)} termínů...")
                
                if self.is_running:
                    driver.refresh()
                    try:
                        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "table_2")))
                    except TimeoutException:
                        self.log("⚠️ Tabulka s termíny se nenačetla.")
                        if len(driver.find_elements(By.ID, "credential_0")) > 0 or len(driver.find_elements(By.XPATH, "//div[@data-sysid='email']")) > 0:
                            self.log("⚠️ Odhlášeno! Zkouším re-login...")
                            self.login_process(driver, username, password)
                            self.navigate_to_exams(driver)
                        continue

                target_found_in_this_cycle = False

                for t in current_targets:
                    if not self.is_running: break
                    
                    subj = t["subject"]
                    date = t["date"]
                    filtr = t["filter"]
                    original_line = t["original_line"]
                    
                    xpath = f"//table[@id='table_2']//tr[contains(., '{subj}')]"
                    if date: xpath += f"[contains(., '{date}')]"
                    if filtr: xpath += f"[contains(., '{filtr}')]"
                    
                    try:
                        rows = driver.find_elements(By.XPATH, xpath)
                        
                        if rows:
                            for row in rows:
                                row_text = row.text
                                blacklisted_item = next((b for b in blacklist if b in row_text), None)
                                if blacklisted_item:
                                    self.log(f"🚫 Ignoruji termín (blacklist '{blacklisted_item}'): {row_text[:40]}...") 
                                    continue

                                try:
                                    double_arrow_xpath = ".//a[contains(@href, 'prihlasit_ihned=1')] | .//span[@data-sysid='small-arrow-right-double']/.."
                                    register_btn = row.find_element(By.XPATH, double_arrow_xpath)
                                    
                                    info_msg = f"{subj} ({date if date else 'JAKÝKOLIV'} - {filtr})"
                                    try:
                                        found_date = re.search(r"\d{2}\.\d{2}\.", row_text).group(0)
                                        info_msg += f" [Datum: {found_date}]"
                                    except: pass

                                    self.log(f"🔥 NAŠEL JSEM VOLNO: {info_msg}")
                                    self.log("🖱️ KLIKÁM NA PŘIHLÁSIT!")
                                    
                                    driver.execute_script("arguments[0].click();", register_btn)
                                    
                                    try:
                                        WebDriverWait(driver, 3).until(EC.alert_is_present())
                                        driver.switch_to.alert.accept()
                                        self.log("✅ Alert potvrzen.")
                                    except: pass
                                    
                                    self.log(f"🎉 ZAPSÁNO: {info_msg}")
                                    self.remove_target_from_gui(original_line)
                                    
                                    target_found_in_this_cycle = True
                                    break 
                                except:
                                    pass 
                        
                        if target_found_in_this_cycle:
                            break 

                    except StaleElementReferenceException:
                        self.log("⚠️ Stránka se změnila. Přeskakuji cyklus.")
                        break
                
                if target_found_in_this_cycle:
                    time.sleep(2) 
                    continue

                wait_time = random.uniform(3, 9)
                time.sleep(wait_time)
                cycle += 1

        except Exception as e:
            self.log(f"🔴 KRITICKÁ CHYBA: {e}")
        finally:
            if driver: driver.quit()
            self.root.after(0, self.reset_ui)

    def run_dog_process(self, username, password, targets):
        driver = self.init_driver()
        if not driver:
            self.root.after(0, self.reset_ui)
            return

        try:
            if not self.login_process(driver, username, password):
                driver.quit()
                self.root.after(0, self.reset_ui)
                return

            self.navigate_to_exams(driver)
            
            blacklist_raw = self.entry_blacklist.get().strip()
            blacklist = [b.strip() for b in blacklist_raw.split(";") if b.strip()]

            self.log("🐶 Zahajuji nastavování hlídacích psů...")
            
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "table_2")))
            except:
                self.log("⚠️ Tabulka termínů nenalezena.")
                return

            current_targets = self.get_targets()
            
            for t in current_targets:
                if not self.is_running: break
                
                subj = t["subject"]
                date = t["date"]
                filtr = t["filter"]
                
                self.log(f"🔍 Hledám termín pro psa: {subj} ({date})")
                
                xpath = f"//table[@id='table_2']//tr[contains(., '{subj}')]"
                if date: xpath += f"[contains(., '{date}')]"
                if filtr: xpath += f"[contains(., '{filtr}')]"
                
                while self.is_running:
                    found_dog_action = False
                    
                    rows = driver.find_elements(By.XPATH, xpath)
                    
                    for row in rows:
                        row_text = row.text
                        
                        if any(b in row_text for b in blacklist):
                            continue

                        try:
                            dog_xpath = ".//a[.//span[@data-sysid='terminy-pes'] or .//use[contains(@href, 'glyph1561')]]"
                            dog_btn = row.find_element(By.XPATH, dog_xpath)
                            
                            self.log(f"   🐶 Našel jsem psa! Klikám...")
                            driver.execute_script("arguments[0].click();", dog_btn)
                            
                            time.sleep(2)
                            
                            self.log("   🔙 Vracím se na seznam...")
                            driver.back()
                            
                            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "table_2")))
                            
                            found_dog_action = True
                            self.log(f"   ✅ Pes nastaven pro: {subj}")
                            break 
                            
                        except:
                            pass
                    
                    if not found_dog_action:
                         break

            self.log("🏁 Hotovo. Hlídací psi nastaveni (kde to šlo).")
            messagebox.showinfo("Hotovo", "Proces nastavování psů dokončen.")
            self.is_running = False

        except Exception as e:
            self.log(f"🔴 CHYBA PSA: {e}")
        finally:
            if driver: driver.quit()
            self.root.after(0, self.reset_ui)

if __name__ == "__main__":
    root = tk.Tk()
    app = SniperApp(root)
    root.mainloop()
