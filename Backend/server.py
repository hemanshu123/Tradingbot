# server.py
import os, sys, json, time, signal, platform, subprocess, pathlib
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = pathlib.Path(__file__).resolve().parent
RUNTIME = ROOT / "runtime"
RUNTIME.mkdir(parents=True, exist_ok=True)

F_SNAPSHOT = RUNTIME / "latest.json"
F_POSITION = RUNTIME / "open_position.json"
F_TRADES   = RUNTIME / "trades.json"
F_LOGS     = RUNTIME / "logs.jsonl"
F_OUT_LOG  = RUNTIME / "bot.out.log"
F_ERR_LOG  = RUNTIME / "bot.err.log"
F_PID      = RUNTIME / "bot.pid"

# paper trade files
F_PAPER_SNAP      = RUNTIME / "paper_snapshot.json"
F_PAPER_PID       = RUNTIME / "paper.pid"
F_PAPER_OUT       = RUNTIME / "paper.out.log"
F_PAPER_ERR       = RUNTIME / "paper.err.log"

BOT_FILE   = ROOT / "run_bot.py"
PAPER_FILE = ROOT / "paper_trade.py"
BOT_CWD    = ROOT
BOT_CMD    = [sys.executable, "-u", str(BOT_FILE)]
PAPER_CMD  = [sys.executable, "-u", str(PAPER_FILE)]

@asynccontextmanager
async def lifespan(_: FastAPI):
    start_paper()        # auto-start paper trader on server startup
    yield
    stop_paper()         # auto-stop paper trader on server shutdown

app = FastAPI(title="Trading Bot API", version="1.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

def read_json(path: pathlib.Path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def tail_text(path: pathlib.Path, max_bytes: int = 64_000) -> str:
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(-max_bytes, os.SEEK_END)
            data = f.read()
        return data.decode("utf-8", errors="replace")
    except:
        return ""

def is_running() -> bool:
    if not F_PID.exists():
        return False
    try:
        pid = int(F_PID.read_text().strip())
    except:
        return False
    try:
        # os.kill(pid, 0) works on Windows too (process existence check)
        os.kill(pid, 0)
        return True
    except:
        return False

class StartResponse(BaseModel):
    started: bool
    running: bool
    pid: Optional[int] = None
    error: Optional[str] = None
    stderr_tail: Optional[str] = None

@app.get("/status")
def status():
    return {
        "running": is_running(),
        "snapshot": read_json(F_SNAPSHOT, {}),
        "position": read_json(F_POSITION, {}),
        "trades_count": len(read_json(F_TRADES, []))
    }

@app.post("/start-bot", response_model=StartResponse)
def start_bot():
    # already running?
    if is_running():
        pid = int(F_PID.read_text().strip())
        return StartResponse(started=False, running=True, pid=pid)

    if not BOT_FILE.exists():
        return StartResponse(
            started=False, running=False, error=f"Bot file not found: {BOT_FILE}"
        )

    # open logs for append (don’t truncate)
    out_f = open(F_OUT_LOG, "ab", buffering=0)
    err_f = open(F_ERR_LOG, "ab", buffering=0)

    creationflags = 0
    if platform.system() == "Windows":
        # new process group so we can taskkill tree
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    try:
        proc = subprocess.Popen(
            BOT_CMD,
            cwd=str(BOT_CWD),
            stdout=out_f,
            stderr=err_f,
            creationflags=creationflags,
            shell=False
        )
    except Exception as e:
        # write error to err log and return
        err_f.write(str(e).encode("utf-8", errors="replace") + b"\n")
        out_f.close(); err_f.close()
        return StartResponse(started=False, running=False, error=str(e))

    # Save PID
    F_PID.write_text(str(proc.pid))

    # Give it a moment to import modules; then verify it’s still alive
    time.sleep(1.0)
    if proc.poll() is not None:
        # crashed immediately
        stderr_tail = tail_text(F_ERR_LOG, 32_000)
        try:
            F_PID.unlink(missing_ok=True)
        except:
            pass
        out_f.close(); err_f.close()
        return StartResponse(
            started=False,
            running=False,
            error="Bot exited immediately after start",
            stderr_tail=stderr_tail,
        )

    out_f.close(); err_f.close()
    return StartResponse(started=True, running=True, pid=proc.pid)

@app.post("/stop-bot")
def stop_bot():
    if not F_PID.exists():
        return {"stopped": False, "running": False, "message": "No PID file"}

    try:
        pid = int(F_PID.read_text().strip())
    except:
        F_PID.unlink(missing_ok=True)
        return {"stopped": False, "running": False, "message": "Bad PID file"}

    stopped = False
    err = None

    try:
        if platform.system() == "Windows":
            # Kill process tree
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, text=True)
            stopped = True
        else:
            os.kill(pid, signal.SIGTERM)
            # small grace period
            for _ in range(10):
                time.sleep(0.2)
                try:
                    os.kill(pid, 0)
                except:
                    stopped = True
                    break
            if not stopped:
                os.kill(pid, signal.SIGKILL)
                stopped = True
    except Exception as e:
        err = str(e)

    try:
        F_PID.unlink(missing_ok=True)
    except:
        pass

    return {"stopped": stopped, "running": False, "error": err}

@app.get("/fisher")
def fisher():
    return read_json(F_SNAPSHOT, {})

@app.get("/position")
def position():
    return read_json(F_POSITION, {})

@app.get("/trades")
def trades():
    return read_json(F_TRADES, [])

@app.get("/logs")
def logs(n: int = Query(default=200, ge=1, le=5000)):
    text = tail_text(F_LOGS, 128_000)
    lines = [l for l in text.splitlines() if l.strip()]
    js = []
    for l in lines[-n:]:
        try:
            js.append(json.loads(l))
        except:
            pass
    return js


# ── Paper trading helpers ────────────────────────────────────────────────────
def is_paper_running() -> bool:
    if not F_PAPER_PID.exists():
        return False
    try:
        pid = int(F_PAPER_PID.read_text().strip())
        os.kill(pid, 0)
        return True
    except:
        return False


# ── Paper trading endpoints ──────────────────────────────────────────────────
@app.post("/start-paper")
def start_paper():
    if is_paper_running():
        pid = int(F_PAPER_PID.read_text().strip())
        return {"started": False, "running": True, "pid": pid, "message": "Already running"}

    if not PAPER_FILE.exists():
        return {"started": False, "running": False, "error": f"paper_trade.py not found"}

    out_f = open(F_PAPER_OUT, "ab", buffering=0)
    err_f = open(F_PAPER_ERR, "ab", buffering=0)
    creationflags = 0
    if platform.system() == "Windows":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    try:
        proc = subprocess.Popen(
            PAPER_CMD, cwd=str(BOT_CWD),
            stdout=out_f, stderr=err_f,
            creationflags=creationflags, shell=False
        )
    except Exception as e:
        out_f.close(); err_f.close()
        return {"started": False, "running": False, "error": str(e)}

    F_PAPER_PID.write_text(str(proc.pid))
    time.sleep(1.0)

    if proc.poll() is not None:
        stderr_tail = tail_text(F_PAPER_ERR, 32_000)
        try: F_PAPER_PID.unlink(missing_ok=True)
        except: pass
        out_f.close(); err_f.close()
        return {"started": False, "running": False,
                "error": "Paper trader crashed on startup", "stderr_tail": stderr_tail}

    out_f.close(); err_f.close()
    return {"started": True, "running": True, "pid": proc.pid,
            "message": "Paper trading started — 10x and 20x virtual accounts running"}


@app.post("/stop-paper")
def stop_paper():
    if not F_PAPER_PID.exists():
        return {"stopped": False, "running": False, "message": "Not running"}
    try:
        pid = int(F_PAPER_PID.read_text().strip())
    except:
        F_PAPER_PID.unlink(missing_ok=True)
        return {"stopped": False, "running": False, "message": "Bad PID file"}

    stopped = False
    try:
        if platform.system() == "Windows":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, text=True)
            stopped = True
        else:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                time.sleep(0.2)
                try: os.kill(pid, 0)
                except: stopped = True; break
            if not stopped:
                os.kill(pid, signal.SIGKILL); stopped = True
    except Exception:
        pass
    try: F_PAPER_PID.unlink(missing_ok=True)
    except: pass
    return {"stopped": stopped, "running": False}


