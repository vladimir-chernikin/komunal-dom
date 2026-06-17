server {
    listen 80;
    server_name max.komunal-dom.ru;

    client_max_body_size 100M;

    access_log /var/log/nginx/max.komunal-dom.ru.access.log;
    error_log /var/log/nginx/max.komunal-dom.ru.error.log;

    location /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name max.komunal-dom.ru;

    root /var/www/komunal-dom_ru/max_app/dist;
    index index.html;

    client_max_body_size 100M;

    ssl_certificate /etc/letsencrypt/live/max.komunal-dom.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/max.komunal-dom.ru/privkey.pem;
    ssl_session_cache shared:max_komunal_dom_ru_ssl:10m;
    ssl_session_timeout 1d;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers off;

    access_log /var/log/nginx/max.komunal-dom.ru.access.log;
    error_log /var/log/nginx/max.komunal-dom.ru.error.log;

    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /assets/ {
        try_files $uri =404;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
