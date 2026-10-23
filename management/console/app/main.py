"""ROS Console - fleet management server.

Two interfaces live here:

* a small JSON API that ros-agent talks to (enroll, heartbeat, policy), and
* a web UI an administrator uses to see the fleet and edit desktop policy.

They share one database and one policy model, so what the UI previews is
byte-for-byte what the agent writes.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__, db, policy as policy_mod

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ADMIN_PASSWORD = os.environ.get("ROS_ADMIN_PASSWORD", "ros-admin")
SESSION_COOKIE = "ros_session"
SESSION_MAX_AGE = 12 * 3600

app = FastAPI(title="ROS Console", version=__version__, docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# --------------------------------------------------------------------------- #
# Startup
# --------------------------------------------------------------------------- #
@app.on_event("startup")
def startup() -> None:
    db.init_db(policy_mod.default_policy())
    if not db.get_setting("enrollment_key"):
        key = os.environ.get("ROS_ENROLLMENT_KEY") or secrets.token_urlsafe(24)
        db.set_setting("enrollment_key", key)
        db.log_event("console", "generated a new enrollment key")


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def current_session(request: Request) -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    row = db.query_one("SELECT token, created_at FROM sessions WHERE token = ?", (token,))
    if not row:
        return None
    if int(time.time()) - row["created_at"] > SESSION_MAX_AGE:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        return None
    return token


def require_admin(request: Request) -> str:
    token = current_session(request)
    if not token:
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return token


def authenticate_device(request: Request, device_id: str) -> Dict[str, Any]:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = header.split(" ", 1)[1].strip()

    device = db.query_one("SELECT * FROM devices WHERE id = ?", (device_id,))
    if not device or not hmac.compare_digest(device["token_hash"], hash_token(token)):
        # Same answer for "no such device" and "wrong token": an unauthenticated
        # caller should not be able to enumerate device IDs.
        raise HTTPException(status_code=401, detail="authentication failed")
    return dict(device)


# --------------------------------------------------------------------------- #
# Device API
# --------------------------------------------------------------------------- #
@app.get("/api/v1/health")
def health() -> Dict[str, Any]:
    devices = db.query_one("SELECT COUNT(*) AS n FROM devices")["n"]
    return {"status": "ok", "version": __version__, "devices": devices}


@app.post("/api/v1/enroll")
async def enroll(request: Request) -> JSONResponse:
    body = await request.json()
    expected = db.get_setting("enrollment_key")
    supplied = str(body.get("enrollment_key", ""))
    if not expected or not hmac.compare_digest(expected, supplied):
        db.log_event("security", "rejected enrollment from %s" % (request.client.host if request.client else "?"))
        raise HTTPException(status_code=403, detail="invalid enrollment key")

    machine_id = str(body.get("machine_id") or "").strip()
    hostname = str(body.get("hostname") or "unknown").strip()
    if not machine_id:
        raise HTTPException(status_code=400, detail="machine_id is required")

    inventory = body.get("inventory") or {}
    token = secrets.token_urlsafe(32)
    now = int(time.time())

    existing = db.query_one("SELECT id FROM devices WHERE machine_id = ?", (machine_id,))
    if existing:
        # Re-enrollment: same machine, new token. The device keeps its history
        # and its group assignment.
        device_id = existing["id"]
        db.execute(
            "UPDATE devices SET hostname = ?, token_hash = ?, inventory = ?,"
            " last_seen = ?, policy_revision = 0, policy_status = 'pending' WHERE id = ?",
            (hostname, hash_token(token), json.dumps(inventory), now, device_id),
        )
        db.log_event("enroll", "re-enrolled %s" % hostname, device_id)
    else:
        device_id = secrets.token_hex(8)
        default_group = db.query_one("SELECT id FROM groups WHERE is_default = 1")
        db.execute(
            "INSERT INTO devices (id, hostname, machine_id, token_hash, group_id,"
            " enrolled_at, last_seen, agent_version, inventory)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                device_id,
                hostname,
                machine_id,
                hash_token(token),
                default_group["id"] if default_group else None,
                now,
                now,
                str(inventory.get("agent_version", "")),
                json.dumps(inventory),
            ),
        )
        db.log_event("enroll", "enrolled %s" % hostname, device_id)

    return JSONResponse({"device_id": device_id, "token": token})


@app.post("/api/v1/devices/{device_id}/heartbeat")
async def heartbeat(device_id: str, request: Request) -> Dict[str, Any]:
    device = authenticate_device(request, device_id)
    body = await request.json()
    inventory = body.get("inventory") or {}

    db.execute(
        "UPDATE devices SET last_seen = ?, inventory = ?, agent_version = ?,"
        " hostname = ? WHERE id = ?",
        (
            int(time.time()),
            json.dumps(inventory),
            str(body.get("agent_version", "")),
            str(inventory.get("hostname") or device["hostname"]),
            device_id,
        ),
    )

    group = device_group(device)
    return {
        "policy_revision": group["revision"] if group else 0,
        "policy_name": group["name"] if group else None,
        "server_time": int(time.time()),
    }


def device_group(device: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    row = None
    if device.get("group_id"):
        row = db.query_one("SELECT * FROM groups WHERE id = ?", (device["group_id"],))
    if row is None:
        row = db.query_one("SELECT * FROM groups WHERE is_default = 1")
    return dict(row) if row else None


@app.get("/api/v1/devices/{device_id}/policy")
def get_policy(device_id: str, request: Request) -> Dict[str, Any]:
    device = authenticate_device(request, device_id)
    group = device_group(device)
    if not group:
        return {"name": "none", "revision": 0, "dconf": {}, "locks": []}
    return policy_mod.compile_policy(
        group["name"], group["revision"], json.loads(group["policy"])
    )


@app.post("/api/v1/devices/{device_id}/policy-result")
async def policy_result(device_id: str, request: Request) -> Dict[str, str]:
    authenticate_device(request, device_id)
    body = await request.json()
    status = str(body.get("status", "unknown"))
    revision = int(body.get("revision", 0))

    db.execute(
        "UPDATE devices SET policy_revision = ?, policy_status = ? WHERE id = ?",
        (revision, status, device_id),
    )
    db.log_event(
        "policy",
        "revision %d %s: %s" % (revision, status, json.dumps(body.get("detail", {}))),
        device_id,
    )
    return {"status": "recorded"}


# --------------------------------------------------------------------------- #
# Web UI
# --------------------------------------------------------------------------- #
def render(request: Request, template: str, **context: Any) -> HTMLResponse:
    context.setdefault("version", __version__)
    context.setdefault("default_password_in_use", ADMIN_PASSWORD == "ros-admin")
    context["request"] = request
    return templates.TemplateResponse(template, context)


def seen_label(last_seen: Optional[int]) -> str:
    if not last_seen:
        return "never"
    delta = int(time.time()) - last_seen
    if delta < 90:
        return "just now"
    if delta < 3600:
        return "%d min ago" % (delta // 60)
    if delta < 86400:
        return "%d h ago" % (delta // 3600)
    return "%d d ago" % (delta // 86400)


def device_rows() -> list:
    rows = db.query(
        "SELECT d.*, g.name AS group_name, g.revision AS group_revision"
        " FROM devices d LEFT JOIN groups g ON g.id = d.group_id"
        " ORDER BY d.last_seen DESC NULLS LAST"
    )
    out = []
    for row in rows:
        item = dict(row)
        item["inventory"] = json.loads(item["inventory"] or "{}")
        item["seen_label"] = seen_label(item["last_seen"])
        item["online"] = bool(item["last_seen"] and time.time() - item["last_seen"] < 1800)
        item["in_sync"] = item["policy_revision"] == (item["group_revision"] or 0)
        out.append(item)
    return out


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return render(request, "login.html", error=None)


@app.post("/login")
def login(request: Request, password: str = Form(...)) -> Response:
    if not hmac.compare_digest(password, ADMIN_PASSWORD):
        db.log_event("security", "failed console login")
        return render(request, "login.html", error="Incorrect password.")
    token = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO sessions (token, created_at) VALUES (?, ?)", (token, int(time.time()))
    )
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=SESSION_MAX_AGE
    )
    return response


@app.get("/logout")
def logout(request: Request) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, _: str = Depends(require_admin)) -> HTMLResponse:
    devices = device_rows()
    groups = db.query("SELECT * FROM groups ORDER BY is_default DESC, name")
    events = db.query("SELECT * FROM events ORDER BY ts DESC LIMIT 12")
    stats = {
        "total": len(devices),
        "online": sum(1 for d in devices if d["online"]),
        "in_sync": sum(1 for d in devices if d["in_sync"]),
        "groups": len(groups),
    }
    return render(
        request,
        "dashboard.html",
        stats=stats,
        devices=devices[:8],
        groups=groups,
        events=[dict(e, when=seen_label(e["ts"])) for e in map(dict, events)],
        enrollment_key=db.get_setting("enrollment_key"),
    )


@app.get("/devices", response_class=HTMLResponse)
def devices_page(request: Request, _: str = Depends(require_admin)) -> HTMLResponse:
    return render(
        request,
        "devices.html",
        devices=device_rows(),
        groups=db.query("SELECT * FROM groups ORDER BY name"),
    )


@app.get("/devices/{device_id}", response_class=HTMLResponse)
def device_page(request: Request, device_id: str, _: str = Depends(require_admin)) -> HTMLResponse:
    row = db.query_one("SELECT * FROM devices WHERE id = ?", (device_id,))
    if not row:
        raise HTTPException(status_code=404, detail="no such device")
    device = dict(row)
    device["inventory"] = json.loads(device["inventory"] or "{}")
    device["seen_label"] = seen_label(device["last_seen"])
    group = device_group(device)
    compiled = (
        policy_mod.compile_policy(group["name"], group["revision"], json.loads(group["policy"]))
        if group
        else None
    )
    return render(
        request,
        "device.html",
        device=device,
        group=group,
        groups=db.query("SELECT * FROM groups ORDER BY name"),
        keyfile=policy_mod.keyfile_preview(compiled) if compiled else "",
        events=[
            dict(e, when=seen_label(e["ts"]))
            for e in map(dict, db.query(
                "SELECT * FROM events WHERE device_id = ? ORDER BY ts DESC LIMIT 25",
                (device_id,),
            ))
        ],
    )


@app.post("/devices/{device_id}/group")
def assign_group(
    request: Request,
    device_id: str,
    group_id: str = Form(...),
    _: str = Depends(require_admin),
) -> Response:
    target = int(group_id) if group_id else None
    db.execute(
        "UPDATE devices SET group_id = ?, policy_status = 'pending' WHERE id = ?",
        (target, device_id),
    )
    db.log_event("policy", "assigned to group %s" % group_id, device_id)
    return RedirectResponse("/devices/%s" % device_id, status_code=303)


@app.post("/devices/{device_id}/delete")
def delete_device(request: Request, device_id: str, _: str = Depends(require_admin)) -> Response:
    db.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    db.log_event("device", "removed device %s" % device_id)
    return RedirectResponse("/devices", status_code=303)


@app.get("/groups", response_class=HTMLResponse)
def groups_page(request: Request, _: str = Depends(require_admin)) -> HTMLResponse:
    rows = []
    for group in db.query("SELECT * FROM groups ORDER BY is_default DESC, name"):
        item = dict(group)
        item["device_count"] = db.query_one(
            "SELECT COUNT(*) AS n FROM devices WHERE group_id = ?", (group["id"],)
        )["n"]
        rows.append(item)
    return render(request, "groups.html", groups=rows)


@app.post("/groups")
def create_group(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    _: str = Depends(require_admin),
) -> Response:
    now = int(time.time())
    try:
        group_id = db.execute(
            "INSERT INTO groups (name, description, policy, revision, is_default,"
            " created_at, updated_at) VALUES (?, ?, ?, 1, 0, ?, ?)",
            (name.strip(), description.strip(), json.dumps(policy_mod.default_policy()), now, now),
        )
    except Exception:
        return RedirectResponse("/groups", status_code=303)
    db.log_event("policy", "created group '%s'" % name)
    return RedirectResponse("/groups/%d" % group_id, status_code=303)


@app.get("/groups/{group_id}", response_class=HTMLResponse)
def group_page(request: Request, group_id: int, _: str = Depends(require_admin)) -> HTMLResponse:
    row = db.query_one("SELECT * FROM groups WHERE id = ?", (group_id,))
    if not row:
        raise HTTPException(status_code=404, detail="no such group")
    group = dict(row)
    stored = json.loads(group["policy"])
    settings = dict(policy_mod.DEFAULT_SETTINGS)
    settings.update(stored.get("settings") or {})
    compiled = policy_mod.compile_policy(group["name"], group["revision"], stored)
    return render(
        request,
        "group.html",
        group=group,
        settings=settings,
        locks="\n".join(stored.get("locks") or []),
        extra_dconf=json.dumps(stored.get("extra_dconf") or {}, indent=2),
        keyfile=policy_mod.keyfile_preview(compiled),
        accent_colors=policy_mod.ACCENT_COLORS,
        color_schemes=policy_mod.COLOR_SCHEMES,
        dock_positions=policy_mod.DOCK_POSITIONS,
        device_count=db.query_one(
            "SELECT COUNT(*) AS n FROM devices WHERE group_id = ?", (group_id,)
        )["n"],
    )


@app.post("/groups/{group_id}")
async def save_group(request: Request, group_id: int, _: str = Depends(require_admin)) -> Response:
    form = dict(await request.form())
    new_policy = policy_mod.policy_from_form(form)
    db.execute(
        "UPDATE groups SET policy = ?, description = ?, revision = revision + 1,"
        " updated_at = ? WHERE id = ?",
        (json.dumps(new_policy), str(form.get("description", "")), int(time.time()), group_id),
    )
    group = db.query_one("SELECT name, revision FROM groups WHERE id = ?", (group_id,))
    db.log_event(
        "policy", "saved '%s' as revision %d" % (group["name"], group["revision"])
    )
    return RedirectResponse("/groups/%d" % group_id, status_code=303)


@app.post("/groups/{group_id}/delete")
def delete_group(request: Request, group_id: int, _: str = Depends(require_admin)) -> Response:
    row = db.query_one("SELECT is_default, name FROM groups WHERE id = ?", (group_id,))
    if row and not row["is_default"]:
        db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        db.log_event("policy", "deleted group '%s'" % row["name"])
    return RedirectResponse("/groups", status_code=303)


@app.get("/events", response_class=HTMLResponse)
def events_page(request: Request, _: str = Depends(require_admin)) -> HTMLResponse:
    events = [
        dict(e, when=seen_label(e["ts"]))
        for e in map(dict, db.query("SELECT * FROM events ORDER BY ts DESC LIMIT 300"))
    ]
    return render(request, "events.html", events=events)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, _: str = Depends(require_admin)) -> HTMLResponse:
    return render(
        request,
        "settings.html",
        enrollment_key=db.get_setting("enrollment_key"),
        server_url=str(request.base_url).rstrip("/"),
    )


@app.post("/settings/rotate-key")
def rotate_key(request: Request, _: str = Depends(require_admin)) -> Response:
    db.set_setting("enrollment_key", secrets.token_urlsafe(24))
    db.log_event("security", "rotated the enrollment key")
    return RedirectResponse("/settings", status_code=303)
