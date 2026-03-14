import os
import shutil
import subprocess
import winreg

print("=== CapCut Full Cleaner ===\n")

# 1. Kill CapCut process
print("[1] Closing CapCut...")
subprocess.call("taskkill /f /im CapCut.exe", shell=True)

# 2. Try uninstall via WMIC
print("[2] Attempting uninstall...")
try:
    subprocess.call('wmic product where "name like \'%%CapCut%%\'" call uninstall', shell=True)
except:
    pass


# 3. Known folders
paths = [
    r"C:\Program Files\CapCut",
    r"C:\Program Files (x86)\CapCut",
    os.path.expandvars(r"%LOCALAPPDATA%\CapCut"),
    os.path.expandvars(r"%APPDATA%\CapCut"),
    os.path.expandvars(r"%TEMP%\CapCut"),
]

def delete_folder(path):
    if os.path.exists(path):
        try:
            shutil.rmtree(path, ignore_errors=True)
            print("Deleted:", path)
        except:
            print("Failed:", path)

print("[3] Removing main folders...")
for p in paths:
    delete_folder(p)


# 4. Search AppData for leftovers
print("[4] Scanning for leftovers...")

def search_delete(base):
    for root, dirs, files in os.walk(base):
        for d in dirs:
            if "capcut" in d.lower():
                full = os.path.join(root, d)
                try:
                    shutil.rmtree(full, ignore_errors=True)
                    print("Removed:", full)
                except:
                    pass

search_delete(os.path.expandvars(r"%LOCALAPPDATA%"))
search_delete(os.path.expandvars(r"%APPDATA%"))
search_delete(os.path.expandvars(r"%TEMP%"))


# 5. Delete registry keys
print("[5] Cleaning registry...")

reg_paths = [
    r"Software\CapCut",
    r"Software\Bytedance\CapCut"
]

for path in reg_paths:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        print("Deleted registry:", path)
    except:
        pass


# 6. Optional deep scan on C drive
print("[6] Deep scan (capcut folders)...")

for root, dirs, files in os.walk("C:\\"):
    for d in dirs:
        if "capcut" in d.lower():
            try:
                shutil.rmtree(os.path.join(root, d), ignore_errors=True)
                print("Deep removed:", os.path.join(root, d))
            except:
                pass

print("\n✅ CapCut removal completed.")
input("Press Enter to exit...")