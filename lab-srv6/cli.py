# /// script
# dependencies = ["paramiko"]
# ///
"""Run IOS commands on lab nodes. Usage: uv run cli.py <node> "cmd1" "cmd2" ..."""
import sys, time, paramiko

PREFIX = "clab-iol-srv6-"
USER = PASSWORD = "admin"
READ_DELAY = 1.5
SLOW = 12
BUF = 65535


def run(node, cmds):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(PREFIX + node, username=USER, password=PASSWORD, look_for_keys=False,
              allow_agent=False, timeout=15)
    sh = c.invoke_shell()
    time.sleep(READ_DELAY)
    sh.recv(BUF)
    out = ""
    for cmd in ["terminal length 0"] + cmds:
        sh.send(cmd + "\n")
        time.sleep(SLOW if cmd.startswith(('ping','traceroute')) else READ_DELAY)
        while sh.recv_ready():
            out += sh.recv(BUF).decode(errors="replace")
            time.sleep(0.3)
    c.close()
    return out


if __name__ == "__main__":
    print(run(sys.argv[1], sys.argv[2:]))
