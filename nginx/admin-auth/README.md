Optional HTTP basic auth for `/admin/` (in addition to the IP allowlist and superuser-only login).

1. Create a password file: `htpasswd -c nginx/admin-auth/.htpasswd admin`
2. Create `nginx/admin-auth/basic-auth.conf` containing:

       auth_basic "Restricted";
       auth_basic_user_file /etc/nginx/admin-auth/.htpasswd;

3. `docker compose restart nginx`
