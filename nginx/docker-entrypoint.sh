#!/bin/sh
# Picks the nginx server block at start-up so HTTPS works with no manual steps.
#
#   HTTPS=auto (default)  use nginx/certs/{fullchain,privkey}.pem if mounted, otherwise a self-signed
#                         certificate generated once and kept in the nginx_tls volume.
#   HTTPS=off             plain HTTP (cameras then only work on http://localhost).
#
# Phones and other devices need HTTPS for the camera (QR scanner), so HTTPS is on by default. Plain HTTP
# requests on the same port are redirected to HTTPS.
set -eu

CONF=/etc/nginx/conf.d/default.conf
PROVIDED_CERT=/etc/nginx/certs/fullchain.pem
PROVIDED_KEY=/etc/nginx/certs/privkey.pem
TLS_DIR=/var/lib/nginx/tls
mode=$(echo "${HTTPS:-auto}" | tr '[:upper:]' '[:lower:]')

write_http() {
  cat > "$CONF" <<'EOF'
map $http_x_forwarded_proto $forwarded_proto { default $scheme; https https; }

server {
  listen 2025 default_server;
  server_name _;
  include /etc/nginx/snippets/app.conf;
}
EOF
}

write_https() {
  cert=$1 key=$2 hsts=$3
  cat > "$CONF" <<EOF
map \$http_x_forwarded_proto \$forwarded_proto { default \$scheme; }

server {
  listen 2025 ssl default_server;
  http2 on;
  server_name _;

  ssl_certificate     $cert;
  ssl_certificate_key $key;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_prefer_server_ciphers off;
  ssl_session_cache shared:SSL:2m;
  ssl_session_timeout 1d;
  $hsts

  # Plain HTTP sent to this port is redirected to HTTPS on the same host and port.
  error_page 497 =301 https://\$http_host\$request_uri;

  include /etc/nginx/snippets/app.conf;
}
EOF
}

generate_self_signed() {
  mkdir -p "$TLS_DIR"
  if [ -s "$TLS_DIR/cert.pem" ] && [ -s "$TLS_DIR/key.pem" ]; then
    return  # keep the same certificate so devices only have to accept it once
  fi
  # Extra names (comma separated) can be added with TLS_HOSTS, e.g. "assets.lan,192.168.1.10".
  san="DNS:localhost,IP:127.0.0.1,IP:::1"
  for h in $(echo "${TLS_HOSTS:-}" | tr ',' ' '); do
    case "$h" in
      *[!0-9.:]*) san="$san,DNS:$h" ;;
      *) san="$san,IP:$h" ;;
    esac
  done
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -subj "/CN=${TLS_COMMON_NAME:-Asset Management Tools}" \
    -addext "subjectAltName=$san" \
    -addext "basicConstraints=critical,CA:FALSE" \
    -addext "extendedKeyUsage=serverAuth" \
    -keyout "$TLS_DIR/key.pem" -out "$TLS_DIR/cert.pem" 2>/dev/null
  chmod 600 "$TLS_DIR/key.pem"
  echo "Generated a self-signed TLS certificate (valid 825 days)."
}

case "$mode" in
  off | false | 0 | no)
    write_http
    echo "Serving plain HTTP on :2025 (HTTPS=off)."
    ;;
  *)
    if [ -s "$PROVIDED_CERT" ] && [ -s "$PROVIDED_KEY" ]; then
      write_https "$PROVIDED_CERT" "$PROVIDED_KEY" 'add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;'
      echo "Serving HTTPS on :2025 with the certificate from nginx/certs/."
    else
      generate_self_signed
      # No HSTS with a self-signed certificate: it would lock browsers out once a real certificate changes.
      write_https "$TLS_DIR/cert.pem" "$TLS_DIR/key.pem" ""
      echo "Serving HTTPS on :2025 with a self-signed certificate. Open https://<this machine's IP>:2025 and accept the warning once per device."
    fi
    ;;
esac

exec "$@"
