import paramiko
from config import LANCELOT_IP, WHITELIST

SSH_USER = "sshuser"
SSH_KEY = "/home/artoria/.ssh/id_ed25519"
PYTHON_PATH = "C:/Users/asmit/AppData/Local/Programs/Python/Python312/python.exe"


def run_on_lancelot(script_path, callback=None):
    if script_path not in WHITELIST:
        return "", f"Script '{script_path}' is not whitelisted. Access Denied."

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(LANCELOT_IP, username=SSH_USER, key_filename=SSH_KEY)

    stdin, stdout, stderr = client.exec_command(f"{PYTHON_PATH} {script_path}")

    output = []
    for line in stdout:
        line = line.strip()
        output.append(line)
        if callback:
            callback(line)

    errors = stderr.read().decode().strip()
    client.close()

    return "\n".join(output), errors


def ssh_exec(command):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(LANCELOT_IP, username=SSH_USER, key_filename=SSH_KEY)
    stdin, stdout, stderr = client.exec_command(command)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    client.close()
    return out, err


def ask_lancelot(prompt):
    full_prompt = f"Summarise or respond to the following in 3-5 sentences: {prompt}"
    command = f'"C:/Users/asmit/AppData/Local/Programs/Ollama/ollama.exe" run phi3:mini "{full_prompt}"'
    return ssh_exec(command)
