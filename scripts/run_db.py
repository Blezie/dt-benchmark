#!/usr/bin/env python3
import argparse, subprocess, sys, os, time, re
from pathlib import Path
import urllib.request
import yaml

SERVICES = ("postgres", "mongodb", "influxdb")

def run(cmd, check=True, capture=False):
    print(">", " ".join(cmd))
    if capture:
        p = subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return p.returncode, p.stdout, p.stderr
    subprocess.run(cmd, check=check)

def read_env(path: Path) -> dict:
    if not path.exists(): return {}
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env

def write_env(cfg, root):
    env_path = root / ".env"
    current = read_env(env_path)
    imgs = cfg.get("images", {})
    conts = cfg.get("metrics", {}).get("containers", {})
    current.update({
        "POSTGRES_IMAGE": imgs.get("postgres", ""),
        "MONGODB_IMAGE":  imgs.get("mongodb", ""),
        "INFLUXDB_IMAGE": imgs.get("influxdb", ""),
        "POSTGRES_NAME":  conts.get("postgres", {}).get("name", "dtbench-pg"),
        "MONGODB_NAME":   conts.get("mongodb", {}).get("name", "dtbench-mongo"),
        "INFLUXDB_NAME":  conts.get("influxdb", {}).get("name", "dtbench-influx"),
    })
    (root / ".env").write_text("\n".join(f"{k}={v}" for k,v in current.items() if v) + "\n", encoding="utf-8")
    print("[ok] wrote .env")

def wait_influx_ready(timeout_s=90) -> bool:
    url = "http://localhost:8181/health"
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status in (200, 401): return True
        except urllib.error.HTTPError as e:
            if e.code in (200, 401): return True
        except Exception:
            pass
        time.sleep(1)
    return False

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
def extract_token(text: str) -> str:
    clean = ANSI.sub("", text or "")
    m = re.search(r"(apiv3_[A-Za-z0-9\-_]+)", clean)
    return m.group(1) if m else ""

def ensure_influx_token(root, container_name):
    env_path = root / ".env"
    if "INFLUX_TOKEN" in read_env(env_path):
        print("[ok] INFLUX_TOKEN exists, skip")
        return

    print("[..] waiting for Influx @ /health (200/401)")
    if not wait_influx_ready(90):
        print("[warn] influx not ready; skip token")
        return

    rc, out, err = run(["docker","exec","-i",container_name,"influxdb3","create","token","--admin"], capture=True)
    token = extract_token(out) or extract_token(err)
    if token.startswith("apiv3_"):
        with env_path.open("a", encoding="utf-8") as f:
            f.write(f"INFLUX_TOKEN={token}\n")
        print(f"[ok] stored INFLUX_TOKEN ({token[:6]}...)")
        return

    if "401" in (out + err):
        print("[warn] InfluxDB returned 401 creating admin token. This usually means an operator token already exists for this data dir.")
        print("      Either set INFLUX_TOKEN manually in .env, or reset the data volume to start fresh:")
        print("      docker compose stop influxdb && docker volume rm dt-benchmark_dtbench_influx && python scripts/run_db.py up")
        print("--- stdout ---\n" + (out.strip() or "(empty)"))
        print("--- stderr ---\n" + (err.strip() or "(empty)"))
        return

    print("[warn] could not parse token from output; raw stdout/stderr:")
    print("--- stdout ---\n" + (out.strip() or "(empty)"))
    print("--- stderr ---\n" + (err.strip() or "(empty)"))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["up","down","restart","status","logs"])
    p.add_argument("-c","--config", default="workload/config.yaml")
    a = p.parse_args()

    root = Path(__file__).resolve().parent.parent
    if not (root / "docker-compose.yml").exists():
        sys.exit("missing docker-compose.yml")
    cfg_path = root / a.config
    if not cfg_path.exists():
        sys.exit(f"missing {cfg_path}")

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    db = cfg.get("db")
    if db not in SERVICES:
        sys.exit(f"invalid db: {db}")

    os.chdir(root)
    write_env(cfg, root)

    others = [s for s in SERVICES if s != db]
    if a.action == "up":
        run(["docker","compose","stop", *others], check=False)
        run(["docker","compose","up","-d", db])
        if db == "influxdb":
            name = cfg.get("metrics", {}).get("containers", {}).get("influxdb", {}).get("name", "dtbench-influx")
            ensure_influx_token(root, name)
    elif a.action == "down":
        run(["docker","compose","stop", db], check=False)
    elif a.action == "restart":
        run(["docker","compose","stop", *others], check=False)
        run(["docker","compose","restart", db])
    elif a.action == "status":
        run(["docker","compose","ps"])
    elif a.action == "logs":
        run(["docker","compose","logs","-f","--tail","100", db], check=False)

if __name__ == "__main__":
    main()