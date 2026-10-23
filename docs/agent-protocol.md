# Agent protocol

The HTTP contract between `ros-agent` and the console. It is small on purpose:
four endpoints, JSON in and out, bearer tokens.

Base path: `/api/v1`. All request and response bodies are `application/json`.

## Authentication

| Endpoint | Credential |
|---|---|
| `POST /enroll` | The shared enrollment key, in the body |
| everything else | `Authorization: Bearer <device token>` |

Device tokens are 32 random URL-safe bytes, stored on the server as a SHA-256
hash and compared in constant time. A wrong token and an unknown device both
return `401` with the same body, so an unauthenticated caller cannot enumerate
device IDs.

## `GET /api/v1/health`

Unauthenticated. For load balancers and container health checks.

```json
{"status": "ok", "version": "0.1.0", "devices": 42}
```

## `POST /api/v1/enroll`

```json
{
  "enrollment_key": "…",
  "hostname": "ros-desk-014",
  "machine_id": "9f2c…",
  "inventory": { }
}
```

```json
{"device_id": "a1b2c3d4e5f60718", "token": "…"}
```

`machine_id` is `/etc/machine-id`, and it is the identity: enrolling twice with
the same machine ID updates the existing device and issues a new token rather
than creating a duplicate. The device keeps its group and its history.

Errors: `400` if `machine_id` is missing, `403` if the key is wrong — and a
rejected attempt is recorded in the activity log.

## `POST /api/v1/devices/{id}/heartbeat`

```json
{
  "inventory": { "hostname": "…", "os_pretty": "…", "kernel": "…", "…": "…" },
  "agent_version": "0.1.0",
  "policy_revision": 3
}
```

```json
{"policy_revision": 4, "policy_name": "Finance", "server_time": 1761200000}
```

The agent compares the returned revision with its own and only fetches policy
when it is behind. This is what keeps a large fleet cheap: an up-to-date machine
costs one small request per sync.

## `GET /api/v1/devices/{id}/policy`

```json
{
  "name": "Finance",
  "revision": 4,
  "dconf": {
    "org/gnome/desktop/interface": {
      "accent-color": "'teal'",
      "color-scheme": "'prefer-light'"
    },
    "org/gnome/shell": {
      "favorite-apps": "['org.gnome.Nautilus.desktop', 'org.gnome.TextEditor.desktop']"
    }
  },
  "locks": ["/org/gnome/desktop/background/picture-uri"]
}
```

Values are **GVariant text**, passed through to the keyfile unchanged. Strings
arrive already quoted. The console is responsible for producing valid GVariant;
the agent does not validate it, because the only thing that can authoritatively
validate it is `dconf update`, which the agent then runs and whose failure it
reports.

The agent writes this to `/etc/dconf/db/ros.d/50-managed`, writes `locks` to
`/etc/dconf/db/ros.d/locks/50-managed`, and runs `dconf update`.

## `POST /api/v1/devices/{id}/policy-result`

```json
{"revision": 4, "status": "applied", "detail": {"sections": 6, "locks": 3}}
```

`status` is `applied` or `failed`; on failure `detail` carries the error, and
the device shows as failed in the console instead of silently drifting.

## Transport

The console speaks plain HTTP and expects a TLS-terminating proxy in front of
it. `verify_tls` in `/etc/ros/agent.conf` is honoured for HTTPS servers.

## Timing

| | |
|---|---|
| First sync | 2 minutes after boot |
| Interval | every 15 minutes |
| Jitter | up to 2 minutes, so a power cut does not become a thundering herd |
| Missed runs | caught up on next boot (`Persistent=true`) |
| Request timeout | 20 seconds, configurable |

## Failure behaviour

- **No server configured**: the agent logs one line and exits 0. An unmanaged
  ROS install is a supported configuration, not an error.
- **Server unreachable**: exit 1, nothing changes, the timer tries again. The
  last policy stays applied; `ros-agent apply` re-applies it with no network.
- **`dconf update` fails**: the failure is reported to the console and logged
  locally. The partially written keyfile stays on disk, so the next successful
  sync overwrites it.