@app.get("/paper/status")
def paper_status():
    snap = read_json(F_PAPER_SNAP, {})
    return {
        "running":  is_paper_running(),
        "snapshot": snap,
    }


@app.get("/paper/trades")
def paper_trades(lev: int = Query(default=0)):
    """Get paper trades. lev=10 for 10x only, lev=20 for 20x only, lev=0 for both."""
    result = {}
    for l in [10, 20]:
        if lev == 0 or lev == l:
            f = RUNTIME / f"paper_{l}x_trades.json"
            d = read_json(f, {"equity": 100000, "trades": []})
            result[f"{l}x"] = d
    return result


@app.get("/paper/position")
def paper_position():
    """Get current open paper positions for both leverages."""
    result = {}
    for l in [10, 20]:
        f = RUNTIME / f"paper_{l}x_position.json"
        result[f"{l}x"] = read_json(f, {})
    return result


@app.get("/paper/summary")
def paper_summary():
    """Full P&L summary for both accounts."""
    snap = read_json(F_PAPER_SNAP, {})
    if not snap:
        result = {}
        for l in [10, 20]:
            f  = RUNTIME / f"paper_{l}x_trades.json"
            d  = read_json(f, {"equity": 100000, "trades": []})
            ts = d.get("trades", [])
            wins   = [t for t in ts if t.get("reason")=="TP"]
            losses = [t for t in ts if t.get("reason")=="SL"]
            result[f"{l}x"] = {
                "leverage":       l,
                "virtual_capital": 100000,
                "current_equity": d.get("equity", 100000),
                "total_profit_rs": round(sum(t.get("pnl_rs",0) for t in ts), 2),
                "growth_pct":     round((d.get("equity",100000)/100000-1)*100, 2),
                "total_trades":   len(ts),
                "wins":           len(wins),
                "losses":         len(losses),
                "win_rate_pct":   round(len(wins)/len(ts)*100,1) if ts else 0,
                "last_5_trades":  ts[-5:],
                "running":        is_paper_running(),
            }
        return result
    return {"10x": snap.get("10x", {}), "20x": snap.get("20x", {}),
            "running": is_paper_running(), "price": snap.get("price"),
            "time": snap.get("time")}


# uvicorn server:app --host 0.0.0.0 --port 8000

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=True)