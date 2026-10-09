# Secure phone access (private)

Goal: view the office from your phone **without exposing anything publicly**.

The office keeps its own token; the Hermes API (`127.0.0.1:8642`) stays private
and is never proxied. Only the office server is reachable, and only over your
private tailnet.

## Recommended: Tailscale Serve (private tailnet)

Prerequisites: [Tailscale](https://tailscale.com/) installed and signed in on
**both** the Mac and the phone (same tailnet).

1. Start the office on loopback (the default):

   ```bash
   export HERMES_OFFICE_TOKEN='a-long-random-string'
   export HERMES_API_KEY='your-API_SERVER_KEY'
   python3 -m hermes_office            # binds 127.0.0.1:8765
   ```

2. In another terminal, publish **only that port** to your tailnet over HTTPS:

   ```bash
   tailscale serve --bg --https=443 http://127.0.0.1:8765
   ```

   `tailscale serve` is reachable **only by devices in your tailnet** — not the
   public internet. It prints a URL like
   `https://<machine>.<your-tailnet>.ts.net/`.

3. Open that URL on your phone and sign in with `HERMES_OFFICE_TOKEN`.

4. Check state / stop it:

   ```bash
   tailscale serve status
   tailscale serve --https=443 off
   ```

### Verify the boundary

- `curl -s -o /dev/null -w '%{http_code}\n' https://<machine>.<tailnet>.ts.net/api/office`
  → **401** (no token). With the bearer token → **200**.
- From a device **outside** the tailnet, the URL is unreachable — that is the
  point.

## Do NOT

- Do **not** use `tailscale funnel` (that publishes to the public internet)
  unless you fully intend it; if you ever do, keep a strong token and treat the
  office as internet-facing.
- Do **not** proxy or expose `127.0.0.1:8642` — that is the Hermes API with
  your key.
- Do **not** bind the office to `0.0.0.0` on an untrusted network.
- Do **not** commit `.env` or your token.

## Alternatives

- **SSH port-forward** (no Tailscale): `ssh -L 8765:127.0.0.1:8765 you@mac`
  then browse `http://127.0.0.1:8765` on the phone via a local forward app.
- **Reverse proxy with auth** (Caddy/Traefik + basic auth or OIDC) in front of
  the office if you already run one — keep the office token as a second layer.

All of the above are network changes you make deliberately; the project itself
never touches your Tailscale, DNS or firewall configuration.
